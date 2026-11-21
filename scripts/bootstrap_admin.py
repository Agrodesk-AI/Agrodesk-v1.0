"""Create the first platform admin. Run once from the repo root:

    cd apps/api && python -m scripts.bootstrap_admin "+919999999999" "Prasad"

(or set BOOTSTRAP_PHONE / BOOTSTRAP_NAME in env)."""
import asyncio
import os
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import User
from app.security.phone import normalize_phone
from app.security.tenant import set_tenant_context


async def main(phone: str, name: str) -> None:
    normalized = normalize_phone(phone)
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        existing = await s.scalar(select(User).where(User.phone == normalized))
        if existing is not None:
            print(f"platform admin already exists: {existing.id}")
            return
        u = User(dealer_id=None, name=name, phone=normalized, role="platform_admin")
        s.add(u)
        await s.flush()
        print(f"created platform admin {u.id} ({normalized})")


if __name__ == "__main__":
    phone = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BOOTSTRAP_PHONE", "")
    name = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("BOOTSTRAP_NAME", "Platform Admin")
    if not phone:
        print("usage: python -m scripts.bootstrap_admin <phone> [name]", file=sys.stderr)
        sys.exit(2)
    asyncio.run(main(phone, name))
