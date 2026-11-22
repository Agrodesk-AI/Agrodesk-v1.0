from datetime import date, datetime

from sqlalchemy import TIMESTAMP, Boolean, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Account(UUIDPKMixin, TimestampMixin, Base):
    """One per phone. Profiles (users = dealer/admin, farmers) hang off it."""

    __tablename__ = "accounts"

    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    dob: Mapped[date | None] = mapped_column(Date)
    age_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
