from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.db import get_session_platform
from app.schemas.auth import OtpRequestIn, OtpRequestOut, OtpVerifyIn, RefreshIn, TokenPair
from app.security.jwt import create_access_token, create_refresh_token, decode_token
from app.services import auth_service
from packages.channels.sms import FakeSmsProvider

router = APIRouter(prefix="/v1/auth", tags=["auth"])

_sms = FakeSmsProvider()


@router.post("/otp/request", response_model=OtpRequestOut)
async def otp_request(
    body: OtpRequestIn,
    session: AsyncSession = Depends(get_session_platform),
) -> OtpRequestOut:
    try:
        await auth_service.request_otp(session, body.phone, _sms.send)
    except auth_service.OtpRateLimited as e:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "otp_rate_limited",
            headers={"Retry-After": str(e.retry_after)},
        ) from None
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad_phone") from None
    return OtpRequestOut()


@router.post("/otp/verify", response_model=TokenPair)
async def otp_verify(
    body: OtpVerifyIn,
    session: AsyncSession = Depends(get_session_platform),
) -> TokenPair:
    try:
        user = await auth_service.verify_otp(session, body.phone, body.code)
    except auth_service.OtpInvalid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_otp") from None
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad_phone") from None
    return TokenPair(
        access_token=create_access_token(
            str(user.id), user.role, str(user.dealer_id) if user.dealer_id else None
        ),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshIn,
    session: AsyncSession = Depends(get_session_platform),
) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_refresh") from None
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong_token_type")
    from sqlalchemy import select

    from app.models import User

    user = await session.scalar(select(User).where(User.id == payload["sub"], User.active.is_(True)))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no_such_user")
    return TokenPair(
        access_token=create_access_token(
            str(user.id), user.role, str(user.dealer_id) if user.dealer_id else None
        ),
        refresh_token=create_refresh_token(str(user.id)),
    )
