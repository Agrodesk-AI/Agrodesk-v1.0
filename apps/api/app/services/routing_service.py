"""Consented farmer -> dealer lead routing (design §3.3).

Flow:
  1. Farmer states a buying interest and accepts the exact consent text (stored).
  2. Rank verified dealers serving the farmer's tehsil / its neighbours.
  3. Create a lead for the top dealer with an SLA (business hours).
  4. Any staff action on that lead (stage change, call, note) = responded.
  5. A beat sweep re-routes overdue leads to the next candidate, at most
     `lead_routing_max_reroutes` times, then parks the interest on a wait list.

Routing crosses tenants (farmer row -> dealer lead), so it runs in platform
context with explicit ownership checks, like OTP verify.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_hours import IST, add_business_hours
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import (
    Account,
    BuyingInterest,
    Dealer,
    DealerServiceArea,
    Farmer,
    FarmerConsent,
    Lead,
    LeadRoute,
    Task,
    User,
    Village,
)
from app.schemas.customer import CustomerCreateIn
from app.schemas.routing import InterestCreateIn
from app.security.tenant import set_tenant_context
from app.services import location_service
from app.services.customer_service import create_or_get_by_phone
from app.services.lead_service import _upsert_task_for_next_action, _write_event

PURPOSE = "lead_routing"
CONSENT_VERSION = "v1"
# Exact text shown and stored. Changing wording = new version, never edit in place.
CONSENT_TEXTS: dict[str, dict[str, str]] = {
    "v1": {
        "en": (
            "I agree that Agrodesk may share my name, phone number, village and this "
            "request with up to {n} verified tractor dealers near me, one at a time, so "
            "they can call or WhatsApp me about it. I can cancel this request any time."
        ),
        "hi": (
            "मैं सहमत हूँ कि Agrodesk मेरा नाम, फ़ोन नंबर, गाँव और यह अनुरोध मेरे पास के "
            "अधिकतम {n} सत्यापित ट्रैक्टर डीलरों से, एक-एक करके, साझा कर सकता है ताकि वे "
            "मुझे इस बारे में कॉल या WhatsApp कर सकें। मैं यह अनुरोध कभी भी रद्द कर सकता/सकती हूँ।"
        ),
        "mr": (
            "मी सहमत आहे की Agrodesk माझे नाव, फोन नंबर, गाव आणि ही विनंती माझ्या जवळच्या "
            "जास्तीत जास्त {n} पडताळलेल्या ट्रॅक्टर डीलर्सना, एकावेळी एक, देऊ शकते, जेणेकरून ते "
            "मला याबद्दल कॉल किंवा WhatsApp करू शकतील. मी ही विनंती कधीही रद्द करू शकतो/शकते."
        ),
    }
}
OPEN_STATUSES = ("routing", "assigned")


class RoutingError(Exception):
    def __init__(self, code: str, status: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def max_dealers() -> int:
    return settings.lead_routing_max_reroutes + 1


def consent_text(lang: str, version: str = CONSENT_VERSION) -> tuple[str, str]:
    """(language actually used, text). Languages without a reviewed text get English."""
    texts = CONSENT_TEXTS[version]
    used = lang if lang in texts else "en"
    return used, texts[used].format(n=max_dealers())


# ---------------------------------------------------------------- ranking


async def rank_candidates(
    session: AsyncSession, *, tehsil_id: int, brand_hint: str | None, now: datetime
) -> list[tuple[Dealer, dict]]:
    """Verified, active dealers serving the farmer's area, best first.

    Order: nearest service tehsil (0 = farmer's own, then curated neighbours, 99 =
    same-district fallback) -> home-tehsil match -> response rate (last 90 days)
    -> remaining capacity today. Dealers at today's cap are skipped."""
    nearby = {t.id: rank for t, rank in await location_service.nearby_tehsils(session, tehsil_id)}
    if not nearby:
        return []

    rows = (
        await session.execute(
            select(Dealer, DealerServiceArea)
            .join(DealerServiceArea, DealerServiceArea.dealer_id == Dealer.id)
            .where(
                DealerServiceArea.tehsil_id.in_(nearby.keys()),
                Dealer.verified_at.is_not(None),
                Dealer.status == "active",
            )
        )
    ).all()

    best: dict[UUID, dict] = {}
    dealers: dict[UUID, Dealer] = {}
    for dealer, area in rows:
        if brand_hint and brand_hint.strip().lower() not in {b.lower() for b in dealer.brands}:
            continue
        dist = nearby[area.tehsil_id]
        home = area.is_home and area.tehsil_id == tehsil_id
        cur = best.get(dealer.id)
        if cur is None or (dist, not home) < (cur["distance_rank"], not cur["home_match"]):
            best[dealer.id] = {
                "distance_rank": dist,
                "home_match": home,
                "via_tehsil": area.tehsil_id,
            }
        dealers[dealer.id] = dealer
    if not best:
        return []

    ids = list(best)
    since = now - timedelta(days=90)
    stat_rows = (
        await session.execute(
            select(
                LeadRoute.dealer_id,
                func.count().filter(LeadRoute.responded_at.is_not(None)),
                func.count().filter(LeadRoute.status == "re_routed"),
            )
            .where(LeadRoute.dealer_id.in_(ids), LeadRoute.created_at >= since)
            .group_by(LeadRoute.dealer_id)
        )
    ).all()
    stats = {d: (ok, bad) for d, ok, bad in stat_rows}
    day_start = now.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    today = dict(
        (
            await session.execute(
                select(LeadRoute.dealer_id, func.count())
                .where(LeadRoute.dealer_id.in_(ids), LeadRoute.created_at >= day_start)
                .group_by(LeadRoute.dealer_id)
            )
        ).all()
    )

    ranked: list[tuple[Dealer, dict]] = []
    for did, reason in best.items():
        dealer = dealers[did]
        ok, bad = stats.get(did, (0, 0))
        # New dealers start at 0.5 so they get a fair first chance.
        rate = ok / (ok + bad) if ok + bad >= 3 else 0.5
        left = dealer.routing_daily_cap - today.get(did, 0)
        if left <= 0:
            continue
        reason = {**reason, "response_rate": round(rate, 3), "capacity_left": left}
        ranked.append((dealer, reason))
    ranked.sort(
        key=lambda x: (
            x[1]["distance_rank"],
            not x[1]["home_match"],
            -x[1]["response_rate"],
            -x[1]["capacity_left"],
            x[0].name,
        )
    )
    return ranked[: settings.lead_routing_candidates]


