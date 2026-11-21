"""The gate test for E1: dealer A must not be able to read, modify, or delete
dealer B's users by ID. RLS + service-layer filtering together should make these
look like 404s, not 403s (avoid id-oracles)."""
import pytest

from tests._helpers import make_dealer_and_owner, token_for


@pytest.mark.asyncio
async def test_owner_a_cannot_read_user_of_dealer_b(client):
    dealer_a, owner_a_id, _, _ = await make_dealer_and_owner("Dealer A", "9999902001")
    dealer_b, owner_b_id, _, _ = await make_dealer_and_owner("Dealer B", "9999902002")

    owner_a_token = token_for(owner_a_id, "owner", dealer_a)
    hdr = {"Authorization": f"Bearer {owner_a_token}"}

    r = await client.get(f"/v1/users/{owner_b_id}", headers=hdr)
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_owner_a_cannot_deactivate_user_of_dealer_b(client):
    dealer_a, owner_a_id, _, _ = await make_dealer_and_owner("Dealer A", "9999902003")
    dealer_b, owner_b_id, _, _ = await make_dealer_and_owner("Dealer B", "9999902004")

    owner_a_token = token_for(owner_a_id, "owner", dealer_a)
    hdr = {"Authorization": f"Bearer {owner_a_token}"}

    r = await client.delete(f"/v1/users/{owner_b_id}", headers=hdr)
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_platform_admin_can_see_both(client):
    dealer_a, owner_a_id, phone_a, _ = await make_dealer_and_owner("Dealer A", "9999902005")
    dealer_b, owner_b_id, phone_b, _ = await make_dealer_and_owner("Dealer B", "9999902006")

    # Make a platform admin and a token for it
    from tests._helpers import make_platform_admin

    admin_id, _ = await make_platform_admin("9999902007")
    admin_token = token_for(admin_id, "platform_admin", None)
    hdr = {"Authorization": f"Bearer {admin_token}"}

    for uid in (owner_a_id, owner_b_id):
        r = await client.get(f"/v1/users/{uid}", headers=hdr)
        assert r.status_code == 200, r.text
