from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.db import get_session_tenant
from app.models import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/v1", tags=["me"])


@router.get("/me", response_model=UserOut)
async def me(
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> UserOut:
    user = await session.scalar(select(User).where(User.id == principal["user_id"]))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return UserOut(
        id=user.id,
        dealer_id=user.dealer_id,
        name=user.name,
        phone=user.phone,
        role=user.role,
        active=user.active,
    )