# ---------------------------------------------------------------- create / assign


async def create_interest(
    session: AsyncSession, *, farmer_id: UUID, data: InterestCreateIn, now: datetime | None = None
) -> BuyingInterest:
    now = now or datetime.now(UTC)
    farmer = await session.get(Farmer, farmer_id)
    if farmer is None or farmer.status != "active":
        raise RoutingError("no_such_farmer", 404)

    recent = await session.scalar(
        select(func.count())
        .select_from(BuyingInterest)
        .where(
            BuyingInterest.farmer_id == farmer_id,
            BuyingInterest.created_at >= now - timedelta(hours=24),
        )
    )
    if (recent or 0) >= settings.farmer_interest_daily_limit:
        raise RoutingError("too_many_requests", 429)

    brand = data.brand_hint.strip() if data.brand_hint else None
    dup = await session.scalar(
        select(BuyingInterest.id).where(
            BuyingInterest.farmer_id == farmer_id,
            BuyingInterest.status.in_(OPEN_STATUSES),
            func.lower(func.coalesce(BuyingInterest.brand_hint, "")) == (brand or "").lower(),
        )
    )
    if dup is not None:
        raise RoutingError("already_open", 409)

    if data.consent_version != CONSENT_VERSION:
        raise RoutingError("stale_consent_text", 409)
    lang, text = consent_text(data.consent_language or farmer.language)
    consent = FarmerConsent(
        farmer_id=farmer_id,
        purpose=PURPOSE,
        text_version=CONSENT_VERSION,
        language=lang,
        text_shown=text,
        granted=True,
        channel=data.channel,
        recorded_at=now,
    )
    session.add(consent)
    await session.flush()

    ranked = await rank_candidates(session, tehsil_id=farmer.tehsil_id, brand_hint=brand, now=now)
    interest = BuyingInterest(
        farmer_id=farmer_id,
        consent_id=consent.id,
        tehsil_id=farmer.tehsil_id,
        brand_hint=brand,
        hp_min=data.hp_min,
        hp_max=data.hp_max,
        timeline=data.timeline,
        notes=data.notes,
        status="routing",
        candidate_dealer_ids=[d.id for d, _ in ranked],
        reroute_count=0,
    )
    session.add(interest)
    await session.flush()
    reasons = {d.id: r for d, r in ranked}
    await _assign_next(session, interest, farmer, now, reasons)
    return interest


