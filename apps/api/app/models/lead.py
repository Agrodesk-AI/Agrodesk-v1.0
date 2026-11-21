from datetime import datetime
from uuid import UUID

from sqlalchemy import TIMESTAMP, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Lead(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "leads"

    dealer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    referrer_customer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL")
    )
    model_interest: Mapped[str | None] = mapped_column(String(200))
    stage: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    score: Mapped[str | None] = mapped_column(String(10))
    owner_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    next_action_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    lost_reason: Mapped[str | None] = mapped_column(Text)
    won_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    campaign: Mapped[str | None] = mapped_column(String(200))
    ad_name: Mapped[str | None] = mapped_column(String(200))
    created_via: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
