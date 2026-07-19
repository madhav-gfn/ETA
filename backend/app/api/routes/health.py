"""Basic liveness route — confirms the API process is up and settings load."""

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "service": "urbanair-intel-backend",
    }
