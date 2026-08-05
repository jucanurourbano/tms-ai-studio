"""Nodo MODEL_MAP (determinista): el andamio del modelo físico.

Es la pieza **anti-invención** del agente. Aquí, en Python y sin LLM, queda fijado:

- **Qué tablas existen**: una por entidad del EF, más las tablas puente que exija
  una relación N:M. El LLM que viene después (TABLES) recibe este conjunto ya
  cerrado y solo puede tipar y describir lo que hay; no puede añadir una tabla que
  el EF no pida. Los catálogos son la única ampliación posible y llegan por su
  propio nodo, con detección determinista y evidencia citada.
- **Qué columnas son candidatas**: una por campo del EF de esa entidad, con su
  tipo ya normalizado (``types.normalize_type``), más la PK subrogada y las FK que
  se deriven de las relaciones.
- **Cómo se llama todo**: vía ``naming``, de forma reproducible.

Lo que MODEL_MAP **no** decide (y por eso quedan marcados): la longitud/precisión
exacta, la descripción, el ejemplo, el dueño de una relación 1:1 y las acciones
referenciales cuando el EF no las indica.
"""

from typing import Any, Optional

from .naming import (
    fk_column_name,
    junction_table_name,
    pk_column_name,
    snake,
    table_name,
)
from .schemas.enums import LogicalType, TableKind
from .types import TypeSource, default_length, default_precision, normalize_type

#: Cardinalidades tal como las declara el EF (``ai/agents/ef/schemas/enums.py``).
ONE_TO_ONE = "1:1"
ONE_TO_MANY = "1:N"
MANY_TO_MANY = "N:M"


def _fields_by_entity(fields: list[dict]) -> dict[str, list[dict]]:
    """Campos del EF agrupados por ``entity_ref``, en orden estable."""
    grouped: dict[str, list[dict]] = {}
    for field in fields:
        ref = field.get("entity_ref")
        if ref:
            grouped.setdefault(ref, []).append(field)
    for items in grouped.values():
        items.sort(key=lambda f: f.get("id") or "")
    return grouped


def build_table_candidates(sources: dict[str, Any], engine: str) -> list[dict]:
    """Una tabla candidata por entidad del EF, con sus columnas candidatas.

    El orden de salida sigue el ``id`` de la entidad para que la numeración de
    tablas y columnas sea reproducible entre corridas.
    """
    ef = sources.get("ef", {}) or {}
    entities = sorted(
        (e for e in ef.get("entities", []) or [] if e.get("id")),
        key=lambda e: e["id"],
    )
    fields_by_entity = _fields_by_entity(ef.get("fields", []) or [])

    candidates: list[dict] = []
    for position, entity in enumerate(entities, start=1):
        base = snake(entity.get("name") or entity["id"])
        physical = table_name(entity.get("name") or entity["id"])
        candidates.append(
            {
                "id": f"TBL-{position:03d}",
                "name": physical,
                "singular": base,
                "kind": TableKind.ENTITY.value,
                "entity_ref": entity["id"],
                "entity_name": entity.get("name"),
                "description": entity.get("description"),
                "source_refs": [entity["id"]],
                "origin": entity.get("origin"),
                "confidence": entity.get("confidence"),
                "pk_column": pk_column_name(base),
                "columns": _column_candidates(fields_by_entity.get(entity["id"], [])),
            }
        )
    return candidates


def _column_candidates(fields: list[dict]) -> list[dict]:
    """Columnas candidatas de una tabla, desde los campos del EF de su entidad."""
    columns: list[dict] = []
    for field in fields:
        name = snake(field.get("name") or field.get("id") or "")
        required = bool(field.get("required"))
        decision = normalize_type(
            field.get("data_type"), field_name=name, required=required
        )
        logical = decision.logical_type
        precision, scale = default_precision(logical)
        columns.append(
            {
                "name": name,
                "field_ref": field.get("id"),
                "logical_type": logical.value,
                "type_source": decision.source.value,
                "type_ambiguous": decision.ambiguous,
                "raw_type": decision.raw,
                "length": default_length(logical, name),
                "precision": precision,
                "scale": scale,
                "nullable": not required,
                "source_refs": [
                    ref for ref in (field.get("entity_ref"), field.get("id")) if ref
                ],
                "origin": field.get("origin"),
                "confidence": min(
                    decision.confidence, field.get("confidence") or decision.confidence
                ),
            }
        )
    return columns


