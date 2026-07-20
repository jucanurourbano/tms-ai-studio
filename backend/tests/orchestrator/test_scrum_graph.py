"""Tests del grafo Scrum con stubs y del gate LOAD_EF (B2)."""

import pytest

from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.load_ef import (
    assert_ef_ready,
    extract_ef_context,
    functional_requirement_refs,
)
from ai.errors import GateError
from ai.orchestrator import build_scrum_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer


def _ef_dict():
    return ef_example().model_dump(mode="json")


async def _noop_persist(job_id, artifact, status, metrics):
    return None


def _base_config():
    return {
        "configurable": {
            "thread_id": "S-1",
            "persist": _noop_persist,
        }
    }


async def test_gate_bloquea_ef_no_listo():
    graph = build_scrum_graph(build_memory_checkpointer())
    state = {
        "job_id": "S-1",
        "ef_job_id": "EF-1",
        "ef_artifact": _ef_dict(),
        "ef_ready": False,  # EF con preguntas bloqueantes pendientes
        "capacity_points": 20,
    }
    with pytest.raises(GateError):
        await graph.ainvoke(state, _base_config())


async def test_grafo_end_to_end_con_stubs():
    graph = build_scrum_graph(build_memory_checkpointer())
    state = {
        "job_id": "S-1",
        "ef_job_id": "EF-1",
        "ef_artifact": _ef_dict(),
        "ef_artifact_hash": "a1b2c3",
        "ef_ready": True,
        "capacity_points": 20,
    }
    result = await graph.ainvoke(state, _base_config())

    assert result["status"] == "COMPLETED"
    art = result["artifact"]
    assert art["schema_version"] == "1.0.0"
    assert art["source"]["ef_job_id"] == "EF-1"
    assert art["source"]["ready_snapshot"] is True
    # ef_context expuesto por LOAD_EF a partir del EFArtifact real.
    assert result["ef_context"]["processes"]


async def test_checkpointer_conserva_estado():
    graph = build_scrum_graph(build_memory_checkpointer())
    config = _base_config()
    await graph.ainvoke(
        {
            "job_id": "S-1",
            "ef_job_id": "EF-1",
            "ef_artifact": _ef_dict(),
            "ef_ready": True,
            "capacity_points": 20,
        },
        config,
    )
    snapshot = await graph.aget_state(config)
    assert snapshot.values["status"] == "COMPLETED"


def test_assert_ef_ready_lanza_gate_error():
    with pytest.raises(GateError):
        assert_ef_ready(False, "EF-99")
    # Listo: no lanza.
    assert_ef_ready(True, "EF-99")


def test_extract_ef_context_y_rf_refs():
    ctx = extract_ef_context(_ef_dict())
    assert ctx["summary"]
    assert {p["id"] for p in ctx["processes"]} == {"PRO-001"}
    assert functional_requirement_refs(ctx) == ["REQ-F-001"]
