"""Tests de CRITIQUE (cobertura/ciclos/refs) y QUESTION_GEN (B5)."""

import json

from ai.agents.scrum.critique import (
    compute_coverage,
    critique,
    detect_cycles,
    find_orphan_refs,
)
from ai.agents.scrum.question_gen import generate_questions


def _ef_context():
    return {
        "requirements": {
            "business": [],
            "functional": [
                {"id": "REQ-F-001", "text": "Registrar."},
                {"id": "REQ-F-002", "text": "Cambiar estado."},
                {"id": "REQ-F-003", "text": "Anular."},
            ],
            "non_functional": [],
        },
        "processes": [],
        "business_rules": [],
        "validations": [],
        "modules": [],
        "entities": [],
        "actors": [],
    }


def _stories():
    return [
        {
            "id": "US-001",
            "epic_ref": "EPIC-001",
            "source_refs": {"requirement_refs": ["REQ-F-001"]},
            "dependencies": [],
            "estimation_confidence": 0.8,
            "confidence": 0.8,
            "priority": "must",
        },
        {
            "id": "US-002",
            "epic_ref": "EPIC-001",
            "source_refs": {"requirement_refs": ["REQ-F-002"]},
            "dependencies": ["US-001"],
            "estimation_confidence": 0.3,  # baja confianza -> pregunta
            "confidence": 0.8,
            "priority": "should",
        },
    ]


class CritiqueLLM:
    async def complete_json(self, *, system, user):
        return json.dumps(
            {
                "risks": [
                    {
                        "description": "Capacidad ajustada en el primer sprint.",
                        "severity": "media",
                        "source_ref": "SPRINT-1",
                    }
                ]
            }
        )


class SprintAwareLLM:
    """Devuelve un riesgo que reporta CUÁNTOS sprints vio en el payload.

    Sirve para verificar que CRITIQUE le pasa el plan de sprints real (antes se
    le pasaba [] y reportaba 'sprints vacío')."""

    async def complete_json(self, *, system, user):
        payload = json.loads(user.split("\n", 1)[1])
        n = len(payload.get("sprints", []))
        return json.dumps(
            {"risks": [{"description": f"Analicé {n} sprints.", "severity": "media"}]}
        )


async def test_critique_pasa_sprints_reales_al_llm():
    """REGRESIÓN (#3): el pase de riesgos ve el plan final, no una lista vacía."""
    sprints = [
        {"id": "SPRINT-1", "total_points": 20},
        {"id": "SPRINT-2", "total_points": 15},
    ]
    result, _ = await critique(
        _stories(), [], _ef_context(), [], sprints=sprints, llm=SprintAwareLLM()
    )
    assert any("Analicé 2 sprints" in r["description"] for r in result["risks"])


async def test_critique_sin_sprints_reporta_cero():
    result, _ = await critique(
        _stories(), [], _ef_context(), [], sprints=[], llm=SprintAwareLLM()
    )
    assert any("Analicé 0 sprints" in r["description"] for r in result["risks"])


def test_cobertura_reporta_rf_no_cubiertos():
    cov = compute_coverage(_stories(), _ef_context())
    assert cov["requirements_total"] == 3
    assert cov["requirements_covered"] == 2
    assert cov["uncovered_requirement_refs"] == ["REQ-F-003"]
    assert cov["coverage_ratio"] == round(2 / 3, 4)


def test_detect_cycles():
    stories = [
        {"id": "A", "dependencies": ["B"]},
        {"id": "B", "dependencies": ["A"]},
        {"id": "C", "dependencies": []},
    ]
    cycles = detect_cycles(stories)
    assert cycles  # hay al menos un ciclo A<->B
    assert set(cycles[0]) == {"A", "B"}


def test_find_orphan_refs():
    stories = [
        {"id": "US-001", "epic_ref": "EPIC-9", "dependencies": ["US-404"]},
    ]
    orphans = find_orphan_refs(stories, epics=[])
    refs = {o["ref"] for o in orphans}
    assert refs == {"EPIC-9", "US-404"}


async def test_critique_completo_con_llm():
    critique_dict, tokens = await critique(
        _stories(), [{"id": "EPIC-001"}], _ef_context(), [], llm=CritiqueLLM()
    )
    assert critique_dict["coverage"]["uncovered_requirement_refs"] == ["REQ-F-003"]
    # Riesgo del pase LLM presente, con id asignado.
    assert any("Capacidad" in r["description"] for r in critique_dict["risks"])
    assert critique_dict["risks"][0]["id"].startswith("RISK-")
    assert tokens["total"] > 0
    findings = critique_dict["findings"]
    assert findings["uncovered_requirement_refs"] == ["REQ-F-003"]
    assert "US-002" in findings["low_confidence_estimates"]


async def test_critique_unassigned_must_observacion():
    critique_dict, _ = await critique(
        _stories(), [{"id": "EPIC-001"}], _ef_context(), ["US-001"]
    )
    assert "US-001" in critique_dict["findings"]["unassigned_must"]
    assert any("must" in o["description"] for o in critique_dict["observations"])


async def test_question_gen_fuentes():
    critique_dict, _ = await critique(
        _stories(), [{"id": "EPIC-001"}], _ef_context(), []
    )
    questions = generate_questions(critique_dict, _stories())
    # RF-003 no cubierto -> pregunta bloqueante.
    uncovered_q = [q for q in questions if q["linked_to_ref"] == "REQ-F-003"]
    assert uncovered_q and uncovered_q[0]["blocking"] is True
    # US-002 baja confianza de estimación -> pregunta NO bloqueante.
    est_q = [q for q in questions if q["linked_to_ref"] == "US-002"]
    assert est_q and est_q[0]["blocking"] is False
    # ids secuenciales.
    assert [q["id"] for q in questions] == [
        f"Q-{i:03d}" for i in range(1, len(questions) + 1)
    ]


async def test_question_gen_ciclo_bloqueante():
    stories = [
        {"id": "A", "dependencies": ["B"], "source_refs": {"requirement_refs": []}},
        {"id": "B", "dependencies": ["A"], "source_refs": {"requirement_refs": []}},
    ]
    critique_dict, _ = await critique(stories, [], _ef_context(), [])
    questions = generate_questions(critique_dict, stories)
    cycle_q = [q for q in questions if "circular" in q["question"]]
    assert cycle_q and cycle_q[0]["blocking"] is True
    assert cycle_q[0]["audience"] == "tecnico"
