"""Farmer-to-farmer equipment rental (design §3.5).

Listings / needs CRUD and browsing run in the farmer's own RLS context.
Booking operations touch two farmers' rows (booking, need, contact), so they
run in platform context with explicit party checks, like lead routing.

Booking state machine:

    requested --agree(owner)--> agreed --start(either)--> in_progress
        |  \\--decline(owner)--> declined        |              |
        \\--cancel(renter)--> cancelled <--cancel(either)--/     |
                                                              complete(each side)
    in_progress --both completed--> completed_by_both --both rated--> rated
    in_progress | completed_by_both(<=7d) --dispute(either)--> disputed --resolve(admin)--> resolved
"""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import Boolean, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    EquipmentListing,
    Farmer,
    RentalBooking,
    RentalBookingEvent,
    RentalNeed,
    RentalRating,
    Tehsil,
)
from app.schemas.rental import (
    BookingEventOut,
    BookingIn,
    BookingOut,
    ListingIn,
    ListingOut,
    ListingUpdateIn,
    NeedIn,
    NeedOut,
)
from app.services import location_service, trust_service

DAILY_NEEDS = 5
DAILY_REQUESTS = 10
DISPUTE_WINDOW = timedelta(days=7)
CONTACT_STATES = {"agreed", "in_progress", "completed_by_both", "rated", "disputed", "resolved"}


