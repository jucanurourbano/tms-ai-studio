"""Configuración central de la aplicación.

Carga las variables de entorno desde el archivo ``.env`` ubicado en la raíz del
repositorio usando ``pydantic-settings``. Los valores por defecto permiten
arrancar en desarrollo sin ``.env`` presente.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repositorio: backend/app/config/settings.py -> parents[3] = raíz.
BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Ajustes de la aplicación leídos desde el entorno / archivo ``.env``."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Aplicación ---
    APP_NAME: str = "TMS AI Studio"
    APP_ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # --- Anthropic / Claude ---
    # En desarrollo y tests SIEMPRE se usan mocks; la clave se deja vacía a
    # propósito (ver REGLA DE PRESUPUESTO en CLAUDE.md).
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_TIMEOUT: int = 180
    CLAUDE_PRICE_INPUT_PER_MTOK: float = 3
    CLAUDE_PRICE_OUTPUT_PER_MTOK: float = 15

    # --- Infraestructura (contenedores de docker-compose) ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://tms:tms_dev_password@localhost:5432/tms_ai_studio"
    )
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- CORS (desarrollo: abierto) ---
    CORS_ORIGINS: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia cacheada de la configuración."""
    return Settings()


settings = get_settings()
