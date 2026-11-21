from sqlalchemy import String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Dealer(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "dealers"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brands: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    city: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    default_language: Mapped[str] = mapped_column(String(10), nullable=False, default="mr")
    whatsapp_number: Mapped[str | None] = mapped_column(String(20))
    business_hours: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
