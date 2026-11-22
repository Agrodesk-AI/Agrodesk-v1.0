from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead, LeadEvent, Task
from app.schemas.customer import CustomerCreateIn
from app.schemas.lead import LeadTransitionIn, LeadUpdateIn, QuickAddLeadIn
from app.services.customer_service import create_or_get_by_phone

# --- state machine ---
STAGES = {"new", "contacted", "qualified", "visit_planned", "negotiation", "won", "lost"}
TERMINAL_STAGES = {"won"}
OPEN_STAGES = STAGES - {"won", "lost"}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "new": {"contacted", "lost"},
    "contacted": {"qualified", "lost"},
    "qualified": {"visit_planned", "negotiation", "lost"},
    "visit_planned": {"negotiation", "qualified", "lost", "won"},
    "negotiation": {"won", "lost", "visit_planned"},
    "won": set(),
    "lost": {"new"},  # reopen
}

ALLOWED_SOURCES = {"facebook", "walk_in", "referral", "oem", "other"}
ALLOWED_SCORES = {"hot", "warm", "dead"}


class LeadError(Exception):
    """Base class for lead service domain errors (422 at the router)."""


class InvalidTransition(LeadError):
    pass


class LostReasonRequired(LeadError):
    pass


class NextActionRequired(LeadError):
    pass


class UnknownStage(LeadError):
    pass


class BadFieldValue(LeadError):
    pass


async def _routing_responded(session: AsyncSession, lead: Lead) -> None:
    """A staff action on a routed lead stops its re-route SLA clock."""
    if lead.source == "agrodesk_guide":
        from app.services.routing_service import mark_responded  # avoid import cycle

        await mark_responded(session, lead)


def _write_event(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    lead_id: UUID,
    type_: str,
    payload: dict,
    actor_type: str,
    actor_id: UUID | None,
) -> LeadEvent:
    ev = LeadEvent(
        dealer_id=dealer_id,
        lead_id=lead_id,
        type=type_,
        payload=payload,
        actor_type=actor_type,
        actor_id=actor_id,
        occurred_at=datetime.now(UTC),
    )
    session.add(ev)
    return ev


async def _upsert_task_for_next_action(
    session: AsyncSession, lead: Lead
) -> Task | None:
    """Ensure there's a pending task matching the lead's next_action_at + owner."""
    if lead.owner_user_id is None or lead.next_action_at is None:
        return None
    existing = await session.scalar(
        select(Task).where(
            Task.lead_id == lead.id,
            Task.user_id == lead.owner_user_id,
            Task.status == "pending",
        )
    )
    if existing is not None:
        existing.due_at = lead.next_action_at
        return existing
    t = Task(
        dealer_id=lead.dealer_id,
        lead_id=lead.id,
        user_id=lead.owner_user_id,
        due_at=lead.next_action_at,
        type="follow_up",
    )
    session.add(t)
    return t


async def create_lead(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    actor_user_id: UUID,
    data: QuickAddLeadIn,
) -> Lead:
    if data.source not in ALLOWED_SOURCES:
        raise BadFieldValue(f"bad_source:{data.source}")
    if data.score is not None and data.score not in ALLOWED_SCORES:
        raise BadFieldValue(f"bad_score:{data.score}")
    if data.next_action_at is None:
        raise NextActionRequired()

    customer, _ = await create_or_get_by_phone(
        session,
        dealer_id,
        CustomerCreateIn(name=data.name, phone=data.phone, language=data.language),
    )

    owner_id = data.owner_user_id or actor_user_id
    lead = Lead(
        dealer_id=dealer_id,
        customer_id=customer.id,
        source=data.source,
        referrer_customer_id=data.referrer_customer_id,
        model_interest=data.model_interest,
        stage="new",
        score=data.score,
        owner_user_id=owner_id,
        next_action_at=data.next_action_at,
        campaign=data.campaign,
        ad_name=data.ad_name,
        created_via="manual",
    )
    session.add(lead)
    await session.flush()

    _write_event(
        session,
        dealer_id=dealer_id,
        lead_id=lead.id,
        type_="created",
        payload={
            "source": data.source,
            "customer_id": str(customer.id),
            "owner_user_id": str(owner_id),
        },
        actor_type="user",
        actor_id=actor_user_id,
    )
    await _upsert_task_for_next_action(session, lead)
    await session.flush()
    return lead


