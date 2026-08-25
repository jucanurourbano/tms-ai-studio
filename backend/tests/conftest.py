"""Fixtures compartidas de tests.

Provee una base de datos async efímera (SQLite in-memory con StaticPool, para
que la conexión persista entre sesiones) sin depender de contenedores, y el
**cortafuegos contra las llamadas reales** (REGLA DE PRESUPUESTO), cuyas cuatro
capas viven en ``tests/firewall.py``.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from tests import firewall


@pytest.fixture(autouse=True)
def sin_api_real(monkeypatch: pytest.MonkeyPatch) -> None:
    """Capa 3 — ``get_claude_client``, la costura histórica del cortafuegos.

    Los nodos generativos caen en ``ClaudeLLMClient`` cuando nadie les inyecta un
    mock por ``config``. Si un test nuevo se olvida de inyectarlo, el pipeline
    intentaría una llamada real: precisamente lo que prohíbe la REGLA DE
    PRESUPUESTO de ``CLAUDE.md``. Aquí ese descuido falla con un mensaje claro en
    vez de salir a la red.

    Se conserva **sin cambios** aunque las capas 1 y 2 la cubran: es el símbolo
    que parchean los tests que ya existen, y quitarla sería cambiar dos cosas a
    la vez en el bloque que viene a garantizar que no se cambia ninguna.

    Es autouse a propósito: la protección no puede depender de que cada test se
    acuerde de pedirla.
    """

    def _boom(*_args, **_kwargs):
        raise AssertionError(firewall.MENSAJE_LLM)

    monkeypatch.setattr("app.dependencies.claude.get_claude_client", _boom)


@pytest.fixture(autouse=True)
def sin_llm_real(monkeypatch: pytest.MonkeyPatch) -> None:
    """Capas 1 y 2 — la fábrica y los constructores de cada SDK.

    Generalizan la capa 3 a **cualquier** proveedor registrado: la 1 por
    construcción (todo lo que salga de ``get_llm``), la 2 para quien se salte la
    fábrica importando el SDK directamente.
    """
    firewall.blindar_fabrica(monkeypatch)
    firewall.blindar_sdks(monkeypatch)


@pytest.fixture
def sdk_construible(monkeypatch: pytest.MonkeyPatch) -> None:
    """Levanta SOLO la capa 2 para los tests cuyo objeto es el constructor.

    No es autouse y hay que pedirla por nombre: construir el cliente no abre
    conexión ni consume tokens, y las capas 1, 3 y 4 siguen puestas — la
    garantía de que no sale un paquete a la red no cambia. Ver
    ``tests/firewall.py::liberar_sdks``.
    """
    firewall.liberar_sdks(monkeypatch)


@pytest.fixture(autouse=True)
def sin_red_externa(monkeypatch: pytest.MonkeyPatch) -> None:
    """Capa 4 — la red. La única que no hay que actualizar nunca.

    Cubre al proveedor que nadie ha escrito todavía, a un ``httpx`` suelto en un
    test nuevo y a un webhook. Los destinos locales (Postgres, Redis, un
    servidor de prueba en ``127.0.0.1``, un socket unix) pasan sin fricción.
    """
    firewall.blindar_red(monkeypatch)


@pytest.fixture(autouse=True)
def sin_inventario_real(monkeypatch: pytest.MonkeyPatch) -> None:
    """Impide que un test abra una conexión real al consultar el inventario.

    La fase RECONCILE (INV4) carga el inventario del sistema destino desde
    Postgres. En la suite eso significaría abrir conexiones de verdad: lento,
    dependiente de que haya contenedor levantado y con resultados que cambian
    según lo que haya en la base local — justo lo que un test no debe tener.

    Por defecto la fase se declara **no ejecutada**, que es exactamente lo que
    ocurre en un despliegue sin inventario, así que el pipeline se ejerce por su
    camino normal. Los tests que SÍ quieren reconciliar inyectan su propia carga
    (``config['configurable']['reconcile_tables']``) o parchean este punto.

    Autouse por el mismo motivo que el cortafuegos de la API de Anthropic: la
    protección no puede depender de que cada test se acuerde de pedirla.
    """

    async def _sin_inventario(system_id=None, **_kwargs):
        return {
            "performed": False,
            "reason": "Inventario no consultado (entorno de pruebas).",
            "assets": [],
        }

    monkeypatch.setattr("ai.inventory.loader.load_target_inventory", _sin_inventario)
    monkeypatch.setattr("ai.inventory.nodes.load_target_inventory", _sin_inventario)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Engine SQLite async in-memory con el esquema creado."""
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sesión async ligada al engine de prueba."""
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        yield s
