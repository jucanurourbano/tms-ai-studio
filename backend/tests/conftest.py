"""Fixtures compartidas de tests.

Provee una base de datos async efímera (SQLite in-memory con StaticPool, para
que la conexión persista entre sesiones) sin depender de contenedores, y un
**cortafuegos contra la API real de Anthropic** (REGLA DE PRESUPUESTO).
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


@pytest.fixture(autouse=True)
def sin_api_real(monkeypatch: pytest.MonkeyPatch) -> None:
    """Impide que un test alcance la API real de Anthropic.

    Los nodos generativos caen en ``ClaudeLLMClient`` cuando nadie les inyecta un
    mock por ``config``. Si un test nuevo se olvida de inyectarlo, el pipeline
    intentaría una llamada real: precisamente lo que prohíbe la REGLA DE
    PRESUPUESTO de ``CLAUDE.md``. Aquí ese descuido falla con un mensaje claro en
    vez de salir a la red.

    Es autouse a propósito: la protección no puede depender de que cada test se
    acuerde de pedirla.
    """

    def _boom(*_args, **_kwargs):
        raise AssertionError(
            "Un test intentó usar el cliente REAL de Anthropic. Inyecta un mock "
            "en config['configurable']['llm'] (ver tests/mocks.py). "
            "REGLA DE PRESUPUESTO: nunca se llama a la API real en tests."
        )

    monkeypatch.setattr("app.dependencies.claude.get_claude_client", _boom)


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
