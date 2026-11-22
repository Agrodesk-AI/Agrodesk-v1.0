"""Deterministic trust signals + badges (design §3.7).

Signals are counts over confirmed events only. Badges are awarded / revoked by
rules, never by a learned score, and other farmers see badges, never numbers.

Badges:
  trusted_renter     >= 5 rentals completed by both sides (either role) in 365 d
                     AND no open disputes
  helpful_neighbour  >= 25 helpful marks on own published posts in 365 d, from
                     >= 10 distinct farmers whose accounts were >= 7 d old at the time

An admin revoke sticks: the system never re-awards a badge an admin revoked
within the last ADMIN_REVOKE_HOLD.

Anti-gaming (daily): ratings from accounts younger than 7 days don't count
(see `rating_filter`); pairs who rated each other on >= 3 bookings in 90 d
are flagged for admin review.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.models import (
    Account,
    Farmer,
    FarmerBadge,
    Post,
    PostHelpful,
    RentalBooking,
    RentalRating,
    TrustFlag,
)
from app.security.tenant import set_tenant_context

WINDOW = timedelta(days=365)
NEW_ACCOUNT = timedelta(days=7)
ADMIN_REVOKE_HOLD = timedelta(days=90)
RING_WINDOW = timedelta(days=90)
RING_MIN_PAIRS = 3

RULES = {
    "trusted_renter": {"completed_rentals": 5, "open_disputes_max": 0},
    "helpful_neighbour": {"helpful_marks": 25, "distinct_markers": 10},
}
COMPLETED = ("completed_by_both", "rated")


def rating_filter():
    """SQL condition: the rater's account was >= 7 days old when they rated."""
    return RentalRating.from_farmer_id.in_(
        select(Farmer.id)
        .join(Account, Account.id == Farmer.account_id)
        .where(Account.created_at <= RentalRating.created_at - NEW_ACCOUNT)
        .correlate(RentalRating)
        .scalar_subquery()
    )


