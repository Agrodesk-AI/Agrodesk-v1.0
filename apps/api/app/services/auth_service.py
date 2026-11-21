from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import OtpCode, User
from app.security.otp import generate_code, hash_code, verify_code
from app.security.phone import normalize_phone


class OtpRateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


class OtpInvalid(Exception):
    pass


async def request_otp(session: AsyncSession, raw_phone: str, send_sms) -> None:
    phone = normalize_phone(raw_phone, settings.default_phone_region)

    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    count = await session.scalar(
        select(func.count(OtpCode.id)).where(
            OtpCode.phone == phone, OtpCode.created_at >= one_hour_ago
        )
    )
    if (count or 0) >= settings.otp_max_per_hour:
        raise OtpRateLimited(retry_after=3600)

    code = generate_code()
    now = datetime.now(UTC)
    session.add(
        OtpCode(
            phone=phone,
            code_hash=hash_code(code),
            expires_at=now + timedelta(minutes=settings.otp_ttl_minutes),
            created_at=now,
        )
    )
    await session.flush()
    await send_sms(phone=phone, body=f"Agrodesk code: {code}. Valid {settings.otp_ttl_minutes}m.")


async def verify_otp(session: AsyncSession, raw_phone: str, code: str) -> User:
    phone = normalize_phone(raw_phone, settings.default_phone_region)
    now = datetime.now(UTC)

    row = await session.scalar(
        select(OtpCode)
        .where(OtpCode.phone == phone, OtpCode.used.is_(False))
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )
    if row is None or row.expires_at < now or row.attempts >= settings.otp_max_attempts:
        raise OtpInvalid("expired_or_missing")

    row.attempts += 1
    if not verify_code(code, row.code_hash):
        await session.flush()
        raise OtpInvalid("wrong_code")

    row.used = True

    # NOTE: this lookup must run with platform-admin context so RLS on users
    # doesn't hide the row before we know who's logging in.
    user = await session.scalar(select(User).where(User.phone == phone, User.active.is_(True)))
    if user is None:
        raise OtpInvalid("no_such_user")

    user.last_login_at = now
    await session.flush()
    return user
