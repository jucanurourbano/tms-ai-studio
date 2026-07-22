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
    CLAUDE_MODEL: str = "claude-sonnet-5"
    CLAUDE_TIMEOUT: int = 180
    # max_tokens de salida por llamada. El default de ChatAnthropic (4096) es
    # COMPARTIDO con los tokens de razonamiento (bloques thinking); la dimensión
    # más grande (requirements, ~10 RF con evidencia) truncaba su JSON a mitad
    # (JSONDecodeError) mientras las pequeñas cabían. Se sube para dar holgura.
    CLAUDE_MAX_TOKENS: int = 8192
    CLAUDE_PRICE_INPUT_PER_MTOK: float = 3
    CLAUDE_PRICE_OUTPUT_PER_MTOK: float = 15

    # --- Infraestructura (contenedores de docker-compose) ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://tms:tms_dev_password@localhost:5432/tms_ai_studio"
    )
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Pipeline del Agente EF ---
    MAX_UPLOAD_MB: int = 10
    STORAGE_DIR: str = str(BASE_DIR / "storage")
    SINGLE_SHOT_TOKEN_THRESHOLD: int = 4096
    EXTRACT_CONCURRENCY: int = 3
    # Gate del EF hacia el Agente Scrum (semáforo compuesto, condición Y):
    # sin preguntas blocking pendientes Y contenido mínimo de RF funcionales Y
    # cobertura de extracción suficiente. Antes bastaba con no tener blocking,
    # así que el semáforo salía VERDE con 0 requisitos funcionales.
    EF_GATE_MIN_FUNCTIONAL: int = 1
    EF_GATE_MIN_COVERAGE: float = 1.0

    # --- Pipeline del Agente Scrum ---
    SCRUM_SPRINT_CAPACITY: int = 20  # D4: puntos por sprint (configurable)
    SCRUM_COVERAGE_THRESHOLD: float = 1.0  # D5: RF cubiertos por >=1 historia

    # --- Integración ClickUp (cuenta COMPARTIDA: guard fail-closed) ---
    # Sin allowlist configurada, el módulo NO escribe nada (ver CLAUDE.md).
    CLICKUP_API_TOKEN: str = ""
    CLICKUP_WORKSPACE_ID: str = ""  # team
    CLICKUP_SPACE_ID: str = ""  # espacio de Sistemas (único autorizado)
    CLICKUP_FOLDER_ID: str = ""  # opcional
    CLICKUP_ALLOWED_LIST_IDS: list[str] = []  # allowlist explícita de listas
    CLICKUP_DRY_RUN: bool = True  # fase (b): por defecto no crea nada

    # --- Autenticación (JWT) ---
    # JWT_SECRET firma los access tokens. El default es SOLO para arrancar en
    # desarrollo sin ``.env``; en producción se define uno fuerte en el entorno y
    # se ROTA periódicamente (rotarlo invalida todos los tokens vigentes). Nunca
    # se registran contraseñas ni tokens en logs (ver CLAUDE.md).
    JWT_SECRET: str = "dev-insecure-secret-cambiar-en-produccion"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 12  # 12 h

    # --- CORS (desarrollo: abierto) ---
    CORS_ORIGINS: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia cacheada de la configuración."""
    return Settings()


settings = get_settings()
