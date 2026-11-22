from fastapi import FastAPI

from app.routers import (
    auth, catalogue, customers, dealers, imports, kb, leads, me, tasks, users, webhooks,
)

app = FastAPI(title="Agrodesk API", version="0.1.0")

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
