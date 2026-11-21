from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class QuickAddLeadIn(BaseModel):
    # Customer side
    name: str = Field(min_length=1, max_length=200)
    phone: str
    language: str = "mr"
    # Lead side
    source: str  # facebook|walk_in|referral|oem|other
    model_interest: str | None = None
    next_action_at: datetime
    owner_user_id: UUID | None = None  # defaults to caller
    campaign: str | None = None
    ad_name: str | None = None
    referrer_customer_id: UUID | None = None
    score: str | None = None  # hot|warm|dead


class LeadUpdateIn(BaseModel):
    model_interest: str | None = None
    owner_user_id: UUID | None = None
    next_action_at: datetime | None = None
    score: str | None = None
    campaign: str | None = None
    ad_name: str | None = None


class LeadTransitionIn(BaseModel):
    to_stage: str
    lost_reason: str | None = None
    notes: str | None = None
    next_action_at: datetime | None = None


class LeadOut(BaseModel):
    id: UUID
    dealer_id: UUID
    customer_id: UUID
    source: str
    referrer_customer_id: UUID | None
    model_interest: str | None
    stage: str
    score: str | None
    owner_user_id: UUID | None
    next_action_at: datetime | None
    lost_reason: str | None
    won_at: datetime | None
    campaign: str | None
    ad_name: str | None
    created_via: str
    created_at: datetime


class LeadEventOut(BaseModel):
    id: UUID
    lead_id: UUID
    type: str
    payload: dict
    actor_type: str
    actor_id: UUID | None
    occurred_at: datetime


class LeadEventCreateIn(BaseModel):
    type: str  # one of EVENT_TYPES (except stage_changed which goes through /transition)
    payload: dict = {}


class LeadTransitionOut(BaseModel):
    lead: LeadOut
    event: LeadEventOut
