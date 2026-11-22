from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class DealerModel(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "dealer_models"
    __table_args__ = (
        UniqueConstraint("dealer_id", "catalogue_id", name="dealer_models_tenant_cat_key"),
    )

    dealer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False
    )
    catalogue_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tractor_catalogue.id", ondelete="CASCADE"),
        nullable=False,
    )
    price_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    offers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    valid_till: Mapped[date | None] = mapped_column(Date)
