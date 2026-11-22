from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.security.jwt import KIND_ACCOUNT, KIND_FARMER, KIND_STAFF, decode_token

bearer = HTTPBearer(auto_error=False)


async def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """Any authenticated token: staff, farmer, or account-only (onboarding)."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_bearer")
    try:
        payload = decode_token(creds.credentials)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token") from None
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong_token_type")
    kind = payload.get("kind") or KIND_STAFF  # tokens minted before kinds existed
    principal = {
        "kind": kind,
        "user_id": payload["sub"],
        "role": payload["role"],
        "dealer_id": payload.get("dealer_id"),
        "account_id": payload.get("acct"),
        "farmer_id": payload["sub"] if kind == KIND_FARMER else None,
    }
    if kind == KIND_ACCOUNT:
        principal["account_id"] = payload["sub"]
    request.state.principal = principal
    return principal


async def get_current_user(principal: dict = Depends(get_principal)) -> dict:
    """Dealer staff / platform admin only. Every dealer-side route depends on this,
    so a farmer or onboarding token can never reach dealer data."""
    if principal["kind"] != KIND_STAFF:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "staff_only")
    return principal


async def get_current_farmer(principal: dict = Depends(get_principal)) -> dict:
    if principal["kind"] != KIND_FARMER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "farmer_only")
    return principal


def require_role(*roles: str):
    async def checker(principal: dict = Depends(get_current_user)) -> dict:
        if principal["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
        return principal

    return checker