class RentalError(Exception):
    def __init__(self, code: str, status: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


# ---------------------------------------------------------------- helpers


def _busy(listing_id, start, end):
    """SECURITY DEFINER fn: is the listing booked on these dates? (boolean only)"""
    return func.rental_listing_busy(listing_id, start, end, type_=Boolean)


async def _farmer(session: AsyncSession, farmer_id: UUID) -> Farmer:
    f = await session.get(Farmer, farmer_id)
    if f is None or f.status != "active":
        raise RentalError("no_such_farmer", 404)
    return f


async def _nearby(session: AsyncSession, tehsil_id: int) -> dict[int, int]:
    return {t.id: r for t, r in await location_service.nearby_tehsils(session, tehsil_id)}


async def _tehsil_names(session: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = await session.execute(select(Tehsil.id, Tehsil.name_en).where(Tehsil.id.in_(ids)))
    return dict(rows.all())


async def _rating_stats(session: AsyncSession, farmer_ids: set[UUID]) -> dict[UUID, tuple]:
    if not farmer_ids:
        return {}
    rows = await session.execute(
        select(RentalRating.to_farmer_id, func.avg(RentalRating.score), func.count())
        .where(RentalRating.to_farmer_id.in_(farmer_ids), trust_service.rating_filter())
        .group_by(RentalRating.to_farmer_id)
    )
    return {fid: (round(float(avg), 2), n) for fid, avg, n in rows.all()}


async def listings_out(
    session: AsyncSession, rows: list[EquipmentListing], ranks: dict[int, int] | None = None
) -> list[ListingOut]:
    names = await _tehsil_names(session, {r.tehsil_id for r in rows})
    stats = await _rating_stats(session, {r.owner_farmer_id for r in rows})
    badges = await trust_service.badges_for(session, {r.owner_farmer_id for r in rows})
    out = []
    for r in rows:
        avg, n = stats.get(r.owner_farmer_id, (None, 0))
        out.append(
            ListingOut(
                id=r.id,
                owner_farmer_id=r.owner_farmer_id,
                owner_name=r.owner_name,
                tehsil_id=r.tehsil_id,
                tehsil_name=names.get(r.tehsil_id, ""),
                distance_rank=(ranks or {}).get(r.tehsil_id),
                kind=r.kind,
                title=r.title,
                hp=r.hp,
                rate_paise=r.rate_paise,
                rate_unit=r.rate_unit,
                operator_included=r.operator_included,
                fuel_included=r.fuel_included,
                notes=r.notes,
                status=r.status,
                owner_rating=avg,
                owner_rating_count=n,
                owner_badges=badges.get(r.owner_farmer_id, []),
            )
        )
    return out


async def needs_out(
    session: AsyncSession, rows: list[RentalNeed], ranks: dict[int, int] | None = None
) -> list[NeedOut]:
    names = await _tehsil_names(session, {r.tehsil_id for r in rows})
    return [
        NeedOut(
            id=r.id,
            renter_farmer_id=r.renter_farmer_id,
            renter_name=r.renter_name,
            tehsil_id=r.tehsil_id,
            tehsil_name=names.get(r.tehsil_id, ""),
            distance_rank=(ranks or {}).get(r.tehsil_id),
            kind=r.kind,
            acreage=r.acreage,
            start_date=r.start_date,
            end_date=r.end_date,
            budget_paise=r.budget_paise,
            notes=r.notes,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ---------------------------------------------------------------- listings (RLS ctx)


async def create_listing(
    session: AsyncSession, farmer_id: UUID, data: ListingIn
) -> EquipmentListing:
    f = await _farmer(session, farmer_id)
    row = EquipmentListing(
        owner_farmer_id=f.id,
        owner_name=f.display_name,
        tehsil_id=f.tehsil_id,
        village_id=f.village_id,
        status="active",
        **data.model_dump(),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def update_listing(
    session: AsyncSession, farmer_id: UUID, listing_id: UUID, data: ListingUpdateIn
) -> EquipmentListing:
    row = await session.get(EquipmentListing, listing_id)
    if row is None or row.owner_farmer_id != farmer_id:
        raise RentalError("not_found", 404)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(row, k, v)
    await session.flush()
    await session.refresh(row)
    return row


async def browse_listings(
    session: AsyncSession,
    farmer_id: UUID,
    *,
    kind: str | None,
    start: date | None,
    end: date | None,
    limit: int = 50,
) -> tuple[list[EquipmentListing], dict[int, int]]:
    """Active listings in the farmer's nearby tehsils, not their own, free on the
    dates if given. Nearest first, then cheapest."""
    f = await _farmer(session, farmer_id)
    ranks = await _nearby(session, f.tehsil_id)
    q = select(EquipmentListing).where(
        EquipmentListing.status == "active",
        EquipmentListing.owner_farmer_id != farmer_id,
        EquipmentListing.tehsil_id.in_(ranks.keys()),
    )
    if kind:
        q = q.where(EquipmentListing.kind == kind)
    if start and end:
        q = q.where(_busy(EquipmentListing.id, start, end).is_(False))
    rows = list((await session.scalars(q.limit(500))).all())
    rows.sort(key=lambda r: (ranks.get(r.tehsil_id, 999), r.rate_paise, r.title))
    return rows[:limit], ranks


# ---------------------------------------------------------------- needs (RLS ctx)


async def create_need(
    session: AsyncSession, farmer_id: UUID, data: NeedIn, today: date | None = None
) -> RentalNeed:
    f = await _farmer(session, farmer_id)
    today = today or datetime.now(UTC).date()
    if data.start_date < today:
        raise RentalError("start_in_past")
    recent = await session.scalar(
        select(func.count())
        .select_from(RentalNeed)
        .where(
            RentalNeed.renter_farmer_id == farmer_id,
            RentalNeed.created_at >= datetime.now(UTC) - timedelta(hours=24),
        )
    )
    if (recent or 0) >= DAILY_NEEDS:
        raise RentalError("too_many_requests", 429)
    row = RentalNeed(
        renter_farmer_id=f.id,
        renter_name=f.display_name,
        tehsil_id=f.tehsil_id,
        village_id=f.village_id,
        status="open",
        **data.model_dump(),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def cancel_need(session: AsyncSession, farmer_id: UUID, need_id: UUID) -> RentalNeed:
    row = await session.get(RentalNeed, need_id)
    if row is None or row.renter_farmer_id != farmer_id:
        raise RentalError("not_found", 404)
    if row.status != "open":
        raise RentalError("not_open", 409)
    row.status = "cancelled"
    await session.flush()
    await session.refresh(row)
    return row


async def nearby_needs(
    session: AsyncSession, farmer_id: UUID, kind: str | None
) -> tuple[list[RentalNeed], dict[int, int]]:
    """Open needs near this farmer that match a kind they list (or `kind`)."""
    f = await _farmer(session, farmer_id)
    ranks = await _nearby(session, f.tehsil_id)
    if kind:
        kinds = {kind}
    else:
        kinds = set(
            (
                await session.scalars(
                    select(EquipmentListing.kind).where(
                        EquipmentListing.owner_farmer_id == farmer_id,
                        EquipmentListing.status == "active",
                    )
                )
            ).all()
        )
    if not kinds:
        return [], ranks
    today = datetime.now(UTC).date()
    rows = list(
        (
            await session.scalars(
                select(RentalNeed)
                .where(
                    RentalNeed.status == "open",
                    RentalNeed.renter_farmer_id != farmer_id,
                    RentalNeed.tehsil_id.in_(ranks.keys()),
                    RentalNeed.kind.in_(kinds),
                    RentalNeed.end_date >= today,
                )
                .limit(200)
            )
        ).all()
    )
    rows.sort(key=lambda r: (ranks.get(r.tehsil_id, 999), r.start_date))
    return rows, ranks


# ---------------------------------------------------------------- bookings (platform ctx)


def _role(b: RentalBooking, farmer_id: UUID) -> str:
    if b.owner_farmer_id == farmer_id:
        return "owner"
    if b.renter_farmer_id == farmer_id:
        return "renter"
    raise RentalError("not_found", 404)


def allowed_actions(b: RentalBooking, role: str, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(UTC)
    s = b.state
    if s == "requested":
        return ["agree", "decline"] if role == "owner" else ["cancel"]
    if s == "agreed":
        return ["start", "cancel"]
    if s == "in_progress":
        mine = b.owner_completed_at if role == "owner" else b.renter_completed_at
        return (["complete"] if mine is None else []) + ["dispute"]
    if s == "completed_by_both":
        done = max(filter(None, [b.owner_completed_at, b.renter_completed_at]))
        return ["dispute"] if now - done <= DISPUTE_WINDOW else []
    return []


def _event(
    b: RentalBooking,
    frm: str | None,
    to: str,
    action: str,
    actor: UUID | None,
    note: str | None,
    now: datetime,
) -> RentalBookingEvent:
    return RentalBookingEvent(
        booking_id=b.id,
        owner_farmer_id=b.owner_farmer_id,
        renter_farmer_id=b.renter_farmer_id,
        from_state=frm,
        to_state=to,
        action=action,
        actor_farmer_id=actor,
        note=note,
        at=now,
    )


async def booking_out(session: AsyncSession, b: RentalBooking, farmer_id: UUID) -> BookingOut:
    role = _role(b, farmer_id)
    listing = await session.get(EquipmentListing, b.listing_id)
    i_rated = await session.scalar(
        select(RentalRating.id).where(
            RentalRating.booking_id == b.id, RentalRating.from_farmer_id == farmer_id
        )
    )
    mine, theirs = (
        (b.owner_shared_contact_at, b.renter_shared_contact_at)
        if role == "owner"
        else (b.renter_shared_contact_at, b.owner_shared_contact_at)
    )
    actions = allowed_actions(b, role)
    if b.state in CONTACT_STATES and mine is None:
        actions.append("share_contact")
    if b.state in ("completed_by_both", "rated") and i_rated is None:
        actions.append("rate")
    other = b.renter_farmer_id if role == "owner" else b.owner_farmer_id
    other_badges = (await trust_service.badges_for(session, {other})).get(other, [])
    return BookingOut(
        id=b.id,
        listing_id=b.listing_id,
        listing_title=listing.title if listing else "",
        kind=listing.kind if listing else "",
        need_id=b.need_id,
        my_role=role,
        owner_name=b.owner_name,
        renter_name=b.renter_name,
        start_date=b.start_date,
        end_date=b.end_date,
        state=b.state,
        note=b.note,
        owner_completed=b.owner_completed_at is not None,
        renter_completed=b.renter_completed_at is not None,
        i_shared_contact=mine is not None,
        they_shared_contact=theirs is not None,
        i_rated=i_rated is not None,
        dispute_reason=b.dispute_reason,
        allowed_actions=actions,
        other_badges=other_badges,
        created_at=b.created_at,
    )


async def create_booking(
    session: AsyncSession, farmer_id: UUID, data: BookingIn, today: date | None = None
) -> RentalBooking:
    renter = await _farmer(session, farmer_id)
    today = today or datetime.now(UTC).date()
    if data.start_date < today:
        raise RentalError("start_in_past")
    listing = await session.get(EquipmentListing, data.listing_id)
    if listing is None or listing.status != "active":
        raise RentalError("listing_unavailable", 404)
    if listing.owner_farmer_id == farmer_id:
        raise RentalError("own_listing")
    if listing.tehsil_id not in await _nearby(session, renter.tehsil_id):
        raise RentalError("too_far")
    if data.need_id is not None:
        need = await session.get(RentalNeed, data.need_id)
        if need is None or need.renter_farmer_id != farmer_id or need.status != "open":
            raise RentalError("bad_need")
        if need.kind != listing.kind:
            raise RentalError("need_kind_mismatch")

    recent = await session.scalar(
        select(func.count())
        .select_from(RentalBooking)
        .where(
            RentalBooking.renter_farmer_id == farmer_id,
            RentalBooking.created_at >= datetime.now(UTC) - timedelta(hours=24),
        )
    )
    if (recent or 0) >= DAILY_REQUESTS:
        raise RentalError("too_many_requests", 429)
    dup = await session.scalar(
        select(RentalBooking.id).where(
            RentalBooking.listing_id == listing.id,
            RentalBooking.renter_farmer_id == farmer_id,
            RentalBooking.state.in_(("requested", "agreed", "in_progress")),
        )
    )
    if dup is not None:
        raise RentalError("already_requested", 409)
    busy = await session.scalar(select(_busy(listing.id, data.start_date, data.end_date)))
    if busy:
        raise RentalError("dates_taken", 409)

    now = datetime.now(UTC)
    b = RentalBooking(
        listing_id=listing.id,
        need_id=data.need_id,
        owner_farmer_id=listing.owner_farmer_id,
        renter_farmer_id=farmer_id,
        owner_name=listing.owner_name,
        renter_name=renter.display_name,
        start_date=data.start_date,
        end_date=data.end_date,
        state="requested",
        note=data.note,
    )
    session.add(b)
    await session.flush()
    session.add(_event(b, None, "requested", "request", farmer_id, data.note, now))
    await session.flush()
    await session.refresh(b)
    return b


async def get_booking(
    session: AsyncSession, farmer_id: UUID, booking_id: UUID, lock: bool = False
) -> RentalBooking:
    b = await session.get(RentalBooking, booking_id, with_for_update=lock)
    if b is None:
        raise RentalError("not_found", 404)
    _role(b, farmer_id)
    return b


async def transition(
    session: AsyncSession,
    farmer_id: UUID,
    booking_id: UUID,
    action: str,
    note: str | None,
    now: datetime | None = None,
) -> RentalBooking:
    now = now or datetime.now(UTC)
    b = await get_booking(session, farmer_id, booking_id, lock=True)
    role = _role(b, farmer_id)
    if action not in allowed_actions(b, role, now):
        raise RentalError(f"invalid_action:{b.state}:{action}", 409)
    frm = b.state
    completed_now = False

    if action == "agree":
        b.state = "agreed"
        try:
            async with session.begin_nested():
                await session.flush()  # exclusion constraint guards double booking
        except IntegrityError:
            raise RentalError("dates_taken", 409) from None
        # Other pending requests for overlapping dates can no longer be honoured.
        clashing = (
            await session.scalars(
                select(RentalBooking)
                .where(
                    RentalBooking.listing_id == b.listing_id,
                    RentalBooking.id != b.id,
                    RentalBooking.state == "requested",
                    RentalBooking.start_date <= b.end_date,
                    RentalBooking.end_date >= b.start_date,
                )
                .with_for_update()
            )
        ).all()
        for other in clashing:
            other.state = "declined"
            session.add(
                _event(
                    other,
                    "requested",
                    "declined",
                    "auto_decline",
                    None,
                    "Dates booked by another farmer",
                    now,
                )
            )
        if b.need_id:
            need = await session.get(RentalNeed, b.need_id)
            if need is not None and need.status == "open":
                need.status = "matched"
    elif action == "decline":
        b.state = "declined"
    elif action == "cancel":
        b.state = "cancelled"
    elif action == "start":
        b.state = "in_progress"
    elif action == "complete":
        if role == "owner":
            b.owner_completed_at = now
        else:
            b.renter_completed_at = now
        if b.owner_completed_at and b.renter_completed_at:
            b.state = "completed_by_both"
            completed_now = True
    elif action == "dispute":
        if not note:
            raise RentalError("reason_required")
        b.state = "disputed"
        b.dispute_reason = note

    session.add(_event(b, frm, b.state, action, farmer_id, note, now))
    await session.flush()
    if completed_now or action == "dispute":
        # badges reflect completions / disputes now, not only at the nightly run
        for fid in (b.owner_farmer_id, b.renter_farmer_id):
            await trust_service.recompute(session, fid, now)
    await session.refresh(b)
    return b


async def share_contact(session: AsyncSession, farmer_id: UUID, booking_id: UUID) -> RentalBooking:
    b = await get_booking(session, farmer_id, booking_id, lock=True)
    if b.state not in CONTACT_STATES:
        raise RentalError("contact_not_available", 409)
    now = datetime.now(UTC)
    if _role(b, farmer_id) == "owner":
        b.owner_shared_contact_at = b.owner_shared_contact_at or now
    else:
        b.renter_shared_contact_at = b.renter_shared_contact_at or now
    await session.flush()
    await session.refresh(b)
    return b


async def contact(session: AsyncSession, farmer_id: UUID, booking_id: UUID) -> tuple[str, str]:
    """The other party's phone, only once both sides have chosen to share."""
    b = await get_booking(session, farmer_id, booking_id)
    if b.state not in CONTACT_STATES or not (
        b.owner_shared_contact_at and b.renter_shared_contact_at
    ):
        raise RentalError("contact_masked", 403)
    other_id = b.renter_farmer_id if _role(b, farmer_id) == "owner" else b.owner_farmer_id
    other = await session.get(Farmer, other_id)
    account = await session.get(Account, other.account_id)
    return other.display_name, account.phone


async def rate(
    session: AsyncSession, farmer_id: UUID, booking_id: UUID, score: int, text_: str | None
) -> RentalBooking:
    b = await get_booking(session, farmer_id, booking_id, lock=True)
    role = _role(b, farmer_id)
    if b.state not in ("completed_by_both", "rated"):
        raise RentalError("rating_before_completion", 409)
    other = b.renter_farmer_id if role == "owner" else b.owner_farmer_id
    try:
        async with session.begin_nested():
            session.add(
                RentalRating(
                    booking_id=b.id,
                    from_farmer_id=farmer_id,
                    to_farmer_id=other,
                    score=score,
                    text=text_,
                    created_at=datetime.now(UTC),
                )
            )
            await session.flush()
    except IntegrityError:
        raise RentalError("already_rated", 409) from None
    n = await session.scalar(
        select(func.count()).select_from(RentalRating).where(RentalRating.booking_id == b.id)
    )
    if n == 2 and b.state == "completed_by_both":
        b.state = "rated"
        session.add(
            _event(b, "completed_by_both", "rated", "rate", farmer_id, None, datetime.now(UTC))
        )
    await session.flush()
    await session.refresh(b)
    return b


async def resolve(session: AsyncSession, booking_id: UUID, resolution: str) -> RentalBooking:
    b = await session.get(RentalBooking, booking_id, with_for_update=True)
    if b is None:
        raise RentalError("not_found", 404)
    if b.state != "disputed":
        raise RentalError("not_disputed", 409)
    b.state = "resolved"
    b.resolution = resolution
    session.add(_event(b, "disputed", "resolved", "resolve", None, resolution, datetime.now(UTC)))
    await session.flush()
    for fid in (b.owner_farmer_id, b.renter_farmer_id):
        await trust_service.recompute(session, fid)
    await session.refresh(b)
    return b


async def my_bookings(session: AsyncSession, farmer_id: UUID) -> list[RentalBooking]:
    return list(
        (
            await session.scalars(
                select(RentalBooking)
                .where(
                    (RentalBooking.owner_farmer_id == farmer_id)
                    | (RentalBooking.renter_farmer_id == farmer_id)
                )
                .order_by(RentalBooking.created_at.desc())
                .limit(100)
            )
        ).all()
    )


async def events_out(session: AsyncSession, b: RentalBooking) -> list[BookingEventOut]:
    rows = (
        await session.scalars(
            select(RentalBookingEvent)
            .where(RentalBookingEvent.booking_id == b.id)
            .order_by(RentalBookingEvent.at)
        )
    ).all()

    def by(actor):
        if actor is None:
            return "admin"
        return "owner" if actor == b.owner_farmer_id else "renter"

    return [
        BookingEventOut(
            from_state=e.from_state,
            to_state=e.to_state,
            action=e.action,
            by=by(e.actor_farmer_id),
            note=e.note,
            at=e.at,
        )
        for e in rows
    ]
