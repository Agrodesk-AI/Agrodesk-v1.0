from uuid import UUID

from pydantic import BaseModel


class UserOut(BaseModel):
    id: UUID
    dealer_id: UUID | None
    name: str
    phone: str
    role: str
    active: bool


class UserInviteIn(BaseModel):
    name: str
    phone: str
    role: str  # sales | recovery | service | owner
