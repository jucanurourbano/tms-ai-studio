"""Nodo TABLES: completa cada tabla candidata (LLM *map*, una pasada por tabla).

El andamio de MODEL_MAP llega ya cerrado: qué tablas hay, qué columnas y con qué
nombres. Este nodo solo **completa** lo que requiere juicio —longitudes, precisión,
descripción, ejemplo, clave primaria— y por eso las salvaguardas de aquí son de
*reconciliación*, no de creatividad:

- Las columnas que el modelo devuelva **de más se descartan** y las que **falten se
  conservan** con su valor pre-normalizado. El conjunto de columnas es el del EF.
- El tipo lógico se acepta, pero si el pre-normalizado venía de un tipo
  **declarado** en el EF y el modelo lo cambia, gana el EF: una fuente declarada
  pesa más que una opinión, y el cambio queda como observación.
- La ambigüedad **no se puede borrar**: si MODEL_MAP no pudo deducir el tipo, el
  modelo no puede declarar que ya está resuelto. Solo puede añadir ambigüedad.

Un *map* por tabla (y no una sola llamada con todo el esquema) mantiene los
prompts pequeños, permite concurrencia y hace que una tabla irreparable caiga a
cuarentena sin arrastrar al resto.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .naming import constraint_name, snake
from .prompts import build_system
from .schemas.enums import LogicalType, PrimaryKeyStrategy, TableKind
from .schemas.extraction import TableExtract
from .types import TypeSource, default_length, default_precision


def number_columns(tables: list[dict]) -> None:
    """Asigna ids ``COL-0001…`` a todas las columnas del esquema, en su orden.

    La numeración es **global** (no por tabla) y se recalcula cada vez que cambia
    el conjunto de columnas, porque RELATIONS añade las columnas de las claves
    foráneas después de TABLES. Se renumera en vez de reservar huecos para que los
    ids no dependan del orden en que corrieron los nodos.
    """
    counter = 0
    for table in tables:
        for ordinal, column in enumerate(table.get("columns", []), start=1):
            counter += 1
            column["id"] = f"COL-{counter:04d}"
            column["ordinal"] = ordinal


def build_tables_user(candidate: dict, sources: dict[str, Any]) -> str:
    """Compone el mensaje de una tabla: su andamio + el contexto del EF que la toca."""
    entity_ref = candidate.get("entity_ref")
    ef = sources.get("ef", {}) or {}
    field_refs = {c.get("field_ref") for c in candidate.get("columns", [])}

    payload = {
        "table": {
            "name": candidate.get("name"),
            "entity_ref": entity_ref,
            "entity_name": candidate.get("entity_name"),
            "description": candidate.get("description"),
            "pk_column": candidate.get("pk_column"),
            "columns": [
                {
                    "name": col.get("name"),
                    "field_ref": col.get("field_ref"),
                    "logical_type": col.get("logical_type"),
                    "type_source": col.get("type_source"),
                    "type_ambiguous": col.get("type_ambiguous"),
                    "raw_type": col.get("raw_type"),
                    "nullable": col.get("nullable"),
                }
                for col in candidate.get("columns", [])
            ],
        },
        "context": {
            # Campos del EF de esta entidad, con lo que dijera el documento.
            "fields": [
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "data_type": f.get("data_type"),
                    "required": f.get("required"),
                    "evidence": f.get("evidence"),
                }
                for f in ef.get("fields", [])
                if f.get("id") in field_refs
            ],
            # Reglas y validaciones ligadas a esos campos (ayudan a tipar).
            "rules": [
                {"id": r.get("id"), "statement": r.get("statement")}
                for r in ef.get("business_rules", [])
            ],
            "validations": [
                {
                    "id": v.get("id"),
                    "rule": v.get("rule"),
                    "field_ref": v.get("field_ref"),
                }
                for v in ef.get("validations", [])
                if v.get("field_ref") in field_refs or not v.get("field_ref")
            ],
        },
    }
    return "TABLA A COMPLETAR:\n" + json.dumps(payload, ensure_ascii=False)


def _reconcile_column(candidate: dict, proposed: Optional[dict]) -> tuple[dict, list]:
    """Funde la columna candidata con lo que propuso el modelo.

    Devuelve ``(columna, notas)``, donde ``notas`` recoge las correcciones que se
    aplicaron sobre la propuesta del modelo, para que ASSEMBLE las registre como
    observaciones (nunca se corrige en silencio).
    """
    notas: list[dict] = []
    logical = LogicalType(candidate["logical_type"])
    ambiguous = bool(candidate.get("type_ambiguous"))
    declared = candidate.get("type_source") == TypeSource.DECLARED.value

    length = candidate.get("length")
    precision = candidate.get("precision")
    scale = candidate.get("scale")
    nullable = bool(candidate.get("nullable", True))
    default = None
    description = candidate.get("description")
    example = None
    confidence = candidate.get("confidence")

    if proposed is not None:
        propuesto = LogicalType(proposed["logical_type"])
        if propuesto is not logical:
            if declared:
                # El EF declaró el tipo: su palabra vale más que la del modelo.
                notas.append(
                    {
                        "description": (
                            f"Se conservó el tipo declarado en el EF para "
                            f"«{candidate['name']}» ({logical.value})."
                        ),
                        "reason": (
                            f"El modelo propuso {propuesto.value}, pero el campo "
                            f"{candidate.get('field_ref')} lo declara explícitamente."
                        ),
                    }
                )
            else:
                logical = propuesto

        length = proposed.get("length") if proposed.get("length") else length
        precision = (
            proposed.get("precision") if proposed.get("precision") else precision
        )
        scale = proposed.get("scale") if proposed.get("scale") is not None else scale
        nullable = bool(proposed.get("nullable", nullable))
        default = proposed.get("default")
        description = proposed.get("description") or description
        example = proposed.get("example")
        if proposed.get("confidence") is not None:
            confidence = proposed["confidence"]
        # La ambigüedad se puede añadir, nunca quitar.
        ambiguous = ambiguous or bool(proposed.get("type_ambiguous"))

    # Coherencia tipo ↔ parámetros: un DATE no lleva longitud, un DECIMAL sí escala.
    if logical is not LogicalType.STRING:
        length = None
    elif not length:
        length = default_length(logical, candidate["name"])
    if logical is not LogicalType.DECIMAL:
        precision, scale = None, None
    elif not precision:
        precision, scale = default_precision(logical)

    column = {
        "name": candidate["name"],
        "logical_type": logical.value,
        "length": length,
        "precision": precision,
        "scale": scale,
        "nullable": nullable,
        "default": default,
        "description": description,
        "example": example,
        "is_primary_key": False,
        "is_generated": False,
        "field_ref": candidate.get("field_ref"),
        "source_refs": list(candidate.get("source_refs") or []),
        "type_ambiguous": ambiguous,
        "confidence": confidence,
        "origin": candidate.get("origin") or "derived",
    }
    return column, notas


def _pk_column(candidate: dict, engine: str) -> dict:
    """Columna de PK subrogada generada por el motor (no viene del EF)."""
    return {
        "name": candidate["pk_column"],
        "logical_type": LogicalType.BIGINT.value,
        "length": None,
        "precision": None,
        "scale": None,
        "nullable": False,
        "default": None,
        "description": f"Identificador interno de {candidate['name']}.",
        "example": "1",
        "is_primary_key": True,
        "is_generated": True,
        "field_ref": None,
        "source_refs": [ref for ref in (candidate.get("entity_ref"),) if ref],
        "type_ambiguous": False,
        "confidence": 0.9,
        "origin": "derived",
    }


def build_table(
    candidate: dict, extracted: Optional[dict], engine: str
) -> tuple[dict, list[dict]]:
    """Ensambla una tabla del artefacto desde su andamio + la salida del modelo.

    Sin salida del modelo (cuarentena) la tabla **igualmente se construye** con lo
    determinista: perder una entidad del EF por un fallo del LLM sería peor que
    entregarla sin descripciones.
    """
    notas: list[dict] = []
    propuestas = {c["name"]: c for c in (extracted or {}).get("columns", [])}

    columns: list[dict] = [_pk_column(candidate, engine)]
    for col in candidate.get("columns", []):
        column, col_notas = _reconcile_column(col, propuestas.get(col["name"]))
        notas.extend(col_notas)
        columns.append(column)

    # Columnas que el modelo se inventó: se descartan dejando rastro.
    conocidas = {c["name"] for c in candidate.get("columns", [])}
    for extra in sorted(set(propuestas) - conocidas):
        notas.append(
            {
                "description": (
                    f"Columna «{extra}» descartada en la tabla " f"{candidate['name']}."
                ),
                "reason": (
                    "El modelo la propuso pero no corresponde a ningún campo del "
                    "EF (anti-invención)."
                ),
            }
        )

    for ordinal, column in enumerate(columns, start=1):
        column["ordinal"] = ordinal

    pk = _resolve_primary_key(candidate, extracted, columns, engine, notas)
    table = {
        "id": candidate["id"],
        "name": candidate["name"],
        "entity_ref": candidate.get("entity_ref"),
        "kind": candidate.get("kind") or TableKind.ENTITY.value,
        "description": (extracted or {}).get("description")
        or candidate.get("description"),
        "columns": columns,
        "primary_key": pk,
        "foreign_keys": [],
        "unique_constraints": [],
        "check_constraints": [],
        "indexes": [],
        "source_refs": list(candidate.get("source_refs") or []),
        "confidence": candidate.get("confidence"),
        "origin": candidate.get("origin") or "derived",
    }
    return table, notas


def _resolve_primary_key(
    candidate: dict,
    extracted: Optional[dict],
    columns: list[dict],
    engine: str,
    notas: list[dict],
) -> dict:
    """Decide la PK: la propuesta del modelo si es válida; si no, la subrogada."""
    name = constraint_name("primary_key", candidate["name"], engine)
    surrogate = {
        "name": name,
        "columns": [candidate["pk_column"]],
        "strategy": PrimaryKeyStrategy.SURROGATE.value,
        "rationale": "Clave subrogada generada por el motor (convención de la casa).",
        "origin": "derived",
    }

    proposed = (extracted or {}).get("primary_key") or {}
    cols = [snake(c) for c in proposed.get("columns") or []]
    existentes = {c["name"] for c in columns}
    if not cols or not set(cols) <= existentes:
        if cols:
            notas.append(
                {
                    "description": (
                        f"Se ignoró la clave primaria propuesta para "
                        f"{candidate['name']}."
                    ),
                    "reason": (
                        f"Cita columnas que no existen en la tabla: "
                        f"{sorted(set(cols) - existentes)}."
                    ),
                }
            )
        return surrogate

    strategy = proposed.get("strategy") or PrimaryKeyStrategy.SURROGATE.value
    if cols == [candidate["pk_column"]]:
        strategy = PrimaryKeyStrategy.SURROGATE.value
    elif strategy == PrimaryKeyStrategy.SURROGATE.value:
        # Dice subrogada pero apunta a columnas del negocio: es natural.
        strategy = (
            PrimaryKeyStrategy.COMPOSITE.value
            if len(cols) > 1
            else PrimaryKeyStrategy.NATURAL.value
        )

    # Una PK natural deja de ser generada por el motor: la subrogada sobra.
    if strategy in (
        PrimaryKeyStrategy.NATURAL.value,
        PrimaryKeyStrategy.COMPOSITE.value,
    ):
        for column in columns:
            if column["name"] == candidate["pk_column"]:
                columns.remove(column)
                break
        for ordinal, column in enumerate(columns, start=1):
            column["ordinal"] = ordinal

    for column in columns:
        column["is_primary_key"] = column["name"] in cols
        if column["name"] in cols:
            column["nullable"] = False

    return {
        "name": name,
        "columns": cols,
        "strategy": strategy,
        "rationale": proposed.get("rationale"),
        "origin": "derived",
    }


async def run_tables(
    llm: LLMClient,
    model_map: dict,
    sources: dict[str, Any],
    engine: str,
    *,
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Completa todas las tablas candidatas.

    Devuelve ``(tables, observations, skipped, tokens)``. Las tablas puente NO
    pasan por el LLM: son íntegramente deterministas.
    """
    candidates = list(model_map.get("tables") or [])
    knowledge = knowledge_block(engine, authoritative_context)
    system = build_system("tables.md", knowledge)

    items = [{"candidate": c} for c in candidates]
    results, skipped, tokens = await run_structured_map(
        llm,
        items,
        build_system=lambda _item: system,
        build_user=lambda item: build_tables_user(item["candidate"], sources),
        schema=TableExtract,
        ref_of=lambda item: item["candidate"]["id"],
        stage="TABLES",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
        max_repairs=max_repairs,
    )

    extracted_by_ref = {r["ref"]: r["data"] for r in results}
    tables: list[dict] = []
    observations: list[dict] = []
    for candidate in candidates:
        table, notas = build_table(
            candidate, extracted_by_ref.get(candidate["id"]), engine
        )
        tables.append(table)
        observations.extend(notas)

    # Tablas puente: deterministas de principio a fin.
    for junction in (model_map.get("relations") or {}).get("junction_tables") or []:
        tables.append(build_junction_table(junction, engine))

    number_columns(tables)
    return tables, observations, skipped, tokens