async def _dealer_owner(session: AsyncSession, dealer_id: UUID) -> User | None:
    return await session.scalar(
        select(User)
        .where(User.dealer_id == dealer_id, User.role == "owner", User.active.is_(True))
        .order_by(User.created_at)
        .limit(1)
    )


def _model_interest(i: BuyingInterest) -> str:
    parts = [i.brand_hint or "Any brand"]
    if i.hp_min or i.hp_max:
        parts.append(f"{i.hp_min or '?'}-{i.hp_max or '?'} HP")
    return " · ".join(parts)


async def _assign_next(
    session: AsyncSession,
    interest: BuyingInterest,
    farmer: Farmer,
    now: datetime,
    reasons: dict[UUID, dict] | None = None,
) -> LeadRoute | None:
    tried = set(
        (
            await session.scalars(
                select(LeadRoute.dealer_id).where(LeadRoute.interest_id == interest.id)
            )
        ).all()
    )
    route = None
    if interest.reroute_count <= settings.lead_routing_max_reroutes:
        for dealer_id in interest.candidate_dealer_ids:
            if dealer_id in tried:
                continue
            dealer = await session.get(Dealer, dealer_id)
            if dealer is None or dealer.verified_at is None or dealer.status != "active":
                continue  # lost verification since ranking
            owner = await _dealer_owner(session, dealer_id)
            if owner is None:
                continue
            route = await _create_route(
                session,
                interest,
                farmer,
                dealer,
                owner,
                len(tried) + 1,
                now,
                (reasons or {}).get(dealer_id, {}),
            )
            break

    if route is None:
        interest.status = "waitlist"
        interest.current_dealer_id = None
        interest.current_dealer_name = None
        interest.current_dealer_phone = None
    await session.flush()
    return route


async def _create_route(
    session: AsyncSession,
    interest: BuyingInterest,
    farmer: Farmer,
    dealer: Dealer,
    owner: User,
    attempt: int,
    now: datetime,
    reason: dict,
) -> LeadRoute:
    account = await session.get(Account, farmer.account_id)
    village = await session.get(Village, farmer.village_id) if farmer.village_id else None
    customer, _ = await create_or_get_by_phone(
        session,
        dealer.id,
        CustomerCreateIn(
            name=farmer.display_name,
            phone=account.phone,
            language=farmer.language,
            village=village.name_en if village else None,
            notes="Via Agrodesk Guide",
            consent_whatsapp=True,
            consent_call=True,
        ),
    )
    # The farmer just consented to this dealer contacting them.
    customer.consent_call = True
    customer.consent_whatsapp = True

    sla_due = add_business_hours(now, settings.lead_routing_sla_hours, dealer.business_hours)
    lead = Lead(
        dealer_id=dealer.id,
        customer_id=customer.id,
        source="agrodesk_guide",
        model_interest=_model_interest(interest)[:200],
        stage="new",
        score="hot" if interest.timeline == "now" else "warm",
        owner_user_id=owner.id,
        next_action_at=sla_due,
        created_via="routing",
    )
    session.add(lead)
    await session.flush()
    route = LeadRoute(
        interest_id=interest.id,
        dealer_id=dealer.id,
        lead_id=lead.id,
        attempt=attempt,
        status="pending",
        rank_reason=reason,
        sla_due_at=sla_due,
        created_at=now,
    )
    session.add(route)
    _write_event(
        session,
        dealer_id=dealer.id,
        lead_id=lead.id,
        type_="routed",
        payload={
            "interest_id": str(interest.id),
            "consent_id": str(interest.consent_id),
            "attempt": attempt,
            "sla_due_at": sla_due.isoformat(),
            "timeline": interest.timeline,
            "notes": interest.notes,
        },
        actor_type="system",
        actor_id=None,
    )
    await _upsert_task_for_next_action(session, lead)

    interest.status = "assigned"
    interest.current_dealer_id = dealer.id
    interest.current_dealer_name = dealer.name
    interest.current_dealer_phone = dealer.whatsapp_number
    await session.flush()
    return route


