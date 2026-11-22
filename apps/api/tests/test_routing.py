"""Consented farmer -> dealer lead routing (design §3.3)."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text

from app.core.business_hours import add_business_hours
from app.core.db import SessionLocal
from app.models import Dealer, FarmerConsent, Lead, LeadRoute
from app.security.tenant import set_tenant_context
from app.services import routing_service
from tests._helpers import make_dealer_and_owner, token_for
from tests.test_farmer import _h, _login, _onboard_body, _seed_locations

IST = ZoneInfo("Asia/Kolkata")
NIPHAD, SINNAR, YEOLA = 904101, 904102, 904103


async def _dealer(
    name: str,
    phone: str,
    *,
    brands: list[str],
    areas: list[tuple[int, bool]],
    verified: bool = True,
) -> dict:
    dealer_id, owner_id, _, _ = await make_dealer_and_owner(name, phone)
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        d = await s.get(Dealer, dealer_id)
        d.brands = brands
        d.whatsapp_number = "+91" + phone
        d.verified_at = datetime.now(UTC) if verified else None
    return {
        "id": dealer_id,
        "owner": owner_id,
        "areas": areas,
        "h": {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer_id)}"},
    }


async def _set_areas(client, d: dict) -> None:
    body = {"areas": [{"tehsil_id": t, "is_home": h} for t, h in d["areas"]]}
    r = await client.put("/v1/dealer/service-areas", json=body, headers=d["h"])
    assert r.status_code == 200, r.text


async def _farmer(client, phone: str, **kw) -> dict:
    acct = await _login(client, phone)
    r = await client.post("/v1/farmer/onboard", json=_onboard_body(**kw), headers=_h(acct))
    assert r.status_code == 201, r.text
    return r.json()


async def _interest(client, farmer: dict, **kw):
    ct = (
        await client.get(
            "/v1/farmer/interests/consent-text", params={"lang": "mr"}, headers=_h(farmer)
        )
    ).json()
    body = {
        "brand_hint": "Mahindra",
        "hp_min": 40,
        "hp_max": 50,
        "timeline": "now",
        "consent_granted": True,
        "consent_version": ct["version"],
        "consent_language": "mr",
    }
    body.update(kw)
    return await client.post("/v1/farmer/interests", json=body, headers=_h(farmer))


async def _leads(client, d: dict) -> list[dict]:
    r = await client.get("/v1/leads", headers=d["h"])
    assert r.status_code == 200, r.text
    return [x for x in r.json() if x["source"] == "agrodesk_guide"]


async def _world(client):
    await _seed_locations()
    near = await _dealer(
        "Niphad Mahindra", "9666600001", brands=["Mahindra"], areas=[(NIPHAD, True)]
    )
    district = await _dealer(
        "Sinnar Mahindra", "9666600002", brands=["mahindra", "Swaraj"], areas=[(SINNAR, True)]
    )
    unverified = await _dealer(
        "Unverified", "9666600003", brands=["Mahindra"], areas=[(NIPHAD, True)], verified=False
    )
    other_brand = await _dealer(
        "Niphad Swaraj", "9666600004", brands=["Swaraj"], areas=[(NIPHAD, True)]
    )
    for d in (near, district, unverified, other_brand):
        await _set_areas(client, d)
    farmer = await _farmer(client, "9555500001")
    return near, district, unverified, other_brand, farmer


# ---------------------------------------------------------------- routing


@pytest.mark.asyncio
async def test_routes_to_nearest_verified_brand_dealer(client):
    near, district, unverified, other_brand, farmer = await _world(client)

    r = await _interest(client, farmer)
    assert r.status_code == 201, r.text
    interest = r.json()
    assert interest["status"] == "assigned"
    assert interest["dealer_name"] == "Niphad Mahindra"
    assert interest["dealer_phone"] == "+919666600001"

    leads = await _leads(client, near)
    assert len(leads) == 1
    lead = leads[0]
    assert lead["stage"] == "new" and lead["score"] == "hot"
    assert lead["model_interest"] == "Mahindra · 40-50 HP"
    assert lead["owner_user_id"] == near["owner"]
    # SLA doubles as the follow-up time so it lands in Today's tasks
    assert lead["next_action_at"] is not None

    for d in (district, unverified, other_brand):
        assert await _leads(client, d) == []

    # candidate list: near first (own tehsil), then same-district fallback; unverified
    # and wrong-brand dealers never make the list
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        route = await s.scalar(select(LeadRoute))
        assert route.rank_reason["distance_rank"] == 0
        assert route.rank_reason["home_match"] is True
        consent = await s.scalar(select(FarmerConsent))
        assert consent.granted and consent.language == "mr"
        _, expected = routing_service.consent_text("mr")
        assert consent.text_shown == expected  # server text, not client-supplied

    # farmer sees it
    r = await client.get("/v1/farmer/interests", headers=_h(farmer))
    assert [i["status"] for i in r.json()] == ["assigned"]


@pytest.mark.asyncio
async def test_no_brand_hint_matches_any_brand(client):
    near, district, unverified, other_brand, farmer = await _world(client)
    r = await _interest(client, farmer, brand_hint=None)
    assert r.status_code == 201
    # both Niphad dealers are rank 0 home matches; tie broken by name
    assert r.json()["dealer_name"] == "Niphad Mahindra"


@pytest.mark.asyncio
async def test_no_dealers_goes_to_waitlist(client):
    await _seed_locations()
    farmer = await _farmer(client, "9555500002")
    r = await _interest(client, farmer)
    assert r.status_code == 201
    assert r.json()["status"] == "waitlist"
    assert r.json()["dealer_name"] is None


@pytest.mark.asyncio
async def test_consent_rules(client):
    _, _, _, _, farmer = await _world(client)
    r = await _interest(client, farmer, consent_granted=False)
    assert r.status_code == 422
    r = await _interest(client, farmer, consent_version="v0")
    assert r.status_code == 409 and r.json()["detail"] == "stale_consent_text"
    # unreviewed language falls back to English text, and says so
    r = await client.get(
        "/v1/farmer/interests/consent-text", params={"lang": "ta"}, headers=_h(farmer)
    )
    assert r.json()["language"] == "en" and "4 verified tractor dealers" in r.json()["text"]


@pytest.mark.asyncio
async def test_anti_abuse_limits(client):
    _, _, _, _, farmer = await _world(client)
    assert (await _interest(client, farmer)).status_code == 201
    r = await _interest(client, farmer)
    assert r.status_code == 409 and r.json()["detail"] == "already_open"
    assert (await _interest(client, farmer, brand_hint="Swaraj")).status_code == 201
    assert (await _interest(client, farmer, brand_hint="Sonalika")).status_code == 201
    r = await _interest(client, farmer, brand_hint="John Deere")
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_dealer_and_staff_tokens_cannot_create_interest(client):
    near, *_ = await _world(client)
    r = await client.post("/v1/farmer/interests", json={}, headers=near["h"])
    assert r.status_code == 403


# ---------------------------------------------------------------- SLA


@pytest.mark.asyncio
async def test_sla_reroutes_then_waitlists(client):
    near, district, _, _, farmer = await _world(client)
    await _interest(client, farmer)
    later = datetime.now(UTC) + timedelta(days=3)

    res = await routing_service.process_due_routes(now=later)
    assert res == {"expired": 1, "rerouted": 1, "waitlisted": 0}
    old = (await _leads(client, near))[0]
    assert old["stage"] == "lost" and old["lost_reason"] == "rerouted_sla"
    r = await client.get(f"/v1/leads/{old['id']}/events", headers=near["h"])
    assert [e["type"] for e in r.json()][-1] == "re_routed"
    assert len(await _leads(client, district)) == 1
    i = (await client.get("/v1/farmer/interests", headers=_h(farmer))).json()[0]
    assert i["dealer_name"] == "Sinnar Mahindra" and i["reroute_count"] == 1

    # running again before the new SLA is a no-op
    assert (await routing_service.process_due_routes(now=datetime.now(UTC)))["expired"] == 0

    res = await routing_service.process_due_routes(now=later + timedelta(days=3))
    assert res == {"expired": 1, "rerouted": 0, "waitlisted": 1}
    i = (await client.get("/v1/farmer/interests", headers=_h(farmer))).json()[0]
    assert i["status"] == "waitlist" and i["dealer_name"] is None


@pytest.mark.asyncio
async def test_dealer_action_stops_sla(client):
    near, district, _, _, farmer = await _world(client)
    await _interest(client, farmer)
    lead = (await _leads(client, near))[0]
    r = await client.post(
        f"/v1/leads/{lead['id']}/events",
        json={"type": "call_made", "payload": {}},
        headers=near["h"],
    )
    assert r.status_code == 201, r.text

    res = await routing_service.process_due_routes(now=datetime.now(UTC) + timedelta(days=5))
    assert res["expired"] == 0
    assert await _leads(client, district) == []


@pytest.mark.asyncio
async def test_farmer_cancel_closes_dealer_lead(client):
    near, _, _, _, farmer = await _world(client)
    iid = (await _interest(client, farmer)).json()["id"]
    r = await client.post(f"/v1/farmer/interests/{iid}/cancel", headers=_h(farmer))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    lead = (await _leads(client, near))[0]
    assert lead["stage"] == "lost" and lead["lost_reason"] == "farmer_cancelled"
    assert (
        await client.post(f"/v1/farmer/interests/{iid}/cancel", headers=_h(farmer))
    ).status_code == 409
    # cancelled interests never re-route
    res = await routing_service.process_due_routes(now=datetime.now(UTC) + timedelta(days=5))
    assert res["expired"] == 0

    other = await _farmer(client, "9555500009")
    r = await client.post(f"/v1/farmer/interests/{iid}/cancel", headers=_h(other))
    assert r.status_code == 404


# ---------------------------------------------------------------- isolation


@pytest.mark.asyncio
async def test_rls_on_routes_and_interests(client):
    near, district, _, _, farmer = await _world(client)
    await _interest(client, farmer)
    other = await _farmer(client, "9555500003")
    assert (await client.get("/v1/farmer/interests", headers=_h(other))).json() == []

    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=district["id"], is_platform_admin=False)
        assert (await s.scalars(select(LeadRoute))).all() == []
        assert (await s.execute(text("SELECT count(*) FROM buying_interests"))).scalar() == 0
        assert (await s.execute(text("SELECT count(*) FROM farmer_consents"))).scalar() == 0
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=near["id"], is_platform_admin=False)
        assert len((await s.scalars(select(LeadRoute))).all()) == 1
        assert len((await s.scalars(select(Lead))).all()) == 1


# ---------------------------------------------------------------- service areas + verify


@pytest.mark.asyncio
async def test_service_area_rules(client):
    await _seed_locations()
    d = await _dealer("Areas", "9666600010", brands=[], areas=[])
    put = lambda body, h=d["h"]: client.put("/v1/dealer/service-areas", json=body, headers=h)  # noqa: E731

    r = await put(
        {"areas": [{"tehsil_id": NIPHAD, "is_home": True}, {"tehsil_id": YEOLA, "is_home": False}]}
    )
    assert r.status_code == 200
    assert [(a["tehsil_id"], a["is_home"]) for a in r.json()] == [(NIPHAD, True), (YEOLA, False)]
    assert (await put({"areas": [{"tehsil_id": NIPHAD}, {"tehsil_id": YEOLA}]})).status_code == 422
    assert (await put({"areas": [{"tehsil_id": 1, "is_home": True}]})).status_code == 422

    from app.security.jwt import create_access_token
    from tests._helpers import make_platform_admin

    sales_h = {"Authorization": "Bearer " + create_access_token(d["owner"], "sales", d["id"])}
    assert (await put({"areas": []}, sales_h)).status_code == 403

    admin_id, _ = await make_platform_admin("9666600011")
    admin_h = {"Authorization": f"Bearer {token_for(admin_id, 'platform_admin', None)}"}
    r = await client.post(f"/v1/admin/dealers/{d['id']}/unverify", headers=admin_h)
    assert r.status_code == 200 and r.json()["verified_at"] is None
    r = await client.post(f"/v1/admin/dealers/{d['id']}/verify", headers=admin_h)
    assert r.status_code == 200 and r.json()["verified_at"]
    assert (
        await client.post(f"/v1/admin/dealers/{d['id']}/verify", headers=d["h"])
    ).status_code == 403


# ---------------------------------------------------------------- business hours


def _ist(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def test_business_hours_default_schedule():
    # 2026-11-21 is a Saturday. 18:00 + 4h -> 1h Sat, Sun closed, 3h Mon -> Mon 12:00
    assert add_business_hours(_ist(2026, 11, 21, 18), 4) == _ist(2026, 11, 23, 12)
    # before opening: clock starts at 09:00
    assert add_business_hours(_ist(2026, 11, 23, 6), 4) == _ist(2026, 11, 23, 13)
    # inside hours
    assert add_business_hours(_ist(2026, 11, 23, 10, 30), 4) == _ist(2026, 11, 23, 14, 30)
    # UTC input is handled
    utc = _ist(2026, 11, 23, 10).astimezone(UTC)
    assert add_business_hours(utc, 1) == _ist(2026, 11, 23, 11)


def test_business_hours_custom_and_broken_schedules():
    sched = {"mon": ["10:00", "12:00"], "tue": ["10:00", "12:00"]}
    assert add_business_hours(_ist(2026, 11, 23, 11), 2, sched) == _ist(2026, 11, 24, 11)
    # all-closed / garbage schedule falls back to the default instead of never expiring
    assert add_business_hours(_ist(2026, 11, 23, 10), 1, {"sun": None}) == _ist(2026, 11, 23, 11)
    assert add_business_hours(_ist(2026, 11, 23, 10), 1, {"mon": ["x", "y"]}) == _ist(
        2026, 11, 23, 11
    )
