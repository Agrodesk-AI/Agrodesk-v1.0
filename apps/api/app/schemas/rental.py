from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

Kind = Literal[
    "tractor",
    "rotavator",
    "cultivator",
    "plough",
    "seed_drill",
    "harvester",
    "sprayer",
    "thresher",
    "trolley",
    "baler",
    "other",
]
RateUnit = Literal["hour", "day", "acre"]
Action = Literal["agree", "decline", "cancel", "start", "complete", "dispute"]

MAX_RENTAL_DAYS = 60


def _check_dates(start: date, end: date) -> None:
    if end < start:
        raise ValueError("end_date before start_date")
    if (end - start).days + 1 > MAX_RENTAL_DAYS:
        raise ValueError(f"max {MAX_RENTAL_DAYS} days")


class ListingIn(BaseModel):
    kind: Kind
    title: str = Field(min_length=2, max_length=120)
    hp: int | None = Field(default=None, ge=5, le=200)
    rate_paise: int = Field(gt=0, le=10_000_000)  # <= ₹1,00,000 per unit
    rate_unit: RateUnit
    operator_included: bool = False
    fuel_included: bool = False
    notes: str | None = Field(default=None, max_length=1000)


class ListingUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=120)
    hp: int | None = Field(default=None, ge=5, le=200)
    rate_paise: int | None = Field(default=None, gt=0, le=10_000_000)
    rate_unit: RateUnit | None = None
    operator_included: bool | None = None
    fuel_included: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)
    status: Literal["active", "paused", "removed"] | None = None


class ListingOut(BaseModel):
    id: UUID
    owner_farmer_id: UUID
    owner_name: str
    tehsil_id: int
    tehsil_name: str
    distance_rank: int | None = None  # 0 same tehsil, 1.. neighbour, 99 same district
    kind: str
    title: str
    hp: int | None
    rate_paise: int
    rate_unit: str
    operator_included: bool
    fuel_included: bool
    notes: str | None
    status: str
    owner_rating: float | None = None
    owner_rating_count: int = 0
    owner_badges: list[str] = []


class NeedIn(BaseModel):
    kind: Kind
    acreage: Decimal | None = Field(default=None, gt=0, le=10000)
    start_date: date
    end_date: date
    budget_paise: int | None = Field(default=None, gt=0, le=100_000_000)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _dates(self):
        _check_dates(self.start_date, self.end_date)
        return self


class NeedOut(BaseModel):
    id: UUID
    renter_farmer_id: UUID
    renter_name: str
    tehsil_id: int
    tehsil_name: str
    distance_rank: int | None = None
    kind: str
    acreage: Decimal | None
    start_date: date
    end_date: date
    budget_paise: int | None
    notes: str | None
    status: str
    created_at: datetime


class BookingIn(BaseModel):
    listing_id: UUID
    need_id: UUID | None = None
    start_date: date
    end_date: date
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _dates(self):
        _check_dates(self.start_date, self.end_date)
        return self


class TransitionIn(BaseModel):
    action: Action
    note: str | None = Field(default=None, max_length=1000)


class BookingOut(BaseModel):
    id: UUID
    listing_id: UUID
    listing_title: str
    kind: str
    need_id: UUID | None
    my_role: Literal["owner", "renter"]
    owner_name: str
    renter_name: str
    start_date: date
    end_date: date
    state: str
    note: str | None
    owner_completed: bool
    renter_completed: bool
    i_shared_contact: bool
    they_shared_contact: bool
    i_rated: bool
    dispute_reason: str | None
    allowed_actions: list[str]
    other_badges: list[str] = []
    created_at: datetime


class BookingEventOut(BaseModel):
    from_state: str | None
    to_state: str
    action: str
    by: Literal["owner", "renter", "admin"]
    note: str | None
    at: datetime


class ContactOut(BaseModel):
    name: str
    phone: str


class RatingIn(BaseModel):
    score: int = Field(ge=1, le=5)
    text: str | None = Field(default=None, max_length=500)


class ResolveIn(BaseModel):
    resolution: str = Field(min_length=3, max_length=2000)
