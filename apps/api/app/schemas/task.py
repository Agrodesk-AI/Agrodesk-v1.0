from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TaskOut(BaseModel):
    id: UUID
    dealer_id: UUID
    lead_id: UUID | None
    user_id: UUID
    due_at: datetime
    type: str
    status: str
    outcome: str | None
    completed_at: datetime | None


class TaskOutcomeIn(BaseModel):
    outcome: str
    notes: str | None = None
    next_action_at: datetime | None = None  # optional reschedule (overrides the suggestion)


class SuggestOut(BaseModel):
    outcome: str
    next_action_at: datetime | None
