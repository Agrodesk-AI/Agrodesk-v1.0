"""Deterministic trust signals + badges (design §3.7)."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.db import SessionLocal
from app.models import (
    Account,
    EquipmentListing,
    Farmer,
    FarmerBadge,
    Post,
    PostHelpful,
    RentalBooking,
    RentalRating,
    TrustFlag,
)
from app.security.tenant import set_tenant_context
from app.services import trust_service
from tests._helpers import make_platform_admin, token_for
from tests.test_farmer import _h, _login, _onboard_body, _seed_locations

NIPHAD = 904101
NOW = datetime.now(UTC)


class _Admin:
    async def __aenter__(self):
        self.cm = SessionLocal()
        self.s = await self.cm.__aenter__()
        self.tx = self.s.begin()
        await self.tx.__aenter__()
        await set_tenant_context(self.s, dealer_id=None, is_platform_admin=True)
        return self.s

    async def __aexit__(self, *exc):
        await self.tx.__aexit__(*exc)
        await self.cm.__aexit__(*exc)


async def _quick_farmer(phone: str, name: str, age_days: int = 30) -> UUID:
    async with _Admin() as s:
        acct = Account(phone=phone)
        s.add(acct)
        await s.flush()
        acct.created_at = NOW - timedelta(days=age_days)
        f = Farmer(
            account_id=acct.id, display_name=name, language="mr", tehsil_id=NIPHAD, status="active"
        )
        s.add(f)
        await s.flush()
        return f.id


async def _app_farmer(client, phone: str, name: str) -> dict:
    acct = await _login(client, phone)
    r = await client.post(
        "/v1/farmer/onboard",
        json=_onboard_body(display_name=name, village_id=None),
        headers=_h(acct),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _listing(owner: UUID) -> UUID:
    async with _Admin() as s:
        row = EquipmentListing(
            owner_farmer_id=owner,
            owner_name="Owner",
            tehsil_id=NIPHAD,
            kind="tractor",
            title="Tractor",
            rate_paise=50000,
            rate_unit="hour",
            status="active",
        )
        s.add(row)
        await s.flush()
        return row.id


async def _completed(
    listing: UUID,
    owner: UUID,
    renter: UUID,
    n: int,
    state="completed_by_both",
    start_offset: int = 0,
) -> list[UUID]:
    ids = []
    async with _Admin() as s:
        for i in range(n):
            d = date.today() - timedelta(days=200 - start_offset - i * 3)
            b = RentalBooking(
                listing_id=listing,
                owner_farmer_id=owner,
                renter_farmer_id=renter,
                owner_name="O",
                renter_name="R",
                start_date=d,
                end_date=d,
                state=state,
                owner_completed_at=NOW,
                renter_completed_at=NOW,
            )
            s.add(b)
            await s.flush()
            ids.append(b.id)
    return ids


async def _recompute(fid: UUID) -> dict:
    async with _Admin() as s:
        return await trust_service.recompute(s, fid)


async def _live(fid: UUID) -> list[str]:
    async with _Admin() as s:
        return (await trust_service.badges_for(s, {fid})).get(fid, [])


async def _admin_h():
    admin_id, _ = await make_platform_admin("9000000090")
    return {"Authorization": f"Bearer {token_for(admin_id, 'platform_admin', None)}"}


# ---------------------------------------------------------------- trusted_renter


@pytest.mark.asyncio
async def test_trusted_renter_awarded_live_on_fifth_completion(client):
    await _seed_locations()
    owner = await _app_farmer(client, "9000000001", "Owner Patil")
    renter = await _app_farmer(client, "9000000002", "Renter Jadhav")
    oid, rid = UUID(owner["active_profile_id"]), UUID(renter["active_profile_id"])
    lid = await _listing(oid)
    await _completed(lid, oid, rid, 4)
    assert (await _recompute(oid))["awarded"] == []

    # 5th rental through the real API: badge appears without waiting for the nightly job
    d = (date.today() + timedelta(days=2)).isoformat()
    bid = (
        await client.post(
            "/v1/rentals/bookings",
            headers=_h(renter),
            json={"listing_id": str(lid), "start_date": d, "end_date": d},
        )
    ).json()["id"]
    for who, action in (
        (owner, "agree"),
        (owner, "start"),
        (owner, "complete"),
        (renter, "complete"),
    ):
        r = await client.post(
            f"/v1/rentals/bookings/{bid}/transition", headers=_h(who), json={"action": action}
        )
        assert r.status_code == 200, r.text
    assert await _live(oid) == ["trusted_renter"]
    assert await _live(rid) == ["trusted_renter"]  # either side of the rental counts

    # shown on the listing and the booking, as a badge (no counts)
    other = await _app_farmer(client, "9000000003", "Browser")
    listings = (await client.get("/v1/rentals/listings", headers=_h(other))).json()
    assert listings[0]["owner_badges"] == ["trusted_renter"]
    b = (await client.get(f"/v1/rentals/bookings/{bid}", headers=_h(renter))).json()
    assert b["other_badges"] == ["trusted_renter"]

    # the farmer sees their own progress numbers
    me = (await client.get("/v1/farmer/trust", headers=_h(owner))).json()
    assert me["badges"] == ["trusted_renter"]
    assert me["progress"]["trusted_renter"]["completed_rentals"] == [5, 5]


@pytest.mark.asyncio
async def test_open_dispute_revokes_then_resolve_restores(client):
    await _seed_locations()
    owner = await _app_farmer(client, "9000000011", "Owner")
    renter = await _app_farmer(client, "9000000012", "Renter")
    oid, rid = UUID(owner["active_profile_id"]), UUID(renter["active_profile_id"])
    lid = await _listing(oid)
    await _completed(lid, oid, rid, 5)
    await _recompute(oid)
    assert await _live(oid) == ["trusted_renter"]

    [bid] = await _completed(lid, oid, rid, 1, state="in_progress", start_offset=100)
    async with _Admin() as s:  # in_progress booking: undo the completion stamps
        b = await s.get(RentalBooking, bid)
        b.owner_completed_at = b.renter_completed_at = None
    r = await client.post(
        f"/v1/rentals/bookings/{bid}/transition",
        headers=_h(renter),
        json={"action": "dispute", "note": "Broke down"},
    )
    assert r.json()["state"] == "disputed"
    assert await _live(oid) == []  # revoked immediately by the rule

    admin = await _admin_h()
    await client.post(
        f"/v1/admin/rentals/bookings/{bid}/resolve",
        headers=admin,
        json={"resolution": "Sorted out"},
    )
    assert await _live(oid) == ["trusted_renter"]
    async with _Admin() as s:  # history kept: one system-revoked + one live row
        rows = (await s.scalars(select(FarmerBadge).where(FarmerBadge.farmer_id == oid))).all()
        assert sorted((r.revoked_by or "live") for r in rows) == ["live", "system"]


@pytest.mark.asyncio
async def test_admin_revoke_sticks(client):
    await _seed_locations()
    oid = await _quick_farmer("9000000021", "O")
    rid = await _quick_farmer("9000000022", "R")
    lid = await _listing(oid)
    await _completed(lid, oid, rid, 6)
    await _recompute(oid)
    admin = await _admin_h()
    r = await client.post(
        f"/v1/admin/trust/farmers/{oid}/badges/trusted_renter/revoke",
        headers=admin,
        json={"reason": "rating ring with R"},
    )
    assert r.status_code == 204
    assert (await client.post("/v1/admin/trust/recompute", headers=admin)).status_code == 200
    assert await _live(oid) == []  # not re-awarded by the system
    assert await _live(rid) == ["trusted_renter"]
    r = await client.post(
        f"/v1/admin/trust/farmers/{oid}/badges/trusted_renter/revoke",
        headers=admin,
        json={"reason": "again"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------- helpful_neighbour


async def _helpful_world(marker_age_days: int, markers: int = 10, posts: int = 3) -> UUID:
    author = await _quick_farmer("9000000030", "Author")
    marker_ids = [
        await _quick_farmer(f"90000001{i:02d}", f"M{i}", marker_age_days) for i in range(markers)
    ]
    async with _Admin() as s:
        post_ids = []
        for i in range(posts):
            p = Post(
                farmer_id=author,
                author_name="Author",
                kind="experience",
                tehsil_id=NIPHAD,
                language="mr",
                body=f"Tip {i}",
                status="published",
            )
            s.add(p)
            await s.flush()
            post_ids.append(p.id)
        for pid in post_ids:
            for m in marker_ids:
                s.add(PostHelpful(post_id=pid, farmer_id=m, created_at=NOW))
    return author


@pytest.mark.asyncio
async def test_helpful_neighbour(client):
    await _seed_locations()
    author = await _helpful_world(marker_age_days=30)
    assert (await _recompute(author))["awarded"] == ["helpful_neighbour"]


@pytest.mark.asyncio
async def test_helpful_marks_from_new_accounts_dont_count(client):
    await _seed_locations()
    author = await _helpful_world(marker_age_days=2)
    assert (await _recompute(author))["awarded"] == []
    async with _Admin() as s:
        sig = await trust_service.signals(s, author)
    assert sig["helpful_marks"] == 0


@pytest.mark.asyncio
async def test_too_few_distinct_markers(client):
    await _seed_locations()
    author = await _helpful_world(marker_age_days=30, markers=5, posts=6)  # 30 marks, 5 people
    assert (await _recompute(author))["awarded"] == []


# ---------------------------------------------------------------- anti-gaming


@pytest.mark.asyncio
async def test_ratings_from_new_accounts_excluded_and_rings_flagged(client):
    await _seed_locations()
    a = await _quick_farmer("9000000041", "A", age_days=60)
    b = await _quick_farmer("9000000042", "B", age_days=60)
    fresh = await _quick_farmer("9000000043", "Fresh", age_days=1)
    lid = await _listing(a)
    pair = await _completed(lid, a, b, 3, state="rated")
    [fresh_b] = await _completed(lid, a, fresh, 1, state="completed_by_both", start_offset=50)
    async with _Admin() as s:
        for bid in pair:  # A and B rate each other 5/5 on every booking
            s.add(
                RentalRating(
                    booking_id=bid, from_farmer_id=a, to_farmer_id=b, score=5, created_at=NOW
                )
            )
            s.add(
                RentalRating(
                    booking_id=bid, from_farmer_id=b, to_farmer_id=a, score=5, created_at=NOW
                )
            )
        s.add(
            RentalRating(
                booking_id=fresh_b, from_farmer_id=fresh, to_farmer_id=a, score=1, created_at=NOW
            )
        )
        sig = await trust_service.signals(s, a)
    assert sig["rating_count"] == 3 and sig["rating_avg"] == 5.0  # fresh 1-star ignored

    res = await trust_service.recompute_all()
    assert res["ring_flags"] == 1
    assert (await trust_service.recompute_all())["ring_flags"] == 0  # one open flag per pair

    admin = await _admin_h()
    flags = (await client.get("/v1/admin/trust/flags", headers=admin)).json()
    assert len(flags) == 1 and flags[0]["detail"]["bookings"] == 3
    assert sorted(flags[0]["farmer_ids"]) == sorted([str(a), str(b)])
    r = await client.post(
        f"/v1/admin/trust/flags/{flags[0]['id']}/close",
        headers=admin,
        json={"note": "brothers, legit"},
    )
    assert r.json()["status"] == "closed"


# ---------------------------------------------------------------- isolation


@pytest.mark.asyncio
async def test_rls(client):
    await _seed_locations()
    viewer = await _app_farmer(client, "9000000051", "Viewer")
    oid = await _quick_farmer("9000000052", "O")
    rid = await _quick_farmer("9000000053", "R")
    lid = await _listing(oid)
    await _completed(lid, oid, rid, 5)
    await _recompute(oid)
    async with _Admin() as s:
        s.add(
            FarmerBadge(
                farmer_id=oid,
                badge="helpful_neighbour",
                awarded_at=NOW,
                awarded_by="system",
                revoked_at=NOW,
                revoked_by="system",
            )
        )
        s.add(
            TrustFlag(
                kind="rating_ring", farmer_ids=sorted([oid, rid]), status="open", created_at=NOW
            )
        )

    async with SessionLocal() as s, s.begin():
        await set_tenant_context(
            s, dealer_id=None, is_platform_admin=False, farmer_id=viewer["active_profile_id"]
        )
        rows = (await s.scalars(select(FarmerBadge))).all()
        assert [(r.badge, r.revoked_at) for r in rows] == [("trusted_renter", None)]
        assert (await s.execute(text("SELECT count(*) FROM trust_flags"))).scalar() == 0
        with pytest.raises(DBAPIError):
            await s.execute(
                text(
                    "INSERT INTO farmer_badges (farmer_id, badge, awarded_at, awarded_by) "
                    "VALUES (:f, 'trusted_renter', now(), 'me')"
                ),
                {"f": viewer["active_profile_id"]},
            )

    assert (await client.get("/v1/admin/trust/flags", headers=_h(viewer))).status_code == 403
