from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.db import get_session_tenant
from app.schemas.customer import CustomerCreateIn, CustomerOut, CustomerUpdateIn
from app.services import customer_service

router = APIRouter(prefix="/v1/customers", tags=["customers"])


def _out(c) -> CustomerOut:
    return CustomerOut(
        id=c.id,
        dealer_id=c.dealer_id,
        name=c.name,
        phone=c.phone,
        language=c.language,
        village=c.village,
        farm_size_acres=c.farm_size_acres,
        crop=c.crop,
        notes=c.notes,
        consent_whatsapp=c.consent_whatsapp,
        consent_call=c.consent_call,
        opted_out_at=c.opted_out_at,
    )


@router.post("", response_model=CustomerOut)
async def create_or_get(
    body: CustomerCreateIn,
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> CustomerOut:
    dealer_id = principal["dealer_id"]
    if not dealer_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_dealer_scope")
    try:
        cust, _ = await customer_service.create_or_get_by_phone(session, UUID(dealer_id), body)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad_phone") from None
    return _out(cust)


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: UUID,
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> CustomerOut:
    cust = await customer_service.get(session, customer_id)
    if cust is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return _out(cust)


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: UUID,
    body: CustomerUpdateIn,
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> CustomerOut:
    cust = await customer_service.get(session, customer_id)
    if cust is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    cust = await customer_service.update(session, cust, body)
    return _out(cust)


@router.post("/{customer_id}/opt-out", response_model=CustomerOut)
async def opt_out(
    customer_id: UUID,
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> CustomerOut:
    cust = await customer_service.get(session, customer_id)
    if cust is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    cust = await customer_service.opt_out(session, cust)
    return _out(cust)
