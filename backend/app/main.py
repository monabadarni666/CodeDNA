from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.repositories import (
    router as repositories_router,
)
from app.core.config import (
    APP_DESCRIPTION,
    APP_NAME,
    APP_VERSION,
)

app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
)

app.include_router(
    health_router,
    prefix="/api/v1",
)

app.include_router(
    repositories_router,
    prefix="/api/v1",
)


@app.get("/", tags=["General"])
def root() -> dict[str, str]:
    return {
        "message": "Welcome to CodeDNA API",
        "version": APP_VERSION,
    }
