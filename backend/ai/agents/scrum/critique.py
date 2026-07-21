"""Nodo CRITIQUE: chequeos deterministas (Python) + pase LLM de riesgos.

Determinístico primero: cobertura de requisitos funcionales (siempre reportada,
incluidos los RF no cubiertos), referencias huérfanas, ciclos de dependencias,
capacidad excedida y estimaciones de baja confianza. Luego un pase LLM opcional
(mockeable) que solo aporta riesgos.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import glossary_with_context
from .load_ef import functional_requirement_refs
from .prompts import build_system
from .schemas.extraction import CritiqueExtract

_LOW_CONFIDENCE = 0.5


def compute_coverage(stories: list[dict], ef_context: dict) -> dict:
    """Cobertura de RF por >=1 historia. Reporta SIEMPRE los RF no cubiertos (D5)."""
    functional = functional_requirement_refs(ef_context)
    covered: set[str] = set()
    for story in stories:
        for ref in story.get("source_refs", {}).get("requirement_refs", []):
            if ref in functional:
                covered.add(ref)
    uncovered = [rf for rf in functional if rf not in covered]
    total = len(functional)
    return {
        "requirements_total": total,
        "requirements_covered": len(covered),
        "coverage_ratio": round(len(covered) / total, 4) if total else 1.0,
        "uncovered_requirement_refs": uncovered,
    }


def find_orphan_refs(stories: list[dict], epics: list[dict]) -> list[dict]:
    """Referencias internas huérfanas (epic_ref/dependencies inexistentes)."""
    story_ids = {s["id"] for s in stories}
    epic_ids = {e["id"] for e in epics}
    orphans: list[dict] = []
    for s in stories:
        epic_ref = s.get("epic_ref")
        if epic_ref and epic_ref not in epic_ids:
            orphans.append({"ref": epic_ref, "where": f"{s['id']}.epic_ref"})
        for dep in s.get("dependencies", []):
            if dep not in story_ids:
                orphans.append({"ref": dep, "where": f"{s['id']}.dependencies"})
    return orphans


def detect_cycles(stories: list[dict]) -> list[list[str]]:
    """Detecta ciclos en el grafo de dependencias entre historias (DFS)."""
    ids = {s["id"] for s in stories}
    graph = {
        s["id"]: [d for d in s.get("dependencies", []) if d in ids] for s in stories
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
    llm: LLMClient, stories: list[dict], sprints: list[dict], authoritative_context
) -> tuple[list[dict], dict]:
    """Pase LLM opcional de riesgos (mockeable). Ante fallo, sin riesgos."""
    glossary_ctx = glossary_with_context(authoritative_context)
    system = build_system("critique.md", glossary_ctx)
    payload = {
        "stories": [
            {
                "id": s["id"],
                "story_points": s.get("story_points"),
                "priority": s.get("priority"),
                "dependencies": s.get("dependencies", []),
            }
            for s in stories
        ],
        "sprints": [
            {"id": sp["id"], "total_points": sp["total_points"]} for sp in sprints
        ],
    }
    user = "PLAN CONSOLIDADO:\n" + json.dumps(payload, ensure_ascii=False)
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


async def critique(
    stories: list[dict],
    epics: list[dict],
    ef_context: dict,
    unassigned_story_ids: list[str],
    *,
    sprints: Optional[list[dict]] = None,
    llm: Optional[LLMClient] = None,
    authoritative_context: Optional[str] = None,
) -> tuple[dict[str, Any], dict]:
    """Genera el bloque de crítica + hallazgos para QUESTION_GEN.

    Devuelve (critique_dict, tokens). ``critique_dict`` lleva ``coverage``,
    ``risks`` y ``observations`` (para el artefacto) más ``findings`` (para el
    generador de preguntas al PO).
    """
    coverage = compute_coverage(stories, ef_context)
    orphans = find_orphan_refs(stories, epics)
    cycles = detect_cycles(stories)

    unassigned_set = set(unassigned_story_ids or [])
    unassigned_must = [
        s["id"]
        for s in stories
        if s["id"] in unassigned_set and s.get("priority") == "must"
    ]
    low_conf_estimates = [
        s["id"]
        for s in stories
        if s.get("estimation_confidence") is not None
        and s["estimation_confidence"] < _LOW_CONFIDENCE
    ]
    ambiguous = [
        s["id"]
        for s in stories
        if s.get("confidence") is not None and s["confidence"] < _LOW_CONFIDENCE
    ]

    # Observaciones deterministas (técnicas internas): refs huérfanas + capacidad.
    observations: list[dict] = []
    for orphan in orphans:
        observations.append(
            {
                "description": (
                    f"Referencia huérfana: '{orphan['ref']}' en {orphan['where']}."
                ),
                "reason": "Referencia interna a resolver por Sistemas.",
            }
        )
    for sid in unassigned_must:
        observations.append(
            {
                "description": f"Historia 'must' {sid} quedó sin asignar a un sprint.",
                "reason": "Revisar capacidad o dependencias antes de planificar.",
            }
        )

    # Riesgos deterministas (ciclos) + pase LLM opcional.
    risks: list[dict] = []
    for cycle in cycles:
        risks.append(
            {
                "description": (
                    "Dependencia circular entre historias: " + " -> ".join(cycle)
                ),
                "severity": "alta",
                "source_ref": cycle[0] if cycle else None,
            }
        )
    tokens = {"input": 0, "output": 0, "total": 0}
    if llm is not None:
        # El pase de riesgos DEBE ver el plan de sprints final; antes recibía []
        # (RISK "sprints vacío" sobre un plan ya poblado).
        llm_risks, tokens = await _llm_risks(
            llm, stories, sprints or [], authoritative_context
        )
        risks += llm_risks

    critique_dict = {
        "coverage": coverage,
        "risks": _with_ids(risks, "RISK"),
        "observations": _with_ids(observations, "OBS"),
        "findings": {
            "uncovered_requirement_refs": coverage["uncovered_requirement_refs"],
            "cycles": cycles,
            "low_confidence_estimates": low_conf_estimates,
            "ambiguous_stories": ambiguous,
            "unassigned_must": unassigned_must,
        },
    }
    return critique_dict, tokens


def _with_ids(items: list[dict], prefix: str) -> list[dict]:
    for i, item in enumerate(items, start=1):
        item["id"] = f"{prefix}-{i:03d}"
    return items
