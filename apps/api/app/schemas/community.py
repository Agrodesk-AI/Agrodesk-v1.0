from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

PostKind = Literal[
    "ask", "need_equipment", "offer_equipment", "price_report", "scheme_alert", "experience"
]
Tab = Literal["all", "ask", "market", "equipment", "alerts", "stories"]
TAB_KINDS: dict[str, tuple[str, ...] | None] = {
    "all": None,
    "ask": ("ask",),
    "market": ("price_report",),
    "equipment": ("need_equipment", "offer_equipment"),
    "alerts": ("scheme_alert",),
    "stories": ("experience",),
}
ReportReason = Literal["spam", "scam", "abuse", "wrong_info", "other"]


class PriceTags(BaseModel):
    crop: str = Field(min_length=2, max_length=60)
    price_paise: int = Field(gt=0, le=100_000_000)
    unit: Literal["quintal", "kg", "tonne", "dozen", "crate"]
    market: str | None = Field(default=None, max_length=100)


class PostTags(BaseModel):
    crop: str | None = Field(default=None, max_length=60)
    equipment: str | None = Field(default=None, max_length=60)
    price_paise: int | None = Field(default=None, gt=0, le=100_000_000)
    unit: str | None = Field(default=None, max_length=20)
    market: str | None = Field(default=None, max_length=100)


class PostIn(BaseModel):
    kind: PostKind
    body: str = Field(min_length=3, max_length=2000)
    tags: PostTags = PostTags()

    @model_validator(mode="after")
    def _kind_tags(self):
        if self.kind == "price_report":
            # a price report is only useful with crop + price + unit
            PriceTags.model_validate(self.tags.model_dump())
        return self


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


class ReportIn(BaseModel):
    target_type: Literal["post", "reply"]
    target_id: UUID
    reason: ReportReason
    note: str | None = Field(default=None, max_length=500)


class ReplyOut(BaseModel):
    id: UUID
    author_name: str
    is_mine: bool
    body: str
    status: str
    created_at: datetime


class PostOut(BaseModel):
    id: UUID
    kind: str
    author_name: str
    is_mine: bool
    tehsil_id: int
    tehsil_name: str
    locality: Literal["village", "tehsil", "nearby", "district"] | None = None
    language: str
    body: str
    tags: dict
    status: str
    # hidden below a threshold so early posts don't show "0 helpful"
    helpful_count: int | None
    i_found_helpful: bool
    reply_count: int
    expires_at: datetime | None
    created_at: datetime


class PostDetailOut(PostOut):
    replies: list[ReplyOut]


class FeedOut(BaseModel):
    items: list[PostOut]
    page: int
    has_more: bool


class ModerationItemOut(BaseModel):
    id: UUID
    target_type: str
    target_id: UUID
    source: str
    reasons: list
    status: str
    sla_due_at: datetime
    overdue: bool
    body: str | None
    author_name: str | None
    report_count: int
    decision: str | None
    created_at: datetime


class DecisionIn(BaseModel):
    decision: Literal["approve", "remove"]
    note: str | None = Field(default=None, max_length=1000)
