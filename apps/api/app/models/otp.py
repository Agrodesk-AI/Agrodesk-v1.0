from datetime import datetime

from sqlalchemy import TIMESTAMP, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class OtpCode(UUIDPKMixin, Base):
    __tablename__ = "otp_codes"

    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
