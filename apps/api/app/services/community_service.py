"""Community feed (design §3.4) + moderation queue (§3.8).

Reads (feed, post detail) run in the farmer's RLS context.
Writes (post, reply, report, helpful) run in platform context with explicit
ownership checks, because they also write the admin-only moderation queue.
"""

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ContentReport,
    Farmer,
    ModerationItem,
    Post,
    PostHelpful,
    PostReply,
    Tehsil,
)
from app.schemas.community import (
    TAB_KINDS,
    FeedOut,
    ModerationItemOut,
    PostDetailOut,
    PostIn,
    PostOut,
    ReplyOut,
)
from app.services import location_service, moderation

PAGE_SIZE = 20
WIDEN_BELOW = 10  # first page thinner than this -> widen to the whole district
HELPFUL_VISIBLE_AT = 10
REPORTS_TO_HIDE = 3
MODERATION_SLA = timedelta(hours=24)
POSTS_PER_HOUR = 5
REPLIES_PER_HOUR = 30
FEED_WINDOW = timedelta(days=30)
RECENCY_HALF_LIFE_H = 48.0
TTL: dict[str, timedelta | None] = {
    "price_report": timedelta(days=3),
    "need_equipment": timedelta(days=14),
    "offer_equipment": timedelta(days=14),
    "scheme_alert": timedelta(days=30),
    "ask": None,
    "experience": None,
}
LOCALITY = {"village": 1.0, "tehsil": 0.7, "nearby": 0.4, "district": 0.1}


