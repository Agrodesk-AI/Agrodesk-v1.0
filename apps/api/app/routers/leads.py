from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.db import get_session_tenant
from app.schemas.lead import (
    LeadEventCreateIn,
    LeadEventOut,
    LeadOut,
    LeadTransitionIn,
    LeadTransitionOut,
    LeadUpdateIn,
    QuickAddLeadIn,
)
from app.services import lead_service

router = APIRouter(prefix="/v1/leads", tags=["leads"])


def _out(lead) -> LeadOut:
    return LeadOut(
        id=lead.id,
        dealer_id=lead.dealer_id,
        customer_id=lead.customer_id,
        source=lead.source,
        referrer_customer_id=lead.referrer_customer_id,
        model_interest=lead.model_interest,
        stage=lead.stage,
        score=lead.score,
        owner_user_id=lead.owner_user_id,
        next_action_at=lead.next_action_at,
        lost_reason=lead.lost_reason,
        won_at=lead.won_at,
        campaign=lead.campaign,
        ad_name=lead.ad_name,
        created_via=lead.created_via,
        created_at=lead.created_at,
    )


def _event_out(ev) -> LeadEventOut:
    return LeadEventOut(
        id=ev.id,
        lead_id=ev.lead_id,
        type=ev.type,
        payload=ev.payload or {},
        actor_type=ev.actor_type,
        actor_id=ev.actor_id,
        occurred_at=ev.occurred_at,
    )


def _dealer_id(principal: dict) -> UUID:
    if not principal["dealer_id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_dealer_scope")
    return UUID(principal["dealer_id"])


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(
    body: QuickAddLeadIn,
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> LeadOut:
    dealer_id = _dealer_id(principal)
    try:
        lead = await lead_service.create_lead(
            session,
            dealer_id=dealer_id,
            actor_user_id=UUID(principal["user_id"]),
            data=body,
        )
    except lead_service.NextActionRequired:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "next_action_required") from None
    except lead_service.BadFieldValue as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad_phone") from None
    return _out(lead)


@router.get("", response_model=list[LeadOut])
async def list_leads(
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
    stage: str | None = Query(None),
    owner: UUID | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[LeadOut]:
    _dealer_id(principal)
    rows = await lead_service.list_leads(
        session, stage=stage, owner_user_id=owner, source=source, limit=limit
    )
    return [_out(x) for x in rows]


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(
    lead_id: UUID,
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> LeadOut:
    lead = await lead_service.get(session, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return _out(lead)


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(
    lead_id: UUID,
    body: LeadUpdateIn,
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> LeadOut:
    lead = await lead_service.get(session, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    try:
        lead = await lead_service.update_lead(
            session, lead=lead, actor_user_id=UUID(principal["user_id"]), data=body
        )
    except lead_service.NextActionRequired:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "next_action_required") from None
    except lead_service.BadFieldValue as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return _out(lead)


@router.post("/{lead_id}/transition", response_model=LeadTransitionOut)
async def transition(
    lead_id: UUID,
    body: LeadTransitionIn,
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> LeadTransitionOut:
    lead = await lead_service.get(session, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    try:
        lead, ev = await lead_service.transition(
            session, lead=lead, actor_user_id=UUID(principal["user_id"]), data=body
        )
    except lead_service.InvalidTransition as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"invalid_transition:{e}") from None
    except lead_service.UnknownStage as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown_stage:{e}") from None
    except lead_service.LostReasonRequired:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "lost_reason_required") from None
    except lead_service.NextActionRequired:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "next_action_required") from None
    return LeadTransitionOut(lead=_out(lead), event=_event_out(ev))


@router.get("/{lead_id}/events", response_model=list[LeadEventOut])
async def list_events(
    lead_id: UUID,
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[LeadEventOut]:
    lead = await lead_service.get(session, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    events = await lead_service.list_events(session, lead_id)
    return [_event_out(x) for x in events]


@router.post("/{lead_id}/events", response_model=LeadEventOut, status_code=status.HTTP_201_CREATED)
async def add_event(
    lead_id: UUID,
    body: LeadEventCreateIn,
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> LeadEventOut:
    lead = await lead_service.get(session, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    try:
        ev = await lead_service.add_event(
            session,
            lead=lead,
            actor_user_id=UUID(principal["user_id"]),
            type_=body.type,
            payload=body.payload,
        )
    except lead_service.BadFieldValue as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return _event_out(ev)
