"""Tests de contenido de ADRS, CONTRACTS y DIAGRAMS (A4). LLM mockeado."""

import json

from ai.agents.arquitectura.adrs import choose_style, run_adrs
from ai.agents.arquitectura.contracts import run_contracts
from ai.agents.arquitectura.diagrams import (
    build_component_diagram,
    build_context_diagram,
)
from ai.agents.arquitectura.load_sources import extract_sources
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from tests.mocks import ArchMapLLM


def _sources():
    return extract_sources(
        ef_example().model_dump(mode="json"),
        scrum_example().model_dump(mode="json"),
    )


# --- ADRS -------------------------------------------------------------------


def test_choose_style_determinista():
    assert choose_style("S").value == "modular_monolith"
    assert choose_style("M").value == "modular_monolith"
    assert choose_style("L").value == "microservices"


async def test_run_adrs_estilo_y_filtrado_de_refs():
    components = [{"id": "CMP-001", "name": "Módulo", "type": "domain"}]
    stack = [{"id": "STK-001", "layer": "framework_backend", "technology": "X"}]
    valid = {"ENT-001", "REQ-N-001", "CMP-001", "STK-001"}
    adrs, style, skipped, tokens = await run_adrs(
        ArchMapLLM(), "M", {"entities": 2, "modules": 1}, components, stack, valid
    )
    # ADR-001 de estilo, determinista.
    assert adrs[0]["id"] == "ADR-001"
    assert "modular_monolith" in adrs[0]["title"]
    assert style["chosen"] == "modular_monolith"
    assert style["adr_ref"] == "ADR-001"
    # ADR del LLM: ADR-002 con refs filtradas (REF-INEXISTENTE descartada).
    assert adrs[1]["id"] == "ADR-002"
    assert set(adrs[1]["source_refs"]) == {"ENT-001", "REQ-N-001"}
    assert tokens["total"] > 0


async def test_run_adrs_estilo_large_microservices():
    _, style, _, _ = await run_adrs(ArchMapLLM(), "L", {}, [], [], set())
    assert style["chosen"] == "microservices"


# --- CONTRACTS --------------------------------------------------------------


def _components():
    return [
        {
            "id": "CMP-001",
            "name": "Módulo Siniestros",
            "type": "domain",
            "depends_on": ["CMP-002"],
            "confidence": 0.8,
        },
        {
            "id": "CMP-002",
            "name": "Base de Datos",
            "type": "datastore",
            "depends_on": [],
            "confidence": 0.8,
        },
    ]


async def test_run_contracts_deterministas_e_integracion():
    contracts, integrations, cross_cutting, skipped, tokens = await run_contracts(
        ArchMapLLM(), _sources(), _components()
    )
    assert skipped == []
    # Contrato determinista desde depends_on (CMP-001 -> CMP-002, síncrono).
    dep = next(c for c in contracts if c["kind"] == "sync_api")
    assert dep["from_ref"] == "CMP-001" and dep["to_ref"] == "CMP-002"
    # Integración detectada + contrato externo hacia ella.
    assert len(integrations) == 1 and integrations[0]["id"] == "INT-001"
    ext = next(c for c in contracts if c["kind"] == "external")
    assert ext["to_ref"] == "INT-001"
    # Transversal (auditoría) anclado a una regla real.
    assert cross_cutting[0]["concern"] == "audit"
    assert cross_cutting[0]["source_refs"] == ["BR-001"]
    assert tokens["total"] > 0


class _GhostContractsLLM:
    """Integración y transversal SIN refs reales -> cuarentena en ambos."""

    async def complete_json(self, *, system: str, user: str) -> str:
        if "Detector de integraciones" in system:
            return json.dumps(
                {
                    "integrations": [
                        {
                            "name": "Sistema Inventado",
                            "system": "x",
                            "purpose": "sin base",
                            "source_refs": ["PRO-999"],
                        }
                    ]
                }
            )
        if "Analista de requisitos transversales" in system:
            return json.dumps(
                {
                    "cross_cutting": [
                        {
                            "concern": "notifications",
                            "requirement": "sin base",
                            "approach": "x",
                            "source_refs": ["RNF-999"],
                        }
                    ]
                }
            )
        return "{}"


async def test_run_contracts_cuarentena_sin_refs():
    contracts, integrations, cross_cutting, skipped, _ = await run_contracts(
        _GhostContractsLLM(), _sources(), _components()
    )
    assert integrations == []
    assert cross_cutting == []
    reasons = " ".join(s["reason"] for s in skipped)
    assert reasons.count("anti-alucinación") == 2
    # Sin integraciones no hay contrato externo; solo el determinista.
    assert all(c["kind"] == "sync_api" for c in contracts)


# --- DIAGRAMS ---------------------------------------------------------------


def test_build_component_diagram_mermaid_valido():
    components = [
        {
            "id": "CMP-001",
            "name": 'Módulo "raro" [x]',
            "type": "domain",
            "layer": "dominio",
        },
        {
            "id": "CMP-002",
            "name": "Base de Datos",
            "type": "datastore",
            "layer": "datos",
        },
    ]
    contracts = [
        {"from_ref": "CMP-001", "to_ref": "CMP-002", "kind": "sync_api"},
        {"from_ref": "CMP-001", "to_ref": "INT-001", "kind": "external"},
    ]
    integrations = [{"id": "INT-001", "name": "Planillas"}]
    code = build_component_diagram(components, contracts, integrations)
    assert code.startswith("flowchart LR")
    # Ids saneados (sin guiones) y etiqueta sin comillas/corchetes que rompan Mermaid.
    assert "CMP_001" in code and "INT_001" in code
    assert '"' not in code.split("\n", 1)[1].replace('["', "").replace('"]', "")
    assert "-.->" in code  # arista externa punteada
    assert "subgraph" in code


def test_build_context_diagram_actores_e_integraciones():
    actors = [{"id": "ACT-001", "name": "Operador de siniestros"}]
    integrations = [{"id": "INT-001", "name": "Planillas"}]
    code = build_context_diagram(actors, integrations, "Sistema de Siniestros")
    assert "SYS" in code
    assert "Operador de siniestros" in code
    assert "INT_001" in code
