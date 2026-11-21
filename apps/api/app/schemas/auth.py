from pydantic import BaseModel, Field


class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=6, max_length=20)


class OtpRequestOut(BaseModel):
    ok: bool = True
    retry_after_seconds: int | None = None


class OtpVerifyIn(BaseModel):
    phone: str
    code: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str
