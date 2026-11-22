from datetime import datetime
from uuid import UUID

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


def _farmer():
    return mapped_column(
        PGUUID(as_uuid=True), ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False
    )


class Post(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "posts"

    farmer_id: Mapped[UUID] = _farmer()
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    tehsil_id: Mapped[int] = mapped_column(Integer, ForeignKey("tehsils.id"), nullable=False)
    village_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("villages.id"))
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="published")
    moderation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class PostReply(UUIDPKMixin, Base):
    __tablename__ = "post_replies"

    post_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    farmer_id: Mapped[UUID] = _farmer()
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="published")
    moderation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class PostHelpful(Base):
    __tablename__ = "post_helpful"

    post_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("farmers.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class ContentReport(UUIDPKMixin, Base):
    __tablename__ = "content_reports"

    target_type: Mapped[str] = mapped_column(String(10), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reporter_farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class ModerationItem(UUIDPKMixin, Base):
    __tablename__ = "moderation_queue"

    target_type: Mapped[str] = mapped_column(String(10), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    sla_due_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(10))
    decided_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
