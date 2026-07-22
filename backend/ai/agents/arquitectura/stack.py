"""Nodo STACK: recomienda el stack por capa desde el allow-list de la casa.

El allow-list (`ai/knowledge/tech_stack.yaml`) se inyecta en el prompt y, además,
se valida en Python: una tecnología fuera de la lista blanca de su capa (o una
capa desconocida) se descarta a cuarentena — nunca se cuela un exotismo. Las
tecnologías descartadas por "no estar en la casa" generarán una pregunta al
Arquitecto en el bloque de QUESTION_GEN (A5).
"""

import json
from typing import Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.knowledge import load_tech_stack, tech_stack_block
from ai.tools.chunker import estimate_tokens

from .common import glossary_with_context
from .prompts import build_system
from .schemas.extraction import StackExtract


def allowed_by_layer() -> dict[str, set[str]]:
    """Mapa capa -> conjunto de tecnologías permitidas (desde tech_stack.yaml)."""
    layers = load_tech_stack().get("layers") or {}
    return {layer: set(cfg.get("allowed", []) or []) for layer, cfg in layers.items()}


def build_stack_user(sources: dict, size_class: str, component_types: list[str]) -> str:
    """Compone el mensaje con size_class, RNF y tipos de componente presentes."""
    ef = sources.get("ef", {}) or {}
    nfr = ef.get("requirements", {}).get("non_functional", []) or []
    payload = {
        "size_class": size_class,
        "component_types": component_types,
        "non_functional_requirements": [
            {"id": r.get("id"), "text": r.get("text")} for r in nfr
        ],
    }
    return "ALCANCE PARA EL STACK:\n" + json.dumps(payload, ensure_ascii=False)


async def run_stack(
    llm: LLMClient,
    sources: dict,
    size_class: str,
    component_types: list[str],
    *,
    authoritative_context: Optional[str] = None,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], dict]:
    """Recomienda el stack por capa. Devuelve (stack, skipped, tokens)."""
    glossary_ctx = glossary_with_context(authoritative_context)
    system = build_system("stack.md", glossary_ctx) + "\n\n" + tech_stack_block()
    user = build_stack_user(sources, size_class, component_types)

    tokens = {"input": 0, "output": 0, "total": 0}
    skipped: list[dict] = []
    tokens["input"] += estimate_tokens(system + user)

    model, err = await complete_structured(
        llm, system=system, user=user, schema=StackExtract, max_repairs=max_repairs
    )
    if model is None:
        skipped.append(
            {
                "ref": "STACK",
                "stage": "STACK",
                "reason": f"schema inválido: {err[:150]}",
            }
        )
        tokens["total"] = tokens["input"]
        return [], skipped, tokens

    allowed = allowed_by_layer()

    stack: list[dict] = []
    for choice in model.stack:
        layer_allowed = allowed.get(choice.layer)
        if layer_allowed is None:
            skipped.append(
                {
                    "ref": f"STK:{choice.layer}",
                    "stage": "STACK",
                    "reason": f"capa desconocida fuera del stack de la casa: {choice.layer}",
                }
            )
            continue
        if choice.technology not in layer_allowed:
            skipped.append(
                {
                    "ref": f"STK:{choice.layer}:{choice.technology}",
                    "stage": "STACK",
                    "reason": (
                        f"tecnología «{choice.technology}» fuera del allow-list de "
                        f"«{choice.layer}» (anti-exotismo)"
                    ),
                }
            )
            continue
        # Solo se conservan alternativas que también estén en la lista blanca.
        alternatives = [a for a in choice.alternatives if a in layer_allowed]
        item = {
            "id": f"STK-{len(stack) + 1:03d}",
            "layer": choice.layer,
            "technology": choice.technology,
            "version": choice.version,
            "rationale": choice.rationale,
            "alternatives": alternatives,
            "source_refs": choice.source_refs,
            "confidence": choice.confidence,
            "origin": "derived",
        }
        tokens["output"] += estimate_tokens(json.dumps(item, ensure_ascii=False))
        stack.append(item)

    tokens["total"] = tokens["input"] + tokens["output"]
    return stack, skipped, tokens
