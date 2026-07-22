"""Tests de la API del Agente Arquitectura (A6) con pipeline mockeado."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.services.arquitectura_service as arquitectura_service
from ai.agents.arquitectura.schemas.examples import example_artifact as arch_example
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from app.dependencies.current_user import get_current_user
from app.dependencies.database import get_session
from app.models.agent import AgentType, EFSourceDocType, JobStatus
from app.models.user import User, UserRole
from app.repositories.agent_job_repository import AgentJobRepository
from app.repositories.ef_repository import EFRepository
from main import app


def _fake_user() -> User:
    return User(
        id="test-user",
        email="qa@urbano.com.pe",
        full_name="QA",
        password_hash="x",
        role=UserRole.ADMIN,
        is_active=True,
    )


async def _seed_scrum_job(factory, *, blocking_po: bool = False) -> str:
    """Siembra un EF COMPLETED + un Scrum COMPLETED (listo salvo blocking_po)."""
    async with factory() as session:
        ef_repo = EFRepository(session)
        doc = await ef_repo.get_or_create_source_doc(
            f"ef-hash-{blocking_po}", EFSourceDocType.TEXT
        )
        ef_job = await ef_repo.create_job(
            doc.id, title="Siniestros", source_type="text"
        )
        ef_art = ef_example().model_dump(mode="json")
        await ef_repo.save_artifact(ef_job.id, ef_art, ef_art["schema_version"])
        await ef_repo.update_job_status(ef_job.id, JobStatus.COMPLETED)

        repo = AgentJobRepository(session)
        scrum_job = await repo.create_job(
            AgentType.SCRUM,
            input_job_id=ef_job.id,
            title="Siniestros",
            source_type="text",
        )
        scrum_art = scrum_example().model_dump(mode="json")
        if blocking_po:
            scrum_art["questions_for_po"][0]["blocking"] = True
        await repo.save_artifact(scrum_job.id, scrum_art, scrum_art["schema_version"])
        await repo.update_job_metrics(scrum_job.id, scrum_art["metrics"])
        await repo.update_job_status(scrum_job.id, JobStatus.COMPLETED)
        await session.commit()
        return scrum_job.id


@pytest_asyncio.fixture
async def ctx(engine, monkeypatch):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_current_user] = _fake_user

    scrum_job_id = await _seed_scrum_job(factory)

    async def fake_pipeline(
        job_id,
        scrum_job_id,
        scrum_artifact,
        scrum_artifact_hash,
        ef_job_id,
        ef_artifact,
        ef_artifact_hash,
        scrum_ready,
        authoritative_context=None,
    ):
        async with factory() as session:
            repo = AgentJobRepository(session)
            art = arch_example().model_dump(mode="json")
            await repo.save_artifact(job_id, art, art["schema_version"])
            await repo.update_job_metrics(job_id, art["metrics"])
            await repo.update_job_status(job_id, JobStatus.COMPLETED)
            await session.commit()

    monkeypatch.setattr(
        arquitectura_service, "run_arquitectura_pipeline", fake_pipeline
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, scrum_job_id, factory

    app.dependency_overrides.clear()


async def test_design_rechazado_si_scrum_no_listo(ctx):
    client, _, factory = ctx
    not_ready = await _seed_scrum_job(factory, blocking_po=True)
    r = await client.post(
        "/api/v1/arquitectura/designs", json={"scrum_job_id": not_ready}
    )
    assert r.status_code == 409
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "GateError"
    assert "no está listo" in body["message"]


async def test_design_scrum_inexistente_400(ctx):
    client, _, _ = ctx
    r = await client.post("/api/v1/arquitectura/designs", json={"scrum_job_id": "NOPE"})
    assert r.status_code == 400
    assert r.json()["data"]["code"] == "IngestError"


async def test_design_ok_y_artifact(ctx):
    client, scrum_job_id, _ = ctx
    r = await client.post(
        "/api/v1/arquitectura/designs", json={"scrum_job_id": scrum_job_id}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["input_job_id"] == scrum_job_id
    arch_job_id = data["job_id"]

    r = await client.get(f"/api/v1/arquitectura/jobs/{arch_job_id}")
    assert r.json()["data"]["status"] == "COMPLETED"

    r = await client.get(f"/api/v1/arquitectura/jobs/{arch_job_id}/artifact")
    art = r.json()["data"]
    assert art["schema_version"] == "1.0.0"
    assert art["source"]["scrum_job_id"]
    assert art["source"]["ef_job_id"]
    assert art["architecture_style"]["chosen"] == "modular_monolith"
    assert art["components"][0]["id"] == "CMP-001"


async def test_semaforo_bloqueado_hasta_responder(ctx):
    client, scrum_job_id, _ = ctx
    arch_job_id = (
        await client.post(
            "/api/v1/arquitectura/designs", json={"scrum_job_id": scrum_job_id}
        )
    ).json()["data"]["job_id"]

    summary = (
        await client.get(f"/api/v1/arquitectura/jobs/{arch_job_id}/validations")
    ).json()["data"]
    # El artefacto de ejemplo tiene Q-001 bloqueante (integración sin contrato).
    assert summary["ready_for_next_stage"] is False
    assert "Q-001" in summary["blocking_pending"]
    # Contenido mínimo cumplido salvo bloqueantes.
    assert summary["checks"]["style_decided"] is True
    assert summary["checks"]["has_components"] is True
    assert summary["checks"]["coverage_met"] is True

    r = await client.patch(
        f"/api/v1/arquitectura/jobs/{arch_job_id}/validations",
        json={
            "target_type": "question",
            "target_id": "Q-001",
            "status": "confirmado",
            "respuesta": "Planillas expone un servicio REST.",
        },
    )
    assert r.status_code == 200

    summary = (
        await client.get(f"/api/v1/arquitectura/jobs/{arch_job_id}/validations")
    ).json()["data"]
    assert summary["ready_for_next_stage"] is True
    assert summary["blocking_pending"] == []


async def test_listado_y_available_scrum(ctx):
    client, scrum_job_id, _ = ctx
    await client.post(
        "/api/v1/arquitectura/designs", json={"scrum_job_id": scrum_job_id}
    )

    jobs = (await client.get("/api/v1/arquitectura/jobs")).json()["data"]
    assert jobs["total"] >= 1
    item = jobs["items"][0]
    assert item["title"] == "Siniestros"
    assert item["input_job_id"] == scrum_job_id

    scrum_jobs = (await client.get("/api/v1/arquitectura/available-scrum-jobs")).json()[
        "data"
    ]
    item = next(i for i in scrum_jobs["items"] if i["job_id"] == scrum_job_id)
    assert item["ready_for_next_stage"] is True


async def test_refine_crea_job_hijo(ctx):
    client, scrum_job_id, _ = ctx
    parent_id = (
        await client.post(
            "/api/v1/arquitectura/designs", json={"scrum_job_id": scrum_job_id}
        )
    ).json()["data"]["job_id"]

    await client.patch(
        f"/api/v1/arquitectura/jobs/{parent_id}/validations",
        json={
            "target_type": "question",
            "target_id": "Q-001",
            "status": "confirmado",
            "respuesta": "Planillas expone un servicio REST.",
        },
    )

    r = await client.post(f"/api/v1/arquitectura/jobs/{parent_id}/refine")
    assert r.status_code == 200
    child = r.json()["data"]
    assert child["parent_job_id"] == parent_id
    assert child["job_id"] != parent_id
