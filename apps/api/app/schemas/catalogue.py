from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class CatalogueRowOut(BaseModel):
    catalogue_id: UUID
    brand: str
    model: str
    hp: int | None
    specs: dict
    price_min: float | None
    price_max: float | None
    offers: dict
    valid_till: str | None
    overlay_expired: bool


class DealerOverlayIn(BaseModel):
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    offers: dict = {}
    valid_till: date | None = None