async def signals(session: AsyncSession, farmer_id: UUID, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    since = now - WINDOW
    party = or_(
        RentalBooking.owner_farmer_id == farmer_id, RentalBooking.renter_farmer_id == farmer_id
    )
    completed = await session.scalar(
        select(func.count())
        .select_from(RentalBooking)
        .where(party, RentalBooking.state.in_(COMPLETED), RentalBooking.updated_at >= since)
    )
    disputes = await session.scalar(
        select(func.count())
        .select_from(RentalBooking)
        .where(party, RentalBooking.state == "disputed")
    )
    marker_account = (
        select(Account.created_at)
        .join(Farmer, Farmer.account_id == Account.id)
        .where(Farmer.id == PostHelpful.farmer_id)
        .correlate(PostHelpful)
        .scalar_subquery()
    )
    helpful_q = (
        select(func.count(), func.count(func.distinct(PostHelpful.farmer_id)))
        .select_from(PostHelpful)
        .join(Post, Post.id == PostHelpful.post_id)
        .where(
            Post.farmer_id == farmer_id,
            Post.status == "published",
            PostHelpful.created_at >= since,
            marker_account <= PostHelpful.created_at - NEW_ACCOUNT,
        )
    )
    marks, markers = (await session.execute(helpful_q)).one()
    avg, n = (
        await session.execute(
            select(func.avg(RentalRating.score), func.count()).where(
                RentalRating.to_farmer_id == farmer_id, rating_filter()
            )
        )
    ).one()
    farmer = await session.get(Farmer, farmer_id)
    account = await session.get(Account, farmer.account_id) if farmer else None
    return {
        "completed_rentals": completed or 0,
        "open_disputes": disputes or 0,
        "helpful_marks": marks or 0,
        "distinct_markers": markers or 0,
        "rating_avg": round(float(avg), 2) if avg is not None else None,
        "rating_count": n or 0,
        "account_age_days": (now - account.created_at).days if account else 0,
    }


def qualifies(badge: str, s: dict) -> bool:
    r = RULES[badge]
    if badge == "trusted_renter":
        return (
            s["completed_rentals"] >= r["completed_rentals"]
            and s["open_disputes"] <= r["open_disputes_max"]
        )
    if badge == "helpful_neighbour":
        return (
            s["helpful_marks"] >= r["helpful_marks"]
            and s["distinct_markers"] >= r["distinct_markers"]
        )
    return False


def progress(s: dict) -> dict:
    """What the farmer sees about themself: how far each badge is."""
    return {
        "trusted_renter": {
            "completed_rentals": [
                s["completed_rentals"],
                RULES["trusted_renter"]["completed_rentals"],
            ],
            "open_disputes": s["open_disputes"],
        },
        "helpful_neighbour": {
            "helpful_marks": [s["helpful_marks"], RULES["helpful_neighbour"]["helpful_marks"]],
            "distinct_markers": [
                s["distinct_markers"],
                RULES["helpful_neighbour"]["distinct_markers"],
            ],
        },
    }


async def recompute(session: AsyncSession, farmer_id: UUID, now: datetime | None = None) -> dict:
    """Award / revoke system badges for one farmer. Platform context required."""
    now = now or datetime.now(UTC)
    s = await signals(session, farmer_id, now)
    changes = {"awarded": [], "revoked": []}
    for badge in RULES:
        live = await session.scalar(
            select(FarmerBadge).where(
                FarmerBadge.farmer_id == farmer_id,
                FarmerBadge.badge == badge,
                FarmerBadge.revoked_at.is_(None),
            )
        )
        ok = qualifies(badge, s)
        if ok and live is None:
            held = await session.scalar(
                select(FarmerBadge.id).where(
                    FarmerBadge.farmer_id == farmer_id,
                    FarmerBadge.badge == badge,
                    FarmerBadge.revoked_by.is_not(None),
                    FarmerBadge.revoked_by != "system",
                    FarmerBadge.revoked_at >= now - ADMIN_REVOKE_HOLD,
                )
            )
            if held is None:
                session.add(
                    FarmerBadge(
                        farmer_id=farmer_id,
                        badge=badge,
                        awarded_at=now,
                        awarded_by="system",
                        evidence=s,
                    )
                )
                changes["awarded"].append(badge)
        elif not ok and live is not None and live.awarded_by == "system":
            live.revoked_at = now
            live.revoked_by = "system"
            live.revoke_reason = "rule_no_longer_met"
            changes["revoked"].append(badge)
    await session.flush()
    return changes


async def badges_for(session: AsyncSession, farmer_ids: set[UUID]) -> dict[UUID, list[str]]:
    if not farmer_ids:
        return {}
    rows = await session.execute(
        select(FarmerBadge.farmer_id, FarmerBadge.badge)
        .where(FarmerBadge.farmer_id.in_(farmer_ids), FarmerBadge.revoked_at.is_(None))
        .order_by(FarmerBadge.badge)
    )
    out: dict[UUID, list[str]] = {}
    for fid, b in rows.all():
        out.setdefault(fid, []).append(b)
    return out


async def admin_revoke(
    session: AsyncSession, admin_id: UUID, farmer_id: UUID, badge: str, reason: str
) -> bool:
    live = await session.scalar(
        select(FarmerBadge).where(
            FarmerBadge.farmer_id == farmer_id,
            FarmerBadge.badge == badge,
            FarmerBadge.revoked_at.is_(None),
        )
    )
    if live is None:
        return False
    live.revoked_at = datetime.now(UTC)
    live.revoked_by = str(admin_id)
    live.revoke_reason = reason
    await session.flush()
    return True


# ---------------------------------------------------------------- daily job


async def detect_rating_rings(session: AsyncSession, now: datetime) -> int:
    """Pairs who rated each other on >= RING_MIN_PAIRS bookings in RING_WINDOW."""
    rows = (
        await session.execute(
            text("""
                SELECT LEAST(r1.from_farmer_id, r1.to_farmer_id) AS a,
                       GREATEST(r1.from_farmer_id, r1.to_farmer_id) AS b,
                       count(DISTINCT r1.booking_id) AS bookings,
                       avg(r1.score) AS avg_score
                FROM rental_ratings r1
                JOIN rental_ratings r2
                  ON r2.booking_id = r1.booking_id
                 AND r2.from_farmer_id = r1.to_farmer_id
                 AND r2.to_farmer_id = r1.from_farmer_id
                WHERE r1.created_at >= :since
                GROUP BY 1, 2
                HAVING count(DISTINCT r1.booking_id) >= :n
            """),
            {"since": now - RING_WINDOW, "n": RING_MIN_PAIRS},
        )
    ).all()
    created = 0
    for a, b, bookings, avg_score in rows:
        pair = sorted([a, b])
        exists = await session.scalar(
            select(TrustFlag.id).where(
                TrustFlag.kind == "rating_ring",
                TrustFlag.farmer_ids == pair,
                TrustFlag.status == "open",
            )
        )
        if exists is None:
            session.add(
                TrustFlag(
                    kind="rating_ring",
                    farmer_ids=pair,
                    detail={
                        "bookings": bookings,
                        "avg_score": float(avg_score),
                        "window_days": RING_WINDOW.days,
                    },
                    status="open",
                    created_at=now,
                )
            )
            created += 1
    await session.flush()
    return created


async def recompute_all(now: datetime | None = None) -> dict:
    """Daily: recompute every farmer touched in the window + flag rings."""
    now = now or datetime.now(UTC)
    awarded = revoked = 0
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        since = now - WINDOW
        active = (
            set(
                (
                    await s.scalars(
                        select(RentalBooking.owner_farmer_id).where(
                            RentalBooking.updated_at >= since
                        )
                    )
                ).all()
            )
            | set(
                (
                    await s.scalars(
                        select(RentalBooking.renter_farmer_id).where(
                            RentalBooking.updated_at >= since
                        )
                    )
                ).all()
            )
            | set(
                (
                    await s.scalars(
                        select(Post.farmer_id).where(
                            and_(Post.helpful_count > 0, Post.created_at >= since)
                        )
                    )
                ).all()
            )
            | set(
                (
                    await s.scalars(
                        select(FarmerBadge.farmer_id).where(FarmerBadge.revoked_at.is_(None))
                    )
                ).all()
            )
        )
        for fid in active:
            c = await recompute(s, fid, now)
            awarded += len(c["awarded"])
            revoked += len(c["revoked"])
        rings = await detect_rating_rings(s, now)
    return {"farmers": len(active), "awarded": awarded, "revoked": revoked, "ring_flags": rings}
