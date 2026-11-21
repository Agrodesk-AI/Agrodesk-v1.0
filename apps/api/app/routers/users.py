from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import require_role
from app.deps.db import get_session_tenant
from app.schemas.user import UserInviteIn, UserOut
from app.services import user_service

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def invite(
    body: UserInviteIn,
    principal: dict = Depends(require_role("owner", "platform_admin")),
    session: AsyncSession = Depends(get_session_tenant),
) -> UserOut:
    dealer_id = principal["dealer_id"]
    if dealer_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_dealer_scope")
    try:
        u = await user_service.invite_user(session, UUID(dealer_id), body)
    except user_service.RoleNotAllowed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "role_not_allowed") from None
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad_phone") from None
    return UserOut(
        id=u.id, dealer_id=u.dealer_id, name=u.name, phone=u.phone, role=u.role, active=u.active
    )


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: UUID,
    principal: dict = Depends(require_role("owner", "platform_admin")),
    session: AsyncSession = Depends(get_session_tenant),
) -> UserOut:
    u = await user_service.get_user(session, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return UserOut(
        id=u.id, dealer_id=u.dealer_id, name=u.name, phone=u.phone, role=u.role, active=u.active
    )


@router.delete("/{user_id}", response_model=UserOut)
async def deactivate(
    user_id: UUID,
    principal: dict = Depends(require_role("owner", "platform_admin")),
    session: AsyncSession = Depends(get_session_tenant),
) -> UserOut:
    u = await user_service.deactivate_user(session, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return UserOut(
        id=u.id, dealer_id=u.dealer_id, name=u.name, phone=u.phone, role=u.role, active=u.active
    )
