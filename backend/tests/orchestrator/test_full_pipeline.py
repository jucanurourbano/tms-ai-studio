"""Integración completa del grafo con LLM mockeado (Bloque 7).

De texto sintético (siniestros) al EFArtifact v1.2.0 persistido.
"""

from ai.agents.ef.schemas import EFArtifact
from ai.orchestrator import build_ef_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from app.config.settings import settings
from app.models.ef import EFSourceDocType, JobStatus
from app.repositories.ef_repository import EFRepository
from tests.mocks import CritiqueLLM, DimAwareLLM

TEXTO = (
    "# Proceso de Siniestros\n\n"
    "Registro y seguimiento de siniestros (eventos logísticos) ligados a guías.\n\n"
    "- Reportar el siniestro\n- Registrar la guía\n- Recuperar\n- Cerrar\n"
)


async def test_pipeline_completo_persiste_artifact(monkeypatch, tmp_path, session):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))

    repo = EFRepository(session)
    doc = await repo.get_or_create_source_doc("hash-full", EFSourceDocType.TEXT)
    job = await repo.create_job(doc.id)
    await session.commit()

    async def persist(job_id, artifact, status, metrics):
        await repo.save_artifact(job_id, artifact, artifact["schema_version"])
        await repo.update_job_metrics(job_id, metrics)
        await repo.update_job_status(job_id, JobStatus[status])
        await session.commit()

    graph = build_ef_graph(build_memory_checkpointer())
    config = {
        "configurable": {
            "thread_id": job.id,
            "llm": DimAwareLLM(),
            "critique_llm": CritiqueLLM(),
            "persist": persist,
        }
    }
    result = await graph.ainvoke(
        {"job_id": job.id, "filename": "siniestros.txt", "content": TEXTO.encode()},
        config,
    )

    assert result["status"] == "COMPLETED"

    # El artefacto quedó persistido y es un EFArtifact v1.2.0 válido.
    row = await repo.get_artifact(job.id)
    assert row is not None
    artifact = EFArtifact.model_validate(row.data)
    assert artifact.schema_version == "1.2.0"

    # Contenido real derivado del pipeline (no stubs).
    assert artifact.requirements.business  # requisitos extraídos
    assert any(a.name.startswith("Operador") for a in artifact.actors)
    assert artifact.entities  # entidades inferidas (Siniestro/Guia)
    assert any(e.name == "Siniestro" for e in artifact.entities)
    assert artifact.relationships  # relación inferida guia_id
    assert artifact.systems_interpretation.interpretation_assumptions  # glosario
    assert artifact.questions_for_analyst  # preguntas generadas

    # Métricas reales.
    assert artifact.metrics.tokens.total > 0
    assert artifact.metrics.chunks_total >= 1
    assert 0.0 <= artifact.metrics.coverage <= 1.0

    # El job quedó COMPLETED con métricas persistidas.
    refreshed = await repo.get_job(job.id)
    assert refreshed.status == JobStatus.COMPLETED
    assert refreshed.metrics["tokens"]["total"] > 0
