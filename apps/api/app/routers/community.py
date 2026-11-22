"""Community feed + moderation queue endpoints."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_farmer, require_role
from app.deps.db import get_session_platform, get_session_tenant
from app.models import Farmer, Post
from app.schemas.community import (
    DecisionIn,
    FeedOut,
    ModerationItemOut,
    PostDetailOut,
    PostIn,
    PostOut,
    ReplyIn,
    ReplyOut,
    ReportIn,
    Tab,
)
from app.services import community_service as svc

router = APIRouter(prefix="/v1/community", tags=["community"])
admin_router = APIRouter(prefix="/v1/admin/moderation", tags=["admin"])


def _me(p: dict) -> UUID:
    return UUID(p["farmer_id"])


def _err(e: svc.CommunityError):
    raise HTTPException(e.status, e.code) from None


@router.get("/feed", response_model=FeedOut)
async def feed(
    tab: Tab = "all",
    page: int = Query(default=1, ge=1, le=50),
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> FeedOut:
    try:
        return await svc.feed(s, _me(p), tab, page)
    except svc.CommunityError as e:
        _err(e)


@router.get("/posts/mine", response_model=list[PostOut])
async def my_posts(
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> list[PostOut]:
    farmer = await s.get(Farmer, _me(p))
    rows = (
        await s.scalars(
            select(Post)
            .where(Post.farmer_id == _me(p), Post.status != "archived")
            .order_by(Post.created_at.desc())
            .limit(50)
        )
    ).all()
    return await svc.posts_out(s, list(rows), farmer)


@router.post("/posts", response_model=PostOut, status_code=201)
async def create_post(
    body: PostIn,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> PostOut:
    try:
        post = await svc.create_post(s, _me(p), body)
    except svc.CommunityError as e:
        _err(e)
    farmer = await s.get(Farmer, _me(p))
    return (await svc.posts_out(s, [post], farmer))[0]


@router.get("/posts/{post_id}", response_model=PostDetailOut)
async def get_post(
    post_id: UUID,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_tenant),
) -> PostDetailOut:
    try:
        return await svc.post_detail(s, _me(p), post_id)
    except svc.CommunityError as e:
        _err(e)


@router.delete("/posts/{post_id}", status_code=204)
async def archive_post(
    post_id: UUID,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> None:
    try:
        await svc.archive_post(s, _me(p), post_id)
    except svc.CommunityError as e:
        _err(e)


@router.post("/posts/{post_id}/replies", response_model=ReplyOut, status_code=201)
async def reply(
    post_id: UUID,
    body: ReplyIn,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> ReplyOut:
    try:
        r = await svc.create_reply(s, _me(p), post_id, body.body)
    except svc.CommunityError as e:
        _err(e)
    return ReplyOut(
        id=r.id,
        author_name=r.author_name,
        is_mine=True,
        body=r.body,
        status=r.status,
        created_at=r.created_at,
    )


@router.put("/posts/{post_id}/helpful", status_code=204)
async def mark_helpful(
    post_id: UUID,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> None:
    try:
        await svc.set_helpful(s, _me(p), post_id, True)
    except svc.CommunityError as e:
        _err(e)


@router.delete("/posts/{post_id}/helpful", status_code=204)
async def unmark_helpful(
    post_id: UUID,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> None:
    try:
        await svc.set_helpful(s, _me(p), post_id, False)
    except svc.CommunityError as e:
        _err(e)


@router.post("/reports", status_code=204)
async def report(
    body: ReportIn,
    p: dict = Depends(get_current_farmer),
    s: AsyncSession = Depends(get_session_platform),
) -> None:
    try:
        await svc.report(s, _me(p), body.target_type, body.target_id, body.reason, body.note)
    except svc.CommunityError as e:
        _err(e)


# ---------------- admin ----------------


@admin_router.get("", response_model=list[ModerationItemOut])
async def queue(
    status: Literal["open", "closed"] = "open",
    _: dict = Depends(require_role("platform_admin")),
    s: AsyncSession = Depends(get_session_platform),
) -> list[ModerationItemOut]:
    return await svc.queue_items(s, status)


@admin_router.post("/{item_id}/decide", response_model=ModerationItemOut)
async def decide(
    item_id: UUID,
    body: DecisionIn,
    p: dict = Depends(require_role("platform_admin")),
    s: AsyncSession = Depends(get_session_platform),
) -> ModerationItemOut:
    try:
        it = await svc.decide(s, UUID(p["user_id"]), item_id, body.decision, body.note)
    except svc.CommunityError as e:
        _err(e)
    items = await svc.queue_items(s, "closed")
    return next(i for i in items if i.id == it.id)
