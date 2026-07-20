"""Tests de EPICS/STORIES/CRITERIA con LLM mockeado (B3) + trazabilidad."""

import json

from ai.agents.scrum.criteria import run_criteria
from ai.agents.scrum.epics import run_epics
from ai.agents.scrum.stories import run_stories
from tests.mocks import ScrumMapLLM


def _ef_context():
    """Contexto EF con 2 requisitos funcionales (para probar dependencias)."""
    return {
        "summary": "Gestión de siniestros.",
        "requirements": {
            "business": [{"id": "REQ-B-001", "text": "Registrar siniestro."}],
            "functional": [
                {"id": "REQ-F-001", "text": "Registrar siniestro con guía."},
                {"id": "REQ-F-002", "text": "Cambiar el estado del siniestro."},
            ],
            "non_functional": [],
        },
        "processes": [{"id": "PRO-001", "name": "Registro", "steps": ["Reportar"]}],
        "business_rules": [{"id": "BR-001", "statement": "Sin guía no se registra."}],
        "validations": [{"id": "VAL-001", "rule": "Fecha no futura."}],
        "modules": [{"id": "MOD-001", "name": "Siniestros"}],
        "entities": [{"id": "ENT-001", "name": "Siniestro"}],
        "actors": [{"id": "ACT-001", "name": "Operador"}],
    }


class ScriptedLLM:
    def __init__(self, response):
        self.response = response

    async def complete_json(self, *, system, user):
        return self.response


async def test_epics_traza_source_refs_reales():
    epics, skipped, tokens = await run_epics(ScrumMapLLM(), _ef_context())
    assert len(epics) == 1
    assert epics[0]["id"] == "EPIC-001"
    assert set(epics[0]["source_refs"]) <= {"MOD-001", "PRO-001"}
    assert epics[0]["origin"] == "derived"
    assert tokens["total"] > 0
    assert skipped == []


async def test_epics_descarta_sin_source_ref_real():
    bogus = ScriptedLLM(
        json.dumps({"epics": [{"title": "X", "source_refs": ["MOD-999"]}]})
    )
    epics, skipped, _ = await run_epics(bogus, _ef_context())
    assert epics == []
    assert len(skipped) == 1
    assert skipped[0]["stage"] == "EPICS"


async def test_stories_trazabilidad_y_dependencias():
    ctx = _ef_context()
    epics, _, _ = await run_epics(ScrumMapLLM(), ctx)
    stories, skipped, tokens = await run_stories(
        ScrumMapLLM(), ctx, epics, ef_job_id="JOB123"
    )

    assert [s["id"] for s in stories] == ["US-001", "US-002"]
    # Cada historia ancla su requisito funcional.
    us1 = next(s for s in stories if s["id"] == "US-001")
    us2 = next(s for s in stories if s["id"] == "US-002")
    assert "REQ-F-001" in us1["source_refs"]["requirement_refs"]
    assert "REQ-F-002" in us2["source_refs"]["requirement_refs"]
    # US-002 (REQ-F-002) depende de la historia de REQ-F-001 => US-001.
    assert us2["dependencies"] == ["US-001"]
    assert us1["dependencies"] == []
    # Statement "Como/quiero/para" y compatibilidad ClickUp.
    assert us1["statement"].startswith("Como operador de siniestros quiero")
    assert "ef:JOB123" in us1["tags"]
    assert us1["external_key"] == "JOB123:US-001"
    # Épica enlazada por epic_hint MOD-001 -> EPIC-001, con story_ids poblados.
    assert us1["epic_ref"] == "EPIC-001"
    assert set(epics[0]["story_ids"]) == {"US-001", "US-002"}
    assert tokens["total"] > 0
    assert skipped == []


async def test_criteria_anclados_a_reglas():
    ctx = _ef_context()
    epics, _, _ = await run_epics(ScrumMapLLM(), ctx)
    stories, _, _ = await run_stories(ScrumMapLLM(), ctx, epics, ef_job_id="J")
    stories, skipped, tokens = await run_criteria(ScrumMapLLM(), stories, ctx)

    ac = stories[0]["acceptance_criteria"]
    assert len(ac) == 1
    assert ac[0]["source_refs"] == ["BR-001"]
    assert ac[0]["format"] == "gherkin"
    assert ac[0]["id"].startswith("AC-US-001")
    assert tokens["total"] > 0


async def test_criteria_descarta_sin_ancla():
    ctx = _ef_context()
    stories = [
        {
            "id": "US-001",
            "statement": "Como X quiero Y para Z.",
            "source_refs": {"requirement_refs": ["REQ-F-001"], "rule_refs": ["BR-001"]},
            "acceptance_criteria": [],
        }
    ]
    # Criterio sin source_refs válidos -> cuarentena.
    bogus = ScriptedLLM(
        json.dumps(
            {
                "acceptance_criteria": [
                    {"format": "gherkin", "given": "g", "then": "t", "source_refs": []}
                ]
            }
        )
    )
    stories, skipped, _ = await run_criteria(bogus, stories, ctx)
    assert stories[0]["acceptance_criteria"] == []
    assert len(skipped) == 1
    assert skipped[0]["stage"] == "CRITERIA"
