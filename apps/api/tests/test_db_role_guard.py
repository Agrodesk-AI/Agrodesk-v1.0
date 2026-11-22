"""Guards against running with a role that bypasses row-level security."""
import pytest
from sqlalchemy import text

from app.core import db
from app.core.config import settings


@pytest.mark.asyncio
async def test_test_suite_runs_as_rls_enforced_role():
    # If this fails, every cross-tenant test is meaningless: point
    # TEST_DATABASE_URL at the agrodesk_app role, not the owner/superuser.
    async with db.engine.connect() as conn:
        is_super, bypass = (await conn.execute(text(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ))).one()
    assert not is_super and not bypass
    await db.assert_rls_enforced()


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _FakeConn:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _stmt):
        return _FakeResult(self._row)


class _FakeEngine:
    def __init__(self, row):
        self._row = row

    def connect(self):
        return _FakeConn(self._row)


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [("agrodesk", True, True), ("svc", False, True)])
async def test_guard_refuses_bypass_roles(row, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "allow_rls_bypass_role", True)  # ignored outside local
    with pytest.raises(db.RlsBypassRoleError):
        await db.assert_rls_enforced(_FakeEngine(row))


@pytest.mark.asyncio
async def test_guard_local_opt_out(monkeypatch):
    monkeypatch.setattr(settings, "env", "local")
    monkeypatch.setattr(settings, "allow_rls_bypass_role", False)
    with pytest.raises(db.RlsBypassRoleError):
        await db.assert_rls_enforced(_FakeEngine(("agrodesk", True, True)))
    monkeypatch.setattr(settings, "allow_rls_bypass_role", True)
    await db.assert_rls_enforced(_FakeEngine(("agrodesk", True, True)))
