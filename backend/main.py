"""Punto de entrada de la aplicación FastAPI de TMS AI Studio.

Arrancar en desarrollo (desde backend/, con el venv activo):
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config.settings import settings
from app.core.logger import logger
from app.middlewares.exceptions import register_exception_handlers
from app.services.spend_sink import install_db_sink


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación (arranque / apagado)."""
    # El libro mayor de gasto se instala aquí y en ningún otro sitio. Mientras no
    # esté instalado, el sumidero por defecto NIEGA toda llamada al modelo
    # (GAS-D7): un despliegue mal configurado deja de funcionar en vez de gastar
    # sin medir. Es el orden correcto del error.
    install_db_sink()
    logger.info(
        "Aplicación %s inicializada (env=%s, modelo=%s)",
        settings.APP_NAME,
        settings.APP_ENV,
        settings.CLAUDE_MODEL,
    )
    yield
    logger.info("Aplicación %s detenida", settings.APP_NAME)


def create_app() -> FastAPI:
    """Construye e inicializa la instancia de FastAPI."""
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description=(
            "Plataforma interna de Urbano TI que asiste al ciclo de vida del "
            "desarrollo mediante agentes de IA (ISDF)."
        ),
        lifespan=lifespan,
    )

    # CORS abierto para desarrollo. allow_credentials=False es obligatorio cuando
    # allow_origins usa el comodín "*" (los navegadores rechazan la combinación).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    register_exception_handlers(app)
    return app


app = create_app()
