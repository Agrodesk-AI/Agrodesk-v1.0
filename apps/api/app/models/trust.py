from datetime import datetime
from uuid import UUID

from sqlalchemy import TIMESTAMP, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class FarmerBadge(UUIDPKMixin, Base):
    __tablename__ = "farmer_badges"

    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False
    )
    badge: Mapped[str] = mapped_column(String(30), nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    awarded_by: Mapped[str] = mapped_column(String(60), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(60))
    revoke_reason: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class TrustFlag(UUIDPKMixin, Base):
    __tablename__ = "trust_flags"

    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    farmer_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    note: Mapped[str | None] = mapped_column(Text)
    closed_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
