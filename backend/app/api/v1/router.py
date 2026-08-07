"""Router principal de la API v1.

Agrega los routers de cada recurso bajo el prefijo ``/api/v1``.
"""

from fastapi import APIRouter

from app.api.v1 import apis, arquitectura, auth, bd, ef, health, scrum

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(ef.router)
api_router.include_router(scrum.router)
api_router.include_router(arquitectura.router)
api_router.include_router(bd.router)
api_router.include_router(apis.router)
