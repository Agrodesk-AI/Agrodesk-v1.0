from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    body: str | None = None
    source: str | None = None
    language: str = "en"
    tags: list[str] = []
    shared: bool = False  # platform-admin only when True


class DocumentOut(BaseModel):
    id: UUID
    dealer_id: UUID | None
    title: str
    source: str | None
    language: str
    tags: list[str]
    last_verified_at: datetime | None
    created_at: datetime


class UploadResult(BaseModel):
    document: DocumentOut
    chunks: int


class SearchHit(BaseModel):
    chunk_id: UUID
    document_id: UUID
    title: str
    source: str | None
    language: str
    text: str
    score: float
    dealer_id: UUID | None


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHit]
