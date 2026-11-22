"""Trust: my badges + progress (self only), admin flags / revoke / recompute."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_farmer, require_role
from app.deps.db import get_session_platform
from app.models import TrustFlag
from app.services import trust_service

router = APIRouter(prefix="/v1/farmer/trust", tags=["farmer"])
admin_router = APIRouter(prefix="/v1/admin/trust", tags=["admin"])

Badge = Literal["trusted_renter", "helpful_neighbour"]


class MyTrustOut(BaseModel):
    badges: list[str]
    # Numbers are shown only to the farmer themself (badges, not scores, publicly).
    progress: dict
    rating_avg: float | None
    rating_count: int


class FlagOut(BaseModel):
    id: UUID
    kind: str
    farmer_ids: list[UUID]
    detail: dict
    status: str
    note: str | None
    created_at: datetime


class CloseIn(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


class RevokeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.get("", response_model=MyTrustOut)
async def my_trust(
    p: dict = Depends(get_current_farmer),
    # platform ctx: badge writes are system-only; scoped to the caller's own farmer id
    s: AsyncSession = Depends(get_session_platform),
) -> MyTrustOut:
    fid = UUID(p["farmer_id"])
    # Self-view is always fresh, so progress and badges never disagree.
    await trust_service.recompute(s, fid)
    sig = await trust_service.signals(s, fid)
    badges = (await trust_service.badges_for(s, {fid})).get(fid, [])
    return MyTrustOut(
        badges=badges,
        progress=trust_service.progress(sig),
        rating_avg=sig["rating_avg"],
        rating_count=sig["rating_count"],
    )


@admin_router.get("/flags", response_model=list[FlagOut])
async def flags(
    status: Literal["open", "closed"] = "open",
    _: dict = Depends(require_role("platform_admin")),
    s: AsyncSession = Depends(get_session_platform),
) -> list[FlagOut]:
    rows = (
        await s.scalars(
            select(TrustFlag)
            .where(TrustFlag.status == status)
            .order_by(TrustFlag.created_at.desc())
            .limit(200)
        )
    ).all()
    return [
        FlagOut(
            id=f.id,
            kind=f.kind,
            farmer_ids=f.farmer_ids,
            detail=f.detail,
            status=f.status,
            note=f.note,
            created_at=f.created_at,
        )
        for f in rows
    ]


@admin_router.post("/flags/{flag_id}/close", response_model=FlagOut)
async def close_flag(
    flag_id: UUID,
    body: CloseIn,
    p: dict = Depends(require_role("platform_admin")),
    s: AsyncSession = Depends(get_session_platform),
) -> FlagOut:
    f = await s.get(TrustFlag, flag_id)
    if f is None:
        raise HTTPException(404, "not_found")
    if f.status != "open":
        raise HTTPException(409, "already_closed")
    f.status, f.note = "closed", body.note
    f.closed_by, f.closed_at = UUID(p["user_id"]), datetime.now(UTC)
    await s.flush()
    return FlagOut(
        id=f.id,
        kind=f.kind,
        farmer_ids=f.farmer_ids,
        detail=f.detail,
        status=f.status,
        note=f.note,
        created_at=f.created_at,
    )


@admin_router.post("/farmers/{farmer_id}/badges/{badge}/revoke", status_code=204)
async def revoke(
    farmer_id: UUID,
    badge: Badge,
    body: RevokeIn,
    p: dict = Depends(require_role("platform_admin")),
    s: AsyncSession = Depends(get_session_platform),
) -> None:
    if not await trust_service.admin_revoke(s, UUID(p["user_id"]), farmer_id, badge, body.reason):
        raise HTTPException(404, "no_live_badge")


@admin_router.post("/recompute")
async def recompute_now(_: dict = Depends(require_role("platform_admin"))) -> dict:
    return await trust_service.recompute_all()
