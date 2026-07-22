"""Tests del grafo Arquitectura con stubs, del gate y del scope profile (A2)."""

import pytest

from ai.agents.arquitectura.context import (
    build_scope_profile,
    classify_size,
    scope_score,
)
from ai.agents.arquitectura.load_sources import (
    assert_scrum_ready,
    extract_sources,
    resolve_ef_hash,
)
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from ai.errors import GateError
from ai.orchestrator import build_arquitectura_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from tests.mocks import ArchMapLLM


def _ef_dict():
    return ef_example().model_dump(mode="json")


def _scrum_dict():
    return scrum_example().model_dump(mode="json")


async def _noop_persist(job_id, artifact, status, metrics):
    return None


def _base_config():
    return {
        "configurable": {
            "thread_id": "AR-1",
            "llm": ArchMapLLM(),
            "persist": _noop_persist,
        }
    }


def _base_state(scrum_ready: bool = True):
    return {
        "job_id": "AR-1",
        "scrum_job_id": "SC-1",
        "scrum_artifact": _scrum_dict(),
        "scrum_artifact_hash": "sc123",
        "scrum_ready": scrum_ready,
        "ef_job_id": "EF-1",
        "ef_artifact": _ef_dict(),
        "ef_artifact_hash": "ef123",
    }


async def test_gate_bloquea_scrum_no_listo():
    graph = build_arquitectura_graph(build_memory_checkpointer())
    with pytest.raises(GateError):
        await graph.ainvoke(_base_state(scrum_ready=False), _base_config())


async def test_grafo_end_to_end_con_stubs():
    graph = build_arquitectura_graph(build_memory_checkpointer())
    result = await graph.ainvoke(_base_state(), _base_config())

    assert result["status"] == "COMPLETED"
    art = result["artifact"]
    assert art["schema_version"] == "1.0.0"
    # Enlace a AMBOS jobs de origen (Scrum directo + EF transitivo).
    assert art["source"]["scrum_job_id"] == "SC-1"
    assert art["source"]["ef_job_id"] == "EF-1"
    assert art["source"]["ready_snapshot"] is True
    # CONTEXT determinista: scope profile calculado desde EF+Scrum reales.
    prof = art["context"]["scope_profile"]
    assert prof["entities"] == 2  # EF de ejemplo: 2 entidades
    assert prof["stories"] == 2  # Scrum de ejemplo: 2 historias
    assert prof["nfr_count"] == 1
    assert art["context"]["size_class"] in {"S", "M", "L"}
    # COMPONENTS (A3): componentes con trazabilidad y depends_on resueltos.
    comps = art["components"]
    assert len(comps) == 3
    by_name = {c["name"]: c for c in comps}
    assert by_name["Módulo Siniestros"]["source_refs"]["module_refs"] == ["MOD-001"]
    # depends_on resuelto de nombre -> id real (API -> Módulo Siniestros).
    modulo_id = by_name["Módulo Siniestros"]["id"]
    assert modulo_id in by_name["API Siniestros"]["depends_on"]
    assert art["metrics"]["components_total"] == 3
    # STACK (A3): recomendaciones dentro del allow-list de la casa.
    stack = art["stack"]
    assert {s["technology"] for s in stack} == {"Spring Boot", "SQL Server"}
    # Alternativa fuera del allow-list ("Cobol") descartada.
    backend = next(s for s in stack if s["layer"] == "framework_backend")
    assert "Cobol" not in backend["alternatives"]
    assert "ASP.NET Core" in backend["alternatives"]
    # Nodos aún stub (A4-A5): estilo/ADRs pendientes.
    assert art["architecture_style"] is None
    # Métricas: hubo LLM (mock) -> tokens estimados > 0.
    assert art["metrics"]["tokens"]["total"] > 0


async def test_checkpointer_conserva_estado():
    graph = build_arquitectura_graph(build_memory_checkpointer())
    config = _base_config()
    await graph.ainvoke(_base_state(), config)
    snapshot = await graph.aget_state(config)
    assert snapshot.values["status"] == "COMPLETED"


def test_assert_scrum_ready_lanza_gate_error():
    with pytest.raises(GateError):
        assert_scrum_ready(False, "SC-99")
    assert_scrum_ready(True, "SC-99")  # listo: no lanza


def test_extract_sources_consolida_ef_y_scrum():
    sources = extract_sources(_ef_dict(), _scrum_dict())
    assert sources["ef"]["summary"]
    assert {p["id"] for p in sources["ef"]["processes"]} == {"PRO-001"}
    assert len(sources["ef"]["entities"]) == 2
    assert len(sources["scrum"]["stories"]) == 2
    assert sources["scrum"]["points_total"] == 8


def test_resolve_ef_hash_prioridades():
    scrum = {"source": {"ef_artifact_hash": "fromscrum"}}
    ef = {"source": {"hash": "fromef"}}
    assert resolve_ef_hash("fromstate", scrum, ef) == "fromstate"
    assert resolve_ef_hash("", scrum, ef) == "fromscrum"
    assert resolve_ef_hash("", {}, ef) == "fromef"


def test_scope_profile_desde_ejemplos():
    sources = extract_sources(_ef_dict(), _scrum_dict())
    prof = build_scope_profile(sources)
    assert prof == {
        "entities": 2,
        "relationships": 1,
        "modules": 1,
        "processes": 1,
        "stories": 2,
        "points_total": 8,
        "integrations_detected": 0,
        "nfr_count": 1,
    }
    # score = 2 + 1*2 + 1 + 2 + 0 = 7
    assert scope_score(prof) == 7


def test_classify_size_umbrales():
    small = {"entities": 1, "modules": 1, "processes": 0, "stories": 1}
    medium = {"entities": 4, "modules": 3, "processes": 2, "stories": 3}
    large = {"entities": 8, "modules": 6, "processes": 4, "stories": 6}
    # Umbrales por defecto: small_max=8, large_min=25.
    assert classify_size(small, 8, 25) == "S"  # score 4
    assert classify_size(medium, 8, 25) == "M"  # score 15
    assert classify_size(large, 8, 25) == "L"  # score 30
