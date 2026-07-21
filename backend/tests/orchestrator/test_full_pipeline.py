"""Integración completa del grafo con LLM mockeado (Bloque 7).

De texto sintético (siniestros) al EFArtifact v1.2.0 persistido.
"""

from ai.agents.base.structured import ClaudeLLMClient
from ai.agents.ef.schemas import EFArtifact
from ai.orchestrator import build_ef_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from app.config.settings import settings
from app.models.ef import EFSourceDocType, JobStatus
from app.repositories.ef_repository import EFRepository
from tests.mocks import BlockContentChat, CritiqueLLM, DimAwareLLM

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


async def test_pipeline_con_adaptador_real_extrae_contenido(
    monkeypatch, tmp_path, session
):
    """Guarda-humo del bug de extracción: pipeline a través del ADAPTADOR REAL.

    El bug (todo en cero pese a consumir tokens) vivía en ``ClaudeLLMClient``, que
    los mocks del otro test evitan (devuelven JSON string directo). Aquí el LLM
    responde con la forma REAL de langchain-anthropic 1.x (lista de bloques
    thinking+text) envuelta por ``BlockContentChat`` y procesada por el
    ``ClaudeLLMClient`` real. Verificamos que el artefacto CONTIENE ítems —no solo
    que el grafo no explota— y que NADA cayó en cuarentena.
    """
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))

    repo = EFRepository(session)
    doc = await repo.get_or_create_source_doc("hash-blocks", EFSourceDocType.TEXT)
    job = await repo.create_job(doc.id)
    await session.commit()

    captured: dict = {}

    async def persist(job_id, artifact, status, metrics):
        captured["artifact"] = artifact
        captured["status"] = status
        await repo.save_artifact(job_id, artifact, artifact["schema_version"])
        await repo.update_job_metrics(job_id, metrics)
        await repo.update_job_status(job_id, JobStatus[status])
        await session.commit()

    graph = build_ef_graph(build_memory_checkpointer())
    config = {
        "configurable": {
            "thread_id": job.id,
            # Adaptador REAL envolviendo los mocks en la forma de bloques real.
            "llm": ClaudeLLMClient(client=BlockContentChat(DimAwareLLM())),
            "critique_llm": ClaudeLLMClient(client=BlockContentChat(CritiqueLLM())),
            "persist": persist,
        }
    }
    result = await graph.ainvoke(
        {"job_id": job.id, "filename": "siniestros.txt", "content": TEXTO.encode()},
        config,
    )

    assert result["status"] == "COMPLETED"

    artifact = EFArtifact.model_validate(captured["artifact"])

    # NADA en cuarentena: el adaptador parseó los bloques correctamente.
    assert artifact.metrics.chunks_skipped == 0
    assert not artifact.metrics.skipped
    assert artifact.metrics.coverage == 1.0
    assert artifact.metrics.tokens.output > 0  # hubo salida validada

    # El artefacto CONTIENE contenido extraído (no ceros, que era el síntoma).
    assert artifact.requirements.business or artifact.requirements.functional
    assert artifact.actors
    assert artifact.processes
    assert artifact.modules  # los "menús"/módulos volvieron a salir
