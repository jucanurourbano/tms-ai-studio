"""Nodo PRIORITIZE: híbrido (D3).

El LLM propone MoSCoW + valor/esfuerzo por historia; **Python** arma el
``product_backlog`` ordenado de forma determinista (bucket MoSCoW → ratio
valor/esfuerzo → id como desempate estable).
"""

import json
from typing import Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import glossary_with_context
from .prompts import build_system
from .schemas.extraction import PrioritizeExtract

# Orden de los buckets MoSCoW (primario).
_MOSCOW_RANK = {"must": 0, "should": 1, "could": 2, "wont": 3}


def build_prioritize_user(story: dict) -> str:
    """Compone el mensaje con la historia y sus puntos para priorizar."""
    payload = {
        "id": story.get("id"),
        "statement": story.get("statement"),
        "story_points": story.get("story_points"),
        "requirement_refs": story.get("source_refs", {}).get("requirement_refs", []),
    }
    return "HISTORIA A PRIORIZAR:\n" + json.dumps(payload, ensure_ascii=False)


async def run_prioritize(
    llm: LLMClient,
    stories: list[dict],
    *,
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], dict]:
    """Clasifica cada historia (MoSCoW + valor/esfuerzo). Devuelve (stories, skipped, tokens)."""
    if not stories:
        return stories, [], {"input": 0, "output": 0, "total": 0}

    glossary_ctx = glossary_with_context(authoritative_context)
    results, skipped, tokens = await run_structured_map(
        llm,
        stories,
        build_system=lambda _st: build_system("prioritize.md", glossary_ctx),
        build_user=lambda st: build_prioritize_user(st),
        schema=PrioritizeExtract,
        ref_of=lambda st: st["id"],
        stage="PRIORITIZE",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
        max_repairs=max_repairs,
    )

    by_id = {r["ref"]: r["data"] for r in results}
    for story in stories:
        data = by_id.get(story["id"])
        if not data:
            story.setdefault("priority", "could")
            story.setdefault("value", 3)
            story.setdefault("effort", 3)
            continue
        story["priority"] = data["priority"]
        story["value"] = data["value"]
        story["effort"] = data["effort"]

    return stories, skipped, tokens


def build_backlog(stories: list[dict]) -> dict:
    """Ordena el backlog de forma determinista: MoSCoW → valor/esfuerzo → id."""

    def sort_key(s: dict):
        rank = _MOSCOW_RANK.get(s.get("priority") or "could", 2)
        value = s.get("value") or 1
        effort = s.get("effort") or 1
        ratio = value / effort
        return (rank, -ratio, s["id"])

    ordered = sorted(stories, key=sort_key)
    return {
        "method": "moscow",
        "ordered_story_ids": [s["id"] for s in ordered],
        "rationale": (
            "Orden por bucket MoSCoW (must→should→could→wont); dentro de cada "
            "bucket, mayor ratio valor/esfuerzo primero."
        ),
    }
