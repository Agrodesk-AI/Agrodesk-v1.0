from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


def _farmer(nullable: bool = False):
    return mapped_column(
        PGUUID(as_uuid=True), ForeignKey("farmers.id", ondelete="CASCADE"), nullable=nullable
    )


class EquipmentListing(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "equipment_listings"

    owner_farmer_id: Mapped[UUID] = _farmer()
    owner_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tehsil_id: Mapped[int] = mapped_column(Integer, ForeignKey("tehsils.id"), nullable=False)
    village_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("villages.id"))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    hp: Mapped[int | None] = mapped_column(SmallInteger)
    rate_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_unit: Mapped[str] = mapped_column(String(10), nullable=False)
    operator_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fuel_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")


class RentalNeed(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "rental_needs"

    renter_farmer_id: Mapped[UUID] = _farmer()
    renter_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tehsil_id: Mapped[int] = mapped_column(Integer, ForeignKey("tehsils.id"), nullable=False)
    village_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("villages.id"))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    acreage: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    budget_paise: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")


class RentalBooking(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "rental_bookings"

    listing_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("equipment_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    need_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rental_needs.id", ondelete="SET NULL")
    )
    owner_farmer_id: Mapped[UUID] = _farmer()
    renter_farmer_id: Mapped[UUID] = _farmer()
    owner_name: Mapped[str] = mapped_column(String(200), nullable=False)
    renter_name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    note: Mapped[str | None] = mapped_column(Text)
    owner_completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    renter_completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    owner_shared_contact_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    renter_shared_contact_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    dispute_reason: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)


class RentalBookingEvent(UUIDPKMixin, Base):
    __tablename__ = "rental_booking_events"

    booking_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("rental_bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_farmer_id: Mapped[UUID] = _farmer()
    renter_farmer_id: Mapped[UUID] = _farmer()
    from_state: Mapped[str | None] = mapped_column(String(20))
    to_state: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_farmer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class RentalRating(UUIDPKMixin, Base):
    __tablename__ = "rental_ratings"

    booking_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("rental_bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_farmer_id: Mapped[UUID] = _farmer()
    to_farmer_id: Mapped[UUID] = _farmer()
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
