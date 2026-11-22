from datetime import datetime

from sqlalchemy import TIMESTAMP, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class TractorCatalogue(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "tractor_catalogue"
    __table_args__ = (
        UniqueConstraint("brand", "model", name="tractor_catalogue_brand_model_key"),
    )

    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    hp: Mapped[int | None] = mapped_column(Integer)
    specs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source: Mapped[str | None] = mapped_column(String(200))
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
