from fastapi import FastAPI

from app.routers import auth, dealers, me, users

app = FastAPI(title="Agrodesk API", version="0.1.0")

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(dealers.router)
app.include_router(users.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
