from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings

# Profile kinds carried in tokens.
#   staff   -> sub = users.id (dealer owner/staff, platform admin)
#   farmer  -> sub = farmers.id
#   account -> sub = accounts.id, no profile yet (onboarding only)
KIND_STAFF = "staff"
KIND_FARMER = "farmer"
KIND_ACCOUNT = "account"


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    user_id: str,
    role: str,
    dealer_id: str | None,
    *,
    kind: str = KIND_STAFF,
    account_id: str | None = None,
) -> str:
    now = _now()
    payload = {
        "sub": user_id,
        "role": role,
        "dealer_id": dealer_id,
        "kind": kind,
        "acct": account_id,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str, *, kind: str = KIND_STAFF) -> str:
    now = _now()
    payload = {
        "sub": user_id,
        "kind": kind,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.refresh_token_days)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise ValueError(str(e)) from e
