"""Fase CONSOLIDATE: fusiona las extracciones y renumera de forma estable.

Dedupe determinístico + "semántico" aproximado por normalización de texto
(minúsculas, sin acentos, espacios colapsados). v1 no usa embeddings (sin RAG
pgvector), por lo que el dedupe semántico se aproxima con normalización.
La provenance (source_ref) y la confianza se combinan al fusionar duplicados.
"""

import unicodedata
from typing import Any


def _norm(text: str) -> str:
    """Normaliza para comparar: sin acentos, minúsculas, espacios colapsados."""
    nfkd = unicodedata.normalize("NFKD", text)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def _merge(items: list[dict], key: str, prefix: str) -> list[dict]:
    """Fusiona ítems por clave normalizada; renumera con ``prefix``-NNN."""
    merged: dict[str, dict] = {}
    order: list[str] = []

    for item in items:
        raw_key = str(item.get(key, "")).strip()
        norm = _norm(raw_key)
        if not norm:
            continue
        if norm in merged:
            existing = merged[norm]
            src = item.get("source_ref")
            if src:
                existing["_source_refs"].append(src)
            new_conf = item.get("confidence")
            if new_conf is not None:
                cur = existing.get("confidence")
                existing["confidence"] = new_conf if cur is None else max(cur, new_conf)
            if not existing.get("evidence") and item.get("evidence"):
                existing["evidence"] = item["evidence"]
        else:
            copy = dict(item)
            copy["_source_refs"] = (
                [item["source_ref"]] if item.get("source_ref") else []
            )
            merged[norm] = copy
            order.append(norm)

    out: list[dict] = []
    for i, norm in enumerate(order, start=1):
        item = merged[norm]
        srcs = list(dict.fromkeys(item.pop("_source_refs")))
        item["source_ref"] = ",".join(srcs) if srcs else None
        item["id"] = f"{prefix}-{i:03d}"
        out.append(item)
    return out


def _collect(raw: list[dict], dimension: str, subkey: str) -> list[dict]:
    """Junta una sublista (p. ej. 'actors') de todas las extracciones."""
    acc: list[dict] = []
    for entry in raw:
        if entry.get("dimension") == dimension:
            acc.extend(entry.get("data", {}).get(subkey, []) or [])
    return acc


def consolidate(raw_extractions: list[dict]) -> dict[str, Any]:
    """Consolida las extracciones crudas en un modelo funcional deduplicado."""
    return {
        "requirements": {
            "business": _merge(
                _collect(raw_extractions, "requirements", "business"), "text", "REQ-B"
            ),
            "functional": _merge(
                _collect(raw_extractions, "requirements", "functional"),
                "text",
                "REQ-F",
            ),
            "non_functional": _merge(
                _collect(raw_extractions, "requirements", "non_functional"),
                "text",
                "REQ-N",
            ),
        },
        "actors": _merge(_collect(raw_extractions, "actors", "actors"), "name", "ACT"),
        "modules": _merge(
            _collect(raw_extractions, "modules_menus", "modules"), "name", "MOD"
        ),
        "menus": _merge(
            _collect(raw_extractions, "modules_menus", "menus"), "name", "MEN"
        ),
        "processes": _merge(
            _collect(raw_extractions, "processes", "processes"), "name", "PRO"
        ),
        "business_rules": _merge(
            _collect(raw_extractions, "rules_validations", "business_rules"),
            "statement",
            "BR",
        ),
        "validations": _merge(
            _collect(raw_extractions, "rules_validations", "validations"),
            "rule",
            "VAL",
        ),
        "fields": _merge(_collect(raw_extractions, "fields", "fields"), "name", "FLD"),
    }
