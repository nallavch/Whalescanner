from fastapi import FastAPI

from app.api.routes import backtests, data_sync, health
from app.core.config import settings

app = FastAPI(title="Quant Platform API", version="0.1.0")

app.include_router(health.router)
app.include_router(backtests.router, prefix="/api/backtests", tags=["backtests"])
app.include_router(data_sync.router, prefix="/api/data-sync", tags=["data-sync"])


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "env": settings.app_env, "status": "ok"}
