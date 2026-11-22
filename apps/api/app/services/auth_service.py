from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Account, Farmer, OtpCode, User
from app.schemas.auth import Profile
from app.security.jwt import KIND_FARMER, KIND_STAFF
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


async def get_or_create_account(session: AsyncSession, phone: str) -> Account:
    acct = await session.scalar(select(Account).where(Account.phone == phone))
    if acct is None:
        acct = Account(phone=phone)
        session.add(acct)
        await session.flush()
    return acct


async def list_profiles(session: AsyncSession, account: Account) -> list[Profile]:
    """All active profiles for an account. Needs platform-admin context."""
    profiles: list[Profile] = []
    user = await session.scalar(
        select(User).where(User.phone == account.phone, User.active.is_(True))
    )
    if user is not None:
        if user.account_id is None:
            user.account_id = account.id  # lazy link for users created outside accounts
        profiles.append(
            Profile(
                id=str(user.id),
                kind=KIND_STAFF,
                role=user.role,
                dealer_id=str(user.dealer_id) if user.dealer_id else None,
                display_name=user.name,
            )
        )
    farmer = await session.scalar(
        select(Farmer).where(Farmer.account_id == account.id, Farmer.status == "active")
    )
    if farmer is not None:
        profiles.append(
            Profile(
                id=str(farmer.id),
                kind=KIND_FARMER,
                role="farmer",
                dealer_id=None,
                display_name=farmer.display_name,
            )
        )
    return profiles


def pick_profile(profiles: list[Profile], wanted_id: str | None) -> Profile | None:
    if wanted_id:
        return next((p for p in profiles if p.id == wanted_id), None)
    # Staff first keeps v1 dealer logins unchanged; farmer otherwise.
    for kind in (KIND_STAFF, KIND_FARMER):
        for p in profiles:
            if p.kind == kind:
                return p
    return None


async def mark_login(session: AsyncSession, profile: Profile) -> None:
    model = User if profile.kind == KIND_STAFF else Farmer
    obj = await session.get(model, profile.id)
    if obj is not None:
        obj.last_login_at = datetime.now(UTC)
        await session.flush()


async def verify_otp(session: AsyncSession, raw_phone: str, code: str) -> Account:
    """Check the code and return the phone's account, creating it on first login.
    An account with no profile can only onboard (see farmer router)."""
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

    # NOTE: runs with platform-admin context so RLS doesn't hide rows before we
    # know who's logging in.
    account = await get_or_create_account(session, phone)
    if account.locked:
        raise OtpInvalid("locked")
    await session.flush()
    return account
