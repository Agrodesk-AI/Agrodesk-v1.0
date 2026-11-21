from datetime import date, datetime
from uuid import UUID

from sqlalchemy import TIMESTAMP, Date, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class JobRun(UUIDPKMixin, Base):
    __tablename__ = "job_runs"

    job_name: Mapped[str] = mapped_column(String(100), nullable=False)
    logical_date: Mapped[date] = mapped_column(Date, nullable=False)
    scope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    payload: Mapped[dict | None] = mapped_column(JSONB)
