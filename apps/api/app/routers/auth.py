from fastapi import APIRouter, Depends, HTTPException, status
from packages.channels.sms import FakeSmsProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_principal
from app.deps.db import get_session_platform
from app.models import Account, Farmer, User
from app.schemas.auth import (
    OtpRequestIn,
    OtpRequestOut,
    OtpVerifyIn,
    Profile,
    RefreshIn,
    SwitchProfileIn,
    TokenPair,
)
from app.security.jwt import (
    KIND_ACCOUNT,
    KIND_FARMER,
    KIND_STAFF,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.services import auth_service

router = APIRouter(prefix="/v1/auth", tags=["auth"])

_sms = FakeSmsProvider()


def issue_tokens(account: Account, profile: Profile | None, profiles: list[Profile]) -> TokenPair:
    if profile is None:
        sub, role, dealer_id, kind = str(account.id), "account", None, KIND_ACCOUNT
    else:
        sub, role, dealer_id, kind = profile.id, profile.role, profile.dealer_id, profile.kind
    return TokenPair(
        access_token=create_access_token(
            sub, role, dealer_id, kind=kind, account_id=str(account.id)
        ),
        refresh_token=create_refresh_token(sub, kind=kind),
        active_kind=kind,
        active_profile_id=profile.id if profile else None,
        profiles=profiles,
    )


async def tokens_for_account(
    session: AsyncSession, account: Account, wanted_profile_id: str | None
) -> TokenPair:
    profiles = await auth_service.list_profiles(session, account)
    profile = auth_service.pick_profile(profiles, wanted_profile_id)
    if wanted_profile_id and profile is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "profile_not_owned")
    if profile is not None:
        await auth_service.mark_login(session, profile)
    return issue_tokens(account, profile, profiles)


async def account_for_principal(session: AsyncSession, principal: dict) -> Account | None:
    if principal.get("account_id"):
        return await session.get(Account, principal["account_id"])
    # Staff token minted before accounts existed: resolve via phone.
    user = await session.get(User, principal["user_id"])
    if user is None:
        return None
    return await auth_service.get_or_create_account(session, user.phone)


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
        account = await auth_service.verify_otp(session, body.phone, body.code)
    except auth_service.OtpInvalid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_otp") from None
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad_phone") from None
    return await tokens_for_account(session, account, body.profile_id)


@router.get("/profiles", response_model=list[Profile])
async def profiles(
    principal: dict = Depends(get_principal),
    session: AsyncSession = Depends(get_session_platform),
) -> list[Profile]:
    account = await account_for_principal(session, principal)
    if account is None or account.locked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no_such_account")
    return await auth_service.list_profiles(session, account)


@router.post("/switch-profile", response_model=TokenPair)
async def switch_profile(
    body: SwitchProfileIn,
    principal: dict = Depends(get_principal),
    session: AsyncSession = Depends(get_session_platform),
) -> TokenPair:
    account = await account_for_principal(session, principal)
    if account is None or account.locked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no_such_account")
    return await tokens_for_account(session, account, body.profile_id)


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

    kind = payload.get("kind") or KIND_STAFF
    sub = payload["sub"]
    account: Account | None = None
    if kind == KIND_STAFF:
        user = await session.scalar(select(User).where(User.id == sub, User.active.is_(True)))
        if user is not None:
            account = await auth_service.get_or_create_account(session, user.phone)
    elif kind == KIND_FARMER:
        farmer = await session.scalar(
            select(Farmer).where(Farmer.id == sub, Farmer.status == "active")
        )
        if farmer is not None:
            account = await session.get(Account, farmer.account_id)
    elif kind == KIND_ACCOUNT:
        account = await session.get(Account, sub)
    if account is None or account.locked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no_such_user")

    all_profiles = await auth_service.list_profiles(session, account)
    if kind == KIND_ACCOUNT:
        # Onboarded since the last refresh? Move them onto the new profile.
        return issue_tokens(account, auth_service.pick_profile(all_profiles, None), all_profiles)
    profile = auth_service.pick_profile(all_profiles, sub)
    if profile is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no_such_user")
    return issue_tokens(account, profile, all_profiles)
