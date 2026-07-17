"""Router principal de la API v1.

Agrega los routers de cada recurso bajo el prefijo ``/api/v1``.
"""

from fastapi import APIRouter

from app.api.v1 import ef, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(ef.router)
