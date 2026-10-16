from fastapi import APIRouter

from app.core.config import APP_VERSION
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="codedna-api",
        version=APP_VERSION,
    )
