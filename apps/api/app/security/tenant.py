from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant_context(
    session: AsyncSession, *, dealer_id: str | None, is_platform_admin: bool
) -> None:
    """Bind tenant settings to this transaction. Uses SET LOCAL so it dies with the tx."""
    # Force a transaction so SET LOCAL has scope.
    await session.execute(
        text("SELECT set_config('app.current_dealer', :v, true)"),
        {"v": dealer_id or ""},
    )
    await session.execute(
        text("SELECT set_config('app.is_platform_admin', :v, true)"),
        {"v": "true" if is_platform_admin else "false"},
    )


async def clear_tenant_context(session: AsyncSession) -> None:
    await session.execute(text("SELECT set_config('app.current_dealer', '', true)"))
    await session.execute(text("SELECT set_config('app.is_platform_admin', 'false', true)"))
