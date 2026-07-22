"""Nodo CRITIQUE: chequeos deterministas (Python) + pase LLM de riesgos.

Determinístico primero: cobertura de épicas (Scrum), entidades (EF) y RNF; ciclos
de dependencia entre componentes; integraciones sin contrato conocido; y
componentes de baja confianza. Luego un pase LLM opcional (mockeable) que solo
aporta riesgos técnicos. Los hallazgos alimentan QUESTION_GEN.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import glossary_with_context
from .prompts import build_system
from .schemas.extraction import CritiqueExtract

_LOW_CONFIDENCE = 0.5


def _ids(items: list[dict]) -> list[str]:
    return [i["id"] for i in items or [] if i.get("id")]


def compute_coverage(
    components: list[dict], cross_cutting: list[dict], sources: dict
) -> dict:
    """Cobertura de épicas/entidades/RNF. Reporta SIEMPRE lo no cubierto."""
    ef = sources.get("ef", {}) or {}
    scrum = sources.get("scrum", {}) or {}
    reqs = ef.get("requirements", {}) or {}

    epic_ids = _ids(scrum.get("epics", []))
    entity_ids = _ids(ef.get("entities", []))
    nfr_ids = _ids(reqs.get("non_functional", []))

    mapped_epics: set[str] = set()
    mapped_entities: set[str] = set()
    for c in components:
        refs = c.get("source_refs", {}) or {}
        mapped_epics.update(refs.get("epic_refs", []) or [])
        mapped_entities.update(refs.get("entity_refs", []) or [])

    addressed_nfr: set[str] = set()
    for xc in cross_cutting:
        addressed_nfr.update(xc.get("source_refs", []) or [])

    uncovered_epics = [e for e in epic_ids if e not in mapped_epics]
    uncovered_entities = [e for e in entity_ids if e not in mapped_entities]
    uncovered_nfr = [n for n in nfr_ids if n not in addressed_nfr]

    return {
        "epics_total": len(epic_ids),
        "epics_mapped": len(epic_ids) - len(uncovered_epics),
        "uncovered_epic_refs": uncovered_epics,
        "entities_total": len(entity_ids),
        "entities_mapped": len(entity_ids) - len(uncovered_entities),
        "uncovered_entity_refs": uncovered_entities,
        "nfr_total": len(nfr_ids),
        "nfr_addressed": len(nfr_ids) - len(uncovered_nfr),
        "uncovered_nfr_refs": uncovered_nfr,
    }


def detect_component_cycles(components: list[dict]) -> list[list[str]]:
    """Detecta ciclos en el grafo de dependencias entre componentes (DFS)."""
    ids = {c["id"] for c in components}
    graph = {
        c["id"]: [d for d in c.get("depends_on", []) if d in ids] for c in components
    }
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    stack: list[str] = []
    cycles: list[list[str]] = []

    def dfs(u: str) -> None:
        color[u] = GRAY
        stack.append(u)
        for v in graph.get(u, []):
            if color.get(v, WHITE) == GRAY:
                cycles.append(stack[stack.index(v) :] + [v])
            elif color.get(v, WHITE) == WHITE:
                dfs(v)
        color[u] = BLACK
        stack.pop()

    for node in sorted(graph):
        if color.get(node, WHITE) == WHITE:
            dfs(node)
    return cycles


async def _llm_risks(
    llm: LLMClient,
    components: list[dict],
    integrations: list[dict],
    authoritative_context,
) -> tuple[list[dict], dict]:
    """Pase LLM opcional de riesgos técnicos (mockeable). Ante fallo, sin riesgos."""
    glossary_ctx = glossary_with_context(authoritative_context)
    system = build_system("critique.md", glossary_ctx)
    payload = {
        "components": [
            {
                "id": c["id"],
                "type": c.get("type"),
                "depends_on": c.get("depends_on", []),
            }
            for c in components
        ],
        "integrations": [
            {
                "id": i["id"],
                "protocol": i.get("protocol"),
                "contract_known": i.get("contract_known"),
            }
            for i in integrations
        ],
    }
    user = "ARQUITECTURA CONSOLIDADA:\n" + json.dumps(payload, ensure_ascii=False)
    tokens = {"input": estimate_tokens(system + user), "output": 0, "total": 0}
    model, _err = await complete_structured(
        llm, system=system, user=user, schema=CritiqueExtract, max_repairs=1
    )
    if model is None:
        tokens["total"] = tokens["input"]
        return [], tokens
    risks = [r.model_dump(mode="json") for r in model.risks]
    tokens["output"] = estimate_tokens(json.dumps(risks, ensure_ascii=False))
    tokens["total"] = tokens["input"] + tokens["output"]
    return risks, tokens


async def run_critique(
    components: list[dict],
    contracts: list[dict],
    integrations: list[dict],
    cross_cutting: list[dict],
    sources: dict,
    *,
    llm: Optional[LLMClient] = None,
    authoritative_context: Optional[str] = None,
) -> tuple[dict[str, Any], dict]:
    """Genera el bloque de crítica + hallazgos para QUESTION_GEN."""
    coverage = compute_coverage(components, cross_cutting, sources)
    cycles = detect_component_cycles(components)

    no_contract = [
        {"id": i["id"], "name": i.get("name"), "system": i.get("system")}
        for i in integrations
        if not i.get("contract_known")
    ]
    low_conf = [
        c["id"]
        for c in components
        if c.get("confidence") is not None and c["confidence"] < _LOW_CONFIDENCE
    ]

    # Referencias huérfanas en contratos (defensivo; deberían venir válidas).
    comp_and_int = {c["id"] for c in components} | {i["id"] for i in integrations}
    observations: list[dict] = []
    for con in contracts:
        for side in ("from_ref", "to_ref"):
            ref = con.get(side)
            if ref and ref not in comp_and_int:
                observations.append(
                    {
                        "description": f"Contrato {con.get('id')} referencia '{ref}' inexistente.",
                        "reason": "Referencia interna a resolver.",
                    }
                )

    # Riesgos deterministas: ciclos + integraciones sin contrato.
    risks: list[dict] = []
    for cycle in cycles:
        risks.append(
            {
                "description": "Dependencia circular entre componentes: "
                + " -> ".join(cycle),
                "severity": "alta",
                "mitigation": "Romper el ciclo introduciendo una interfaz o invirtiendo la dependencia.",
                "source_ref": cycle[0] if cycle else None,
            }
        )
    for ig in no_contract:
        risks.append(
            {
                "description": (
                    f"La integración con {ig['name']} no tiene contrato conocido "
                    "(protocolo/formato)."
                ),
                "severity": "alta",
                "mitigation": "Confirmar el contrato con el equipo del sistema externo.",
                "source_ref": ig["id"],
            }
        )

    tokens = {"input": 0, "output": 0, "total": 0}
    if llm is not None:
        llm_risks, tokens = await _llm_risks(
            llm, components, integrations, authoritative_context
        )
        risks += llm_risks

    critique_dict = {
        "coverage": coverage,
        "risks": _with_ids(risks, "RISK"),
        "observations": _with_ids(observations, "OBS"),
        "findings": {
            "uncovered_epic_refs": coverage["uncovered_epic_refs"],
            "uncovered_entity_refs": coverage["uncovered_entity_refs"],
            "uncovered_nfr_refs": coverage["uncovered_nfr_refs"],
            "integrations_without_contract": no_contract,
            "component_cycles": cycles,
            "low_confidence_components": low_conf,
        },
    }
    return critique_dict, tokens


def _with_ids(items: list[dict], prefix: str) -> list[dict]:
    for i, item in enumerate(items, start=1):
        item["id"] = f"{prefix}-{i:03d}"
    return items
