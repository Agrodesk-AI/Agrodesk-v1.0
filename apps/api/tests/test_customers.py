import pytest

from tests._helpers import make_dealer_and_owner, token_for


@pytest.mark.asyncio
async def test_create_customer_normalizes_phone(client):
    dealer_a, owner_id, _, _ = await make_dealer_and_owner("A", "9000000001")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer_a)}"}
    r = await client.post(
        "/v1/customers",
        headers=hdr,
        json={"name": "Ramesh", "phone": "9876543210"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["phone"] == "+919876543210"


@pytest.mark.asyncio
async def test_duplicate_by_phone_returns_existing(client):
    dealer_a, owner_id, _, _ = await make_dealer_and_owner("A", "9000000002")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer_a)}"}
    r1 = await client.post("/v1/customers", headers=hdr, json={"name": "A", "phone": "9876543211"})
    r2 = await client.post(
        "/v1/customers", headers=hdr, json={"name": "A changed", "phone": "+919876543211"}
    )
    assert r1.status_code == 200 and r2.status_code == 200
    # same id (not a new customer)
    assert r1.json()["id"] == r2.json()["id"]
    # name was NOT updated by the dedup path (that's PATCH's job)
    assert r2.json()["name"] == "A"


@pytest.mark.asyncio
async def test_same_phone_different_dealers_is_allowed(client):
    dealer_a, owner_a, _, _ = await make_dealer_and_owner("A", "9000000003")
    dealer_b, owner_b, _, _ = await make_dealer_and_owner("B", "9000000004")
    hdr_a = {"Authorization": f"Bearer {token_for(owner_a, 'owner', dealer_a)}"}
    hdr_b = {"Authorization": f"Bearer {token_for(owner_b, 'owner', dealer_b)}"}

    r_a = await client.post("/v1/customers", headers=hdr_a, json={"name": "P", "phone": "9876543212"})
    r_b = await client.post("/v1/customers", headers=hdr_b, json={"name": "P", "phone": "9876543212"})
    assert r_a.json()["id"] != r_b.json()["id"]


@pytest.mark.asyncio
async def test_opt_out_clears_consents(client):
    dealer, owner_id, _, _ = await make_dealer_and_owner("A", "9000000005")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer)}"}
    r = await client.post(
        "/v1/customers", headers=hdr,
        json={"name": "X", "phone": "9876543213", "consent_whatsapp": True, "consent_call": True},
    )
    cid = r.json()["id"]
    r = await client.post(f"/v1/customers/{cid}/opt-out", headers=hdr)
    data = r.json()
    assert data["opted_out_at"] is not None
    assert data["consent_whatsapp"] is False
    assert data["consent_call"] is False
