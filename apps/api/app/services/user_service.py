from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.user import UserInviteIn
from app.security.phone import normalize_phone

ALLOWED_INVITE_ROLES = {"owner", "sales", "recovery", "service"}


class RoleNotAllowed(Exception):
    pass


async def invite_user(session: AsyncSession, dealer_id: UUID, data: UserInviteIn) -> User:
    if data.role not in ALLOWED_INVITE_ROLES:
        raise RoleNotAllowed(data.role)
    user = User(
        dealer_id=dealer_id,
        name=data.name,
        phone=normalize_phone(data.phone),
        role=data.role,
    )
    session.add(user)
    await session.flush()
    return user


async def deactivate_user(session: AsyncSession, user_id: UUID) -> User | None:
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        return None
    user.active = False
    await session.flush()
    return user


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.scalar(select(User).where(User.id == user_id))
