"""Tests de la API del Agente Scrum (B6) con pipeline mockeado."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.services.scrum_service as scrum_service
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from app.dependencies.database import get_session
from app.models.agent import EFSourceDocType, JobStatus
from app.repositories.agent_job_repository import AgentJobRepository
from app.repositories.ef_repository import EFRepository
from main import app


@pytest_asyncio.fixture
async def ctx(engine, monkeypatch):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session

    # Semilla: un job EF COMPLETED con el artefacto de ejemplo (Q-001 blocking).
    async with factory() as session:
        repo = EFRepository(session)
        doc = await repo.get_or_create_source_doc("ef-hash", EFSourceDocType.TEXT)
        ef_job = await repo.create_job(doc.id, title="Siniestros", source_type="text")
        art = ef_example().model_dump(mode="json")
        await repo.save_artifact(ef_job.id, art, art["schema_version"])
        await repo.update_job_metrics(ef_job.id, art["metrics"])
        await repo.update_job_status(ef_job.id, JobStatus.COMPLETED)
        await session.commit()
        ef_job_id = ef_job.id

    async def fake_scrum_pipeline(
        job_id,
        ef_job_id,
        ef_artifact,
        ef_hash,
        ef_ready,
        capacity,
        authoritative_context=None,
    ):
        async with factory() as session:
            repo = AgentJobRepository(session)
            art = scrum_example().model_dump(mode="json")
            await repo.save_artifact(job_id, art, art["schema_version"])
            await repo.update_job_metrics(job_id, art["metrics"])
            await repo.update_job_status(job_id, JobStatus.COMPLETED)
            await session.commit()

    monkeypatch.setattr(scrum_service, "run_scrum_pipeline", fake_scrum_pipeline)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, ef_job_id

    app.dependency_overrides.clear()


async def _make_ef_ready(client, ef_job_id):
    await client.patch(
        f"/api/v1/ef/jobs/{ef_job_id}/validations",
        json={
            "target_type": "question",
            "target_id": "Q-001",
            "status": "confirmado",
            "respuesta": "El jefe de operaciones autoriza el cierre.",
        },
    )


async def test_plan_rechazado_si_ef_no_listo(ctx):
    client, ef_job_id = ctx
    r = await client.post("/api/v1/scrum/plans", json={"ef_job_id": ef_job_id})
    assert r.status_code == 409
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "GateError"
    assert "no está listo" in body["message"]


async def test_plan_ef_inexistente_400(ctx):
    client, _ = ctx
    r = await client.post("/api/v1/scrum/plans", json={"ef_job_id": "NOPE"})
    assert r.status_code == 400
    assert r.json()["data"]["code"] == "IngestError"


async def test_plan_ok_y_artifact(ctx):
    client, ef_job_id = ctx
    await _make_ef_ready(client, ef_job_id)

    r = await client.post(
        "/api/v1/scrum/plans", json={"ef_job_id": ef_job_id, "capacity_points": 20}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["input_job_id"] == ef_job_id
    scrum_job_id = data["job_id"]

    r = await client.get(f"/api/v1/scrum/jobs/{scrum_job_id}")
    assert r.json()["data"]["status"] == "COMPLETED"

    r = await client.get(f"/api/v1/scrum/jobs/{scrum_job_id}/artifact")
    art = r.json()["data"]
    assert art["schema_version"] == "1.0.0"
    assert art["source"]["ef_job_id"]
    assert art["stories"][0]["id"] == "US-001"


async def test_semaforo_compuesto_listo(ctx):
    client, ef_job_id = ctx
    await _make_ef_ready(client, ef_job_id)
    scrum_job_id = (
        await client.post("/api/v1/scrum/plans", json={"ef_job_id": ef_job_id})
    ).json()["data"]["job_id"]

    summary = (
        await client.get(f"/api/v1/scrum/jobs/{scrum_job_id}/validations")
    ).json()["data"]
    # El artefacto de ejemplo no tiene preguntas bloqueantes y está completo.
    assert summary["ready_for_next_stage"] is True
    assert summary["checks"]["coverage_met"] is True
    assert summary["checks"]["must_should_estimated"] is True
    assert summary["checks"]["no_must_unassigned"] is True


async def test_listado_scrum_jobs_y_available_ef(ctx):
    client, ef_job_id = ctx
    await _make_ef_ready(client, ef_job_id)
    await client.post("/api/v1/scrum/plans", json={"ef_job_id": ef_job_id})

    jobs = (await client.get("/api/v1/scrum/jobs")).json()["data"]
    assert jobs["total"] >= 1

    item = jobs["items"][0]
    # El plan Scrum hereda el título/fuente del EF de origen (historial).
    assert item["title"] == "Siniestros"
    assert item["source_type"] == "text"
    assert item["version"] == 1
    assert item["input_job_id"] == ef_job_id
    assert item["created_at"] is not None
    assert item["completed_at"] is not None

    ef_jobs = (await client.get("/api/v1/scrum/available-ef-jobs")).json()["data"]
    item = next(i for i in ef_jobs["items"] if i["job_id"] == ef_job_id)
    assert item["ready_for_next_stage"] is True


async def test_export_clickup_csv_y_json(ctx):
    client, ef_job_id = ctx
    await _make_ef_ready(client, ef_job_id)
    scrum_job_id = (
        await client.post("/api/v1/scrum/plans", json={"ef_job_id": ef_job_id})
    ).json()["data"]["job_id"]

    r = await client.get(f"/api/v1/scrum/jobs/{scrum_job_id}/export?format=csv")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["format"] == "csv"
    assert "Task Name" in data["content"]

    r = await client.get(f"/api/v1/scrum/jobs/{scrum_job_id}/export?format=json")
    rows = r.json()["data"]["content"]
    assert isinstance(rows, list) and rows[0]["list"]


async def test_refine_crea_job_hijo(ctx):
    client, ef_job_id = ctx
    await _make_ef_ready(client, ef_job_id)
    parent_id = (
        await client.post("/api/v1/scrum/plans", json={"ef_job_id": ef_job_id})
    ).json()["data"]["job_id"]

    # Responder la pregunta al PO del artefacto de ejemplo (Q-001, no bloqueante).
    await client.patch(
        f"/api/v1/scrum/jobs/{parent_id}/validations",
        json={
            "target_type": "question",
            "target_id": "Q-001",
            "status": "confirmado",
            "respuesta": "Un siniestro se liga a una sola guía.",
        },
    )

    r = await client.post(f"/api/v1/scrum/jobs/{parent_id}/refine")
    assert r.status_code == 200
    child = r.json()["data"]
    assert child["parent_job_id"] == parent_id
    assert child["job_id"] != parent_id