def build_relation_plan(
    sources: dict[str, Any], candidates: list[dict], engine: str
) -> dict[str, Any]:
    """Plan de relaciones: FK deterministas, tablas puente y casos a decidir.

    Reglas (deterministas):

    - **1:N** → la FK vive en el lado N. El EF declara ``source`` como el lado 1 y
      ``target`` como el lado N ("una guía puede tener varios siniestros"), así que
      la FK se planta en la tabla de ``target`` apuntando a la de ``source``.
    - **N:M** → tabla puente con PK compuesta. La genera Python: el LLM no crea
      tablas.
    - **1:1** → **no se decide aquí**. Qué lado es dueño de la FK depende de la
      semántica del negocio, así que la relación se deja en ``needs_owner_decision``
      para que RELATIONS (LLM) la resuelva o se pregunte al DBA.

    Una relación que apunte a una entidad inexistente no se descarta en silencio:
    se devuelve en ``orphan_relationships`` para que CRITIQUE la reporte.
    """
    ef = sources.get("ef", {}) or {}
    by_entity = {c["entity_ref"]: c for c in candidates if c.get("entity_ref")}

    foreign_keys: list[dict] = []
    junctions: list[dict] = []
    needs_owner: list[dict] = []
    orphans: list[dict] = []
    seen_junction: set[tuple[str, str]] = set()

    relationships = sorted(
        (r for r in ef.get("relationships", []) or [] if r.get("id")),
        key=lambda r: r["id"],
    )
    for rel in relationships:
        source = by_entity.get(rel.get("source_entity_ref") or "")
        target = by_entity.get(rel.get("target_entity_ref") or "")
        if source is None or target is None:
            orphans.append(
                {
                    "relationship_ref": rel["id"],
                    "reason": (
                        "la relación cita una entidad que no existe en el EF: "
                        f"{rel.get('source_entity_ref')} → "
                        f"{rel.get('target_entity_ref')}"
                    ),
                }
            )
            continue

        cardinality = rel.get("cardinality")
        if cardinality == ONE_TO_MANY:
            foreign_keys.append(_fk_plan(target, source, rel))
        elif cardinality == MANY_TO_MANY:
            key = tuple(sorted((source["name"], target["name"])))
            if key not in seen_junction:
                seen_junction.add(key)
                junctions.append(
                    _junction_plan(
                        source, target, rel, len(candidates) + len(junctions) + 1
                    )
                )
        elif cardinality == ONE_TO_ONE:
            needs_owner.append(
                {
                    "relationship_ref": rel["id"],
                    "candidates": [source["name"], target["name"]],
                    "source_table_ref": source["id"],
                    "target_table_ref": target["id"],
                    "name": rel.get("name"),
                }
            )
        else:
            orphans.append(
                {
                    "relationship_ref": rel["id"],
                    "reason": f"cardinalidad no reconocida: {cardinality!r}",
                }
            )

    return {
        "foreign_keys": foreign_keys,
        "junction_tables": junctions,
        "needs_owner_decision": needs_owner,
        "orphan_relationships": orphans,
    }


def _fk_plan(child: dict, parent: dict, rel: dict) -> dict:
    """FK planificada en el lado N de una relación 1:N."""
    return {
        "table_ref": child["id"],
        "table": child["name"],
        "column": fk_column_name(parent["singular"]),
        "references_table": parent["name"],
        "references_table_ref": parent["id"],
        "references_column": parent["pk_column"],
        "logical_type": LogicalType.BIGINT.value,
        "relationship_ref": rel["id"],
        "relationship_name": rel.get("name"),
        "confidence": rel.get("confidence"),
        "origin": rel.get("origin"),
    }


