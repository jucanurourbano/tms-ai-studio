"""Fase CRITIQUE: verificación determinística + pase LLM opcional.

- Determinístico (Python): referencias huérfanas, dimensiones faltantes y
  candidatos por baja confianza.
- LLM (opcional, mockeable): ambigüedades e inconsistencias semánticas.
"""

import json
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from ai.agents.base.structured import loads_json
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

    # Un field_ref válido puede ser el NOMBRE o el FLD-ID del campo (CONSOLIDATE
    # enlaza el texto libre del LLM al FLD-ID; ver consolidate._link_field_refs).
    field_refs = {f.get("name") for f in consolidated.get("fields", [])} | {
        f.get("id") for f in consolidated.get("fields", [])
    }
    module_names = {m.get("name") for m in consolidated.get("modules", [])}
    entity_ids = {e.get("id") for e in inferred.get("entities", [])}

    for val in consolidated.get("validations", []):
        ref = val.get("field_ref")
        if ref and ref not in field_refs:
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


def _finding_dump(finding: CFinding, drop: tuple[str, ...]) -> dict:
    """Serializa un hallazgo del LLM quitando claves no admitidas por su categoría
    (los modelos del artefacto son estrictos; ver CritiqueExtract vs. Ambiguity)."""
    data = finding.model_dump(exclude_none=True)
    for key in drop:
        data.pop(key, None)
    return data


def _with_ids(items: list[dict], prefix: str) -> list[dict]:
    for i, item in enumerate(items, start=1):
        item["id"] = f"{prefix}-{i:03d}"
    return items


async def _llm_pass(
    llm, consolidated: dict, inferred: dict
) -> tuple[CritiqueExtract, Optional[str]]:
    """Pase LLM (mockeable). Devuelve ``(hallazgos, error)``.

    Tolera *fences* markdown (``loads_json``). Si el parseo/validación falla, NO
    lo silencia: devuelve el error para que ``critique`` deje una observación
    (regla: los descartes nunca son silenciosos, CLAUDE.md §6)."""
    system = build_system("critique.md", glossary_block())
    user = "MODELO CONSOLIDADO:\n" + json.dumps(
        {"consolidated": consolidated, "inferred": inferred}, ensure_ascii=False
    )
    try:
        raw = await llm.complete_json(system=system, user=user)
        return CritiqueExtract.model_validate(loads_json(raw)), None
    except (json.JSONDecodeError, ValidationError) as exc:
        return CritiqueExtract(), str(exc)[:200]


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
        extra, error = await _llm_pass(llm, consolidated, inferred)
        # Cada categoría del artefacto es estricta (extra="forbid"): se emiten SOLO
        # los campos que su esquema admite. En particular ``conflicting_refs`` solo
        # aplica a inconsistencias; si se filtrara vacío a una ambigüedad/faltante,
        # el assembler la descartaría (extra_forbidden).
        ambiguities += [
            _finding_dump(f, ("conflicting_refs", "expected_where"))
            for f in extra.ambiguities
        ]
        missing_info += [
            _finding_dump(f, ("conflicting_refs",)) for f in extra.missing_info
        ]
        inconsistencies += [
            _finding_dump(f, ("expected_where",)) for f in extra.inconsistencies
        ]
        if error is not None:
            # El fallo del pase LLM NO es silencioso: queda como observación.
            observations.append(
                {
                    "description": (
                        "El pase semántico de CRITIQUE no pudo interpretarse "
                        f"(sin hallazgos LLM): {error}"
                    ),
                    "reason": "Respuesta del modelo inválida en CRITIQUE.",
                }
            )

    return {
        "ambiguities": _with_ids(ambiguities, "AMB"),
        "missing_info": _with_ids(missing_info, "MISS"),
        "inconsistencies": _with_ids(inconsistencies, "INC"),
        "observations": _with_ids(observations, "OBS"),
    }
