from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_farmer, get_principal
from app.deps.db import get_session_platform, get_session_tenant
from app.models import Account, Farmer
from app.routers.auth import account_for_principal, tokens_for_account
from app.schemas.auth import TokenPair
from app.schemas.farmer import FarmerOnboardIn, FarmerOut, FarmerUpdateIn
from app.services import farmer_service

router = APIRouter(prefix="/v1/farmer", tags=["farmer"])


def _raise(e: farmer_service.FarmerError):
    raise HTTPException(e.status, e.code) from None


@router.post("/onboard", response_model=TokenPair, status_code=201)
async def onboard(
    body: FarmerOnboardIn,
    principal: dict = Depends(get_principal),
    session: AsyncSession = Depends(get_session_platform),
) -> TokenPair:
    """Any phone-verified account (new, or a dealer staff who also farms) can add a
    farmer profile once. Returns tokens already switched to the farmer profile."""
    account = await account_for_principal(session, principal)
    if account is None:
        raise HTTPException(401, "no_such_account")
    try:
        farmer = await farmer_service.onboard(session, account.id, body)
    except farmer_service.FarmerError as e:
        _raise(e)
    return await tokens_for_account(session, account, str(farmer.id))


async def _me(session: AsyncSession, principal: dict) -> tuple[Farmer, Account]:
    # RLS limits both reads to the caller's own rows.
    farmer = await session.scalar(select(Farmer).where(Farmer.id == principal["farmer_id"]))
    account = await session.get(Account, principal["account_id"]) if farmer else None
    if farmer is None or account is None:
        raise HTTPException(404, "not_found")
    return farmer, account


@router.get("/me", response_model=FarmerOut)
async def get_me(
    principal: dict = Depends(get_current_farmer),
    session: AsyncSession = Depends(get_session_tenant),
) -> FarmerOut:
    farmer, account = await _me(session, principal)
    return await farmer_service.to_out(session, farmer, account.phone, farmer.language)


@router.patch("/me", response_model=FarmerOut)
async def patch_me(
    body: FarmerUpdateIn,
    principal: dict = Depends(get_current_farmer),
    session: AsyncSession = Depends(get_session_tenant),
) -> FarmerOut:
    farmer, account = await _me(session, principal)
    try:
        await farmer_service.update(session, farmer, body)
    except farmer_service.FarmerError as e:
        _raise(e)
    return await farmer_service.to_out(session, farmer, account.phone, farmer.language)
