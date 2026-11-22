"""Rental exchange (design §3.5): listings, needs, booking state machine,
no double booking, masked contact, rating trust gate, RLS."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.db import SessionLocal
from app.models import RentalBooking
from app.security.tenant import set_tenant_context
from tests._helpers import make_platform_admin, token_for
from tests.test_farmer import _h, _login, _onboard_body, _seed_locations

NIPHAD, SINNAR, YEOLA, KUMBAKONAM = 904101, 904102, 904103, 905201


def _d(days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


async def _farmer(client, phone: str, name: str, tehsil: int) -> dict:
    acct = await _login(client, phone)
    body = _onboard_body(display_name=name, tehsil_id=tehsil, village_id=None)
    r = await client.post("/v1/farmer/onboard", json=body, headers=_h(acct))
    assert r.status_code == 201, r.text
    return r.json()


TRACTOR = {
    "kind": "tractor",
    "title": "Mahindra 575 with rotavator",
    "hp": 45,
    "rate_paise": 90000,
    "rate_unit": "hour",
    "operator_included": True,
}


async def _world(client):
    await _seed_locations()
    owner = await _farmer(client, "9444400001", "Owner Patil", NIPHAD)
    renter = await _farmer(client, "9444400002", "Renter Jadhav", YEOLA)
    renter2 = await _farmer(client, "9444400003", "Renter Two", SINNAR)
    far = await _farmer(client, "9444400004", "Far Away", KUMBAKONAM)
    r = await client.post("/v1/rentals/listings", json=TRACTOR, headers=_h(owner))
    assert r.status_code == 201, r.text
    return owner, renter, renter2, far, r.json()


async def _book(client, who, listing_id, start=3, end=4, **kw):
    body = {"listing_id": listing_id, "start_date": _d(start), "end_date": _d(end), **kw}
    return await client.post("/v1/rentals/bookings", json=body, headers=_h(who))


async def _act(client, who, bid, action, note=None):
    return await client.post(
        f"/v1/rentals/bookings/{bid}/transition",
        json={"action": action, "note": note},
        headers=_h(who),
    )


# ---------------------------------------------------------------- browse + needs


@pytest.mark.asyncio
async def test_browse_is_nearby_only_and_excludes_own(client):
    owner, renter, _, far, listing = await _world(client)
    r = await client.get("/v1/rentals/listings", headers=_h(renter))
    assert [(x["id"], x["tehsil_name"], x["distance_rank"]) for x in r.json()] == [
        (listing["id"], "Niphad", 99)  # Yeola -> Niphad via same-district fallback
    ]
    assert r.json()[0]["owner_name"] == "Owner Patil"
    assert (await client.get("/v1/rentals/listings", headers=_h(far))).json() == []
    assert (await client.get("/v1/rentals/listings", headers=_h(owner))).json() == []
    r = await client.get("/v1/rentals/listings", params={"kind": "harvester"}, headers=_h(renter))
    assert r.json() == []
    # dealer / onboarding tokens are refused
    acct = await _login(client, "9444400099")
    assert (await client.get("/v1/rentals/listings", headers=_h(acct))).status_code == 403


@pytest.mark.asyncio
async def test_needs_reach_nearby_owners_with_matching_kind(client):
    owner, renter, _, far, listing = await _world(client)
    need = {"kind": "tractor", "acreage": "3.5", "start_date": _d(5), "end_date": _d(6)}
    r = await client.post("/v1/rentals/needs", json=need, headers=_h(renter))
    assert r.status_code == 201, r.text
    need_id = r.json()["id"]
    await client.post("/v1/rentals/needs", json={**need, "kind": "harvester"}, headers=_h(renter))

    r = await client.get("/v1/rentals/needs/nearby", headers=_h(owner))
    assert [n["id"] for n in r.json()] == [need_id]  # only kinds the owner lists
    assert (await client.get("/v1/rentals/needs/nearby", headers=_h(far))).json() == []

    r = await client.get(f"/v1/rentals/needs/{need_id}/matches", headers=_h(renter))
    assert [x["id"] for x in r.json()] == [listing["id"]]
    assert (
        await client.get(f"/v1/rentals/needs/{need_id}/matches", headers=_h(owner))
    ).status_code == 404

    bad = {**need, "start_date": _d(-1)}
    assert (await client.post("/v1/rentals/needs", json=bad, headers=_h(renter))).status_code == 422
    bad = {**need, "end_date": _d(100)}
    assert (await client.post("/v1/rentals/needs", json=bad, headers=_h(renter))).status_code == 422


# ---------------------------------------------------------------- happy path


@pytest.mark.asyncio
async def test_full_booking_lifecycle(client):
    owner, renter, _, _, listing = await _world(client)
    need = (
        await client.post(
            "/v1/rentals/needs",
            json={"kind": "tractor", "start_date": _d(3), "end_date": _d(4)},
            headers=_h(renter),
        )
    ).json()

    r = await _book(client, renter, listing["id"], need_id=need["id"], note="2 acres")
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["state"] == "requested" and b["my_role"] == "renter"
    assert b["allowed_actions"] == ["cancel"]
    bid = b["id"]

    # contact masked before agreement
    assert (
        await client.get(f"/v1/rentals/bookings/{bid}/contact", headers=_h(owner))
    ).status_code == 403
    assert (
        await client.post(f"/v1/rentals/bookings/{bid}/share-contact", headers=_h(owner))
    ).status_code == 409

    # renter can't agree to their own request
    assert (await _act(client, renter, bid, "agree")).status_code == 409
    r = await _act(client, owner, bid, "agree")
    assert r.status_code == 200 and r.json()["state"] == "agreed"
    assert "share_contact" in r.json()["allowed_actions"]
    mine = (await client.get("/v1/rentals/needs/mine", headers=_h(renter))).json()
    assert mine[0]["status"] == "matched"

    # masked until BOTH share
    await client.post(f"/v1/rentals/bookings/{bid}/share-contact", headers=_h(owner))
    assert (
        await client.get(f"/v1/rentals/bookings/{bid}/contact", headers=_h(renter))
    ).status_code == 403
    r = await client.post(f"/v1/rentals/bookings/{bid}/share-contact", headers=_h(renter))
    assert r.json()["they_shared_contact"] is True
    r = await client.get(f"/v1/rentals/bookings/{bid}/contact", headers=_h(renter))
    assert r.json() == {"name": "Owner Patil", "phone": "+919444400001"}
    r = await client.get(f"/v1/rentals/bookings/{bid}/contact", headers=_h(owner))
    assert r.json()["phone"] == "+919444400002"

    assert (await _act(client, renter, bid, "start")).json()["state"] == "in_progress"

    # rating blocked until both complete
    r = await client.post(
        f"/v1/rentals/bookings/{bid}/rating", json={"score": 5}, headers=_h(renter)
    )
    assert r.status_code == 409
    r = await _act(client, owner, bid, "complete")
    assert r.json()["state"] == "in_progress" and r.json()["owner_completed"] is True
    assert (await _act(client, owner, bid, "complete")).status_code == 409
    r = await _act(client, renter, bid, "complete")
    assert r.json()["state"] == "completed_by_both"
    assert "rate" in r.json()["allowed_actions"]

    r = await client.post(
        f"/v1/rentals/bookings/{bid}/rating",
        json={"score": 5, "text": "On time"},
        headers=_h(renter),
    )
    assert r.json()["state"] == "completed_by_both" and r.json()["i_rated"]
    assert (
        await client.post(
            f"/v1/rentals/bookings/{bid}/rating", json={"score": 1}, headers=_h(renter)
        )
    ).status_code == 409
    r = await client.post(
        f"/v1/rentals/bookings/{bid}/rating", json={"score": 4}, headers=_h(owner)
    )
    assert r.json()["state"] == "rated"

    # owner's rating shows on the listing
    r = await client.get("/v1/rentals/listings", headers=_h(renter))
    assert r.json()[0]["owner_rating"] == 5.0 and r.json()[0]["owner_rating_count"] == 1

    r = await client.get(f"/v1/rentals/bookings/{bid}/events", headers=_h(owner))
    assert [(e["action"], e["by"]) for e in r.json()] == [
        ("request", "renter"),
        ("agree", "owner"),
        ("start", "renter"),
        ("complete", "owner"),
        ("complete", "renter"),
        ("rate", "owner"),
    ]


# ---------------------------------------------------------------- double booking


@pytest.mark.asyncio
async def test_no_double_booking(client):
    owner, renter, renter2, _, listing = await _world(client)
    b1 = (await _book(client, renter, listing["id"], 3, 5)).json()["id"]
    b2 = (await _book(client, renter2, listing["id"], 5, 6)).json()["id"]  # overlaps day 5
    b3 = await _book(client, renter2, listing["id"], 10, 11)  # same renter, same listing
    assert b3.status_code == 409 and b3.json()["detail"] == "already_requested"

    assert (await _act(client, owner, b1, "agree")).status_code == 200
    # the overlapping request was auto-declined
    r = await client.get(f"/v1/rentals/bookings/{b2}", headers=_h(renter2))
    assert r.json()["state"] == "declined"
    # browsing with taken dates hides the listing; free dates show it
    q = {"start_date": _d(4), "end_date": _d(4)}
    assert (await client.get("/v1/rentals/listings", params=q, headers=_h(renter2))).json() == []
    q = {"start_date": _d(7), "end_date": _d(8)}
    assert (
        len((await client.get("/v1/rentals/listings", params=q, headers=_h(renter2))).json()) == 1
    )
    # new request on taken dates is refused up front
    r = await _book(client, renter2, listing["id"], 4, 4)
    assert r.status_code == 409 and r.json()["detail"] == "dates_taken"


@pytest.mark.asyncio
async def test_db_exclusion_constraint_backstops_service(client):
    owner, renter, renter2, _, listing = await _world(client)
    b1 = (await _book(client, renter, listing["id"], 3, 5)).json()["id"]
    b2 = (await _book(client, renter2, listing["id"], 4, 6)).json()["id"]
    await _act(client, owner, b1, "agree")
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        with pytest.raises(DBAPIError):
            await s.execute(
                text("UPDATE rental_bookings SET state='agreed' WHERE id=:i"), {"i": b2}
            )


# ---------------------------------------------------------------- rules


@pytest.mark.asyncio
async def test_booking_rules(client):
    owner, renter, _, far, listing = await _world(client)
    r = await _book(client, owner, listing["id"])
    assert r.json()["detail"] == "own_listing"
    r = await _book(client, far, listing["id"])
    assert r.json()["detail"] == "too_far"
    r = await _book(client, renter, listing["id"], -2, 1)
    assert r.json()["detail"] == "start_in_past"

    await client.patch(
        f"/v1/rentals/listings/{listing['id']}", json={"status": "paused"}, headers=_h(owner)
    )
    r = await _book(client, renter, listing["id"])
    assert r.status_code == 404
    # only the owner can edit
    r = await client.patch(
        f"/v1/rentals/listings/{listing['id']}", json={"status": "active"}, headers=_h(renter)
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_dispute_and_admin_resolve(client):
    owner, renter, _, _, listing = await _world(client)
    bid = (await _book(client, renter, listing["id"])).json()["id"]
    await _act(client, owner, bid, "agree")
    await _act(client, owner, bid, "start")
    r = await _act(client, renter, bid, "dispute")
    assert r.status_code == 422 and r.json()["detail"] == "reason_required"
    r = await _act(client, renter, bid, "dispute", "Engine broke on day 1")
    assert r.json()["state"] == "disputed" and r.json()["allowed_actions"] == ["share_contact"]

    admin_id, _ = await make_platform_admin("9444400090")
    admin_h = {"Authorization": f"Bearer {token_for(admin_id, 'platform_admin', None)}"}
    r = await client.post(
        f"/v1/admin/rentals/bookings/{bid}/resolve",
        json={"resolution": "Half refund agreed"},
        headers=_h(owner),
    )
    assert r.status_code == 403
    r = await client.post(
        f"/v1/admin/rentals/bookings/{bid}/resolve",
        json={"resolution": "Half refund agreed"},
        headers=admin_h,
    )
    assert r.json()["state"] == "resolved"
    ev = (await client.get(f"/v1/rentals/bookings/{bid}/events", headers=_h(renter))).json()
    assert ev[-1]["by"] == "admin"


@pytest.mark.asyncio
async def test_cancel_paths(client):
    owner, renter, _, _, listing = await _world(client)
    bid = (await _book(client, renter, listing["id"])).json()["id"]
    assert (await _act(client, owner, bid, "cancel")).status_code == 409  # owner declines instead
    assert (await _act(client, renter, bid, "cancel")).json()["state"] == "cancelled"
    bid = (await _book(client, renter, listing["id"])).json()["id"]
    await _act(client, owner, bid, "agree")
    assert (await _act(client, owner, bid, "cancel")).json()["state"] == "cancelled"
    # dates free again
    assert (await _book(client, renter, listing["id"])).status_code == 201


# ---------------------------------------------------------------- isolation + trust gate


@pytest.mark.asyncio
async def test_rls_and_rating_trigger(client):
    owner, renter, renter2, _, listing = await _world(client)
    bid = (await _book(client, renter, listing["id"])).json()["id"]

    # third farmer can't see or touch the booking
    assert (await client.get(f"/v1/rentals/bookings/{bid}", headers=_h(renter2))).status_code == 404
    assert (await _act(client, renter2, bid, "agree")).status_code == 404
    assert (await client.get("/v1/rentals/bookings", headers=_h(renter2))).json() == []

    async with SessionLocal() as s, s.begin():
        await set_tenant_context(
            s, dealer_id=None, is_platform_admin=False, farmer_id=renter2["active_profile_id"]
        )
        assert (await s.scalars(select(RentalBooking))).all() == []
        n = (await s.execute(text("SELECT count(*) FROM rental_booking_events"))).scalar()
        assert n == 0
        # can see the active listing (marketplace) but not edit it
        res = await s.execute(text("UPDATE equipment_listings SET title='x'"))
        assert res.rowcount == 0
        # busy function leaks only a boolean
        busy = (
            await s.execute(
                text("SELECT rental_listing_busy(:l, :a, :b)"),
                {"l": listing["id"], "a": date.today(), "b": date.today() + timedelta(days=30)},
            )
        ).scalar()
        assert busy is False

    # trigger: no rating row before completion, even bypassing the service
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(
            s, dealer_id=None, is_platform_admin=False, farmer_id=renter["active_profile_id"]
        )
        with pytest.raises(DBAPIError, match="rating_before_completion"):
            await s.execute(
                text(
                    "INSERT INTO rental_ratings (booking_id, from_farmer_id, to_farmer_id, score) "
                    "VALUES (:b, :f, :t, 5)"
                ),
                {"b": bid, "f": renter["active_profile_id"], "t": owner["active_profile_id"]},
            )
