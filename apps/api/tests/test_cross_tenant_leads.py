import pytest

from tests._helpers import future, make_dealer_and_owner, token_for


async def _mklead(client, hdr, phone):
    r = await client.post(
        "/v1/leads", headers=hdr,
        json={"name": "R", "phone": phone, "source": "facebook", "next_action_at": future()},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_dealer_a_cannot_touch_dealer_b_lead(client):
    dealer_a, owner_a, _, _ = await make_dealer_and_owner("A", "9002000001")
    dealer_b, owner_b, _, _ = await make_dealer_and_owner("B", "9002000002")
    hdr_a = {"Authorization": f"Bearer {token_for(owner_a, 'owner', dealer_a)}"}
    hdr_b = {"Authorization": f"Bearer {token_for(owner_b, 'owner', dealer_b)}"}

    lead_b = await _mklead(client, hdr_b, "9876600001")

    for method, url, body in [
        ("GET", f"/v1/leads/{lead_b}", None),
        ("PATCH", f"/v1/leads/{lead_b}", {"score": "hot"}),
        ("POST", f"/v1/leads/{lead_b}/transition",
         {"to_stage": "contacted", "next_action_at": future()}),
        ("POST", f"/v1/leads/{lead_b}/events", {"type": "note", "payload": {"x": 1}}),
        ("GET", f"/v1/leads/{lead_b}/events", None),
    ]:
        if method == "GET":
            r = await client.get(url, headers=hdr_a)
        elif method == "PATCH":
            r = await client.patch(url, headers=hdr_a, json=body)
        else:
            r = await client.post(url, headers=hdr_a, json=body)
        assert r.status_code == 404, (method, url, r.text)


@pytest.mark.asyncio
async def test_list_leads_is_tenant_scoped(client):
    dealer_a, owner_a, _, _ = await make_dealer_and_owner("A", "9002000003")
    dealer_b, owner_b, _, _ = await make_dealer_and_owner("B", "9002000004")
    hdr_a = {"Authorization": f"Bearer {token_for(owner_a, 'owner', dealer_a)}"}
    hdr_b = {"Authorization": f"Bearer {token_for(owner_b, 'owner', dealer_b)}"}

    await _mklead(client, hdr_a, "9876600010")
    await _mklead(client, hdr_a, "9876600011")
    await _mklead(client, hdr_b, "9876600012")

    r = await client.get("/v1/leads", headers=hdr_a)
    assert len(r.json()) == 2
    r = await client.get("/v1/leads", headers=hdr_b)
    assert len(r.json()) == 1
