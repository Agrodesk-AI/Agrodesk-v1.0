"""Rental exchange endpoints (farmer-only, plus admin dispute resolution)."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_farmer, require_role
from app.deps.db import get_session_platform, get_session_tenant
from app.models import EquipmentListing, RentalNeed
from app.schemas.rental import (
    BookingEventOut,
    BookingIn,
    BookingOut,
    ContactOut,
    Kind,
    ListingIn,
    ListingOut,
    ListingUpdateIn,
    NeedIn,
    NeedOut,
    RatingIn,
    ResolveIn,
    TransitionIn,
)
from app.services import rental_service as svc

router = APIRouter(prefix="/v1/rentals", tags=["rentals"])
admin_router = APIRouter(prefix="/v1/admin/rentals", tags=["admin"])


def _me(principal: dict) -> UUID:
    return UUID(principal["farmer_id"])


def _err(e: svc.RentalError):
    raise HTTPException(e.status, e.code) from None


# ---------------- listings ----------------


@router.post("/listings", response_model=ListingOut, status_code=201)
async def create_listing(
    body: ListingIn,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> ListingOut:
    try:
        row = await svc.create_listing(s, _me(p), body)
    except svc.RentalError as e:
        _err(e)
    return (await svc.listings_out(s, [row]))[0]


@router.get("/listings/mine", response_model=list[ListingOut])
async def my_listings(
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> list[ListingOut]:
    rows = (
        await s.scalars(
            select(EquipmentListing)
            .where(EquipmentListing.owner_farmer_id == _me(p), EquipmentListing.status != "removed")
            .order_by(EquipmentListing.created_at.desc())
        )
    ).all()
    return await svc.listings_out(s, list(rows))


@router.patch("/listings/{listing_id}", response_model=ListingOut)
async def update_listing(
    listing_id: UUID,
    body: ListingUpdateIn,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> ListingOut:
    try:
        row = await svc.update_listing(s, _me(p), listing_id, body)
    except svc.RentalError as e:
        _err(e)
    return (await svc.listings_out(s, [row]))[0]


@router.get("/listings", response_model=list[ListingOut])
async def browse(
    kind: Kind | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> list[ListingOut]:
    if (start_date is None) != (end_date is None) or (
        start_date and end_date and end_date < start_date
    ):
        raise HTTPException(422, "bad_dates")
    try:
        rows, ranks = await svc.browse_listings(
            s, _me(p), kind=kind, start=start_date, end=end_date
        )
    except svc.RentalError as e:
        _err(e)
    return await svc.listings_out(s, rows, ranks)


# ---------------- needs ----------------


@router.post("/needs", response_model=NeedOut, status_code=201)
async def create_need(
    body: NeedIn,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> NeedOut:
    try:
        row = await svc.create_need(s, _me(p), body)
    except svc.RentalError as e:
        _err(e)
    return (await svc.needs_out(s, [row]))[0]


@router.get("/needs/mine", response_model=list[NeedOut])
async def my_needs(
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> list[NeedOut]:
    rows = (
        await s.scalars(
            select(RentalNeed)
            .where(RentalNeed.renter_farmer_id == _me(p))
            .order_by(RentalNeed.created_at.desc())
            .limit(50)
        )
    ).all()
    return await svc.needs_out(s, list(rows))


@router.get("/needs/nearby", response_model=list[NeedOut])
async def nearby_needs(
    kind: Kind | None = None,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> list[NeedOut]:
    """For equipment owners: open needs near them for kinds they list."""
    try:
        rows, ranks = await svc.nearby_needs(s, _me(p), kind)
    except svc.RentalError as e:
        _err(e)
    return await svc.needs_out(s, rows, ranks)


@router.get("/needs/{need_id}/matches", response_model=list[ListingOut])
async def need_matches(
    need_id: UUID,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> list[ListingOut]:
    need = await s.get(RentalNeed, need_id)
    if need is None or need.renter_farmer_id != _me(p):
        raise HTTPException(404, "not_found")
    rows, ranks = await svc.browse_listings(
        s, _me(p), kind=need.kind, start=need.start_date, end=need.end_date
    )
    return await svc.listings_out(s, rows, ranks)


@router.post("/needs/{need_id}/cancel", response_model=NeedOut)
async def cancel_need(
    need_id: UUID,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> NeedOut:
    try:
        row = await svc.cancel_need(s, _me(p), need_id)
    except svc.RentalError as e:
        _err(e)
    return (await svc.needs_out(s, [row]))[0]


# ---------------- bookings (both parties -> platform ctx + explicit checks) ----------------


@router.post("/bookings", response_model=BookingOut, status_code=201)
async def create_booking(
    body: BookingIn,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> BookingOut:
    try:
        b = await svc.create_booking(s, _me(p), body)
    except svc.RentalError as e:
        _err(e)
    return await svc.booking_out(s, b, _me(p))


@router.get("/bookings", response_model=list[BookingOut])
async def my_bookings(
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> list[BookingOut]:
    return [await svc.booking_out(s, b, _me(p)) for b in await svc.my_bookings(s, _me(p))]


@router.get("/bookings/{booking_id}", response_model=BookingOut)
async def get_booking(
    booking_id: UUID,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> BookingOut:
    try:
        b = await svc.get_booking(s, _me(p), booking_id)
    except svc.RentalError as e:
        _err(e)
    return await svc.booking_out(s, b, _me(p))


@router.get("/bookings/{booking_id}/events", response_model=list[BookingEventOut])
async def booking_events(
    booking_id: UUID,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> list[BookingEventOut]:
    try:
        b = await svc.get_booking(s, _me(p), booking_id)
    except svc.RentalError as e:
        _err(e)
    return await svc.events_out(s, b)


@router.post("/bookings/{booking_id}/transition", response_model=BookingOut)
async def transition(
    booking_id: UUID,
    body: TransitionIn,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> BookingOut:
    try:
        b = await svc.transition(s, _me(p), booking_id, body.action, body.note)
    except svc.RentalError as e:
        _err(e)
    return await svc.booking_out(s, b, _me(p))


@router.post("/bookings/{booking_id}/share-contact", response_model=BookingOut)
async def share_contact(
    booking_id: UUID,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> BookingOut:
    try:
        b = await svc.share_contact(s, _me(p), booking_id)
    except svc.RentalError as e:
        _err(e)
    return await svc.booking_out(s, b, _me(p))


@router.get("/bookings/{booking_id}/contact", response_model=ContactOut)
async def contact(
    booking_id: UUID,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> ContactOut:
    try:
        name, phone = await svc.contact(s, _me(p), booking_id)
    except svc.RentalError as e:
        _err(e)
    return ContactOut(name=name, phone=phone)


@router.post("/bookings/{booking_id}/rating", response_model=BookingOut)
async def rate(
    booking_id: UUID,
    body: RatingIn,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> BookingOut:
    try:
        b = await svc.rate(s, _me(p), booking_id, body.score, body.text)
    except svc.RentalError as e:
        _err(e)
    return await svc.booking_out(s, b, _me(p))


# ---------------- admin ----------------


@admin_router.post("/bookings/{booking_id}/resolve")
async def resolve(
    booking_id: UUID,
    body: ResolveIn,
    _: dict = Depends(require_role("platform_admin")),
    s: AsyncSession = Depends(get_session_platform),
) -> dict:
    try:
        b = await svc.resolve(s, booking_id, body.resolution)
    except svc.RentalError as e:
        _err(e)
    return {"id": str(b.id), "state": b.state}
