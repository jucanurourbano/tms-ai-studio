"""Nodo INDEXES: índices estructurales (deterministas) + justificados (LLM).

Reparto:

- **Determinista**: un índice por cada clave foránea. Sin él, todo ``JOIN`` con el
  padre y toda comprobación de integridad al borrar hacen escaneo completo. No hace
  falta que nadie lo justifique: lo justifica la estructura.
- **LLM**: los índices que solo se explican por **cómo se consulta** la tabla, y que
  por eso exigen citar un patrón de acceso real del EF (``API-``/``CRUD-``/``PRO-``/
  ``US-``).

Tres filtros protegen del sobre-indexado, que es el modo de fallo típico de un
diseño generado: cada índice **cuesta** escrituras y espacio.

1. Sin ``access_pattern_refs`` válidos → se descarta.
2. Duplicado (mismas columnas que la PK, un UNIQUE u otro índice; o prefijo de uno
   existente) → se descarta.
3. Tope de ``BD_MAX_INDEXES_PER_TABLE`` índices no estructurales por tabla.

Los tres dejan ``Observation``: **el tope no es un recorte silencioso**.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .naming import columns_suffix, constraint_name, snake
from .prompts import build_system
from .schemas.enums import TableKind
from .schemas.extraction import IndexesExtract


def _existing_column_sets(table: dict) -> set[tuple[str, ...]]:
    """Conjuntos de columnas ya cubiertos por PK, UNIQUE o índices de la tabla."""
    sets: set[tuple[str, ...]] = set()
    pk = table.get("primary_key") or {}
    if pk.get("columns"):
        sets.add(tuple(pk["columns"]))
    for uq in table.get("unique_constraints", []):
        sets.add(tuple(uq["columns"]))
    for idx in table.get("indexes", []):
        sets.add(tuple(idx["columns"]))
    return sets


def _is_prefix_of_existing(columns: list[str], existing: set[tuple[str, ...]]) -> bool:
    """``True`` si un índice existente ya empieza por estas columnas.

    Un índice ``(estado_id)`` es redundante si ya hay uno ``(estado_id, fecha)``: el
    motor puede usar el prefijo del compuesto.
    """
    target = tuple(columns)
    return any(
        cols[: len(target)] == target for cols in existing if len(cols) >= len(target)
    )


def build_fk_indexes(tables: list[dict], engine: str) -> int:
    """Crea un índice por clave foránea (si no está ya cubierto). Devuelve cuántos."""
    creados = 0
    for table in tables:
        for fk in table.get("foreign_keys", []):
            columns = list(fk["columns"])
            existing = _existing_column_sets(table)
            if tuple(columns) in existing or _is_prefix_of_existing(columns, existing):
                continue
            table.setdefault("indexes", []).append(
                {
                    "id": "",
                    "name": constraint_name(
                        "index", table["name"], engine, columns=columns_suffix(columns)
                    ),
                    "columns": columns,
                    "unique": False,
                    "rationale": (
                        f"Índice de la clave foránea hacia {fk['references_table']}: "
                        "sostiene los JOIN con la tabla padre y la comprobación de "
                        "integridad al borrar."
                    ),
                    "access_pattern_refs": [],
                    "source_refs": [r for r in [fk.get("relationship_ref")] if r],
                    "confidence": 0.85,
                    "origin": "derived",
                }
            )
            creados += 1
    return creados


def valid_access_refs(sources: dict[str, Any]) -> set[str]:
    """Ids reales que pueden justificar un índice (patrones de acceso del EF)."""
    ef = sources.get("ef", {}) or {}
    refs: set[str] = set()
    for key in ("apis", "crud", "processes"):
        refs |= {i["id"] for i in ef.get(key, []) or [] if i.get("id")}
    refs |= {
        s["id"]
        for s in (sources.get("scrum", {}) or {}).get("stories", []) or []
        if s.get("id")
    }
    return refs


def build_indexes_user(tables: list[dict], sources: dict[str, Any]) -> str:
    """Compone el mensaje: esquema resumido + patrones de acceso del EF."""
    ef = sources.get("ef", {}) or {}
    payload = {
        "tables": [
            {
                "name": t["name"],
                "columns": [c["name"] for c in t.get("columns", [])],
                "existing_indexes": [list(cols) for cols in _existing_column_sets(t)],
                "kind": t.get("kind"),
            }
            for t in tables
        ],
        "access_patterns": {
            "apis": [
                {
                    "id": a.get("id"),
                    "method": a.get("method"),
                    "path": a.get("path"),
                    "description": a.get("description"),
                }
                for a in ef.get("apis", []) or []
            ],
            "crud": [
                {
                    "id": c.get("id"),
                    "entity_ref": c.get("entity_ref"),
                    "read": c.get("read"),
                }
                for c in ef.get("crud", []) or []
            ],
            "processes": [
                {"id": p.get("id"), "name": p.get("name"), "steps": p.get("steps")}
                for p in ef.get("processes", []) or []
            ],
        },
    }
    return "ESQUEMA Y PATRONES DE ACCESO:\n" + json.dumps(payload, ensure_ascii=False)


def apply_proposed_indexes(
    tables: list[dict],
    extracted: Optional[dict],
    sources: dict[str, Any],
    engine: str,
    max_per_table: int,
) -> list[dict]:
    """Aplica los índices propuestos por el LLM, con sus tres filtros."""
    notas: list[dict] = []
    by_name = {t["name"]: t for t in tables}
    validos = valid_access_refs(sources)
    contador: dict[str, int] = {}

    for raw in (extracted or {}).get("indexes") or []:
        table = by_name.get(snake(raw.get("table") or ""))
        if table is None:
            notas.append(
                {
                    "description": (f"Índice descartado sobre «{raw.get('table')}»."),
                    "reason": "la tabla no existe en el modelo.",
                }
            )
            continue

        columns = [snake(c) for c in raw.get("columns") or []]
        reales = {c["name"] for c in table.get("columns", [])}
        if not columns or not set(columns) <= reales:
            notas.append(
                {
                    "description": f"Índice descartado en {table['name']}.",
                    "reason": (
                        "cita columnas que no existen: "
                        f"{sorted(set(columns) - reales)}"
                    ),
                }
            )
            continue

        refs = [r for r in raw.get("access_pattern_refs") or [] if r in validos]
        if not refs:
            notas.append(
                {
                    "description": (
                        f"Índice ({', '.join(columns)}) descartado en "
                        f"{table['name']}."
                    ),
                    "reason": (
                        "no cita ningún patrón de acceso real del EF: no hay "
                        "índices «por si acaso»."
                    ),
                }
            )
            continue

        if table.get("kind") == TableKind.CATALOG.value:
            notas.append(
                {
                    "description": (
                        f"Índice ({', '.join(columns)}) descartado en el catálogo "
                        f"{table['name']}."
                    ),
                    "reason": (
                        "un catálogo tiene pocas filas: el escaneo es más rápido "
                        "que el índice."
                    ),
                }
            )
            continue

        existing = _existing_column_sets(table)
        if tuple(columns) in existing or _is_prefix_of_existing(columns, existing):
            notas.append(
                {
                    "description": (
                        f"Índice ({', '.join(columns)}) descartado en "
                        f"{table['name']}."
                    ),
                    "reason": "ya está cubierto por la PK, un UNIQUE u otro índice.",
                }
            )
            continue

        usados = contador.get(table["name"], 0)
        if usados >= max_per_table:
            notas.append(
                {
                    "description": (
                        f"Índice ({', '.join(columns)}) no creado en "
                        f"{table['name']}."
                    ),
                    "reason": (
                        f"se alcanzó el tope de {max_per_table} índices no "
                        "estructurales por tabla (evita el sobre-indexado). "
                        "Revisable si el patrón de acceso lo exige."
                    ),
                }
            )
            continue

        contador[table["name"]] = usados + 1
        table.setdefault("indexes", []).append(
            {
                "id": "",
                "name": constraint_name(
                    "index", table["name"], engine, columns=columns_suffix(columns)
                ),
                "columns": columns,
                "unique": bool(raw.get("unique")),
                "rationale": raw.get("rationale"),
                "access_pattern_refs": refs,
                "source_refs": refs,
                "confidence": raw.get("confidence"),
                "origin": "derived",
            }
        )

    return notas


def number_indexes(tables: list[dict]) -> None:
    """Numera todos los índices del esquema con ids estables (``IDX-001``…)."""
    counter = 0
    for table in tables:
        for index in table.get("indexes", []):
            counter += 1
            index["id"] = f"IDX-{counter:03d}"


async def run_indexes(
    llm: LLMClient,
    tables: list[dict],
    sources: dict[str, Any],
    engine: str,
    *,
    max_per_table: int = 3,
    authoritative_context: Optional[str] = None,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Crea los índices. Devuelve ``(tables, observations, skipped, tokens)``.

    Los índices de FK se crean **antes** de llamar al LLM y se le muestran como
    existentes: así el modelo no gasta esfuerzo proponiendo lo que ya está.
    """
    build_fk_indexes(tables, engine)

    tokens = {"input": 0, "output": 0, "total": 0}
    skipped: list[dict] = []
    extracted: Optional[dict] = None

    system = build_system("indexes.md", knowledge_block(engine, authoritative_context))
    user = build_indexes_user(tables, sources)
    tokens["input"] = estimate_tokens(system + user)
    model, err = await complete_structured(
        llm, system=system, user=user, schema=IndexesExtract, max_repairs=max_repairs
    )
    if model is None:
        skipped.append(
            {
                "ref": "INDEXES",
                "stage": "INDEXES",
                "reason": f"schema inválido: {err[:150]}",
            }
        )
    else:
        extracted = model.model_dump(mode="json")
        tokens["output"] = estimate_tokens(json.dumps(extracted, ensure_ascii=False))

    notas = apply_proposed_indexes(tables, extracted, sources, engine, max_per_table)
    number_indexes(tables)
    tokens["total"] = tokens["input"] + tokens["output"]
    return tables, notas, skipped, tokens
