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
    outcome: str  # e.g. not_picked | interested | visit_planned | price_issue | not_interested
    notes: str | None = None
