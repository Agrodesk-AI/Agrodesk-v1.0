import pytest

from tests._helpers import future, make_dealer_and_owner, past, token_for


@pytest.mark.asyncio
async def test_today_task_appears_and_completes(client):
    dealer, owner_id, _, _ = await make_dealer_and_owner("A", "9003000001")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer)}"}
    r = await client.post(
        "/v1/leads", headers=hdr,
        json={"name": "R", "phone": "9876700001", "source": "facebook",
              "next_action_at": future(60)},
    )
    assert r.status_code == 201
    lid = r.json()["id"]

    r = await client.get("/v1/tasks/today", headers=hdr)
    tasks = r.json()
    assert len(tasks) >= 1
    mine = next(t for t in tasks if t["lead_id"] == lid)

    r = await client.post(
        f"/v1/tasks/{mine['id']}/outcome", headers=hdr, json={"outcome": "interested"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "done"

    # event written on lead
    r = await client.get(f"/v1/leads/{lid}/events", headers=hdr)
    types = [e["type"] for e in r.json()]
    assert "task_completed" in types


@pytest.mark.asyncio
async def test_outcome_requires_matching_user(client):
    dealer_a, owner_a, _, _ = await make_dealer_and_owner("A", "9003000002")
    dealer_b, owner_b, _, _ = await make_dealer_and_owner("B", "9003000003")
    hdr_a = {"Authorization": f"Bearer {token_for(owner_a, 'owner', dealer_a)}"}

    r = await client.post(
        "/v1/leads", headers=hdr_a,
        json={"name": "R", "phone": "9876700010", "source": "facebook",
              "next_action_at": future()},
    )
    lid = r.json()["id"]
    r = await client.get("/v1/tasks/today", headers=hdr_a)
    t = next(t for t in r.json() if t["lead_id"] == lid)

    # dealer B's owner cannot even see dealer A's task (cross-tenant → 404)
    hdr_b = {"Authorization": f"Bearer {token_for(owner_b, 'owner', dealer_b)}"}
    r = await client.post(
        f"/v1/tasks/{t['id']}/outcome", headers=hdr_b, json={"outcome": "interested"}
    )
    assert r.status_code == 404
