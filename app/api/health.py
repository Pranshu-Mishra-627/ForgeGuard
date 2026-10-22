"""Health check endpoint."""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Lightweight service liveness check.

    Must remain responsive and NOT fail solely because upstream engine is offline.
    """
    return HealthResponse(
        status="healthy",
        service="forgeguard-orchestration",
        version="1.0.0",
    )
