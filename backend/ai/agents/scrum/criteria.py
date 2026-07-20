"""Nodo CRITERIA: criterios de aceptación (Gherkin) por historia (LLM *map*).

Una pasada por historia. Los criterios se anclan a las reglas de negocio y
validaciones del EF ligadas a la historia (anti-alucinación: cada criterio cita al
menos un ``source_ref`` real; si no, se descarta a cuarentena).
"""

import json
from typing import Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import glossary_with_context
from .prompts import build_system
from .schemas.extraction import CriteriaExtract


def build_criteria_user(story: dict, ef_context: dict) -> str:
    """Compone el mensaje con la historia y las reglas/validaciones relacionadas."""
    rule_refs = set(story.get("source_refs", {}).get("rule_refs", []))
    rules = [
        {"id": b.get("id"), "statement": b.get("statement")}
        for b in ef_context.get("business_rules", [])
        if b.get("id") in rule_refs or not rule_refs
    ]
    validations = [
        {"id": v.get("id"), "rule": v.get("rule"), "field_ref": v.get("field_ref")}
        for v in ef_context.get("validations", [])
    ]
    payload = {
        "story": {
            "id": story.get("id"),
            "statement": story.get("statement"),
            "requirement_refs": story.get("source_refs", {}).get(
                "requirement_refs", []
            ),
        },
        "business_rules": rules,
        "validations": validations,
    }
    return "HISTORIA Y REGLAS/VALIDACIONES:\n" + json.dumps(payload, ensure_ascii=False)


async def run_criteria(
    llm: LLMClient,
    stories: list[dict],
    ef_context: dict,
    *,
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], dict]:
    """Adjunta criterios de aceptación a cada historia. Devuelve (stories, skipped, tokens)."""
    if not stories:
        return stories, [], {"input": 0, "output": 0, "total": 0}

    glossary_ctx = glossary_with_context(authoritative_context)
    valid_refs = {
        b["id"] for b in ef_context.get("business_rules", []) if b.get("id")
    } | {v["id"] for v in ef_context.get("validations", []) if v.get("id")}

    results, skipped, tokens = await run_structured_map(
        llm,
        stories,
        build_system=lambda _st: build_system("criteria.md", glossary_ctx),
        build_user=lambda st: build_criteria_user(st, ef_context),
        schema=CriteriaExtract,
        ref_of=lambda st: st["id"],
        stage="CRITERIA",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
        max_repairs=max_repairs,
    )

    by_id = {r["ref"]: r["data"] for r in results}
    for story in stories:
        data = by_id.get(story["id"])
        if not data:
            continue
        criteria: list[dict] = []
        for c in data.get("acceptance_criteria", []):
            refs = [r for r in c.get("source_refs", []) if r in valid_refs]
            is_gherkin = (c.get("format") or "gherkin") == "gherkin"
            has_body = (
                (c.get("given") and c.get("then")) if is_gherkin else c.get("text")
            )
            if not refs or not has_body:
                skipped.append(
                    {
                        "ref": f"{story['id']}:AC",
                        "stage": "CRITERIA",
                        "reason": "criterio sin source_ref real o sin cuerpo",
                    }
                )
                continue
            criteria.append(
                {
                    "id": f"AC-{story['id']}-{len(criteria) + 1:02d}",
                    "format": c.get("format") or "gherkin",
                    "given": c.get("given"),
                    "when": c.get("when"),
                    "then": c.get("then"),
                    "text": c.get("text"),
                    "source_refs": refs,
                    "origin": "derived",
                }
            )
        story["acceptance_criteria"] = criteria

    return stories, skipped, tokens
