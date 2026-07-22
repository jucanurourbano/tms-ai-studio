"""Tests de contenido de COMPONENTS y STACK (A3): trazabilidad, cuarentena,
allow-list. Todo con LLM mockeado (REGLA DE PRESUPUESTO)."""

import json

from ai.agents.arquitectura.components import run_components
from ai.agents.arquitectura.load_sources import extract_sources
from ai.agents.arquitectura.stack import run_stack
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from tests.mocks import ArchMapLLM


def _sources():
    return extract_sources(
        ef_example().model_dump(mode="json"),
        scrum_example().model_dump(mode="json"),
    )


# --- COMPONENTS -------------------------------------------------------------


async def test_components_trazabilidad_y_depends_on():
    components, skipped, tokens = await run_components(ArchMapLLM(), _sources(), "M")
    assert skipped == []
    assert [c["id"] for c in components] == ["CMP-001", "CMP-002", "CMP-003"]
    by_name = {c["name"]: c for c in components}
    # Refs filtradas a ids reales del EF/Scrum.
    modulo = by_name["Módulo Siniestros"]
    assert modulo["source_refs"]["module_refs"] == ["MOD-001"]
    assert modulo["source_refs"]["entity_refs"] == ["ENT-001"]
    assert modulo["source_refs"]["epic_refs"] == ["EPIC-001"]
    # depends_on resuelto de nombre -> id real.
    assert modulo["id"] in by_name["API Siniestros"]["depends_on"]
    assert by_name["Base de Datos"]["id"] in modulo["depends_on"]
    # Todo derivado, con tokens estimados.
    assert all(c["origin"] == "derived" for c in components)
    assert tokens["total"] > 0


class _GhostComponentsLLM:
    """Devuelve un componente sin ninguna referencia real (anti-alucinación)."""

    async def complete_json(self, *, system: str, user: str) -> str:
        return json.dumps(
            {
                "components": [
                    {
                        "name": "Componente Fantasma",
                        "type": "service",
                        "layer": "aplicación",
                        "responsibility": "Sin base en el EF/Scrum.",
                        "entity_refs": ["ENT-999"],  # no existe
                        "depends_on": [],
                        "confidence": 0.3,
                    }
                ]
            },
            ensure_ascii=False,
        )


async def test_components_cuarentena_sin_refs_reales():
    components, skipped, _ = await run_components(
        _GhostComponentsLLM(), _sources(), "M"
    )
    assert components == []
    assert len(skipped) == 1
    assert skipped[0]["stage"] == "COMPONENTS"
    assert "anti-alucinación" in skipped[0]["reason"]


# --- STACK ------------------------------------------------------------------


async def test_stack_allow_list_y_alternativas():
    stack, skipped, tokens = await run_stack(ArchMapLLM(), _sources(), "M", ["domain"])
    assert skipped == []
    assert {s["technology"] for s in stack} == {"Spring Boot", "SQL Server"}
    backend = next(s for s in stack if s["layer"] == "framework_backend")
    # "Cobol" no está en el allow-list de la capa -> se descarta como alternativa.
    assert backend["alternatives"] == ["ASP.NET Core"]
    assert all(s["origin"] == "derived" for s in stack)
    assert tokens["total"] > 0


class _ExoticStackLLM:
    """Propone una tecnología fuera del allow-list y una capa desconocida."""

    async def complete_json(self, *, system: str, user: str) -> str:
        return json.dumps(
            {
                "stack": [
                    {
                        "layer": "framework_backend",
                        "technology": "Rust (Actix)",  # no está en la lista blanca
                        "rationale": "Exotismo.",
                        "confidence": 0.4,
                    },
                    {
                        "layer": "blockchain",  # capa inexistente
                        "technology": "Ethereum",
                        "rationale": "No aplica.",
                        "confidence": 0.2,
                    },
                ]
            },
            ensure_ascii=False,
        )


async def test_stack_cuarentena_exotico_y_capa_desconocida():
    stack, skipped, _ = await run_stack(_ExoticStackLLM(), _sources(), "M", [])
    assert stack == []
    reasons = " ".join(s["reason"] for s in skipped)
    assert "anti-exotismo" in reasons
    assert "capa desconocida" in reasons
