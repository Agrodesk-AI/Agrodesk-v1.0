from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user, require_role
from app.deps.db import get_session_tenant
from app.schemas.catalogue import CatalogueRowOut, DealerOverlayIn
from app.services import catalogue_service

router = APIRouter(prefix="/v1/catalogue", tags=["catalogue"])


@router.get("", response_model=list[CatalogueRowOut])
async def list_catalogue(
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[CatalogueRowOut]:
    if not principal["dealer_id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_dealer_scope")
    rows = await catalogue_service.list_for_dealer(session, UUID(principal["dealer_id"]))
    return [CatalogueRowOut(**r) for r in rows]


@router.post("/{catalogue_id}/dealer-prices", response_model=CatalogueRowOut)
async def set_overlay(
    catalogue_id: UUID,
    body: DealerOverlayIn,
    principal: dict = Depends(require_role("owner", "platform_admin")),
    session: AsyncSession = Depends(get_session_tenant),
) -> CatalogueRowOut:
    if not principal["dealer_id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_dealer_scope")
    await catalogue_service.upsert_dealer_overlay(
        session,
        dealer_id=UUID(principal["dealer_id"]),
        catalogue_id=catalogue_id,
        price_min=body.price_min, price_max=body.price_max,
        offers=body.offers, valid_till=body.valid_till,
    )
    rows = await catalogue_service.list_for_dealer(session, UUID(principal["dealer_id"]))
    match = next((r for r in rows if r["catalogue_id"] == str(catalogue_id)), None)
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "catalogue_not_found")
    return CatalogueRowOut(**match)
