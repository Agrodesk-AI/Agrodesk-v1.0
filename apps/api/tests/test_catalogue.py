from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.core.db import SessionLocal
from tests._helpers import make_dealer_and_owner, token_for


async def _seed_catalogue(brand: str, model: str, hp: int) -> str:
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        row = (await s.execute(text(
            "INSERT INTO tractor_catalogue(brand, model, hp) VALUES (:b,:m,:h) RETURNING id"
        ), {"b": brand, "m": model, "h": hp})).first()
        return str(row[0])


@pytest.mark.asyncio
async def test_catalogue_lists_shared_rows(client):
    cid = await _seed_catalogue("Mahindra", "575", 45)
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9009000001")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    r = await client.get("/v1/catalogue", headers=hdr)
    assert r.status_code == 200
    rows = r.json()
    assert any(row["catalogue_id"] == cid for row in rows)
    row = next(row for row in rows if row["catalogue_id"] == cid)
    assert row["price_min"] is None  # no overlay yet


@pytest.mark.asyncio
async def test_dealer_overlay_shown(client):
    cid = await _seed_catalogue("Sonalika", "DI 745", 50)
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9009000002")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    await client.post(
        f"/v1/catalogue/{cid}/dealer-prices", headers=hdr,
        json={"price_min": 650000, "price_max": 720000,
              "offers": {"free_service": True}, "valid_till": None},
    )
    r = await client.get("/v1/catalogue", headers=hdr)
    row = next(r_ for r_ in r.json() if r_["catalogue_id"] == cid)
    assert row["price_min"] == 650000.0
    assert row["offers"]["free_service"] is True


@pytest.mark.asyncio
async def test_expired_offer_is_filtered(client):
    cid = await _seed_catalogue("Swaraj", "744 FE", 48)
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9009000003")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await client.post(
        f"/v1/catalogue/{cid}/dealer-prices", headers=hdr,
        json={"price_min": 500000, "price_max": 600000,
              "offers": {"discount": 15000}, "valid_till": yesterday},
    )
    r = await client.get("/v1/catalogue", headers=hdr)
    row = next(r_ for r_ in r.json() if r_["catalogue_id"] == cid)
    assert row["overlay_expired"] is True
    # price + offers are hidden; the catalogue row itself still appears
    assert row["price_min"] is None
    assert row["offers"] == {}


@pytest.mark.asyncio
async def test_dealer_a_cannot_see_dealer_b_overlay(client):
    cid = await _seed_catalogue("New Holland", "3600 TX", 50)
    dealer_a, owner_a, _, _ = await make_dealer_and_owner("A", "9009000004")
    dealer_b, owner_b, _, _ = await make_dealer_and_owner("B", "9009000005")
    hdr_b = {"Authorization": f"Bearer {token_for(owner_b, 'owner', dealer_b)}"}
    hdr_a = {"Authorization": f"Bearer {token_for(owner_a, 'owner', dealer_a)}"}
    await client.post(
        f"/v1/catalogue/{cid}/dealer-prices", headers=hdr_b,
        json={"price_min": 777000, "price_max": 800000, "offers": {}},
    )
    r = await client.get("/v1/catalogue", headers=hdr_a)
    row = next(r_ for r_ in r.json() if r_["catalogue_id"] == cid)
    assert row["price_min"] is None  # B's overlay is invisible to A
