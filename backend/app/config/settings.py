"""Configuración central de la aplicación.

Carga las variables de entorno desde el archivo ``.env`` ubicado en la raíz del
repositorio usando ``pydantic-settings``. Los valores por defecto permiten
arrancar en desarrollo sin ``.env`` presente.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

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

    # --- Proveedor de LLM (ver ai/llm/ y docs/diseno-multiproveedor-llm.md) ---
    # `anthropic` es el default IRRENUNCIABLE: sin nada configurado el sistema
    # usa Anthropic. Los overrides son por rol (gana sobre el global) y el modelo
    # se elige por PROVEEDOR, no por rol.
    #   LLM_ROLE_OVERRIDES='{"qa": "gemini"}'
    #   LLM_MODEL_OVERRIDES='{"gemini": "gemini-2.5-flash-lite"}'
    LLM_PROVIDER: str = "anthropic"
    LLM_ROLE_OVERRIDES: dict[str, str] = {}
    LLM_MODEL_OVERRIDES: dict[str, str] = {}

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

    # --- Pipeline del Agente Arquitectura ---
    # Umbrales del *scope profile* determinista (A2) que clasifican el tamaño del
    # alcance y fundamentan la recomendación de estilo (monolito modular por
    # defecto). score <= SMALL_MAX => S; score >= LARGE_MIN => L; en medio => M.
    ARCH_SIZE_SMALL_MAX: int = 8
    ARCH_SIZE_LARGE_MIN: int = 25
    # Cobertura mínima (épicas/entidades) para el contenido mínimo del semáforo.
    ARCH_COVERAGE_THRESHOLD: float = 1.0

    # --- Pipeline del Agente BD ---
    # Concurrencia del map de TABLES (una pasada por entidad del EF).
    BD_TABLES_CONCURRENCY: int = 3
    # Cobertura mínima de ENTIDADES para el contenido mínimo del semáforo. La de
    # campos/validaciones/reglas NO entra al gate: genera preguntas (mismo criterio
    # que los RNF en Arquitectura).
    BD_COVERAGE_THRESHOLD: float = 1.0
    # Tope de índices NO derivados de FK por tabla, para evitar sobre-indexado. Los
    # descartados quedan como Observation (nunca un cap silencioso).
    BD_MAX_INDEXES_PER_TABLE: int = 3

    # --- Pipeline del Agente API ---
    # Concurrencia del map de SCHEMAS (una pasada por recurso).
    API_SCHEMAS_CONCURRENCY: int = 3
    # Cobertura mínima de TABLAS EXPUESTAS y de APIs declaradas por el EF para el
    # contenido mínimo del semáforo. Las celdas CRUD, las reglas y los actores NO
    # entran al gate: generan preguntas (mismo criterio que los campos en BD).
    API_COVERAGE_THRESHOLD: float = 1.0

    # --- Pipeline del Agente QA ---
    # Concurrencia de los map de TEST_DESIGN y EDGE_CASES (uno por criterio).
    QA_MAP_CONCURRENCY: int = 3
    # Cobertura mínima de los criterios de historias `must`/`should` para el
    # semáforo (QA-D5). Los criterios de historias `could`/`wont` sin caso son
    # advertencia y NO entran al gate: así "criterio sin caso = advertencia" y el
    # umbral del 100% dejan de contradecirse.
    QA_COVERAGE_THRESHOLD: float = 1.0
    # Techo de casos por criterio. Existe por aritmética: 40 historias x 5
    # criterios x 4 tipos son 800 casos, y cada caso de más es tiempo de una
    # persona ejecutándolo. Lo que se poda deja Observation con su id.
    QA_MAX_CASES_PER_CRITERION: int = 6

    # --- Modo C del Agente QA: exploración de una URL viva ---
    # Esto conduce un navegador AUTENTICADO contra una aplicación desplegada, así
    # que hereda las cuatro capas fail-closed de la introspección de BD y añade
    # una quinta que aquella no necesitaba (una base de datos no redirige; una
    # aplicación web sí). Ver ai/agents/qa/explore/.
    #   1. Desactivado por defecto.
    #   2. El cliente manda un ALIAS, nunca una URL: si mandara la URL, quien
    #      pudiera lanzar exploraciones podría apuntar el navegador a cualquier
    #      host (SSRF). Y el destino transporta la credencial de la cuenta de QA,
    #      que por definición no viene del cliente.
    #   3. Allowlist de hosts EXPLÍCITA: lista vacía significa "nada autorizado".
    #   4. La credencial nunca sale (ni artefacto, ni log, ni respuesta).
    #   5. La allowlist se re-verifica en CADA navegación.
    # Cada destino se declara así (JSON en el .env), y `readonly_verified: true`
    # es OBLIGATORIO: sin una cuenta de solo lectura en la aplicación explorada,
    # lo único que separa una escritura de producción de nosotros son nuestras
    # propias capas.
    #   QA_EXPLORE_TARGETS='{"tms-qa": {"url": "https://tms.interno/",
    #                                   "readonly_verified": true}}'
    # `data_class` es "real" salvo que el host sea LOCAL (A2): explorar el entorno
    # de desarrollo propio con semillas sintéticas no es una fuente real, y sin esa
    # excepción —verificada por candado, no por confianza— el Modo C sería
    # imposible de probar de punta a punta sin gastar saldo del proveedor.
    QA_EXPLORE_ENABLED: bool = False
    QA_EXPLORE_TARGETS: dict[str, dict[str, Any]] = {}
    QA_EXPLORE_ALLOWED_HOSTS: list[str] = []
    # Radio de acción. Enteros POSITIVOS: un 0 no significa "sin límite", es
    # inválido (QA-D25.4). Un crawler sin techo contra una aplicación viva es un
    # generador de carga, y un ejecutor de pruebas —que es otro agente— necesita
    # corridas sin techo: no poder pedirlas es parte de la frontera.
    QA_EXPLORE_MAX_PAGES: int = 50
    QA_EXPLORE_MAX_DEPTH: int = 3
    QA_EXPLORE_TIMEOUT_MS: int = 15000
    QA_EXPLORE_TOTAL_BUDGET_S: int = 300
    QA_EXPLORE_MAX_CLICKS_PER_PAGE: int = 8

    # --- Inventario de Sistemas ---
    # Tamaño máximo del dump DDL que se acepta subir (.sql). Un dump completo de
    # producción puede ser enorme y no aporta más esquema por ser más largo.
    INVENTORY_MAX_DDL_MB: int = 5
    # Concurrencia del map de extracción de conocimiento desde documentos (INV3).
    # Mismo criterio que EXTRACT_CONCURRENCY del EF.
    INVENTORY_EXTRACT_CONCURRENCY: int = 3
    # Introspección read-only de bases de datos EXTERNAS. Fail-closed en tres
    # niveles y por el mismo motivo que el guard de ClickUp: esto se conecta a
    # producción.
    #   1. Desactivada por defecto.
    #   2. El cliente manda un ALIAS, nunca una cadena de conexión: si mandara el
    #      DSN, quien pudiera escribir en el inventario podría apuntar el servidor
    #      a cualquier host (SSRF). Los destinos posibles los fija el despliegue.
    #   3. Allowlist de hosts EXPLÍCITA: lista vacía significa "nada autorizado".
    # Las cadenas viven aquí (entorno del despliegue), NUNCA en la base de datos
    # de la plataforma ni en un artefacto, y jamás se devuelven por la API.
    INVENTORY_INTROSPECTION_ENABLED: bool = False
    INVENTORY_INTROSPECTION_DSNS: dict[str, str] = {}
    INVENTORY_INTROSPECTION_ALLOWED_HOSTS: list[str] = []

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
