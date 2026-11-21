from datetime import datetime
from uuid import UUID

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    dealer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dealers.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
