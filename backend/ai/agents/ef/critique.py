"""Fase CRITIQUE: verificación determinística + pase LLM opcional.

- Determinístico (Python): referencias huérfanas, dimensiones faltantes y
  candidatos por baja confianza.
- LLM (opcional, mockeable): ambigüedades e inconsistencias semánticas.
"""

import json
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from ai.knowledge import glossary_block

from .prompts import build_system


class CFinding(BaseModel):
    """Hallazgo del pase LLM de crítica."""

    description: str
    expected_where: Optional[str] = None
    conflicting_refs: list[str] = Field(default_factory=list)
    source_ref: Optional[str] = None
    confidence: Optional[float] = None


class CritiqueExtract(BaseModel):
    """Salida estructurada del pase LLM de crítica."""

    ambiguities: list[CFinding] = Field(default_factory=list)
    missing_info: list[CFinding] = Field(default_factory=list)
    inconsistencies: list[CFinding] = Field(default_factory=list)


def find_orphan_refs(consolidated: dict, inferred: dict) -> list[dict]:
    """Detecta referencias huérfanas (determinístico)."""
    orphans: list[dict] = []

    field_names = {f.get("name") for f in consolidated.get("fields", [])}
    module_names = {m.get("name") for m in consolidated.get("modules", [])}
    entity_ids = {e.get("id") for e in inferred.get("entities", [])}

    for val in consolidated.get("validations", []):
        ref = val.get("field_ref")
        if ref and ref not in field_names:
            orphans.append(
                {"ref": ref, "where": f"validation {val.get('id')}.field_ref"}
            )

    for menu in consolidated.get("menus", []):
        ref = menu.get("module_ref")
        if ref and ref not in module_names:
            orphans.append({"ref": ref, "where": f"menu {menu.get('id')}.module_ref"})

    for crud in inferred.get("crud", []):
        ref = crud.get("entity_ref")
        if ref and ref not in entity_ids:
            orphans.append({"ref": ref, "where": f"crud {crud.get('id')}.entity_ref"})

    return orphans


def _iter_conf_items(consolidated: dict):
    reqs = consolidated.get("requirements", {})
    for cat in ("business", "functional", "non_functional"):
        for r in reqs.get(cat, []):
            yield r, "requisito"
    for key, label in (
        ("actors", "actor"),
        ("modules", "módulo"),
        ("processes", "proceso"),
        ("business_rules", "regla"),
        ("validations", "validación"),
        ("fields", "campo"),
    ):
        for item in consolidated.get(key, []):
            yield item, label


def _with_ids(items: list[dict], prefix: str) -> list[dict]:
    for i, item in enumerate(items, start=1):
        item["id"] = f"{prefix}-{i:03d}"
    return items


async def _llm_pass(llm, consolidated: dict, inferred: dict) -> CritiqueExtract:
    """Pase LLM (mockeable). Ante fallo de schema, devuelve vacío."""
    system = build_system("critique.md", glossary_block())
    user = "MODELO CONSOLIDADO:\n" + json.dumps(
        {"consolidated": consolidated, "inferred": inferred}, ensure_ascii=False
    )
    try:
        raw = await llm.complete_json(system=system, user=user)
        return CritiqueExtract.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError):
        return CritiqueExtract()


async def critique(
    consolidated: dict[str, Any],
    inferred: dict[str, Any],
    *,
    llm=None,
    low_conf_threshold: float = 0.5,
) -> dict[str, Any]:
    """Genera el bloque de análisis crítico."""
    ambiguities: list[dict] = []
    missing_info: list[dict] = []
    inconsistencies: list[dict] = []
    observations: list[dict] = []

    # 1) Referencias huérfanas (determinístico) -> inconsistencias.
    for orphan in find_orphan_refs(consolidated, inferred):
        inconsistencies.append(
            {
                "description": (
                    f"Referencia huérfana: '{orphan['ref']}' en {orphan['where']}."
                ),
                "conflicting_refs": [orphan["ref"]],
                "kind": "orphan_ref",
            }
        )

    # 2) Dimensiones faltantes (determinístico).
    if not consolidated.get("actors"):
        missing_info.append(
            {
                "description": "No se identificaron actores/roles.",
                "expected_where": "Sección de responsabilidades del proceso.",
            }
        )
    if not consolidated.get("processes"):
        missing_info.append(
            {
                "description": "No se identificó ningún proceso.",
                "expected_where": "Descripción del flujo del proceso.",
            }
        )

    # 3) Baja confianza -> candidatos automáticos (ambigüedades).
    for item, label in _iter_conf_items(consolidated):
        conf = item.get("confidence")
        if conf is not None and conf < low_conf_threshold:
            ambiguities.append(
                {
                    "description": (
                        f"Confianza baja ({conf}) en {label} '{item.get('id')}'."
                    ),
                    "confidence": conf,
                    "source_ref": item.get("source_ref"),
                }
            )

    # 4) Pase LLM opcional (ambigüedades/inconsistencias semánticas).
    if llm is not None:
        extra = await _llm_pass(llm, consolidated, inferred)
        ambiguities += [f.model_dump(exclude_none=True) for f in extra.ambiguities]
        missing_info += [f.model_dump(exclude_none=True) for f in extra.missing_info]
        inconsistencies += [
            f.model_dump(exclude_none=True) for f in extra.inconsistencies
        ]

    return {
        "ambiguities": _with_ids(ambiguities, "AMB"),
        "missing_info": _with_ids(missing_info, "MISS"),
        "inconsistencies": _with_ids(inconsistencies, "INC"),
        "observations": _with_ids(observations, "OBS"),
    }
