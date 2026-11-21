
from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models import OtpCode, User
from app.security.jwt import create_access_token
from app.security.phone import normalize_phone


async def make_dealer_and_owner(name: str, owner_phone: str, owner_name: str = "Owner"):
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        from app.schemas.dealer import DealerCreateIn
        from app.services.dealer_service import create_dealer_with_owner

        dealer, owner = await create_dealer_with_owner(
            s, DealerCreateIn(name=name, owner_name=owner_name, owner_phone=owner_phone)
        )
        return str(dealer.id), str(owner.id), owner.phone, owner.role


async def make_platform_admin(phone: str, name: str = "Admin"):
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        u = User(dealer_id=None, name=name, phone=normalize_phone(phone), role="platform_admin")
        s.add(u)
        await s.flush()
        return str(u.id), u.phone


def token_for(user_id: str, role: str, dealer_id: str | None) -> str:
    return create_access_token(user_id, role, dealer_id)


async def last_otp_for(phone: str) -> OtpCode | None:
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        return await s.scalar(
            select(OtpCode).where(OtpCode.phone == normalize_phone(phone))
            .order_by(OtpCode.created_at.desc()).limit(1)
        )
