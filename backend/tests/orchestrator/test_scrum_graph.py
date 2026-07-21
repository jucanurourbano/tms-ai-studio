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
from tests.mocks import ScrumMapLLM


def _ef_dict():
    return ef_example().model_dump(mode="json")


async def _noop_persist(job_id, artifact, status, metrics):
    return None


def _base_config():
    return {
        "configurable": {
            "thread_id": "S-1",
            "llm": ScrumMapLLM(),
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
    # EPICS/STORIES/CRITERIA reales (LLM mockeado).
    assert art["epics"] and art["epics"][0]["id"] == "EPIC-001"
    assert art["stories"] and art["stories"][0]["source_refs"]["requirement_refs"]
    assert art["stories"][0]["acceptance_criteria"]
    assert art["metrics"]["tokens"]["total"] > 0
    # ESTIMATE/PRIORITIZE/SPRINT_PLAN reales.
    assert art["stories"][0]["story_points"] == 5
    assert art["stories"][0]["priority"] == "must"
    assert art["product_backlog"]["ordered_story_ids"] == ["US-001"]
    assert art["sprints"] and art["sprints"][0]["story_ids"] == ["US-001"]
    assert art["metrics"]["points_total"] == 5
    assert art["metrics"]["sprints_total"] == 1
    # CRITIQUE: cobertura reportada (REQ-F-001 cubierto por US-001).
    cov = art["analysis"]["coverage"]
    assert cov["requirements_total"] == 1
    assert cov["uncovered_requirement_refs"] == []
    assert art["metrics"]["coverage"] == 1.0


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


# --- Humo de contenido: dedup, distribución de épicas, critique con sprints ---

import json  # noqa: E402

from tests.mocks import ScrumMapLLM as _ScrumMapLLM  # noqa: E402


def _ef_multi():
    """EF con 4 RF (dos redundantes 'ver saldo') y 2 módulos -> 2 épicas."""
    return {
        "summary": "Gestión de solicitudes de vacaciones.",
        "requirements": {
            "business": [{"id": "REQ-B-001", "text": "Digitalizar vacaciones."}],
            "functional": [
                {"id": "REQ-F-001", "text": "Registrar solicitud."},
                {"id": "REQ-F-002", "text": "Ver saldo disponible."},
                {"id": "REQ-F-003", "text": "Ver saldo antes de enviar."},
                {"id": "REQ-F-004", "text": "Aprobar solicitud."},
            ],
            "non_functional": [],
        },
        "processes": [
            {"id": "PRO-001", "name": "Solicitud", "steps": ["Registrar", "Aprobar"]}
        ],
        "business_rules": [{"id": "BR-001", "statement": "No exceder el saldo."}],
        "validations": [],
        "modules": [
            {"id": "MOD-001", "name": "Solicitudes"},
            {"id": "MOD-002", "name": "Aprobación"},
        ],
        "entities": [],
        "actors": [{"id": "ACT-001", "name": "Trabajador"}],
        "source": {"hash": "h1"},
    }


class _SmokeLLM(_ScrumMapLLM):
    """EPICS (2 épicas) + STORIES (redundantes/distribuidas); resto vía ScrumMapLLM."""

    async def complete_json(self, *, system, user):
        if "Agrupador de épicas" in system:
            return json.dumps(
                {
                    "epics": [
                        {
                            "title": "Solicitudes",
                            "source_refs": ["MOD-001", "PRO-001"],
                            "confidence": 0.8,
                        },
                        {
                            "title": "Aprobación",
                            "source_refs": ["MOD-002", "PRO-001"],
                            "confidence": 0.8,
                        },
                    ]
                },
                ensure_ascii=False,
            )
        if "Redactor de historias" in system:
            payload = json.loads(user.split("\n", 1)[1])
            rf = payload["functional_requirement"]["id"]
            epics = payload.get("epics", [])
            # REQ-F-004 -> épica de aprobación (MOD-002); el resto -> primera épica.
            epic_id = epics[0]["id"] if epics else None
            if rf == "REQ-F-004":
                epic_id = next(
                    (e["id"] for e in epics if "MOD-002" in e.get("source_refs", [])),
                    epic_id,
                )
            # REQ-F-002 y REQ-F-003 comparten objetivo (redundantes -> se fusionan).
            if rf in ("REQ-F-002", "REQ-F-003"):
                goal = "ver mi saldo de dias disponibles antes de enviar la solicitud"
            else:
                goal = f"gestionar {rf} del proceso de vacaciones"
            return json.dumps(
                {
                    "stories": [
                        {
                            "role": "Trabajador",
                            "goal": goal,
                            "benefit": "valor",
                            "requirement_refs": [rf],
                            "process_refs": ["PRO-001"],
                            "rule_refs": ["BR-001"],
                            "depends_on_requirements": [],
                            "epic_hint": epic_id,
                            "confidence": 0.8,
                        }
                    ]
                },
                ensure_ascii=False,
            )
        return await super().complete_json(system=system, user=user)


class _SprintEchoLLM:
    """CRITIQUE: reporta cuántos sprints recibió (coherencia con el plan)."""

    async def complete_json(self, *, system, user):
        payload = json.loads(user.split("\n", 1)[1])
        n = len(payload.get("sprints", []))
        return json.dumps(
            {
                "risks": [
                    {
                        "description": f"Plan con {n} sprints revisado.",
                        "severity": "baja",
                    }
                ]
            }
        )


async def test_humo_scrum_dedup_epicas_y_critique_coherente():
    graph = build_scrum_graph(build_memory_checkpointer())
    state = {
        "job_id": "S-2",
        "ef_job_id": "EF-9",
        "ef_artifact": _ef_multi(),
        "ef_artifact_hash": "h1",
        "ef_ready": True,
        "capacity_points": 20,
    }
    config = {
        "configurable": {
            "thread_id": "S-2",
            "llm": _SmokeLLM(),
            "critique_llm": _SprintEchoLLM(),
            "persist": _noop_persist,
        }
    }
    result = await graph.ainvoke(state, config)
    art = result["artifact"]
    stories = art["stories"]
    epics = art["epics"]

    # #1 Sin duplicados exactos: los dos "ver saldo" (REQ-F-002/003) se fusionaron.
    statements = [s["statement"] for s in stories]
    assert len(statements) == len(set(statements))
    merged = [
        s
        for s in stories
        if {"REQ-F-002", "REQ-F-003"} <= set(s["source_refs"]["requirement_refs"])
    ]
    assert len(merged) == 1  # una sola historia con ambos RF de origen

    # #2 Distribución: cada épica con módulo de origen tiene >=1 historia.
    for ep in epics:
        assert ep["story_ids"], f"épica {ep['id']} quedó vacía"
    assert len({s["epic_ref"] for s in stories}) >= 2  # no todo en EPIC-001

    # #3 CRITIQUE coherente con el plan: vio los sprints reales (no 0).
    sprints_total = art["metrics"]["sprints_total"]
    assert sprints_total >= 1
    assert any(
        f"{sprints_total} sprints" in r["description"] for r in art["analysis"]["risks"]
    )
