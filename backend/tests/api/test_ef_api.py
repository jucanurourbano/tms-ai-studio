"""Tests de la API del Agente EF (Bloque 8) con grafo/pipeline mockeado."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.services.ef_service as ef_service
from ai.agents.ef.schemas.examples import example_artifact
from app.config.settings import settings
from app.dependencies.database import get_session
from app.models.ef import JobStatus
from app.repositories.ef_repository import EFRepository
from main import app

TEXTO_LARGO = (
    "Proceso de registro de siniestros logísticos. " * 5
    + "El operador registra el siniestro asociándolo a su guía y actualiza su "
    "estado hasta el recupero económico."
)


@pytest_asyncio.fixture
async def client(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session

    async def fake_pipeline(job_id, source, authoritative_context=None):
        async with factory() as session:
            repo = EFRepository(session)
            art = example_artifact().model_dump(mode="json")
            await repo.save_artifact(job_id, art, art["schema_version"])
            await repo.update_job_metrics(job_id, art["metrics"])
            await repo.update_job_status(job_id, JobStatus.COMPLETED)
            await session.commit()

    monkeypatch.setattr(ef_service, "run_ef_pipeline", fake_pipeline)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


async def test_health_envelope(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"


async def test_analyze_crea_job_y_recupera_artifact(client):
    r = await client.post(
        "/api/v1/ef/analyze", json={"content": TEXTO_LARGO, "title": "Siniestros"}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["cached"] is False
    job_id = data["job_id"]

    # El background (mockeado) ya persistió el artefacto.
    r = await client.get(f"/api/v1/ef/jobs/{job_id}")
    assert r.json()["data"]["status"] == "COMPLETED"

    r = await client.get(f"/api/v1/ef/jobs/{job_id}/artifact")
    art = r.json()["data"]
    assert art["schema_version"] == "1.2.0"
    assert art["entities"][0]["name"] == "Siniestro"


async def test_analyze_idempotente_cached(client):
    payload = {"content": TEXTO_LARGO, "title": "Siniestros"}
    first = (await client.post("/api/v1/ef/analyze", json=payload)).json()["data"]
    second = (await client.post("/api/v1/ef/analyze", json=payload)).json()["data"]
    assert second["cached"] is True
    assert second["job_id"] == first["job_id"]


async def test_analyze_texto_corto_400(client):
    r = await client.post("/api/v1/ef/analyze", json={"content": "muy corto"})
    assert r.status_code == 400
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "IngestError"


async def test_content_type_no_soportado_400(client):
    r = await client.post(
        "/api/v1/ef/analyze", content=b"texto", headers={"content-type": "text/plain"}
    )
    assert r.status_code == 400
    assert r.json()["success"] is False


async def test_listado_paginado(client):
    await client.post("/api/v1/ef/analyze", json={"content": TEXTO_LARGO, "title": "A"})
    r = await client.get("/api/v1/ef/jobs?limit=10&offset=0")
    data = r.json()["data"]
    assert data["total"] >= 1
    assert "items" in data


async def test_ciclo_validacion_ready_for_next_stage(client):
    job_id = (
        await client.post("/api/v1/ef/analyze", json={"content": TEXTO_LARGO})
    ).json()["data"]["job_id"]

    # El artefacto de ejemplo tiene una pregunta blocking Q-001 pendiente.
    summary = (await client.get(f"/api/v1/ef/jobs/{job_id}/validations")).json()["data"]
    assert summary["ready_for_next_stage"] is False
    assert "Q-001" in summary["blocking_pending"]

    # Confirmar la pregunta blocking.
    r = await client.patch(
        f"/api/v1/ef/jobs/{job_id}/validations",
        json={
            "target_type": "question",
            "target_id": "Q-001",
            "status": "confirmado",
            "respuesta": "El jefe de operaciones autoriza el cierre.",
        },
    )
    assert r.status_code == 200

    summary = (await client.get(f"/api/v1/ef/jobs/{job_id}/validations")).json()["data"]
    assert summary["ready_for_next_stage"] is True
    assert summary["blocking_pending"] == []


async def test_refine_crea_job_hijo(client):
    parent_id = (
        await client.post("/api/v1/ef/analyze", json={"content": TEXTO_LARGO})
    ).json()["data"]["job_id"]

    await client.patch(
        f"/api/v1/ef/jobs/{parent_id}/validations",
        json={
            "target_type": "question",
            "target_id": "Q-001",
            "status": "confirmado",
            "respuesta": "El jefe de operaciones autoriza el cierre.",
        },
    )

    r = await client.post(f"/api/v1/ef/jobs/{parent_id}/refine")
    assert r.status_code == 200
    child = r.json()["data"]
    assert child["parent_job_id"] == parent_id
    assert child["job_id"] != parent_id
