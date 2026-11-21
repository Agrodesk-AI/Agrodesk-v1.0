from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.security.tenant import set_tenant_context


async def get_session_platform(request: Request) -> AsyncIterator[AsyncSession]:
    """Session with platform-admin context (pre-auth, bootstrap, admin routes)."""
    async with SessionLocal() as s:
        async with s.begin():
            await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
            yield s


async def get_session_tenant(request: Request) -> AsyncIterator[AsyncSession]:
    """Session scoped to the authenticated user's tenant."""
    principal = getattr(request.state, "principal", None)
    if principal is None:
        # Route is misconfigured; Depends(get_current_user) should run first.
        raise RuntimeError("tenant session requested without authentication")
    async with SessionLocal() as s:
        async with s.begin():
            await set_tenant_context(
                s,
                dealer_id=str(principal["dealer_id"]) if principal["dealer_id"] else None,
                is_platform_admin=principal["role"] == "platform_admin",
            )
            yield s
