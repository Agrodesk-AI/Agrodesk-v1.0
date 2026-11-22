"""Lead routing endpoints: farmer buying interests, dealer service areas, admin verification."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_farmer, require_role
from app.deps.db import get_session_platform, get_session_tenant
from app.models import BuyingInterest, Dealer, DealerServiceArea, Tehsil
from app.schemas.routing import (
    ConsentTextOut,
    DealerVerificationOut,
    InterestCreateIn,
    InterestOut,
    ServiceAreaOut,
    ServiceAreasIn,
)
from app.services import routing_service

farmer_router = APIRouter(prefix="/v1/farmer/interests", tags=["farmer"])
dealer_router = APIRouter(prefix="/v1/dealer", tags=["dealer"])
admin_router = APIRouter(prefix="/v1/admin/dealers", tags=["admin"])


def _out(i: BuyingInterest) -> InterestOut:
    return InterestOut(
        id=i.id,
        status=i.status,
        brand_hint=i.brand_hint,
        hp_min=i.hp_min,
        hp_max=i.hp_max,
        timeline=i.timeline,
        notes=i.notes,
        reroute_count=i.reroute_count,
        dealer_name=i.current_dealer_name,
        dealer_phone=i.current_dealer_phone,
        created_at=i.created_at,
    )


def _raise(e: routing_service.RoutingError):
    raise HTTPException(e.status, e.code) from None


# ---------------- farmer ----------------


@farmer_router.get("/consent-text", response_model=ConsentTextOut)
async def consent_text(
    lang: str = Query(default="en", max_length=10),
    _: dict = Depends(get_current_farmer),
) -> ConsentTextOut:
    used, text = routing_service.consent_text(lang)
    return ConsentTextOut(version=routing_service.CONSENT_VERSION, language=used, text=text)


@farmer_router.post("", response_model=InterestOut, status_code=201)
async def create_interest(
    body: InterestCreateIn,
    principal: dict = Depends(get_current_farmer),
    session: AsyncSession = Depends(get_session_platform),
) -> InterestOut:
    try:
        interest = await routing_service.create_interest(
            session, farmer_id=UUID(principal["farmer_id"]), data=body
        )
    except routing_service.RoutingError as e:
        _raise(e)
    await session.refresh(interest)
    return _out(interest)


@farmer_router.get("", response_model=list[InterestOut])
async def list_interests(
    principal: dict = Depends(get_current_farmer),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[InterestOut]:
    rows = await session.scalars(
        select(BuyingInterest).order_by(BuyingInterest.created_at.desc()).limit(50)
    )  # RLS: own rows only
    return [_out(i) for i in rows]


@farmer_router.post("/{interest_id}/cancel", response_model=InterestOut)
async def cancel_interest(
    interest_id: UUID,
    principal: dict = Depends(get_current_farmer),
    session: AsyncSession = Depends(get_session_platform),
) -> InterestOut:
    try:
        interest = await routing_service.cancel_interest(
            session, farmer_id=UUID(principal["farmer_id"]), interest_id=interest_id
        )
    except routing_service.RoutingError as e:
        _raise(e)
    await session.refresh(interest)
    return _out(interest)


# ---------------- dealer ----------------


async def _areas_out(session: AsyncSession, dealer_id) -> list[ServiceAreaOut]:
    rows = (
        await session.execute(
            select(DealerServiceArea, Tehsil)
            .join(Tehsil, Tehsil.id == DealerServiceArea.tehsil_id)
            .where(DealerServiceArea.dealer_id == dealer_id)
            .order_by(DealerServiceArea.is_home.desc(), Tehsil.name_en)
        )
    ).all()
    return [ServiceAreaOut(tehsil_id=t.id, name_en=t.name_en, is_home=a.is_home) for a, t in rows]


@dealer_router.get("/service-areas", response_model=list[ServiceAreaOut])
async def get_service_areas(
    principal: dict = Depends(require_role("owner", "sales", "recovery", "service")),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[ServiceAreaOut]:
    return await _areas_out(session, principal["dealer_id"])


@dealer_router.put("/service-areas", response_model=list[ServiceAreaOut])
async def put_service_areas(
    body: ServiceAreasIn,
    principal: dict = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[ServiceAreaOut]:
    ids = {a.tehsil_id for a in body.areas}
    found = set((await session.scalars(select(Tehsil.id).where(Tehsil.id.in_(ids)))).all())
    if found != ids:
        raise HTTPException(422, f"unknown_tehsils:{sorted(ids - found)}")
    dealer_id = principal["dealer_id"]
    await session.execute(delete(DealerServiceArea).where(DealerServiceArea.dealer_id == dealer_id))
    for a in body.areas:
        session.add(
            DealerServiceArea(dealer_id=dealer_id, tehsil_id=a.tehsil_id, is_home=a.is_home)
        )
    await session.flush()
    return await _areas_out(session, dealer_id)


# ---------------- admin ----------------


@admin_router.post("/{dealer_id}/verify", response_model=DealerVerificationOut)
async def verify_dealer(
    dealer_id: UUID,
    principal: dict = Depends(require_role("platform_admin")),
    session: AsyncSession = Depends(get_session_tenant),
) -> DealerVerificationOut:
    dealer = await session.get(Dealer, dealer_id)
    if dealer is None:
        raise HTTPException(404, "not_found")
    dealer.verified_at = datetime.now(UTC)
    dealer.verified_by = UUID(principal["user_id"])
    await session.flush()
    return DealerVerificationOut(dealer_id=dealer.id, verified_at=dealer.verified_at)


@admin_router.post("/{dealer_id}/unverify", response_model=DealerVerificationOut)
async def unverify_dealer(
    dealer_id: UUID,
    _: dict = Depends(require_role("platform_admin")),
    session: AsyncSession = Depends(get_session_tenant),
) -> DealerVerificationOut:
    dealer = await session.get(Dealer, dealer_id)
    if dealer is None:
        raise HTTPException(404, "not_found")
    dealer.verified_at = None
    dealer.verified_by = None
    await session.flush()
    return DealerVerificationOut(dealer_id=dealer.id, verified_at=None)
