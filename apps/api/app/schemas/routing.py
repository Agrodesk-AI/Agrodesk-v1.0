from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

Timeline = Literal["now", "1_3_months", "3_6_months", "later"]


class ConsentTextOut(BaseModel):
    version: str
    language: str
    text: str


class InterestCreateIn(BaseModel):
    brand_hint: str | None = Field(default=None, max_length=100)
    hp_min: int | None = Field(default=None, ge=10, le=150)
    hp_max: int | None = Field(default=None, ge=10, le=150)
    timeline: Timeline
    notes: str | None = Field(default=None, max_length=1000)
    # The farmer must have seen and accepted this exact version of the text.
    consent_granted: Literal[True]
    consent_version: str
    consent_language: str | None = None
    channel: Literal["app", "whatsapp"] = "app"

    @model_validator(mode="after")
    def _hp_order(self):
        if self.hp_min and self.hp_max and self.hp_min > self.hp_max:
            raise ValueError("hp_min must be <= hp_max")
        return self


class InterestOut(BaseModel):
    id: UUID
    status: str  # routing | assigned | waitlist | cancelled | closed
    brand_hint: str | None
    hp_min: int | None
    hp_max: int | None
    timeline: str
    notes: str | None
    reroute_count: int
    dealer_name: str | None
    dealer_phone: str | None
    created_at: datetime


class ServiceAreaIn(BaseModel):
    tehsil_id: int
    is_home: bool = False


class ServiceAreasIn(BaseModel):
    areas: list[ServiceAreaIn] = Field(max_length=50)

    @model_validator(mode="after")
    def _one_home(self):
        if self.areas and sum(a.is_home for a in self.areas) != 1:
            raise ValueError("exactly one home tehsil required")
        if len({a.tehsil_id for a in self.areas}) != len(self.areas):
            raise ValueError("duplicate tehsil")
        return self


class ServiceAreaOut(BaseModel):
    tehsil_id: int
    name_en: str
    is_home: bool


class DealerVerificationOut(BaseModel):
    dealer_id: UUID
    verified_at: datetime | None
