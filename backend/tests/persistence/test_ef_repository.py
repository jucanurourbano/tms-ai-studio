"""Tests de persistencia del Agente EF (Bloque 2)."""

import importlib.util
from pathlib import Path

from ai.agents.ef.schemas.examples import example_artifact
from app.models.ef import (
    EFSourceDocType,
    JobStatus,
    ValidationStatus,
    ValidationTargetType,
)
from app.repositories.ef_repository import EFRepository


async def _nuevo_job(repo: EFRepository, content_hash: str = "hash-1"):
    doc = await repo.get_or_create_source_doc(
        content_hash=content_hash,
        doc_type=EFSourceDocType.TEXT,
        filename="fuente.txt",
        doc_metadata={"size": 123},
    )
    return await repo.create_job(source_doc_id=doc.id), doc


async def test_source_doc_idempotente_por_hash(session):
    repo = EFRepository(session)
    d1 = await repo.get_or_create_source_doc("h-abc", EFSourceDocType.DOCUMENT)
    d2 = await repo.get_or_create_source_doc("h-abc", EFSourceDocType.DOCUMENT)
    assert d1.id == d2.id


async def test_crear_job_pending(session):
    repo = EFRepository(session)
    job, _ = await _nuevo_job(repo)
    assert job.status == JobStatus.PENDING
    assert job.parent_job_id is None


async def test_actualizar_estado_y_metricas(session):
    repo = EFRepository(session)
    job, _ = await _nuevo_job(repo)
    await repo.update_job_status(job.id, JobStatus.RUNNING)
    await repo.update_job_metrics(job.id, {"tokens": {"total": 100}, "cost": 0.01})
    await repo.update_job_status(job.id, JobStatus.FAILED, error="boom")
    refreshed = await repo.get_job(job.id)
    assert refreshed.status == JobStatus.FAILED
    assert refreshed.error == "boom"
    assert refreshed.metrics["cost"] == 0.01


async def test_guardar_y_recuperar_artefacto_upsert(session):
    repo = EFRepository(session)
    job, _ = await _nuevo_job(repo)
    data = example_artifact().model_dump(mode="json")
    row1 = await repo.save_artifact(job.id, data, data["schema_version"])
    # Guardar de nuevo debe reemplazar (no duplicar)
    data["summary"] = "resumen editado"
    row2 = await repo.save_artifact(job.id, data, data["schema_version"])
    assert row1.id == row2.id
    fetched = await repo.get_artifact(job.id)
    assert fetched.data["summary"] == "resumen editado"
    assert fetched.schema_version == "1.2.0"


async def test_idempotencia_find_completed_job_by_hash(session):
    repo = EFRepository(session)
    job, _ = await _nuevo_job(repo, content_hash="h-idem")
    # Aún no completado: no debe encontrarlo
    assert await repo.find_completed_job_by_hash("h-idem") is None
    await repo.update_job_status(job.id, JobStatus.COMPLETED_WITH_WARNINGS)
    found = await repo.find_completed_job_by_hash("h-idem")
    assert found is not None and found.id == job.id


async def test_upsert_validation_unica_por_target(session):
    repo = EFRepository(session)
    job, _ = await _nuevo_job(repo)
    v1 = await repo.upsert_validation(
        job.id, ValidationTargetType.QUESTION, "Q-001", ValidationStatus.PENDIENTE
    )
    v2 = await repo.upsert_validation(
        job.id,
        ValidationTargetType.QUESTION,
        "Q-001",
        ValidationStatus.CONFIRMADO,
        respuesta="Sí, aplica.",
    )
    assert v1.id == v2.id
    assert v2.status == ValidationStatus.CONFIRMADO
    assert v2.respuesta == "Sí, aplica."


async def test_validation_summary(session):
    repo = EFRepository(session)
    job, _ = await _nuevo_job(repo)
    await repo.upsert_validation(
        job.id, ValidationTargetType.QUESTION, "Q-001", ValidationStatus.CONFIRMADO
    )
    await repo.upsert_validation(
        job.id, ValidationTargetType.ASSUMPTION, "SUP-001", ValidationStatus.PENDIENTE
    )
    summary = await repo.validation_summary(job.id)
    assert summary["total"] == 2
    assert summary["by_status"]["confirmado"] == 1
    assert summary["by_target_type"]["assumption"] == 1


async def test_list_jobs_paginado(session):
    repo = EFRepository(session)
    doc = await repo.get_or_create_source_doc("h-list", EFSourceDocType.TEXT)
    for _ in range(3):
        await repo.create_job(doc.id)
    jobs, total = await repo.list_jobs(limit=2, offset=0)
    assert total == 3
    assert len(jobs) == 2


def test_migracion_inicial_importa():
    """La migración inicial debe cargar y declarar su revisión."""
    path = (
        Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0001_initial.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0001", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0001_initial"
    assert mod.down_revision is None
