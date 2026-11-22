"""Location lookups (public reference data, any signed-in token incl. onboarding)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_principal, require_role
from app.deps.db import get_session_tenant
from app.models import Tehsil
from app.schemas.location import NearbyTehsilOut, NeighboursIn, PlaceOut
from app.services import location_service

router = APIRouter(prefix="/v1/locations", tags=["locations"])
admin_router = APIRouter(prefix="/v1/admin/locations", tags=["admin"])

Lang = Query(default="en", max_length=10)


def _out(items, lang: str) -> list[PlaceOut]:
    return [PlaceOut(id=p.id, name=p.name_in(lang), name_en=p.name_en) for p in items]


@router.get("/states", response_model=list[PlaceOut])
async def states(
    lang: str = Lang,
    _: dict = Depends(get_principal),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[PlaceOut]:
    return _out(await location_service.list_states(session), lang)


@router.get("/states/{state_id}/districts", response_model=list[PlaceOut])
async def districts(
    state_id: int,
    lang: str = Lang,
    _: dict = Depends(get_principal),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[PlaceOut]:
    return _out(await location_service.list_districts(session, state_id), lang)


@router.get("/districts/{district_id}/tehsils", response_model=list[PlaceOut])
async def tehsils(
    district_id: int,
    lang: str = Lang,
    _: dict = Depends(get_principal),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[PlaceOut]:
    return _out(await location_service.list_tehsils(session, district_id), lang)


@router.get("/villages", response_model=list[PlaceOut])
async def villages(
    q: str | None = Query(default=None, max_length=100),
    tehsil_id: int | None = None,
    district_id: int | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    lang: str = Lang,
    _: dict = Depends(get_principal),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[PlaceOut]:
    # ~6 lakh villages nationally: always scope to a tehsil or district.
    if tehsil_id is None and district_id is None:
        raise HTTPException(422, "tehsil_or_district_required")
    rows = await location_service.search_villages(
        session, q=q, tehsil_id=tehsil_id, district_id=district_id, limit=limit
    )
    return _out(rows, lang)


@router.get("/tehsils/{tehsil_id}/nearby", response_model=list[NearbyTehsilOut])
async def nearby(
    tehsil_id: int,
    lang: str = Lang,
    _: dict = Depends(get_principal),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[NearbyTehsilOut]:
    rows = await location_service.nearby_tehsils(session, tehsil_id)
    if not rows:
        raise HTTPException(404, "not_found")
    return [
        NearbyTehsilOut(id=t.id, name=t.name_in(lang), name_en=t.name_en, rank=r) for t, r in rows
    ]


@admin_router.put("/tehsils/{tehsil_id}/neighbours", response_model=list[NearbyTehsilOut])
async def set_neighbours(
    tehsil_id: int,
    body: NeighboursIn,
    _: dict = Depends(require_role("platform_admin")),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[NearbyTehsilOut]:
    ids = {tehsil_id} | {n.tehsil_id for n in body.neighbours}
    found = set((await session.scalars(select(Tehsil.id).where(Tehsil.id.in_(ids)))).all())
    if found != ids:
        raise HTTPException(422, f"unknown_tehsils:{sorted(ids - found)}")
    await location_service.set_neighbours(
        session, tehsil_id, [(n.tehsil_id, n.rank) for n in body.neighbours]
    )
    rows = await location_service.nearby_tehsils(session, tehsil_id)
    return [NearbyTehsilOut(id=t.id, name=t.name_en, name_en=t.name_en, rank=r) for t, r in rows]