async def update_lead(
    session: AsyncSession,
    *,
    lead: Lead,
    actor_user_id: UUID,
    data: LeadUpdateIn,
) -> Lead:
    changed = data.model_dump(exclude_unset=True)
    if "score" in changed and changed["score"] is not None and changed["score"] not in ALLOWED_SCORES:
        raise BadFieldValue(f"bad_score:{changed['score']}")

    if "next_action_at" in changed and changed["next_action_at"] is None:
        if lead.stage in OPEN_STAGES:
            raise NextActionRequired()

    before_owner = lead.owner_user_id
    before_next = lead.next_action_at
    for field, value in changed.items():
        setattr(lead, field, value)
    await session.flush()

    if "owner_user_id" in changed and changed["owner_user_id"] != before_owner:
        _write_event(
            session,
            dealer_id=lead.dealer_id,
            lead_id=lead.id,
            type_="assigned",
            payload={
                "from": str(before_owner) if before_owner else None,
                "to": str(changed["owner_user_id"]) if changed["owner_user_id"] else None,
            },
            actor_type="user",
            actor_id=actor_user_id,
        )
    if "next_action_at" in changed and changed["next_action_at"] != before_next:
        _write_event(
            session,
            dealer_id=lead.dealer_id,
            lead_id=lead.id,
            type_="next_action_scheduled",
            payload={"at": changed["next_action_at"].isoformat() if changed["next_action_at"] else None},
            actor_type="user",
            actor_id=actor_user_id,
        )
    await _upsert_task_for_next_action(session, lead)
    await session.flush()
    return lead


async def transition(
    session: AsyncSession,
    *,
    lead: Lead,
    actor_user_id: UUID,
    data: LeadTransitionIn,
) -> tuple[Lead, LeadEvent]:
    if data.to_stage not in STAGES:
        raise UnknownStage(data.to_stage)

    allowed = ALLOWED_TRANSITIONS.get(lead.stage, set())
    if data.to_stage not in allowed:
        raise InvalidTransition(f"{lead.stage}->{data.to_stage}")

    from_stage = lead.stage
    now = datetime.now(UTC)

    if data.to_stage == "lost":
        if not data.lost_reason:
            raise LostReasonRequired()
        lead.lost_reason = data.lost_reason
    elif data.to_stage == "won":
        lead.won_at = now
        lead.next_action_at = None
    elif data.to_stage == "new":  # reopening from lost
        lead.lost_reason = None
        if data.next_action_at is None:
            raise NextActionRequired()

    # If transitioning to an open stage, require next_action_at (either existing or supplied)
    if data.to_stage in OPEN_STAGES:
        if data.next_action_at is not None:
            lead.next_action_at = data.next_action_at
        if lead.next_action_at is None:
            raise NextActionRequired()

    lead.stage = data.to_stage
    await session.flush()
    await _routing_responded(session, lead)

    ev = _write_event(
        session,
        dealer_id=lead.dealer_id,
        lead_id=lead.id,
        type_="stage_changed",
        payload={
            "from": from_stage,
            "to": data.to_stage,
            "lost_reason": data.lost_reason,
            "notes": data.notes,
        },
        actor_type="user",
        actor_id=actor_user_id,
    )
    if lead.stage in {"won", "lost"}:
        # cancel pending follow-up tasks for this lead
        from sqlalchemy import update as sqlupdate

        await session.execute(
            sqlupdate(Task)
            .where(Task.lead_id == lead.id, Task.status == "pending")
            .values(status="skipped", completed_at=now)
        )
    else:
        await _upsert_task_for_next_action(session, lead)
    await session.flush()
    return lead, ev


async def get(session: AsyncSession, lead_id: UUID) -> Lead | None:
    return await session.scalar(select(Lead).where(Lead.id == lead_id))


async def list_events(session: AsyncSession, lead_id: UUID) -> list[LeadEvent]:
    rows = await session.scalars(
        select(LeadEvent).where(LeadEvent.lead_id == lead_id).order_by(LeadEvent.occurred_at.asc())
    )
    return list(rows)


async def add_event(
    session: AsyncSession,
    *,
    lead: Lead,
    actor_user_id: UUID,
    type_: str,
    payload: dict,
) -> LeadEvent:
    ALLOWED = {"note", "call_made", "opted_out"}
    if type_ not in ALLOWED:
        raise BadFieldValue(f"bad_event_type:{type_}")
    ev = _write_event(
        session,
        dealer_id=lead.dealer_id,
        lead_id=lead.id,
        type_=type_,
        payload=payload or {},
        actor_type="user",
        actor_id=actor_user_id,
    )
    await session.flush()
    await _routing_responded(session, lead)
    return ev


async def list_leads(
    session: AsyncSession,
    *,
    stage: str | None = None,
    owner_user_id: UUID | None = None,
    source: str | None = None,
    limit: int = 50,
) -> list[Lead]:
    limit = max(1, min(limit, 200))
    q = select(Lead)
    if stage:
        q = q.where(Lead.stage == stage)
    if owner_user_id:
        q = q.where(Lead.owner_user_id == owner_user_id)
    if source:
        q = q.where(Lead.source == source)
    q = q.order_by(Lead.next_action_at.asc().nullslast(), Lead.created_at.desc()).limit(limit)
    rows = await session.scalars(q)
    return list(rows)
