from datetime import datetime
from uuid import UUID

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class FarmerConsent(UUIDPKMixin, Base):
    __tablename__ = "farmer_consents"

    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    text_version: Mapped[str] = mapped_column(String(20), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    text_shown: Mapped[str] = mapped_column(Text, nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class BuyingInterest(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "buying_interests"

    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False
    )
    consent_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("farmer_consents.id"), nullable=False
    )
    tehsil_id: Mapped[int] = mapped_column(Integer, ForeignKey("tehsils.id"), nullable=False)
    brand_hint: Mapped[str | None] = mapped_column(String(100))
    hp_min: Mapped[int | None] = mapped_column(SmallInteger)
    hp_max: Mapped[int | None] = mapped_column(SmallInteger)
    timeline: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="routing")
    candidate_dealer_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    reroute_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    current_dealer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    current_dealer_name: Mapped[str | None] = mapped_column(String(200))
    current_dealer_phone: Mapped[str | None] = mapped_column(String(20))


class LeadRoute(UUIDPKMixin, Base):
    __tablename__ = "lead_routes"

    interest_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("buying_interests.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    rank_reason: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sla_due_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
