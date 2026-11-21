from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead, LeadEvent, Task

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
    end_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    rows = await session.scalars(
        select(Task)
        .where(Task.user_id == user_id, Task.status == "pending", Task.due_at < end_of_day)
        .order_by(Task.due_at.asc())
    )
    return list(rows)


def suggest_next_action(outcome: str, *, lead: Lead, now: datetime | None = None) -> datetime | None:
    """Rules in code (no AI). Returns None for terminal-leaning outcomes."""
    now = now or datetime.now(UTC)
    if outcome in {"bought_elsewhere", "not_interested"}:
        return None
    if outcome == "not_picked":
        return now + timedelta(days=1)
    if outcome == "interested":
        return now + timedelta(days=2)
    if outcome == "visit_planned":
        # Day before the current next_action_at if far enough out, otherwise +3 days.
        if lead.next_action_at is not None and lead.next_action_at > now + timedelta(days=2):
            return lead.next_action_at - timedelta(days=1)
        return now + timedelta(days=3)
    if outcome == "price_issue":
        return now + timedelta(days=3)
    return now + timedelta(days=2)


async def mark_outcome(
    session: AsyncSession,
    *,
    task: Task,
    acting_user_id: UUID,
    outcome: str,
    next_action_at: datetime | None = None,
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
        lead = await session.scalar(select(Lead).where(Lead.id == task.lead_id))
        if lead is not None:
            # Write task_completed event
            session.add(LeadEvent(
                dealer_id=lead.dealer_id, lead_id=lead.id, type="task_completed",
                payload={"task_id": str(task.id), "outcome": outcome},
                actor_type="user", actor_id=acting_user_id, occurred_at=now,
            ))

            # Reschedule the lead using supplied next_action_at or suggested one
            if lead.stage not in {"won", "lost"}:
                new_next = next_action_at or suggest_next_action(outcome, lead=lead, now=now)
                if new_next is not None and new_next != lead.next_action_at:
                    before = lead.next_action_at
                    lead.next_action_at = new_next
                    session.add(LeadEvent(
                        dealer_id=lead.dealer_id, lead_id=lead.id, type="next_action_scheduled",
                        payload={
                            "at": new_next.isoformat(),
                            "from": before.isoformat() if before else None,
                            "by_outcome": outcome,
                        },
                        actor_type="user", actor_id=acting_user_id, occurred_at=now,
                    ))
                    # Create the next follow-up task
                    if lead.owner_user_id is not None:
                        session.add(Task(
                            dealer_id=lead.dealer_id, lead_id=lead.id,
                            user_id=lead.owner_user_id, due_at=new_next, type="follow_up",
                        ))
    await session.flush()
    return task


async def get(session: AsyncSession, task_id: UUID) -> Task | None:
    return await session.scalar(select(Task).where(Task.id == task_id))
