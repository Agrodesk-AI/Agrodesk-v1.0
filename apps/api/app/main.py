from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import assert_rls_enforced
from app.routers import (
    auth,
    catalogue,
    community,
    customers,
    dealers,
    farmer,
    imports,
    kb,
    leads,
    locations,
    me,
    rentals,
    routing,
    tasks,
    trust,
    users,
    webhooks,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await assert_rls_enforced()
    yield


app = FastAPI(title="Agrodesk API", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(dealers.router)
app.include_router(users.router)
app.include_router(customers.router)
app.include_router(leads.router)
app.include_router(tasks.router)
app.include_router(imports.router)
app.include_router(webhooks.router)
app.include_router(kb.router)
app.include_router(catalogue.router)
app.include_router(farmer.router)
app.include_router(locations.router)
app.include_router(locations.admin_router)
app.include_router(routing.farmer_router)
app.include_router(routing.dealer_router)
app.include_router(routing.admin_router)
app.include_router(rentals.router)
app.include_router(rentals.admin_router)
app.include_router(community.router)
app.include_router(community.admin_router)
app.include_router(trust.router)
app.include_router(trust.admin_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
