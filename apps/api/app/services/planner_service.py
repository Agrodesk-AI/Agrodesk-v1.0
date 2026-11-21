"""Planner business logic. Celery tasks in app.jobs.planner thin-wrap these."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import JobRun, Lead, LeadEvent, Task
from app.security.tenant import set_tenant_context


async def _acquire_run(
    session: AsyncSession, job_name: str, logical_date: date, scope_id: UUID | None = None
) -> bool:
    """Returns True if this is the first run for the key; False if already claimed."""
    run = JobRun(
        job_name=job_name,
        logical_date=logical_date,
        scope_id=scope_id,
        started_at=datetime.now(UTC),
        status="running",
    )
    session.add(run)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return False
    return True


async def _finish_run(
    session: AsyncSession,
    job_name: str,
    logical_date: date,
    scope_id: UUID | None,
    payload: dict,
) -> None:
    coalesce = scope_id if scope_id is not None else UUID("00000000-0000-0000-0000-000000000000")
    row = await session.scalar(
        select(JobRun).where(
            JobRun.job_name == job_name,
            JobRun.logical_date == logical_date,
            func.coalesce(JobRun.scope_id, coalesce) == coalesce,
        )
    )
    if row is None:
        return
    row.finished_at = datetime.now(UTC)
    row.status = "done"
    row.payload = payload
    await session.flush()


async def generate_tasks_for_due(now: datetime | None = None) -> dict:
    """Upsert a pending task for every open lead whose next_action_at is within
    the next 24h and has an owner. Idempotent per logical_date."""
    now = now or datetime.now(UTC)
    logical_date = now.date()
    horizon = now + timedelta(hours=24)

    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        if not await _acquire_run(s, "generate_tasks_for_due", logical_date):
            return {"status": "already_ran"}

    created = 0
    skipped = 0
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        rows = (
            await s.scalars(
                select(Lead).where(
                    Lead.stage.notin_(("won", "lost")),
                    Lead.owner_user_id.is_not(None),
                    Lead.next_action_at.is_not(None),
                    Lead.next_action_at <= horizon,
                )
            )
        ).all()
        for lead in rows:
            has_pending = await s.scalar(
                select(
                    exists().where(
                        and_(
                            Task.lead_id == lead.id,
                            Task.status == "pending",
                            Task.user_id == lead.owner_user_id,
                        )
                    )
                )
            )
            if has_pending:
                skipped += 1
                continue
            s.add(
                Task(
                    dealer_id=lead.dealer_id,
                    lead_id=lead.id,
                    user_id=lead.owner_user_id,
                    due_at=lead.next_action_at,
                    type="follow_up",
                )
            )
            created += 1

        await _finish_run(
            s, "generate_tasks_for_due", logical_date, None,
            {"created": created, "skipped": skipped},
        )
    return {"status": "done", "created": created, "skipped": skipped}


async def check_stale_leads(now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    logical_date = now.date()
    cutoff = now - timedelta(days=settings.stale_lead_days)

    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        if not await _acquire_run(s, "check_stale_leads", logical_date):
            return {"status": "already_ran"}

    flagged = 0
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        last_event = (
            select(
                LeadEvent.lead_id.label("lead_id"),
                func.max(LeadEvent.occurred_at).label("last_at"),
            )
            .group_by(LeadEvent.lead_id)
            .subquery()
        )

        rows = (
            await s.scalars(
                select(Lead)
                .join(last_event, last_event.c.lead_id == Lead.id)
                .where(Lead.stage.notin_(("won", "lost")), last_event.c.last_at < cutoff)
            )
        ).all()
        for lead in rows:
            recent = await s.scalar(
                select(
                    exists().where(
                        LeadEvent.lead_id == lead.id,
                        LeadEvent.type == "note",
                        LeadEvent.payload["kind"].astext == "stale_flagged",
                        LeadEvent.occurred_at > cutoff,
                    )
                )
            )
            if recent:
                continue
            s.add(
                LeadEvent(
                    dealer_id=lead.dealer_id,
                    lead_id=lead.id,
                    type="note",
                    payload={"kind": "stale_flagged", "days": settings.stale_lead_days},
                    actor_type="system",
                    occurred_at=now,
                )
            )
            flagged += 1

        await _finish_run(s, "check_stale_leads", logical_date, None, {"flagged": flagged})
    return {"status": "done", "flagged": flagged}


async def emit_overdue_alerts(now: datetime | None = None) -> dict:
    """For each overdue open lead with an owner, write an overdue_alert event
    once per lead per day (tracked in job_runs with scope_id = lead.id)."""
    now = now or datetime.now(UTC)
    logical_date = now.date()
    overdue_cutoff = now - timedelta(hours=settings.overdue_threshold_hours)

    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        candidates = list(
            (
                await s.scalars(
                    select(Lead).where(
                        Lead.stage.notin_(("won", "lost")),
                        Lead.owner_user_id.is_not(None),
                        Lead.next_action_at.is_not(None),
                        Lead.next_action_at < overdue_cutoff,
                    )
                )
            ).all()
        )
        if not candidates:
            return {"status": "done", "alerted": 0}
        lead_ids = [c.id for c in candidates]

        already = set(
            (
                await s.scalars(
                    select(JobRun.scope_id).where(
                        JobRun.job_name == "emit_overdue_alert",
                        JobRun.logical_date == logical_date,
                        JobRun.scope_id.in_(lead_ids),
                    )
                )
            ).all()
        )

    alerted = 0
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        for lead in candidates:
            if lead.id in already:
                continue
            s.add(
                JobRun(
                    job_name="emit_overdue_alert",
                    logical_date=logical_date,
                    scope_id=lead.id,
                    started_at=now,
                    finished_at=now,
                    status="done",
                    payload={"overdue_since": lead.next_action_at.isoformat()},
                )
            )
            s.add(
                LeadEvent(
                    dealer_id=lead.dealer_id,
                    lead_id=lead.id,
                    type="note",
                    payload={"kind": "overdue_alert", "due_at": lead.next_action_at.isoformat()},
                    actor_type="system",
                    occurred_at=now,
                )
            )
            alerted += 1
    return {"status": "done", "alerted": alerted}
