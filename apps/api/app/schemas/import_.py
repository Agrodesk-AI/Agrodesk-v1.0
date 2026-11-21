from pydantic import BaseModel, Field


class ImportMapping(BaseModel):
    """Maps a canonical field to the header name in the uploaded file."""

    phone: str
    name: str
    model_interest: str | None = None
    source: str | None = None
    campaign: str | None = None
    ad_name: str | None = None
    next_action_at: str | None = None


class ImportRowError(BaseModel):
    row: int  # 1-indexed; header is row 1
    field: str | None
    message: str


class ImportResult(BaseModel):
    total: int = Field(description="Data rows read (excludes the header row)")
    created: int
    updated: int
    skipped: int
    errors: list[ImportRowError] = []
    dry_run: bool = False
