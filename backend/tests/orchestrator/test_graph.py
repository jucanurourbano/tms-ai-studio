"""Test de integración del grafo EF con stubs (Bloque 4)."""

from ai.orchestrator import build_ef_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from app.config.settings import settings
from tests.mocks import DimAwareLLM

TEXTO = (
    "# Proceso de Siniestros\n\n"
    "Registro y seguimiento de siniestros ligados a guías de envío.\n\n"
    "- Reportar el siniestro\n- Registrar la guía\n- Cerrar\n"
)


async def _noop_persist(job_id, artifact, status, metrics):
    """Persistencia no-op para tests del grafo sin BD."""
    return None


async def test_grafo_end_to_end_con_stubs(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    graph = build_ef_graph(build_memory_checkpointer())

    state = {
        "job_id": "J-1",
        "filename": "siniestros.txt",
        "content": TEXTO.encode("utf-8"),
    }
    config = {
        "configurable": {
            "thread_id": "J-1",
            "llm": DimAwareLLM(),
            "persist": _noop_persist,
        }
    }

    result = await graph.ainvoke(state, config)

    # INGEST/PARSE/SEGMENT reales
    assert result["source"]["source_type"] == "text"
    assert result["source"]["content_hash"]
    assert result["cir"]["source_type"] == "text"
    assert result["chunks"]["chunks_total"] >= 1

    # ASSEMBLE/PERSIST stub producen artefacto válido y estado final
    assert result["status"] == "COMPLETED"
    assert result["artifact"]["schema_version"] == "1.2.0"
    assert result["artifact"]["source"]["hash"] == result["source"]["content_hash"]


async def test_checkpointer_persiste_estado(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    graph = build_ef_graph(build_memory_checkpointer())
    config = {
        "configurable": {
            "thread_id": "J-2",
            "llm": DimAwareLLM(),
            "persist": _noop_persist,
        }
    }
    await graph.ainvoke(
        {"job_id": "J-2", "filename": "s.txt", "content": TEXTO.encode("utf-8")},
        config,
    )
    # el checkpointer conserva el estado bajo thread_id = job_id
    snapshot = await graph.aget_state(config)
    assert snapshot.values["status"] == "COMPLETED"
    assert snapshot.values["job_id"] == "J-2"