def build_junction_table(junction: dict, engine: str) -> dict:
    """Tabla puente N:M completa (sin LLM: su forma la dicta la relación)."""
    columns = []
    for ordinal, col in enumerate(junction.get("columns", []), start=1):
        columns.append(
            {
                "name": col["name"],
                "ordinal": ordinal,
                "logical_type": col["logical_type"],
                "length": None,
                "precision": None,
                "scale": None,
                "nullable": False,
                "default": None,
                "description": (
                    f"Referencia a {col['references_table']} en la relación N:M."
                ),
                "example": "1",
                "is_primary_key": True,
                "is_generated": False,
                "field_ref": None,
                "source_refs": [junction.get("relationship_ref")],
                "type_ambiguous": False,
                "confidence": 0.85,
                "origin": "derived",
            }
        )
    return {
        "id": junction["id"],
        "name": junction["name"],
        "entity_ref": None,
        "kind": TableKind.JUNCTION.value,
        "description": junction.get("description"),
        "columns": columns,
        "primary_key": {
            "name": constraint_name("primary_key", junction["name"], engine),
            "columns": [c["name"] for c in columns],
            "strategy": PrimaryKeyStrategy.COMPOSITE.value,
            "rationale": (
                "PK compuesta por las dos claves foráneas: evita duplicar el par."
            ),
            "origin": "derived",
        },
        "foreign_keys": [],
        "unique_constraints": [],
        "check_constraints": [],
        "indexes": [],
        "source_refs": list(junction.get("source_refs") or []),
        "confidence": 0.8,
        "origin": "derived",
    }
