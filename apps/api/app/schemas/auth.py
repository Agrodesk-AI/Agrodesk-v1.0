from pydantic import BaseModel, Field


class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=6, max_length=20)


class OtpRequestOut(BaseModel):
    ok: bool = True
    retry_after_seconds: int | None = None


class OtpVerifyIn(BaseModel):
    phone: str
    code: str
    profile_id: str | None = None  # pick a profile up front; default = staff, then farmer


class Profile(BaseModel):
    id: str
    kind: str  # staff | farmer
    role: str
    dealer_id: str | None
    display_name: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    # kind of the profile these tokens are for: staff | farmer | account (needs onboarding)
    active_kind: str = "staff"
    active_profile_id: str | None = None
    profiles: list[Profile] = []


class RefreshIn(BaseModel):
    refresh_token: str


class SwitchProfileIn(BaseModel):
    profile_id: str
