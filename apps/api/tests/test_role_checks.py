import pytest

from tests._helpers import make_dealer_and_owner, token_for


@pytest.mark.asyncio
async def test_sales_cannot_invite_users(client):
    dealer_id, owner_id, _, _ = await make_dealer_and_owner("Acme", "9999901001")
    # fabricate a sales-role token for a fake user_id; endpoint checks role, not identity, here
    sales_token = token_for("00000000-0000-0000-0000-000000000001", "sales", dealer_id)
    r = await client.post(
        "/v1/users",
        headers={"Authorization": f"Bearer {sales_token}"},
        json={"name": "New Staff", "phone": "9999901002", "role": "sales"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_invite_user(client):
    dealer_id, owner_id, _, _ = await make_dealer_and_owner("Acme", "9999901003")
    owner_token = token_for(owner_id, "owner", dealer_id)
    r = await client.post(
        "/v1/users",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Ramesh", "phone": "9999901004", "role": "sales"},
    )
    assert r.status_code == 201
    assert r.json()["role"] == "sales"


@pytest.mark.asyncio
async def test_owner_cannot_create_platform_admin(client):
    dealer_id, owner_id, _, _ = await make_dealer_and_owner("Acme", "9999901005")
    owner_token = token_for(owner_id, "owner", dealer_id)
    r = await client.post(
        "/v1/users",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "X", "phone": "9999901006", "role": "platform_admin"},
    )
    assert r.status_code == 422
