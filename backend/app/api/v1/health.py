"""Endpoint de salud del servicio."""

from fastapi import APIRouter

from app.config.settings import settings
from shared.responses.api_response import ApiResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[dict])
async def health() -> ApiResponse[dict]:
    """Verifica que el servicio está operativo."""
    data = {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "version": "0.1.0",
    }
    return ApiResponse.ok(data=data, message="Servicio operativo")
