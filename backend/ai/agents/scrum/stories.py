"""Nodo STORIES: una pasada por requisito funcional -> historias (LLM *map*).

Patrón EXTRACT del EF: concurrencia limitada + reparación + cuarentena vía la base
compartida. Cada historia queda anclada a su requisito funcional (anti-alucinación:
prohibido crear una historia sin ``requirement_ref``). Las dependencias entre
historias se resuelven de forma determinista a partir de los requisitos previos.
"""

import json
import unicodedata
from typing import Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import glossary_with_context
from .prompts import build_system
from .schemas.extraction import StoriesExtract


def _all_requirement_ids(ef_context: dict) -> set[str]:
    reqs = ef_context.get("requirements", {})
    ids: set[str] = set()
    for cat in ("business", "functional", "non_functional"):
        ids |= {r["id"] for r in reqs.get(cat, []) if r.get("id")}
    return ids


def build_stories_user(rf: dict, ef_context: dict, epics: list[dict]) -> str:
    """Compone el mensaje con el requisito funcional, su contexto EF y las épicas
    disponibles (para que el LLM asigne ``epic_hint`` a una épica real)."""
    payload = {
        "functional_requirement": {
            "id": rf.get("id"),
            "text": rf.get("text"),
            "priority": rf.get("priority"),
        },
        "epics": [
            {
                "id": e.get("id"),
                "title": e.get("title"),
                "source_refs": e.get("source_refs", []),
            }
            for e in epics
        ],
        "processes": [
            {"id": p.get("id"), "name": p.get("name"), "steps": p.get("steps")}
            for p in ef_context.get("processes", [])
        ],
        "business_rules": [
            {"id": b.get("id"), "statement": b.get("statement")}
            for b in ef_context.get("business_rules", [])
        ],
        "actors": [
            {"id": a.get("id"), "name": a.get("name")}
            for a in ef_context.get("actors", [])
        ],
    }
    return "REQUISITO FUNCIONAL Y CONTEXTO:\n" + json.dumps(payload, ensure_ascii=False)


def _resolve_epic_ref(epic_hint: Optional[str], epics: list[dict]) -> Optional[str]:
    """Resuelve el ``epic_hint`` del LLM a un id de épica real (o None).

    Prioridad para no colapsar todo en la primera épica cuando comparten una ref
    (p. ej. el mismo ``PRO-001``): id exacto de épica > módulo (``MOD-…``, único
    por épica) > título > proceso solo si identifica UNA épica. Con una sola
    épica, todo cuelga de ella."""
    if not epics:
        return None
    if len(epics) == 1:
        return epics[0]["id"]
    if not epic_hint:
        return None
    hint = epic_hint.strip()
    hint_lower = hint.lower()

    # 1) id exacto de épica.
    for ep in epics:
        if hint == ep["id"]:
            return ep["id"]
    # 2) referencia de módulo (única por épica).
    if hint_lower.startswith("mod-"):
        for ep in epics:
            if hint in ep.get("source_refs", []):
                return ep["id"]
    # 3) título de la épica contenido en el hint (o viceversa).
    for ep in epics:
        title = (ep.get("title") or "").lower()
        if title and (hint_lower in title or title in hint_lower):
            return ep["id"]
    # 4) cualquier source_ref (incluye procesos compartidos): solo si es única.
    matches = [ep["id"] for ep in epics if hint in ep.get("source_refs", [])]
    if len(matches) == 1:
        return matches[0]
    return None


async def run_stories(
    llm: LLMClient,
    ef_context: dict,
    epics: list[dict],
    *,
    ef_job_id: str = "",
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], dict]:
    """Genera historias por requisito funcional. Devuelve (stories, skipped, tokens)."""
    glossary_ctx = glossary_with_context(authoritative_context)
    functional = ef_context.get("requirements", {}).get("functional", [])
    valid_req = _all_requirement_ids(ef_context)
    valid_proc = {p["id"] for p in ef_context.get("processes", []) if p.get("id")}
    valid_rule = {b["id"] for b in ef_context.get("business_rules", []) if b.get("id")}

    results, skipped, tokens = await run_structured_map(
        llm,
        functional,
        build_system=lambda _rf: build_system("stories.md", glossary_ctx),
        build_user=lambda rf: build_stories_user(rf, ef_context, epics),
        schema=StoriesExtract,
        ref_of=lambda rf: rf.get("id", "REQ-?"),
        stage="STORIES",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
        max_repairs=max_repairs,
    )

    stories: list[dict] = []
    counter = 1
    for res in results:  # ordenado por ref (RF id) -> ids US-… estables
        rf_id = res["ref"]
        for s in res["data"].get("stories", []):
            req_refs = [r for r in s.get("requirement_refs", []) if r in valid_req]
            if rf_id not in req_refs:  # ancla obligatoria al RF de la pasada
                req_refs.append(rf_id)
            role, goal, benefit = s["role"], s["goal"], s["benefit"]
            story = {
                "id": f"US-{counter:03d}",
                "role": role,
                "goal": goal,
                "benefit": benefit,
                "statement": f"Como {role} quiero {goal} para {benefit}.",
                "epic_ref": _resolve_epic_ref(s.get("epic_hint"), epics),
                "source_refs": {
                    "requirement_refs": req_refs,
                    "process_refs": [
                        r for r in s.get("process_refs", []) if r in valid_proc
                    ],
                    "rule_refs": [r for r in s.get("rule_refs", []) if r in valid_rule],
                },
                "acceptance_criteria": [],
                "dependencies": [],
                "_depends_on_requirements": [
                    r for r in s.get("depends_on_requirements", []) if r in valid_req
                ],
                "tags": _tags(ef_job_id, req_refs),
                "external_key": f"{ef_job_id}:US-{counter:03d}" if ef_job_id else None,
                "confidence": s.get("confidence"),
                "origin": "derived",
            }
            stories.append(story)
            counter += 1

    # Consolida historias redundantes de RF distintos (misma petición): fusiona
    # por similitud y renumera; conserva refs a TODOS los RF de origen.
    stories = _dedupe_stories(stories, ef_job_id)
    _resolve_dependencies(stories)
    _link_epics(stories, epics)
    return stories, skipped, tokens


