from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead, Task

ALLOWED_OUTCOMES = {
    "not_picked",
    "interested",
    "visit_planned",
    "price_issue",
    "bought_elsewhere",
    "not_interested",
    "other",
}


class TaskError(Exception):
    pass


class BadOutcome(TaskError):
    pass


class TaskNotForYou(TaskError):
    pass


async def list_today(session: AsyncSession, *, user_id: UUID) -> list[Task]:
    now = datetime.now(UTC)
    end_of_day = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
    rows = await session.scalars(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.status == "pending",
            Task.due_at < end_of_day,
        )
        .order_by(Task.due_at.asc())
    )
    return list(rows)


async def mark_outcome(
    session: AsyncSession,
    *,
    task: Task,
    acting_user_id: UUID,
    outcome: str,
) -> Task:
    if outcome not in ALLOWED_OUTCOMES:
        raise BadOutcome(outcome)
    if task.user_id != acting_user_id:
        raise TaskNotForYou()

    now = datetime.now(UTC)
    task.status = "done"
    task.outcome = outcome
    task.completed_at = now

    if task.lead_id is not None:
        from app.models import LeadEvent

        lead = await session.scalar(select(Lead).where(Lead.id == task.lead_id))
        if lead is not None:
            ev = LeadEvent(
                dealer_id=lead.dealer_id,
                lead_id=lead.id,
                type="task_completed",
                payload={"task_id": str(task.id), "outcome": outcome},
                actor_type="user",
                actor_id=acting_user_id,
                occurred_at=now,
            )
            session.add(ev)
    await session.flush()
    return task


async def get(session: AsyncSession, task_id: UUID) -> Task | None:
    return await session.scalar(select(Task).where(Task.id == task_id))
