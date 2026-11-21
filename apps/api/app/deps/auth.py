from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.security.jwt import decode_token

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_bearer")
    try:
        payload = decode_token(creds.credentials)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token") from None
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong_token_type")
    principal = {
        "user_id": payload["sub"],
        "role": payload["role"],
        "dealer_id": payload.get("dealer_id"),
    }
    request.state.principal = principal
    return principal


def require_role(*roles: str):
    async def checker(principal: dict = Depends(get_current_user)) -> dict:
        if principal["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
        return principal

    return checker
