"""Nodo ESTIMATE: story points Fibonacci por historia (LLM *map*, D9).

Estimación como **borrador informado** (``origin=derived``): puntos + justificación
+ confianza. Las historias con confianza baja se convierten en pregunta al PO en
QUESTION_GEN; la UI las presenta como "estimación sugerida".
"""

import json
from typing import Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import glossary_with_context
from .prompts import build_system
from .schemas.extraction import EstimateExtract


def build_estimate_user(story: dict) -> str:
    """Compone el mensaje con la historia y sus criterios para estimar."""
    payload = {
        "id": story.get("id"),
        "statement": story.get("statement"),
        "acceptance_criteria": [
            {
                "given": c.get("given"),
                "when": c.get("when"),
                "then": c.get("then"),
                "text": c.get("text"),
            }
            for c in story.get("acceptance_criteria", [])
        ],
        "source_refs": story.get("source_refs", {}),
    }
    return "HISTORIA A ESTIMAR:\n" + json.dumps(payload, ensure_ascii=False)


async def run_estimate(
    llm: LLMClient,
    stories: list[dict],
    *,
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], dict]:
    """Adjunta la estimación a cada historia. Devuelve (stories, skipped, tokens)."""
    if not stories:
        return stories, [], {"input": 0, "output": 0, "total": 0}

    glossary_ctx = glossary_with_context(authoritative_context)
    results, skipped, tokens = await run_structured_map(
        llm,
        stories,
        build_system=lambda _st: build_system("estimate.md", glossary_ctx),
        build_user=lambda st: build_estimate_user(st),
        schema=EstimateExtract,
        ref_of=lambda st: st["id"],
        stage="ESTIMATE",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
        max_repairs=max_repairs,
    )

    by_id = {r["ref"]: r["data"] for r in results}
    for story in stories:
        data = by_id.get(story["id"])
        if not data:
            # Sin estimación válida: queda sin puntos (se preguntará al PO).
            story["story_points"] = None
            story["estimation_rationale"] = None
            story["estimation_confidence"] = None
            continue
        story["story_points"] = data["story_points"]
        story["estimation_rationale"] = data["rationale"]
        story["estimation_confidence"] = data["confidence"]

    return stories, skipped, tokens
