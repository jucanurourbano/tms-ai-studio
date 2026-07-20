"""Tests del repositorio genérico multi-agente (B0)."""

import importlib.util
from pathlib import Path

from app.models.agent import (
    AgentType,
    EFSourceDocType,
    JobStatus,
    ValidationStatus,
    ValidationTargetType,
)
from app.repositories.agent_job_repository import AgentJobRepository


async def test_create_job_con_agent_type_y_source_nullable(session):
    repo = AgentJobRepository(session)
    # Un job Scrum no necesita source_doc (source_doc_id nullable).
    job = await repo.create_job(AgentType.SCRUM)
    assert job.agent_type == AgentType.SCRUM
    assert job.source_doc_id is None
    assert job.status == JobStatus.PENDING


async def test_input_job_id_enlaza_cross_agente(session):
    repo = AgentJobRepository(session)
    doc = await repo.get_or_create_source_doc("h-ef", EFSourceDocType.TEXT)
    ef_job = await repo.create_job(AgentType.EF, source_doc_id=doc.id)
    scrum_job = await repo.create_job(AgentType.SCRUM, input_job_id=ef_job.id)
    assert scrum_job.input_job_id == ef_job.id


async def test_list_jobs_filtra_por_agent_type(session):
    repo = AgentJobRepository(session)
    doc = await repo.get_or_create_source_doc("h-mix", EFSourceDocType.TEXT)
    await repo.create_job(AgentType.EF, source_doc_id=doc.id)
    await repo.create_job(AgentType.SCRUM)
    await repo.create_job(AgentType.SCRUM)

    scrum_jobs, total = await repo.list_jobs(agent_type=AgentType.SCRUM)
    assert total == 2
    assert all(j.agent_type == AgentType.SCRUM for j in scrum_jobs)

    _all, total_all = await repo.list_jobs()
    assert total_all == 3


async def test_find_completed_por_hash_respeta_agent_type(session):
    repo = AgentJobRepository(session)
    doc = await repo.get_or_create_source_doc("h-comp", EFSourceDocType.TEXT)
    ef_job = await repo.create_job(AgentType.EF, source_doc_id=doc.id)
    await repo.update_job_status(ef_job.id, JobStatus.COMPLETED)

    # Buscar como EF lo encuentra; como Scrum no (no comparte fuente por hash).
    assert (
        await repo.find_completed_job_by_hash("h-comp", AgentType.EF)
    ).id == ef_job.id
    assert await repo.find_completed_job_by_hash("h-comp", AgentType.SCRUM) is None


async def test_validacion_question_del_po(session):
    repo = AgentJobRepository(session)
    job = await repo.create_job(AgentType.SCRUM)
    await repo.upsert_validation(
        job.id,
        ValidationTargetType.QUESTION,
        "Q-001",
        ValidationStatus.CONFIRMADO,
        respuesta="Sí, aplica.",
    )
    summary = await repo.validation_summary(job.id)
    assert summary["total"] == 1
    assert summary["by_target_type"]["question"] == 1


async def test_artifact_upsert_generico(session):
    repo = AgentJobRepository(session)
    job = await repo.create_job(AgentType.SCRUM)
    row1 = await repo.save_artifact(
        job.id, {"schema_version": "1.0.0", "x": 1}, "1.0.0"
    )
    row2 = await repo.save_artifact(
        job.id, {"schema_version": "1.0.0", "x": 2}, "1.0.0"
    )
    assert row1.id == row2.id
    fetched = await repo.get_artifact(job.id)
    assert fetched.data["x"] == 2


def test_migracion_0002_importa():
    """La migración de generalización debe cargar y encadenar con la inicial."""
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0002_generalizar_agentes.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0002", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0002_generalizar_agentes"
    assert mod.down_revision == "0001_initial"
