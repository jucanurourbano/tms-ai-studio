"""Tests del filtro por grupo de estado y los contadores del historial.

El filtro se aplica EN LA CONSULTA, así que se comprueba que la paginación de cada
pestaña es real (total del filtro, no de todo) y que los contadores se calculan
sobre todos los jobs del agente, no sobre la página traída.

Los jobs se siembran directamente en la BD: ningún test ejecuta un agente.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.dependencies.database import get_session
from app.models.agent import AgentJob, AgentType, JobStatus
from main import app

PASSWORD = "superseguro1"

# Mezcla deliberada: dos estados caen en el grupo "en_proceso" y hay jobs de otro
# agente para verificar que los contadores no se contaminan entre agentes.
SIEMBRA_EF = [
    JobStatus.COMPLETED,
    JobStatus.COMPLETED,
    JobStatus.COMPLETED,
    JobStatus.COMPLETED_WITH_WARNINGS,
    JobStatus.COMPLETED_WITH_WARNINGS,
    JobStatus.RUNNING,
    JobStatus.PENDING,
    JobStatus.NEEDS_INPUT,
    JobStatus.FAILED,
    JobStatus.FAILED,
]
SIEMBRA_SCRUM = [JobStatus.COMPLETED, JobStatus.FAILED]


@pytest_asyncio.fixture
async def client(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sembrado(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        for status in SIEMBRA_EF:
            s.add(AgentJob(agent_type=AgentType.EF, status=status, title="EF job"))
        for status in SIEMBRA_SCRUM:
            s.add(
                AgentJob(agent_type=AgentType.SCRUM, status=status, title="Scrum job")
            )
        await s.commit()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _admin(client) -> str:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@urbano.com.pe",
            "full_name": "Admin Uno",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 200, r.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@urbano.com.pe", "password": PASSWORD},
    )
    return login.json()["data"]["access_token"]


# --- contadores --------------------------------------------------------------


async def test_contadores_por_grupo_del_agente_ef(client, sembrado):
    token = await _admin(client)
    r = await client.get("/api/v1/ef/jobs", headers=_auth(token))
    assert r.status_code == 200
    counts = r.json()["data"]["status_counts"]
    assert counts == {
        "completados": 3,
        "avisos": 2,
        "en_proceso": 3,  # RUNNING + PENDING + NEEDS_INPUT
        "fallidos": 2,
        "todos": 10,
    }


async def test_los_contadores_no_se_mezclan_entre_agentes(client, sembrado):
    """El historial de Scrum cuenta solo jobs Scrum."""
    token = await _admin(client)
    counts = (await client.get("/api/v1/scrum/jobs", headers=_auth(token))).json()[
        "data"
    ]["status_counts"]
    assert counts == {
        "completados": 1,
        "avisos": 0,
        "en_proceso": 0,
        "fallidos": 1,
        "todos": 2,
    }


async def test_contadores_siempre_traen_las_cinco_claves(client):
    """Sin jobs, los cinco grupos vienen a 0 (el cliente no rellena huecos)."""
    token = await _admin(client)
    counts = (await client.get("/api/v1/ef/jobs", headers=_auth(token))).json()["data"][
        "status_counts"
    ]
    assert counts == {
        "completados": 0,
        "avisos": 0,
        "en_proceso": 0,
        "fallidos": 0,
        "todos": 0,
    }


# --- filtro ------------------------------------------------------------------


@pytest.mark.parametrize(
    "grupo,esperados,estados",
    [
        ("completados", 3, {"COMPLETED"}),
        ("avisos", 2, {"COMPLETED_WITH_WARNINGS"}),
        ("en_proceso", 3, {"RUNNING", "PENDING", "NEEDS_INPUT"}),
        ("fallidos", 2, {"FAILED"}),
        ("todos", 10, None),
    ],
)
async def test_filtro_por_grupo(client, sembrado, grupo, esperados, estados):
    token = await _admin(client)
    r = await client.get(f"/api/v1/ef/jobs?estado={grupo}", headers=_auth(token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # `total` es el del FILTRO, no el global: es lo que pagina cada pestaña.
    assert data["total"] == esperados
    assert len(data["items"]) == esperados
    assert data["estado"] == grupo
    if estados is not None:
        assert {i["status"] for i in data["items"]} <= estados


async def test_sin_estado_devuelve_todos(client, sembrado):
    """El default de la API es `todos`; el default de "completados" es de la UI."""
    token = await _admin(client)
    data = (await client.get("/api/v1/ef/jobs", headers=_auth(token))).json()["data"]
    assert data["estado"] == "todos"
    assert data["total"] == 10


async def test_la_paginacion_respeta_el_filtro(client, sembrado):
    """Paginar dentro de una pestaña no arrastra jobs de otros estados."""
    token = await _admin(client)
    p1 = (
        await client.get(
            "/api/v1/ef/jobs?estado=completados&limit=2&offset=0", headers=_auth(token)
        )
    ).json()["data"]
    p2 = (
        await client.get(
            "/api/v1/ef/jobs?estado=completados&limit=2&offset=2", headers=_auth(token)
        )
    ).json()["data"]

    assert p1["total"] == 3 and p2["total"] == 3
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1
    # Sin solapamiento y todos completados.
    ids1 = {i["job_id"] for i in p1["items"]}
    ids2 = {i["job_id"] for i in p2["items"]}
    assert ids1.isdisjoint(ids2)
    assert all(i["status"] == "COMPLETED" for i in p1["items"] + p2["items"])


async def test_grupo_invalido_rechazado(client):
    token = await _admin(client)
    r = await client.get("/api/v1/ef/jobs?estado=inventado", headers=_auth(token))
    assert r.status_code == 422


async def test_arquitectura_tambien_filtra(client, sembrado):
    """El patrón es el mismo en los tres historiales."""
    token = await _admin(client)
    r = await client.get(
        "/api/v1/arquitectura/jobs?estado=completados", headers=_auth(token)
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["estado"] == "completados"
    assert "status_counts" in data
