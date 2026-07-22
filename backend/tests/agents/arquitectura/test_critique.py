"""Tests de CRITIQUE y QUESTION_GEN (A5): cobertura, ciclos, bloqueantes."""

from ai.agents.arquitectura.critique import (
    compute_coverage,
    detect_component_cycles,
    run_critique,
)
from ai.agents.arquitectura.question_gen import generate_questions


def _sources():
    return {
        "ef": {
            "entities": [{"id": "ENT-001"}, {"id": "ENT-002"}],
            "requirements": {"non_functional": [{"id": "RNF-001", "text": "x"}]},
        },
        "scrum": {"epics": [{"id": "EPIC-001"}, {"id": "EPIC-002"}]},
    }


def _components():
    return [
        {
            "id": "CMP-001",
            "type": "domain",
            "confidence": 0.8,
            "depends_on": ["CMP-002"],
            "source_refs": {"epic_refs": ["EPIC-001"], "entity_refs": ["ENT-001"]},
        },
        {
            "id": "CMP-002",
            "type": "datastore",
            "confidence": 0.3,  # baja confianza -> pregunta no bloqueante
            "depends_on": [],
            "source_refs": {"entity_refs": ["ENT-002"]},
        },
    ]


def test_compute_coverage_reporta_no_cubiertos():
    cov = compute_coverage(_components(), cross_cutting=[], sources=_sources())
    # EPIC-002 sin componente; RNF-001 sin transversal; entidades ambas cubiertas.
    assert cov["epics_mapped"] == 1
    assert cov["uncovered_epic_refs"] == ["EPIC-002"]
    assert cov["entities_mapped"] == 2
    assert cov["uncovered_entity_refs"] == []
    assert cov["uncovered_nfr_refs"] == ["RNF-001"]


def test_compute_coverage_nfr_atendido_por_transversal():
    xc = [{"id": "XC-001", "source_refs": ["RNF-001"]}]
    cov = compute_coverage(_components(), cross_cutting=xc, sources=_sources())
    assert cov["nfr_addressed"] == 1
    assert cov["uncovered_nfr_refs"] == []


def test_detect_component_cycles():
    comps = [
        {"id": "A", "depends_on": ["B"]},
        {"id": "B", "depends_on": ["A"]},
        {"id": "C", "depends_on": []},
    ]
    cycles = detect_component_cycles(comps)
    assert cycles and any("A" in c and "B" in c for c in cycles)


async def test_run_critique_riesgo_integracion_sin_contrato():
    integrations = [
        {
            "id": "INT-001",
            "name": "Planillas",
            "system": "planillas",
            "contract_known": False,
        }
    ]
    critique, _ = await run_critique(
        _components(), [], integrations, [], _sources(), llm=None
    )
    # Riesgo determinista por integración sin contrato.
    assert any(r["source_ref"] == "INT-001" for r in critique["risks"])
    # Hallazgos para QUESTION_GEN.
    f = critique["findings"]
    assert f["uncovered_epic_refs"] == ["EPIC-002"]
    assert f["uncovered_nfr_refs"] == ["RNF-001"]
    assert f["integrations_without_contract"][0]["id"] == "INT-001"
    assert f["low_confidence_components"] == ["CMP-002"]


def test_question_gen_bloqueantes_y_no_bloqueantes():
    findings = {
        "uncovered_epic_refs": ["EPIC-002"],
        "uncovered_entity_refs": [],
        "uncovered_nfr_refs": ["RNF-001"],
        "integrations_without_contract": [{"id": "INT-001", "name": "Planillas"}],
        "component_cycles": [["A", "B", "A"]],
        "low_confidence_components": ["CMP-002"],
    }
    qs = generate_questions({"findings": findings})
    blocking = {q["linked_to_ref"] for q in qs if q["blocking"]}
    # RNF, integración, épica y ciclo -> bloqueantes.
    assert {"RNF-001", "INT-001", "EPIC-002"} <= blocking
    assert any(q["linked_to_ref"] == "A" and q["blocking"] for q in qs)
    # Baja confianza -> no bloqueante.
    non_blocking = {q["linked_to_ref"] for q in qs if not q["blocking"]}
    assert "CMP-002" in non_blocking
    assert all(q["audience"] == "tecnico" for q in qs)
