"""Nodo COMPONENTS: deriva los componentes lógicos (LLM structured, una llamada).

Anti-alucinación: todo componente debe citar al menos una referencia real del
EF/Scrum (`ENT-…`/`API-…`/`MOD-…`/`PRO-…`/`EPIC-…`/`US-…`); si no, se descarta a
cuarentena. Las dependencias (`depends_on`, dadas por nombre) se resuelven de
forma determinista a ids ``CMP-…`` reales.
"""

import json
from typing import Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import glossary_with_context
from .prompts import build_system
from .schemas.extraction import ComponentsExtract

_REF_FIELDS = (
    "epic_refs",
    "story_refs",
    "entity_refs",
    "api_refs",
    "module_refs",
    "process_refs",
)


def _norm(text: str) -> str:
    """Normaliza un nombre para emparejar dependencias (minúsculas, sin espacios extra)."""
    return " ".join((text or "").lower().split())


def valid_refs(sources: dict) -> dict[str, set[str]]:
    """Ids reales por tipo, para validar la trazabilidad de cada componente."""
    ef = sources.get("ef", {}) or {}
    scrum = sources.get("scrum", {}) or {}

    def ids(items: list[dict]) -> set[str]:
        return {i["id"] for i in items or [] if i.get("id")}

    return {
        "entity_refs": ids(ef.get("entities", [])),
        "api_refs": ids(ef.get("apis", [])),
        "module_refs": ids(ef.get("modules", [])),
        "process_refs": ids(ef.get("processes", [])),
        "epic_refs": ids(scrum.get("epics", [])),
        "story_refs": ids(scrum.get("stories", [])),
    }


def build_components_user(sources: dict, size_class: str) -> str:
    """Compone el mensaje con el contexto EF+Scrum relevante para los componentes."""
    ef = sources.get("ef", {}) or {}
    scrum = sources.get("scrum", {}) or {}
    payload = {
        "size_class": size_class,
        "ef": {
            "entities": [
                {"id": e.get("id"), "name": e.get("name")}
                for e in ef.get("entities", [])
            ],
            "apis": [
                {"id": a.get("id"), "method": a.get("method"), "path": a.get("path")}
                for a in ef.get("apis", [])
            ],
            "modules": [
                {"id": m.get("id"), "name": m.get("name")}
                for m in ef.get("modules", [])
            ],
            "processes": [
                {"id": p.get("id"), "name": p.get("name")}
                for p in ef.get("processes", [])
            ],
        },
        "scrum": {
            "epics": [
                {"id": e.get("id"), "title": e.get("title")}
                for e in scrum.get("epics", [])
            ],
            "stories": [
                {"id": s.get("id"), "statement": s.get("statement")}
                for s in scrum.get("stories", [])
            ],
        },
    }
    return "CONTEXTO EF+SCRUM:\n" + json.dumps(payload, ensure_ascii=False)


async def run_components(
    llm: LLMClient,
    sources: dict,
    size_class: str,
    *,
    authoritative_context: Optional[str] = None,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], dict]:
    """Genera los componentes. Devuelve (components, skipped, tokens)."""
    glossary_ctx = glossary_with_context(authoritative_context)
    system = build_system("components.md", glossary_ctx)
    user = build_components_user(sources, size_class)

    tokens = {"input": 0, "output": 0, "total": 0}
    skipped: list[dict] = []
    tokens["input"] += estimate_tokens(system + user)

    model, err = await complete_structured(
        llm, system=system, user=user, schema=ComponentsExtract, max_repairs=max_repairs
    )
    if model is None:
        skipped.append(
            {
                "ref": "COMPONENTS",
                "stage": "COMPONENTS",
                "reason": f"schema inválido: {err[:150]}",
            }
        )
        tokens["total"] = tokens["input"]
        return [], skipped, tokens

    valid = valid_refs(sources)

    # 1) Filtra refs, descarta componentes sin trazabilidad (anti-alucinación).
    pending: list[dict] = []
    for c in model.components:
        filtered = {
            field: [r for r in getattr(c, field) if r in valid[field]]
            for field in _REF_FIELDS
        }
        if sum(len(v) for v in filtered.values()) == 0:
            skipped.append(
                {
                    "ref": f"CMP-src:{c.name[:40]}",
                    "stage": "COMPONENTS",
                    "reason": "componente sin source_ref real del EF/Scrum (anti-alucinación)",
                }
            )
            continue
        pending.append(
            {
                "name": c.name,
                "type": c.type.value,
                "layer": c.layer,
                "responsibility": c.responsibility,
                "source_refs": filtered,
                "depends_on_names": c.depends_on,
                "confidence": c.confidence,
            }
        )

    # 2) Asigna ids estables y arma el mapa nombre -> id.
    name_to_id: dict[str, str] = {}
    for i, p in enumerate(pending, start=1):
        p["id"] = f"CMP-{i:03d}"
        name_to_id[_norm(p["name"])] = p["id"]

    # 3) Resuelve depends_on (nombres -> ids reales; sin auto-dependencia).
    components: list[dict] = []
    for p in pending:
        deps: list[str] = []
        for nm in p["depends_on_names"]:
            rid = name_to_id.get(_norm(nm))
            if rid and rid != p["id"] and rid not in deps:
                deps.append(rid)
        component = {
            "id": p["id"],
            "name": p["name"],
            "type": p["type"],
            "layer": p["layer"],
            "responsibility": p["responsibility"],
            "source_refs": p["source_refs"],
            "depends_on": deps,
            "confidence": p["confidence"],
            "origin": "derived",
        }
        tokens["output"] += estimate_tokens(json.dumps(component, ensure_ascii=False))
        components.append(component)

    tokens["total"] = tokens["input"] + tokens["output"]
    return components, skipped, tokens
