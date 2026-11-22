"""Community feed (design §3.4) + two-layer moderation (§3.8)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.core.db import SessionLocal
from app.models import ModerationItem, Post
from app.security.tenant import set_tenant_context
from app.services import community_service, moderation
from tests._helpers import make_platform_admin, token_for
from tests.test_farmer import _h, _login, _onboard_body, _seed_locations

NIPHAD, YEOLA, KUMBAKONAM = 904101, 904103, 905201
PIMPALGAON, OZAR = 9550001, 9550002


async def _farmer(client, phone, name, tehsil, village=None):
    acct = await _login(client, phone)
    body = _onboard_body(display_name=name, tehsil_id=tehsil, village_id=village)
    r = await client.post("/v1/farmer/onboard", json=body, headers=_h(acct))
    assert r.status_code == 201, r.text
    return r.json()


async def _world(client):
    await _seed_locations()
    a = await _farmer(client, "9222200001", "Asha (Pimpalgaon)", NIPHAD, PIMPALGAON)
    b = await _farmer(client, "9222200002", "Bala (Ozar)", NIPHAD, OZAR)
    c = await _farmer(client, "9222200003", "Chetan (Yeola)", YEOLA)
    d = await _farmer(client, "9222200004", "Devi (Kumbakonam)", KUMBAKONAM)
    return a, b, c, d


async def _post(
    client, who, body="Which seed variety for soybean this kharif?", kind="ask", **tags
):
    return await client.post(
        "/v1/community/posts", json={"kind": kind, "body": body, "tags": tags}, headers=_h(who)
    )


async def _feed(client, who, tab="all"):
    r = await client.get("/v1/community/feed", params={"tab": tab}, headers=_h(who))
    assert r.status_code == 200, r.text
    return r.json()["items"]


async def _admin():
    admin_id, _ = await make_platform_admin("9222200090")
    return {"Authorization": f"Bearer {token_for(admin_id, 'platform_admin', None)}"}


@pytest.fixture(autouse=True)
def _reset_moderation():
    yield
    moderation.set_classifier(moderation.FakeClassifier())
    moderation.load_blocklist([])


# ---------------------------------------------------------------- pre-screen (unit)


@pytest.mark.parametrize(
    "body",
    [
        "call me 9876543210",
        "+91 98765 43210",
        "98765-43210",
        "०९८७६५४३२१०",
        "call ९८७६५ ४३२१०",
        "ping on 0 98765 43210",
    ],
)
def test_prescreen_blocks_phone_numbers_in_any_script(body):
    assert moderation.prescreen(body).as_dict()["reasons"] == ["phone_number"]


@pytest.mark.parametrize(
    "body,reason",
    [
        ("pay advance to kisan@ybl", "payment_handle"),
        ("see www.cheap-tractors.xyz", "link"),
        ("You have won a lottery! claim now", "scam_phrase"),
        ("लॉटरी लागली आहे", "scam_phrase"),
    ],
)
def test_prescreen_flags_scams(body, reason):
    v = moderation.prescreen(body)
    assert v.action == "flag" and reason in v.reasons


@pytest.mark.parametrize(
    "body",
    [
        "Soybean 4,520 per quintal at Lasalgaon today",
        "Sowed 25 kg/acre, yield 18 quintal",
        "2026 kharif plan: 3 acres onion",
    ],
)
def test_prescreen_passes_normal_farm_talk(body):
    assert moderation.prescreen(body).action == "approve"


def test_blocklist_is_loadable():
    moderation.load_blocklist(["badword"])
    assert moderation.prescreen("this BadWord here").reasons == ["blocked_word"]


def test_score_weights():
    now = datetime.now(UTC)
    s = community_service.score
    assert s("village", now, 0, now) > s("tehsil", now, 0, now) > s("nearby", now, 0, now)
    assert s("district", now, 0, now) < s("tehsil", now - timedelta(days=7), 0, now)
    assert s("tehsil", now, 20, now) - s("tehsil", now, 0, now) == pytest.approx(0.1)


# ---------------------------------------------------------------- feed


@pytest.mark.asyncio
async def test_locality_first_feed(client):
    a, b, c, d = await _world(client)
    for who, body in (
        (a, "Pimpalgaon question?"),
        (b, "Ozar question?"),
        (c, "Yeola question?"),
        (d, "Kumbakonam question?"),
    ):
        assert (await _post(client, who, body)).status_code == 201

    items = await _feed(client, a)
    assert [(i["body"], i["locality"]) for i in items] == [
        ("Pimpalgaon question?", "village"),
        ("Ozar question?", "tehsil"),
        ("Yeola question?", "district"),
    ]
    assert items[0]["is_mine"] is True and items[1]["author_name"] == "Bala (Ozar)"
    # Tamil Nadu farmer only sees their own area
    assert [i["body"] for i in await _feed(client, d)] == ["Kumbakonam question?"]


@pytest.mark.asyncio
async def test_tabs_tags_and_expiry(client):
    a, b, _, _ = await _world(client)
    r = await _post(client, a, "Onion rate today", kind="price_report", crop="onion")
    assert r.status_code == 422  # price report needs crop + price + unit
    r = await _post(
        client,
        a,
        "Onion rate today",
        kind="price_report",
        crop="onion",
        price_paise=210000,
        unit="quintal",
        market="Lasalgaon",
    )
    assert r.status_code == 201, r.text
    assert r.json()["tags"]["market"] == "Lasalgaon" and r.json()["expires_at"]
    await _post(client, a, "Need a rotavator Monday", kind="need_equipment")

    assert [i["kind"] for i in await _feed(client, b, "market")] == ["price_report"]
    assert [i["kind"] for i in await _feed(client, b, "equipment")] == ["need_equipment"]
    assert await _feed(client, b, "alerts") == []

    # prices go stale after 3 days
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        await s.execute(
            update(Post)
            .where(Post.kind == "price_report")
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
    assert await _feed(client, b, "market") == []


@pytest.mark.asyncio
async def test_rate_limit(client):
    a, *_ = await _world(client)
    for i in range(community_service.POSTS_PER_HOUR):
        assert (await _post(client, a, f"Question number {i}?")).status_code == 201
    r = await _post(client, a, "One too many?")
    assert r.status_code == 429


# ---------------------------------------------------------------- moderation on write


@pytest.mark.asyncio
async def test_phone_blocked_scam_queued(client):
    a, b, _, _ = await _world(client)
    r = await _post(client, a, "Tractor for rent, call 98765 43210")
    assert r.status_code == 422 and r.json()["detail"] == "blocked:phone_number"
    # phone hidden in a tag is caught too
    r = await _post(
        client,
        a,
        "Rate today",
        kind="price_report",
        crop="onion 9876543210",
        price_paise=1000,
        unit="kg",
    )
    assert r.status_code == 422

    r = await _post(client, a, "Cheap subsidy help, pay fee to agent@ybl")
    assert r.status_code == 201 and r.json()["status"] == "in_review"
    assert await _feed(client, b) == []  # not published
    mine = (await client.get("/v1/community/posts/mine", headers=_h(a))).json()
    assert mine[0]["status"] == "in_review"  # author can still see it
    # others can't open it
    pid = mine[0]["id"]
    assert (await client.get(f"/v1/community/posts/{pid}", headers=_h(b))).status_code == 404

    admin = await _admin()
    q = (await client.get("/v1/admin/moderation", headers=admin)).json()
    assert (
        len(q) == 1 and q[0]["reasons"] == ["payment_handle"] and q[0]["body"].startswith("Cheap")
    )
    r = await client.post(
        f"/v1/admin/moderation/{q[0]['id']}/decide",
        json={"decision": "remove", "note": "fee scam"},
        headers=admin,
    )
    assert r.status_code == 200 and r.json()["decision"] == "remove"
    assert (await client.get("/v1/community/posts/mine", headers=_h(a))).json()[0][
        "status"
    ] == "removed"
    assert (
        await client.post(
            f"/v1/admin/moderation/{q[0]['id']}/decide", json={"decision": "approve"}, headers=admin
        )
    ).status_code == 409


class _Down:
    async def classify(self, text, *, kind, language):
        raise RuntimeError("provider down")


class _Unsure:
    async def classify(self, text, *, kind, language):
        return moderation.Verdict("block", ["pesticide_dose"], layer="classifier", confidence=0.4)


@pytest.mark.asyncio
async def test_classifier_down_or_unsure_never_auto_blocks(client):
    a, b, _, _ = await _world(client)
    moderation.set_classifier(_Down())
    r = await _post(client, a, "How much chlorpyrifos per acre?")
    assert r.status_code == 201 and r.json()["status"] == "in_review"
    moderation.set_classifier(_Unsure())
    r = await _post(client, a, "Mix two pesticides together?")
    assert r.status_code == 201 and r.json()["status"] == "in_review"
    admin = await _admin()
    reasons = sorted(
        tuple(i["reasons"])
        for i in (await client.get("/v1/admin/moderation", headers=admin)).json()
    )
    assert reasons == [("classifier_unavailable",), ("pesticide_dose", "low_confidence")]


# ---------------------------------------------------------------- replies, helpful, reports


@pytest.mark.asyncio
async def test_replies_and_helpful(client):
    a, b, c, _ = await _world(client)
    pid = (await _post(client, a)).json()["id"]

    r = await client.post(
        f"/v1/community/posts/{pid}/replies", json={"body": "JS-335 did well for me"}, headers=_h(b)
    )
    assert r.status_code == 201
    r = await client.post(
        f"/v1/community/posts/{pid}/replies", json={"body": "WhatsApp me 9876543210"}, headers=_h(c)
    )
    assert r.status_code == 422

    assert (
        await client.put(f"/v1/community/posts/{pid}/helpful", headers=_h(a))
    ).status_code == 422  # own post
    for who in (b, b, c):  # idempotent per farmer
        assert (
            await client.put(f"/v1/community/posts/{pid}/helpful", headers=_h(who))
        ).status_code == 204
    d = (await client.get(f"/v1/community/posts/{pid}", headers=_h(b))).json()
    assert d["reply_count"] == 1 and d["replies"][0]["author_name"] == "Bala (Ozar)"
    assert d["helpful_count"] is None  # 2 < threshold: hidden
    assert d["i_found_helpful"] is True
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        assert (await s.get(Post, pid)).helpful_count == 2  # trigger kept the count
        await s.execute(update(Post).where(Post.id == pid).values(helpful_count=12))
    assert (await client.get(f"/v1/community/posts/{pid}", headers=_h(c))).json()[
        "helpful_count"
    ] == 12
    await client.delete(f"/v1/community/posts/{pid}/helpful", headers=_h(b))
    d = (await client.get(f"/v1/community/posts/{pid}", headers=_h(b))).json()
    assert d["i_found_helpful"] is False and d["helpful_count"] == 11


@pytest.mark.asyncio
async def test_reports_auto_hide_then_admin_restores(client):
    a, b, c, _ = await _world(client)
    e = await _farmer(client, "9222200005", "Esha", NIPHAD)
    pid = (await _post(client, a, "Best fertiliser for onion?")).json()["id"]

    rep = {"target_type": "post", "target_id": pid, "reason": "spam"}
    assert (await client.post("/v1/community/reports", json=rep, headers=_h(a))).status_code == 422
    assert (await client.post("/v1/community/reports", json=rep, headers=_h(b))).status_code == 204
    assert (await client.post("/v1/community/reports", json=rep, headers=_h(b))).status_code == 409
    assert len(await _feed(client, b)) == 1  # one report: queued, still visible
    admin = await _admin()
    assert len((await client.get("/v1/admin/moderation", headers=admin)).json()) == 1

    await client.post("/v1/community/reports", json={**rep, "reason": "scam"}, headers=_h(c))
    await client.post("/v1/community/reports", json=rep, headers=_h(e))
    assert await _feed(client, b) == []  # 3 reporters -> hidden pending review
    q = (await client.get("/v1/admin/moderation", headers=admin)).json()
    assert len(q) == 1 and q[0]["report_count"] == 3
    assert sorted(q[0]["reasons"]) == ["report:scam", "report:spam"]

    await client.post(
        f"/v1/admin/moderation/{q[0]['id']}/decide",
        json={"decision": "approve", "note": "legit question"},
        headers=admin,
    )
    assert len(await _feed(client, b)) == 1
    # a fresh report after approval doesn't instantly re-hide it
    f = await _farmer(client, "9222200006", "Farid", NIPHAD)
    await client.post("/v1/community/reports", json=rep, headers=_h(f))
    assert len(await _feed(client, b)) == 1


# ---------------------------------------------------------------- isolation


@pytest.mark.asyncio
async def test_rls_and_admin_only(client):
    a, b, _, _ = await _world(client)
    await _post(client, a, "Scheme help, contact agent@ybl")  # queued
    pid = (await _post(client, a)).json()["id"]

    assert (await client.get("/v1/admin/moderation", headers=_h(a))).status_code == 403
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(
            s, dealer_id=None, is_platform_admin=False, farmer_id=b["active_profile_id"]
        )
        assert (await s.execute(text("SELECT count(*) FROM moderation_queue"))).scalar() == 0
        visible = (await s.scalars(select(Post))).all()
        assert [p.status for p in visible] == ["published"]  # not A's in_review post
        res = await s.execute(text("UPDATE posts SET body='x' WHERE id=:i"), {"i": pid})
        assert res.rowcount == 0
        with pytest.raises(DBAPIError):
            await s.execute(
                text(
                    "INSERT INTO moderation_queue (target_type, target_id, source, sla_due_at) "
                    "VALUES ('post', :i, 'x', now())"
                ),
                {"i": pid},
            )

    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        assert (await s.execute(select(ModerationItem))).first() is not None