def _junction_plan(source: dict, target: dict, rel: dict, position: int) -> dict:
    """Tabla puente de una relación N:M, con PK compuesta por las dos FK."""
    name = junction_table_name(source["name"], target["name"])
    left, right = sorted((source, target), key=lambda c: c["name"])
    return {
        "id": f"TBL-{position:03d}",
        "name": name,
        "singular": name,
        "kind": TableKind.JUNCTION.value,
        "entity_ref": None,
        "description": (
            f"Tabla puente de la relación N:M entre {left['name']} y {right['name']}."
        ),
        "relationship_ref": rel["id"],
        "source_refs": [rel["id"], left["entity_ref"], right["entity_ref"]],
        "columns": [
            {
                "name": fk_column_name(left["singular"]),
                "logical_type": LogicalType.BIGINT.value,
                "nullable": False,
                "is_primary_key": True,
                "references_table": left["name"],
                "references_column": left["pk_column"],
                "references_table_ref": left["id"],
            },
            {
                "name": fk_column_name(right["singular"]),
                "logical_type": LogicalType.BIGINT.value,
                "nullable": False,
                "is_primary_key": True,
                "references_table": right["name"],
                "references_column": right["pk_column"],
                "references_table_ref": right["id"],
            },
        ],
    }


def build_model_map(sources: dict[str, Any], engine: str) -> dict[str, Any]:
    """Andamio completo: tablas candidatas + plan de relaciones + resumen.

    El ``summary`` es lo que alimenta la cobertura y las preguntas: cuántas
    entidades y campos entraron, y qué columnas quedaron con el tipo sin resolver.
    """
    candidates = build_table_candidates(sources, engine)
    relations = build_relation_plan(sources, candidates, engine)
    ef = sources.get("ef", {}) or {}

    fields = ef.get("fields", []) or []
    mapped_field_refs = {
        col["field_ref"]
        for table in candidates
        for col in table["columns"]
        if col.get("field_ref")
    }
    unmapped = sorted(
        f["id"] for f in fields if f.get("id") and f["id"] not in mapped_field_refs
    )
    ambiguous = sorted(
        f"{table['name']}.{col['name']}"
        for table in candidates
        for col in table["columns"]
        if col.get("type_ambiguous")
    )
    inferred = sorted(
        f"{table['name']}.{col['name']}"
        for table in candidates
        for col in table["columns"]
        if col.get("type_source") == TypeSource.INFERRED_FROM_NAME.value
    )

    return {
        "tables": candidates,
        "relations": relations,
        "summary": {
            "entities_total": len(ef.get("entities", []) or []),
            "tables_planned": len(candidates) + len(relations["junction_tables"]),
            "fields_total": len(fields),
            "fields_mapped": len(mapped_field_refs),
            # Campos del EF sin `entity_ref`: no se pierden, se reportan.
            "unmapped_field_refs": unmapped,
            "ambiguous_type_columns": ambiguous,
            "inferred_type_columns": inferred,
            "junctions_planned": len(relations["junction_tables"]),
            "relations_needing_owner": len(relations["needs_owner_decision"]),
            "orphan_relationships": len(relations["orphan_relationships"]),
        },
    }


def resolve_audit_columns(sources: dict[str, Any]) -> Optional[list[dict]]:
    """Columnas de auditoría **solo** si la arquitectura las declaró transversales.

    Devuelve ``None`` cuando no hay base para añadirlas: en ese caso no se
    inventan y QUESTION_GEN emite una pregunta no bloqueante. No se hereda la
    convención de TMS AI Studio al sistema diseñado.
    """
    from ai.knowledge import load_db_conventions

    cross_cutting = (sources.get("architecture", {}) or {}).get("cross_cutting", [])
    if not any((xc.get("concern") == "audit") for xc in cross_cutting or []):
        return None
    return list((load_db_conventions().get("audit", {}) or {}).get("columns", []) or [])