def _norm(text: str) -> str:
    """Normaliza para comparar: sin acentos, minúsculas, espacios colapsados."""
    nfkd = unicodedata.normalize("NFKD", text or "")
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def _goal_tokens(story: dict) -> set[str]:
    return set(_norm(story.get("goal", "")).split())


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _merge_story(dst: dict, src: dict) -> None:
    """Fusiona ``src`` en ``dst``: une refs y dependencias, conserva confianza."""
    for key in ("requirement_refs", "process_refs", "rule_refs"):
        base = dst["source_refs"][key]
        for r in src["source_refs"].get(key, []):
            if r not in base:
                base.append(r)
    for r in src.get("_depends_on_requirements", []):
        if r not in dst["_depends_on_requirements"]:
            dst["_depends_on_requirements"].append(r)
    sc = src.get("confidence")
    if sc is not None:
        dc = dst.get("confidence")
        dst["confidence"] = sc if dc is None else max(dc, sc)


def _dedupe_stories(
    stories: list[dict], ef_job_id: str, threshold: float = 0.72
) -> list[dict]:
    """Fusiona historias casi duplicadas (mismo rol + objetivo muy similar).

    Solo depende de tokens del ``goal`` (sin embeddings, v1): agrupa variantes de
    la misma petición (p. ej. "ver saldo antes de enviar" repetida en varios RF),
    uniendo sus refs de origen. Renumera los ids y recomputa tags/external_key.
    """
    kept: list[dict] = []
    for st in stories:
        role = _norm(st.get("role", ""))
        toks = _goal_tokens(st)
        match = None
        for k in kept:
            if k["_role"] == role and _jaccard(k["_toks"], toks) >= threshold:
                match = k
                break
        if match is not None:
            _merge_story(match["story"], st)
        else:
            kept.append({"_role": role, "_toks": toks, "story": st})

    result: list[dict] = []
    for i, k in enumerate(kept, start=1):
        st = k["story"]
        st["id"] = f"US-{i:03d}"
        req_refs = st["source_refs"]["requirement_refs"]
        st["tags"] = _tags(ef_job_id, req_refs)
        st["external_key"] = f"{ef_job_id}:{st['id']}" if ef_job_id else None
        result.append(st)
    return result


def _tags(ef_job_id: str, requirement_refs: list[str]) -> list[str]:
    tags: list[str] = []
    if ef_job_id:
        tags.append(f"ef:{ef_job_id}")
    tags.extend(requirement_refs)
    return tags


def _resolve_dependencies(stories: list[dict]) -> None:
    """Mapea ``depends_on_requirements`` a ids de historias (determinista)."""
    req_to_stories: dict[str, list[str]] = {}
    for st in stories:
        for rr in st["source_refs"]["requirement_refs"]:
            req_to_stories.setdefault(rr, []).append(st["id"])

    for st in stories:
        deps: list[str] = []
        for req in st.pop("_depends_on_requirements", []):
            for sid in req_to_stories.get(req, []):
                if sid != st["id"] and sid not in deps:
                    deps.append(sid)
        st["dependencies"] = deps
        # Actualiza los tags de épica una vez resuelto el epic_ref.
        if st.get("epic_ref"):
            st["tags"].append(st["epic_ref"])


def _link_epics(stories: list[dict], epics: list[dict]) -> None:
    """Rellena ``story_ids`` de cada épica según el ``epic_ref`` de las historias."""
    for ep in epics:
        ep["story_ids"] = [st["id"] for st in stories if st.get("epic_ref") == ep["id"]]
