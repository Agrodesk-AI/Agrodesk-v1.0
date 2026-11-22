from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_GUCS = ("app.current_dealer", "app.current_farmer", "app.current_account")


async def set_tenant_context(
    session: AsyncSession,
    *,
    dealer_id: str | None,
    is_platform_admin: bool,
    farmer_id: str | None = None,
    account_id: str | None = None,
) -> None:
    """Bind tenant settings to this transaction. Uses SET LOCAL so it dies with the tx."""
    values = {
        "app.current_dealer": dealer_id or "",
        "app.current_farmer": farmer_id or "",
        "app.current_account": account_id or "",
        "app.is_platform_admin": "true" if is_platform_admin else "false",
    }
    for key, value in values.items():
        await session.execute(text("SELECT set_config(:k, :v, true)"), {"k": key, "v": value})


async def clear_tenant_context(session: AsyncSession) -> None:
    for key in _GUCS:
        await session.execute(text("SELECT set_config(:k, '', true)"), {"k": key})
    await session.execute(text("SELECT set_config('app.is_platform_admin', 'false', true)"))