# ---------------------------------------------------------------- dealer response


async def mark_responded(session: AsyncSession, lead: Lead, now: datetime | None = None) -> None:
    """Called from dealer-side lead actions (dealer RLS context). Stops the SLA clock."""
    if lead.source != "agrodesk_guide":
        return
    await session.execute(
        update(LeadRoute)
        .where(LeadRoute.lead_id == lead.id, LeadRoute.status == "pending")
        .values(status="responded", responded_at=now or datetime.now(UTC))
    )


# ---------------------------------------------------------------- SLA sweep


async def _close_lead(
    session: AsyncSession, lead_id: UUID, reason: str, event: str, payload: dict, now: datetime
) -> None:
    lead = await session.get(Lead, lead_id)
    if lead is None:
        return
    if lead.stage not in ("won", "lost"):
        lead.stage = "lost"
        lead.lost_reason = reason
    await session.execute(
        update(Task)
        .where(Task.lead_id == lead_id, Task.status == "pending")
        .values(status="skipped", completed_at=now)
    )
    _write_event(
        session,
        dealer_id=lead.dealer_id,
        lead_id=lead_id,
        type_=event,
        payload=payload,
        actor_type="system",
        actor_id=None,
    )


async def process_due_routes(now: datetime | None = None, batch: int = 100) -> dict:
    """Re-route every pending route past its SLA. Safe to run concurrently
    (SKIP LOCKED) and repeatedly."""
    now = now or datetime.now(UTC)
    rerouted = waitlisted = 0
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        due = (
            await s.scalars(
                select(LeadRoute)
                .where(LeadRoute.status == "pending", LeadRoute.sla_due_at <= now)
                .order_by(LeadRoute.sla_due_at)
                .limit(batch)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for route in due:
            route.status = "re_routed"
            route.closed_at = now
            await _close_lead(
                s,
                route.lead_id,
                "rerouted_sla",
                "re_routed",
                {
                    "interest_id": str(route.interest_id),
                    "sla_due_at": route.sla_due_at.isoformat(),
                    "note": "No response within SLA; the farmer was routed to another dealer.",
                },
                now,
            )
            interest = await s.get(BuyingInterest, route.interest_id, with_for_update=True)
            if interest is None or interest.status not in OPEN_STATUSES:
                continue
            interest.reroute_count += 1
            farmer = await s.get(Farmer, interest.farmer_id)
            nxt = await _assign_next(s, interest, farmer, now)
            if nxt is None:
                waitlisted += 1
            else:
                rerouted += 1
    return {"expired": len(due), "rerouted": rerouted, "waitlisted": waitlisted}


# ---------------------------------------------------------------- farmer cancel


async def cancel_interest(
    session: AsyncSession, *, farmer_id: UUID, interest_id: UUID, now: datetime | None = None
) -> BuyingInterest:
    now = now or datetime.now(UTC)
    interest = await session.get(BuyingInterest, interest_id, with_for_update=True)
    if interest is None or interest.farmer_id != farmer_id:
        raise RoutingError("not_found", 404)
    if interest.status not in (*OPEN_STATUSES, "waitlist"):
        raise RoutingError("not_open", 409)
    routes = (
        await session.scalars(
            select(LeadRoute).where(
                LeadRoute.interest_id == interest.id,
                LeadRoute.status.in_(("pending", "responded")),
            )
        )
    ).all()
    for r in routes:
        r.status = "closed"
        r.closed_at = now
        await _close_lead(
            session,
            r.lead_id,
            "farmer_cancelled",
            "farmer_cancelled",
            {"interest_id": str(interest.id)},
            now,
        )
    interest.status = "cancelled"
    await session.flush()
    return interest
