"""Nodo EPICS: deriva épicas de los módulos y procesos del EF (LLM structured).

Una sola llamada al modelo. Anti-alucinación: toda épica debe citar al menos un
``source_ref`` real (un ``MOD-…`` o ``PRO-…`` del EF); si no, se descarta a
cuarentena (nunca silenciosamente).
"""

import json
from typing import Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import glossary_with_context
from .prompts import build_system
from .schemas.extraction import EpicsExtract


def build_epics_user(modules: list[dict], processes: list[dict]) -> str:
    """Compone el mensaje de usuario con módulos y procesos del EF."""
    payload = {
        "modules": [
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "description": m.get("description"),
            }
            for m in modules
        ],
        "processes": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "description": p.get("description"),
            }
            for p in processes
        ],
    }
    return "MÓDULOS Y PROCESOS DEL EF:\n" + json.dumps(payload, ensure_ascii=False)


async def run_epics(
    llm: LLMClient,
    ef_context: dict,
    *,
    authoritative_context: Optional[str] = None,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], dict]:
    """Genera las épicas. Devuelve (epics, skipped, tokens)."""
    glossary_ctx = glossary_with_context(authoritative_context)
    system = build_system("epics.md", glossary_ctx)
    modules = ef_context.get("modules", [])
    processes = ef_context.get("processes", [])
    valid_refs = {m["id"] for m in modules if m.get("id")} | {
        p["id"] for p in processes if p.get("id")
    }
    user = build_epics_user(modules, processes)

    tokens = {"input": 0, "output": 0, "total": 0}
    skipped: list[dict] = []
    tokens["input"] += estimate_tokens(system + user)

    model, err = await complete_structured(
        llm, system=system, user=user, schema=EpicsExtract, max_repairs=max_repairs
    )
    if model is None:
        skipped.append(
            {
                "ref": "EPICS",
                "stage": "EPICS",
                "reason": f"schema inválido: {err[:150]}",
            }
        )
        tokens["total"] = tokens["input"]
        return [], skipped, tokens

    epics: list[dict] = []
    for epic in model.epics:
        refs = [r for r in epic.source_refs if r in valid_refs]
        if not refs:
            skipped.append(
                {
                    "ref": f"EPIC-src:{epic.title[:40]}",
                    "stage": "EPICS",
                    "reason": "épica sin source_ref real del EF (anti-alucinación)",
                }
            )
            continue
        item = {
            "id": f"EPIC-{len(epics) + 1:03d}",
            "title": epic.title,
            "description": epic.description,
            "source_refs": refs,
            "story_ids": [],
            "confidence": epic.confidence,
            "origin": "derived",
        }
        tokens["output"] += estimate_tokens(json.dumps(item, ensure_ascii=False))
        epics.append(item)

    tokens["total"] = tokens["input"] + tokens["output"]
    return epics, skipped, tokens
