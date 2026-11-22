import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root for `packages`

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://agrodesk:agrodesk@localhost:5432/agrodesk_test",
    ),
)

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.db import engine
from app.main import app


@pytest_asyncio.fixture(loop_scope="session")
async def truncate_db():
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform_admin = 'true'"))
        await conn.execute(text(
            "TRUNCATE kb_chunks, kb_documents, dealer_models, tractor_catalogue, "
            "outbox, messages, conversations, job_runs, tasks, lead_events, "
            "rental_ratings, rental_booking_events, rental_bookings, rental_needs, "
            "equipment_listings, lead_routes, buying_interests, farmer_consents, "
            "leads, consents, customers, farmers, dealer_service_areas, users, accounts, "
            "otp_codes, tehsil_neighbours, villages, tehsils, districts, states, dealers "
            "RESTART IDENTITY CASCADE"
        ))
    yield


@pytest_asyncio.fixture(loop_scope="session")
async def client(truncate_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
