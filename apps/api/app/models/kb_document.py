from datetime import datetime
from uuid import UUID

from sqlalchemy import TIMESTAMP, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class KbDocument(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "kb_documents"

    dealer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dealers.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    source: Mapped[str | None] = mapped_column(String(400))
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    last_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
