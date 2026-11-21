from uuid import UUID

from pydantic import BaseModel


class DealerCreateIn(BaseModel):
    name: str
    brands: list[str] = []
    city: str | None = None
    district: str | None = None
    state: str | None = None
    default_language: str = "mr"
    whatsapp_number: str | None = None
    owner_name: str
    owner_phone: str


class DealerOut(BaseModel):
    id: UUID
    name: str
    brands: list[str]
    city: str | None
    district: str | None
    state: str | None
    default_language: str
    status: str


class DealerWithOwner(BaseModel):
    dealer: DealerOut
    owner_id: UUID
