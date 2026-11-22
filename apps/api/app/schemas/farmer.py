from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.location import PlaceOut

# English + the major Indian languages we plan to serve. Content catalogs may lag;
# the UI falls back to English (or Hindi) when a language has no translations yet.
SUPPORTED_LANGUAGES = frozenset(
    {"en", "hi", "mr", "gu", "pa", "bn", "ta", "te", "kn", "ml", "or", "as", "ur"}
)
MIN_AGE_YEARS = 18


def _check_lang(v: str) -> str:
    v = v.lower()
    if v not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported language {v}")
    return v


class FarmerOnboardIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    language: str
    tehsil_id: int
    village_id: int | None = None
    dob: date

    _lang = field_validator("language")(_check_lang)


class FarmerUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    language: str | None = None
    tehsil_id: int | None = None
    village_id: int | None = None

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str | None) -> str | None:
        return None if v is None else _check_lang(v)


class FarmerOut(BaseModel):
    id: UUID
    display_name: str
    language: str
    phone: str
    status: str
    state: PlaceOut
    district: PlaceOut
    tehsil: PlaceOut
    village: PlaceOut | None