class CommunityError(Exception):
    def __init__(self, code: str, status: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


# ---------------------------------------------------------------- ranking


def score(locality: str, created_at: datetime, helpful: int, now: datetime) -> float:
    """0.6·locality + 0.3·recency + 0.1·helpfulness (design §3.4)."""
    age_h = max((now - created_at).total_seconds() / 3600, 0)
    recency = math.pow(0.5, age_h / RECENCY_HALF_LIFE_H)
    helpfulness = min(helpful, 20) / 20
    return 0.6 * LOCALITY[locality] + 0.3 * recency + 0.1 * helpfulness


def _locality(post: Post, farmer: Farmer, ranks: dict[int, int]) -> str:
    if post.tehsil_id == farmer.tehsil_id:
        if farmer.village_id and post.village_id == farmer.village_id:
            return "village"
        return "tehsil"
    r = ranks.get(post.tehsil_id)
    if r is not None and 0 < r < location_service.FALLBACK_RANK:
        return "nearby"
    return "district"


async def _visible_area(session: AsyncSession, farmer: Farmer, widen: bool) -> dict[int, int]:
    ranks = {t.id: r for t, r in await location_service.nearby_tehsils(session, farmer.tehsil_id)}
    if widen:
        district_id = await session.scalar(
            select(Tehsil.district_id).where(Tehsil.id == farmer.tehsil_id)
        )
        others = (
            await session.scalars(select(Tehsil.id).where(Tehsil.district_id == district_id))
        ).all()
        for tid in others:
            ranks.setdefault(tid, location_service.FALLBACK_RANK)
    return ranks


async def feed(
    session: AsyncSession, farmer_id: UUID, tab: str, page: int, now: datetime | None = None
) -> FeedOut:
    now = now or datetime.now(UTC)
    farmer = await session.get(Farmer, farmer_id)
    if farmer is None:
        raise CommunityError("no_such_farmer", 404)
    kinds = TAB_KINDS[tab]

    async def candidates(ranks: dict[int, int]) -> list[Post]:
        q = select(Post).where(
            Post.status == "published",
            Post.tehsil_id.in_(ranks.keys()),
            Post.created_at >= now - FEED_WINDOW,
            (Post.expires_at.is_(None)) | (Post.expires_at > now),
        )
        if kinds:
            q = q.where(Post.kind.in_(kinds))
        return list((await session.scalars(q.order_by(Post.created_at.desc()).limit(500))).all())

    ranks = await _visible_area(session, farmer, widen=False)
    rows = await candidates(ranks)
    if len(rows) < WIDEN_BELOW:
        wider = await _visible_area(session, farmer, widen=True)
        if len(wider) > len(ranks):
            ranks = wider
            rows = await candidates(ranks)

    scored = sorted(
        rows,
        key=lambda p: (
            -score(_locality(p, farmer, ranks), p.created_at, p.helpful_count, now),
            p.created_at,
        ),
    )
    start = (page - 1) * PAGE_SIZE
    chunk = scored[start : start + PAGE_SIZE]
    items = await posts_out(session, chunk, farmer, ranks)
    return FeedOut(items=items, page=page, has_more=len(scored) > start + PAGE_SIZE)


async def posts_out(
    session: AsyncSession, rows: list[Post], farmer: Farmer, ranks: dict[int, int] | None = None
) -> list[PostOut]:
    names = (
        dict(
            (
                await session.execute(
                    select(Tehsil.id, Tehsil.name_en).where(
                        Tehsil.id.in_({p.tehsil_id for p in rows})
                    )
                )
            ).all()
        )
        if rows
        else {}
    )
    mine = (
        set(
            (
                await session.scalars(
                    select(PostHelpful.post_id).where(
                        PostHelpful.farmer_id == farmer.id,
                        PostHelpful.post_id.in_([p.id for p in rows]),
                    )
                )
            ).all()
        )
        if rows
        else set()
    )
    return [
        PostOut(
            id=p.id,
            kind=p.kind,
            author_name=p.author_name,
            is_mine=p.farmer_id == farmer.id,
            tehsil_id=p.tehsil_id,
            tehsil_name=names.get(p.tehsil_id, ""),
            locality=_locality(p, farmer, ranks) if ranks is not None else None,
            language=p.language,
            body=p.body,
            tags=p.tags,
            status=p.status,
            helpful_count=p.helpful_count if p.helpful_count >= HELPFUL_VISIBLE_AT else None,
            i_found_helpful=p.id in mine,
            reply_count=p.reply_count,
            expires_at=p.expires_at,
            created_at=p.created_at,
        )
        for p in rows
    ]


async def post_detail(session: AsyncSession, farmer_id: UUID, post_id: UUID) -> PostDetailOut:
    farmer = await session.get(Farmer, farmer_id)
    post = await session.get(Post, post_id)  # RLS: published or own
    if farmer is None or post is None:
        raise CommunityError("not_found", 404)
    replies = (
        await session.scalars(
            select(PostReply)
            .where(PostReply.post_id == post_id)
            .order_by(PostReply.created_at)
            .limit(200)
        )
    ).all()  # RLS: published or own
    base = (await posts_out(session, [post], farmer))[0]
    return PostDetailOut(
        **base.model_dump(),
        replies=[
            ReplyOut(
                id=r.id,
                author_name=r.author_name,
                is_mine=r.farmer_id == farmer_id,
                body=r.body,
                status=r.status,
                created_at=r.created_at,
            )
            for r in replies
        ],
    )


# ---------------------------------------------------------------- writes (platform ctx)


async def _queue(
    session: AsyncSession,
    target_type: str,
    target_id: UUID,
    source: str,
    reasons: list[str],
    now: datetime,
) -> None:
    """One open item per target; later signals merge into it."""
    item = await session.scalar(
        select(ModerationItem)
        .where(
            ModerationItem.target_type == target_type,
            ModerationItem.target_id == target_id,
            ModerationItem.status == "open",
        )
        .with_for_update()
    )
    if item is None:
        session.add(
            ModerationItem(
                target_type=target_type,
                target_id=target_id,
                source=source,
                reasons=reasons,
                status="open",
                sla_due_at=now + MODERATION_SLA,
                created_at=now,
            )
        )
    else:
        item.reasons = sorted(set(item.reasons) | set(reasons))
    await session.flush()


async def _author(session: AsyncSession, farmer_id: UUID) -> Farmer:
    f = await session.get(Farmer, farmer_id)
    if f is None or f.status != "active":
        raise CommunityError("no_such_farmer", 404)
    return f


async def create_post(
    session: AsyncSession, farmer_id: UUID, data: PostIn, now: datetime | None = None
) -> Post:
    now = now or datetime.now(UTC)
    f = await _author(session, farmer_id)
    n = await session.scalar(
        select(func.count())
        .select_from(Post)
        .where(Post.farmer_id == farmer_id, Post.created_at >= now - timedelta(hours=1))
    )
    if (n or 0) >= POSTS_PER_HOUR:
        raise CommunityError("too_many_posts", 429)

    tag_text = " ".join(str(v) for v in data.tags.model_dump().values() if v)
    verdict = await moderation.moderate(
        f"{data.body} {tag_text}", kind=data.kind, language=f.language
    )
    if verdict.action == "block":
        raise CommunityError(f"blocked:{','.join(verdict.reasons)}")
    ttl = TTL[data.kind]
    post = Post(
        farmer_id=f.id,
        author_name=f.display_name,
        kind=data.kind,
        tehsil_id=f.tehsil_id,
        village_id=f.village_id,
        language=f.language,
        body=data.body.strip(),
        tags=data.tags.model_dump(exclude_none=True),
        status="published" if verdict.action == "approve" else "in_review",
        moderation=verdict.as_dict(),
        expires_at=now + ttl if ttl else None,
    )
    session.add(post)
    await session.flush()
    if verdict.action == "flag":
        await _queue(session, "post", post.id, verdict.layer, verdict.reasons, now)
    await session.refresh(post)
    return post


async def archive_post(session: AsyncSession, farmer_id: UUID, post_id: UUID) -> None:
    post = await session.get(Post, post_id)
    if post is None or post.farmer_id != farmer_id:
        raise CommunityError("not_found", 404)
    if post.status != "removed":
        post.status = "archived"
    await session.flush()


async def create_reply(
    session: AsyncSession, farmer_id: UUID, post_id: UUID, body: str, now: datetime | None = None
) -> PostReply:
    now = now or datetime.now(UTC)
    f = await _author(session, farmer_id)
    post = await session.get(Post, post_id)
    if post is None or (post.status != "published" and post.farmer_id != farmer_id):
        raise CommunityError("not_found", 404)
    if post.status != "published":
        raise CommunityError("post_not_open", 409)
    n = await session.scalar(
        select(func.count())
        .select_from(PostReply)
        .where(PostReply.farmer_id == farmer_id, PostReply.created_at >= now - timedelta(hours=1))
    )
    if (n or 0) >= REPLIES_PER_HOUR:
        raise CommunityError("too_many_replies", 429)
    verdict = await moderation.moderate(body, kind="reply", language=f.language)
    if verdict.action == "block":
        raise CommunityError(f"blocked:{','.join(verdict.reasons)}")
    reply = PostReply(
        post_id=post_id,
        farmer_id=farmer_id,
        author_name=f.display_name,
        body=body.strip(),
        status="published" if verdict.action == "approve" else "in_review",
        moderation=verdict.as_dict(),
        created_at=now,
    )
    session.add(reply)
    await session.flush()
    if verdict.action == "flag":
        await _queue(session, "reply", reply.id, verdict.layer, verdict.reasons, now)
    return reply


async def set_helpful(session: AsyncSession, farmer_id: UUID, post_id: UUID, on: bool) -> None:
    post = await session.get(Post, post_id)
    if post is None or post.status != "published":
        raise CommunityError("not_found", 404)
    if post.farmer_id == farmer_id:
        raise CommunityError("own_post")
    if on:
        try:
            async with session.begin_nested():
                session.add(
                    PostHelpful(post_id=post_id, farmer_id=farmer_id, created_at=datetime.now(UTC))
                )
                await session.flush()
        except IntegrityError:
            pass  # already marked: idempotent
    else:
        await session.execute(
            delete(PostHelpful).where(
                PostHelpful.post_id == post_id, PostHelpful.farmer_id == farmer_id
            )
        )


async def report(
    session: AsyncSession,
    farmer_id: UUID,
    target_type: str,
    target_id: UUID,
    reason: str,
    note: str | None,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    model = Post if target_type == "post" else PostReply
    target = await session.get(model, target_id)
    if target is None or target.status != "published":
        raise CommunityError("not_found", 404)
    if target.farmer_id == farmer_id:
        raise CommunityError("own_content")
    try:
        async with session.begin_nested():
            session.add(
                ContentReport(
                    target_type=target_type,
                    target_id=target_id,
                    reporter_farmer_id=farmer_id,
                    reason=reason,
                    note=note,
                    created_at=now,
                )
            )
            await session.flush()
    except IntegrityError:
        raise CommunityError("already_reported", 409) from None
    # Only reports since the last human decision count toward auto-hide, so an
    # approved post isn't re-hidden by one new report on top of old ones.
    last_decided = await session.scalar(
        select(func.max(ModerationItem.decided_at)).where(
            ModerationItem.target_type == target_type, ModerationItem.target_id == target_id
        )
    )
    count_q = (
        select(func.count())
        .select_from(ContentReport)
        .where(ContentReport.target_type == target_type, ContentReport.target_id == target_id)
    )
    if last_decided is not None:
        count_q = count_q.where(ContentReport.created_at > last_decided)
    count = await session.scalar(count_q)
    await _queue(session, target_type, target_id, "reports", [f"report:{reason}"], now)
    if count >= REPORTS_TO_HIDE:
        target.status = "in_review"  # hide until a human decides
    await session.flush()


# ---------------------------------------------------------------- admin queue


async def queue_items(
    session: AsyncSession, status: str, now: datetime | None = None
) -> list[ModerationItemOut]:
    now = now or datetime.now(UTC)
    items = (
        await session.scalars(
            select(ModerationItem)
            .where(ModerationItem.status == status)
            .order_by(ModerationItem.sla_due_at)
            .limit(200)
        )
    ).all()
    out = []
    for it in items:
        model = Post if it.target_type == "post" else PostReply
        target = await session.get(model, it.target_id)
        reports = await session.scalar(
            select(func.count())
            .select_from(ContentReport)
            .where(
                ContentReport.target_type == it.target_type,
                ContentReport.target_id == it.target_id,
            )
        )
        out.append(
            ModerationItemOut(
                id=it.id,
                target_type=it.target_type,
                target_id=it.target_id,
                source=it.source,
                reasons=it.reasons,
                status=it.status,
                sla_due_at=it.sla_due_at,
                overdue=it.status == "open" and it.sla_due_at < now,
                body=target.body if target else None,
                author_name=target.author_name if target else None,
                report_count=reports or 0,
                decision=it.decision,
                created_at=it.created_at,
            )
        )
    return out


async def decide(
    session: AsyncSession, admin_id: UUID, item_id: UUID, decision: str, note: str | None
) -> ModerationItem:
    it = await session.get(ModerationItem, item_id, with_for_update=True)
    if it is None:
        raise CommunityError("not_found", 404)
    if it.status != "open":
        raise CommunityError("already_decided", 409)
    model = Post if it.target_type == "post" else PostReply
    target = await session.get(model, it.target_id, with_for_update=True)
    if target is not None and target.status != "archived":
        target.status = "published" if decision == "approve" else "removed"
        target.moderation = {**(target.moderation or {}), "human": decision, "note": note}
    it.status = "closed"
    it.decision = decision
    it.decided_by = admin_id
    it.note = note
    it.decided_at = datetime.now(UTC)
    await session.flush()
    return it
