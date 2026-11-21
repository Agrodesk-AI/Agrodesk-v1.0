from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CustomerCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str
    language: str = "mr"
    village: str | None = None
    farm_size_acres: Decimal | None = None
    crop: str | None = None
    notes: str | None = None
    consent_whatsapp: bool = False
    consent_call: bool = False


class CustomerUpdateIn(BaseModel):
    name: str | None = None
    language: str | None = None
    village: str | None = None
    farm_size_acres: Decimal | None = None
    crop: str | None = None
    notes: str | None = None
    consent_whatsapp: bool | None = None
    consent_call: bool | None = None


class CustomerOut(BaseModel):
    id: UUID
    dealer_id: UUID
    name: str
    phone: str
    language: str
    village: str | None
    farm_size_acres: Decimal | None
    crop: str | None
    notes: str | None
    consent_whatsapp: bool
    consent_call: bool
    opted_out_at: datetime | None
