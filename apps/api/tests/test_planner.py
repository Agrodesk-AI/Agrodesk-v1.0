from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models import Lead, LeadEvent, Task
from app.services import planner_service
from app.services.task_service import suggest_next_action
from tests._helpers import future, make_dealer_and_owner, token_for


async def _mklead(client, hdr, phone, **extra):
    body = {"name": "R", "phone": phone, "source": "facebook", "next_action_at": future()}
    body.update(extra)
    r = await client.post("/v1/leads", headers=hdr, json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _set_next_action_at(lead_id: str, new_at: datetime) -> None:
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        lead = await s.scalar(select(Lead).where(Lead.id == lead_id))
        if lead:
            lead.next_action_at = new_at


async def _remove_pending_tasks(lead_id: str) -> None:
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        await s.execute(text(
            "UPDATE tasks SET status='skipped' WHERE lead_id=:id AND status='pending'"
        ), {"id": lead_id})


@pytest.mark.asyncio
async def test_generate_tasks_idempotent(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9005000001")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead(client, hdr, "9876800001")
    await _remove_pending_tasks(lead["id"])

    r1 = await planner_service.generate_tasks_for_due()
    r2 = await planner_service.generate_tasks_for_due()
    assert r1["status"] == "done"
    assert r2["status"] == "already_ran"

    # exactly one new pending task for the lead
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        rows = (await s.scalars(
            select(Task).where(Task.lead_id == lead["id"], Task.status == "pending")
        )).all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_generate_tasks_skips_leads_without_owner(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9005000002")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead(client, hdr, "9876800002")
    # Null-out the owner
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        await s.execute(text("UPDATE leads SET owner_user_id=NULL WHERE id=:id"),
                        {"id": lead["id"]})
    await _remove_pending_tasks(lead["id"])
    await planner_service.generate_tasks_for_due()
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        rows = (await s.scalars(
            select(Task).where(Task.lead_id == lead["id"], Task.status == "pending")
        )).all()
        assert rows == []


@pytest.mark.asyncio
async def test_stale_leads_flagged(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9005000003")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead(client, hdr, "9876800003")

    # Backdate all events to 20 days ago
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        await s.execute(text(
            "UPDATE lead_events SET occurred_at = now() - interval '20 days' WHERE lead_id=:id"
        ), {"id": lead["id"]})

    await planner_service.check_stale_leads()
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        events = (await s.scalars(
            select(LeadEvent).where(LeadEvent.lead_id == lead["id"])
        )).all()
        kinds = [e.payload.get("kind") for e in events if e.type == "note"]
        assert "stale_flagged" in kinds


@pytest.mark.asyncio
async def test_overdue_alerts_once_per_day(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9005000004")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead(client, hdr, "9876800004")
    # Set next_action_at 3h ago (overdue threshold is 2h)
    await _set_next_action_at(lead["id"], datetime.now(UTC) - timedelta(hours=3))

    r1 = await planner_service.emit_overdue_alerts()
    r2 = await planner_service.emit_overdue_alerts()
    assert r1["alerted"] == 1
    assert r2["alerted"] == 0

    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        events = (await s.scalars(
            select(LeadEvent).where(LeadEvent.lead_id == lead["id"], LeadEvent.type == "note")
        )).all()
        kinds = [e.payload.get("kind") for e in events]
        assert kinds.count("overdue_alert") == 1


def test_suggest_next_action_rules():
    now = datetime(2026, 11, 22, 12, 0, 0, tzinfo=UTC)

    class L:
        next_action_at = None

    assert suggest_next_action("not_picked", lead=L(), now=now) == now + timedelta(days=1)
    assert suggest_next_action("interested", lead=L(), now=now) == now + timedelta(days=2)
    assert suggest_next_action("price_issue", lead=L(), now=now) == now + timedelta(days=3)
    assert suggest_next_action("bought_elsewhere", lead=L(), now=now) is None
    assert suggest_next_action("not_interested", lead=L(), now=now) is None
    # visit_planned without a future date defaults to +3d
    assert suggest_next_action("visit_planned", lead=L(), now=now) == now + timedelta(days=3)

    # visit_planned with a far-future date returns day before
    class L2:
        next_action_at = now + timedelta(days=5)

    assert suggest_next_action("visit_planned", lead=L2(), now=now) == now + timedelta(days=4)


@pytest.mark.asyncio
async def test_outcome_reschedules_lead(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9005000005")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead(client, hdr, "9876800005")
    r = await client.get("/v1/tasks/today", headers=hdr)
    task = next(t for t in r.json() if t["lead_id"] == lead["id"])

    before_next = lead["next_action_at"]
    r = await client.post(
        f"/v1/tasks/{task['id']}/outcome",
        headers=hdr,
        json={"outcome": "not_picked"},
    )
    assert r.status_code == 200

    # Lead's next_action_at should have moved ~1 day out
    r = await client.get(f"/v1/leads/{lead['id']}", headers=hdr)
    after_next = r.json()["next_action_at"]
    assert after_next is not None and after_next != before_next

    # And a new pending task should exist
    r = await client.get("/v1/tasks/today", headers=hdr)
    # the new task might be outside "today" window (+1d); just check at DB level
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        rows = (await s.scalars(
            select(Task).where(Task.lead_id == lead["id"], Task.status == "pending")
        )).all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_outcome_bought_elsewhere_doesnt_reschedule(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9005000006")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead(client, hdr, "9876800006")
    r = await client.get("/v1/tasks/today", headers=hdr)
    task = next(t for t in r.json() if t["lead_id"] == lead["id"])
    before_next = lead["next_action_at"]

    r = await client.post(
        f"/v1/tasks/{task['id']}/outcome", headers=hdr,
        json={"outcome": "bought_elsewhere"},
    )
    assert r.status_code == 200

    r = await client.get(f"/v1/leads/{lead['id']}", headers=hdr)
    # next_action_at should be unchanged (suggestion returned None)
    assert r.json()["next_action_at"] == before_next


@pytest.mark.asyncio
async def test_suggest_endpoint(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9005000007")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead(client, hdr, "9876800007")
    r = await client.get("/v1/tasks/today", headers=hdr)
    task = next(t for t in r.json() if t["lead_id"] == lead["id"])

    r = await client.get(
        f"/v1/tasks/{task['id']}/suggest?outcome=interested", headers=hdr
    )
    assert r.status_code == 200
    data = r.json()
    assert data["outcome"] == "interested"
    assert data["next_action_at"] is not None
