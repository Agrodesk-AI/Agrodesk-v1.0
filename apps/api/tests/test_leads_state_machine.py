import pytest

from tests._helpers import future, make_dealer_and_owner, token_for


async def _create_lead(client, hdr, phone="9876500001", **extra):
    body = {
        "name": "Ramesh",
        "phone": phone,
        "source": "facebook",
        "next_action_at": future(3600),
    }
    body.update(extra)
    r = await client.post("/v1/leads", headers=hdr, json=body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_create_lead_requires_next_action(client):
    dealer, owner_id, _, _ = await make_dealer_and_owner("A", "9001000001")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer)}"}
    r = await client.post(
        "/v1/leads", headers=hdr,
        json={"name": "R", "phone": "9876500002", "source": "facebook"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_lead_rejects_bad_source(client):
    dealer, owner_id, _, _ = await make_dealer_and_owner("A", "9001000002")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer)}"}
    r = await client.post(
        "/v1/leads", headers=hdr,
        json={"name": "R", "phone": "9876500003", "source": "whatever", "next_action_at": future()},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_happy_path_new_to_won(client):
    dealer, owner_id, _, _ = await make_dealer_and_owner("A", "9001000003")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer)}"}
    lead = await _create_lead(client, hdr, phone="9876500010")
    lid = lead["id"]

    for to, extra in [
        ("contacted", {"next_action_at": future()}),
        ("qualified", {"next_action_at": future()}),
        ("visit_planned", {"next_action_at": future()}),
        ("negotiation", {"next_action_at": future()}),
        ("won", {}),
    ]:
        r = await client.post(
            f"/v1/leads/{lid}/transition", headers=hdr,
            json={"to_stage": to, **extra},
        )
        assert r.status_code == 200, (to, r.text)
        assert r.json()["lead"]["stage"] == to
        assert r.json()["event"]["type"] == "stage_changed"

    # won is terminal
    r = await client.post(
        f"/v1/leads/{lid}/transition", headers=hdr,
        json={"to_stage": "lost", "lost_reason": "x"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_invalid_jump_rejected(client):
    dealer, owner_id, _, _ = await make_dealer_and_owner("A", "9001000004")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer)}"}
    lead = await _create_lead(client, hdr, phone="9876500011")
    r = await client.post(
        f"/v1/leads/{lead['id']}/transition", headers=hdr,
        json={"to_stage": "qualified", "next_action_at": future()},
    )
    assert r.status_code == 422
    assert "invalid_transition" in r.json()["detail"]


@pytest.mark.asyncio
async def test_lost_requires_reason_and_can_reopen(client):
    dealer, owner_id, _, _ = await make_dealer_and_owner("A", "9001000005")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer)}"}
    lead = await _create_lead(client, hdr, phone="9876500012")

    r = await client.post(
        f"/v1/leads/{lead['id']}/transition", headers=hdr, json={"to_stage": "lost"}
    )
    assert r.status_code == 422

    r = await client.post(
        f"/v1/leads/{lead['id']}/transition", headers=hdr,
        json={"to_stage": "lost", "lost_reason": "bought_elsewhere"},
    )
    assert r.status_code == 200
    assert r.json()["lead"]["stage"] == "lost"
    assert r.json()["lead"]["lost_reason"] == "bought_elsewhere"

    # reopen
    r = await client.post(
        f"/v1/leads/{lead['id']}/transition", headers=hdr,
        json={"to_stage": "new", "next_action_at": future()},
    )
    assert r.status_code == 200
    assert r.json()["lead"]["stage"] == "new"
    assert r.json()["lead"]["lost_reason"] is None


@pytest.mark.asyncio
async def test_events_count_matches_transitions(client):
    dealer, owner_id, _, _ = await make_dealer_and_owner("A", "9001000006")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer)}"}
    lead = await _create_lead(client, hdr, phone="9876500013")
    lid = lead["id"]

    # created event already written
    r = await client.get(f"/v1/leads/{lid}/events", headers=hdr)
    created_evs = [e for e in r.json() if e["type"] == "created"]
    assert len(created_evs) == 1

    await client.post(
        f"/v1/leads/{lid}/transition", headers=hdr,
        json={"to_stage": "contacted", "next_action_at": future()},
    )
    await client.post(
        f"/v1/leads/{lid}/transition", headers=hdr,
        json={"to_stage": "lost", "lost_reason": "x"},
    )

    r = await client.get(f"/v1/leads/{lid}/events", headers=hdr)
    stage_evs = [e for e in r.json() if e["type"] == "stage_changed"]
    assert len(stage_evs) == 2
    assert stage_evs[0]["payload"]["from"] == "new"
    assert stage_evs[0]["payload"]["to"] == "contacted"
    assert stage_evs[1]["payload"]["from"] == "contacted"
    assert stage_evs[1]["payload"]["to"] == "lost"


@pytest.mark.asyncio
async def test_won_sets_won_at_and_cancels_tasks(client):
    dealer, owner_id, _, _ = await make_dealer_and_owner("A", "9001000007")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer)}"}
    lead = await _create_lead(client, hdr, phone="9876500014")
    lid = lead["id"]
    for to in ("contacted", "qualified", "visit_planned"):
        await client.post(
            f"/v1/leads/{lid}/transition", headers=hdr,
            json={"to_stage": to, "next_action_at": future()},
        )
    r = await client.post(
        f"/v1/leads/{lid}/transition", headers=hdr, json={"to_stage": "won"}
    )
    assert r.json()["lead"]["won_at"] is not None
    # today's tasks should now be empty (lead's pending task was skipped on won)
    r = await client.get("/v1/tasks/today", headers=hdr)
    assert all(t["lead_id"] != lid for t in r.json())


@pytest.mark.asyncio
async def test_update_lead_schedules_event(client):
    dealer, owner_id, _, _ = await make_dealer_and_owner("A", "9001000008")
    hdr = {"Authorization": f"Bearer {token_for(owner_id, 'owner', dealer)}"}
    lead = await _create_lead(client, hdr, phone="9876500015")
    r = await client.patch(
        f"/v1/leads/{lead['id']}", headers=hdr,
        json={"next_action_at": future(7200), "score": "hot"},
    )
    assert r.status_code == 200
    r = await client.get(f"/v1/leads/{lead['id']}/events", headers=hdr)
    types = [e["type"] for e in r.json()]
    assert "next_action_scheduled" in types
