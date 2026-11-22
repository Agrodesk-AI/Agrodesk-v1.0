import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


log = logging.getLogger(__name__)


class RlsBypassRoleError(RuntimeError):
    """The DB role would bypass row-level security, disabling tenant isolation."""


async def assert_rls_enforced(eng=None) -> None:
    """Refuse to run as a role that bypasses RLS (superuser or BYPASSRLS).

    Superusers ignore RLS even with FORCE ROW LEVEL SECURITY, so every tenant
    policy would be silently off. Opt-out (local only): ALLOW_RLS_BYPASS_ROLE=true.
    """
    eng = eng or engine
    async with eng.connect() as conn:
        row = (await conn.execute(text(
            "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
            "WHERE rolname = current_user"
        ))).one()
    user, is_super, bypass = row
    if not (is_super or bypass):
        return
    msg = (
        f"DATABASE_URL connects as '{user}' (superuser={is_super}, bypassrls={bypass}): "
        "row-level security is NOT enforced and tenants can read each other's data. "
        "Connect as the app role (agrodesk_app); keep the owner role for "
        "MIGRATIONS_DATABASE_URL only."
    )
    if settings.env == "local" and settings.allow_rls_bypass_role:
        log.error("RLS GUARD OVERRIDDEN: %s", msg)
        return
    raise RlsBypassRoleError(msg)
