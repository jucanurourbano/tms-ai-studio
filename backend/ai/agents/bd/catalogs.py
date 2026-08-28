"""Nodo CATALOGS: catálogos detectados + datos semilla **citados** en el EF.

Es la **única** ampliación del conjunto de tablas que MODEL_MAP fijó, y por eso la
más vigilada. Un catálogo se acepta solo si:

- cita al menos un ``source_ref`` real del EF (``PRO-``/``BR-``/``VAL-``/``FLD-``);
- la tabla que lo referenciará existe;
- su nombre no choca con una tabla ya modelada.

Los **valores semilla** exigen ``evidence``: una cita textual del EF. Un catálogo
cuyos valores el EF no enumera se crea **vacío** y genera pregunta al DBA — es la
diferencia entre "el EF dice que hay estados pero no cuáles" y "me he inventado
tres estados que suenan bien". La segunda opción sería la más dañina que podría
cometer este agente: datos plausibles y falsos, con aspecto de verdad.

La parte determinista es la **detección de candidatas** entre las entidades ya
modeladas (nombre con pinta de catálogo + pocas columnas): se marcan como
``kind=catalog`` sin llamar al LLM.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .naming import columns_suffix, constraint_name, pk_column_name, singularize, snake
from .prompts import build_system
from .schemas.enums import LogicalType, PrimaryKeyStrategy, ReferentialAction, TableKind
from .schemas.extraction import CatalogsExtract
from .tables import number_columns

#: Columnas de una tabla de catálogo, desde ``db_conventions.yaml``.
_FALLBACK_COLUMNS = [
    {"name": "codigo", "logical_type": "string", "length": 30, "nullable": False},
    {"name": "nombre", "logical_type": "string", "length": 100, "nullable": False},
]


def detect_catalog_candidates(tables: list[dict]) -> list[dict]:
    """Marca como catálogo las tablas ya modeladas que lo parecen (determinista).

    Criterio: el nombre contiene una de las pistas del YAML (``estado``, ``motivo``,
    ``tipo``…) **y** la tabla tiene pocas columnas de negocio. Devuelve las que se
    reclasificaron, para que quede constancia.
    """
    from ai.knowledge import load_db_conventions

    catalogs = load_db_conventions().get("catalogs", {}) or {}
    hints = [snake(h) for h in catalogs.get("name_hints", []) or []]
    max_fields = int(catalogs.get("max_fields", 4))

    reclasificadas: list[dict] = []
    for table in tables:
        if table.get("kind") != TableKind.ENTITY.value:
            continue
        negocio = [c for c in table.get("columns", []) if c.get("field_ref")]
        nombre = snake(table["name"])
        singular = singularize(nombre)
        if len(negocio) > max_fields:
            continue
        if not any(h in nombre or h == singular for h in hints):
            continue
        table["kind"] = TableKind.CATALOG.value
        reclasificadas.append(table)
    return reclasificadas


def build_catalogs_user(
    tables: list[dict], candidates: list[dict], sources: dict[str, Any]
) -> str:
    """Compone el mensaje: tablas, candidatas detectadas y evidencia del EF."""
    ef = sources.get("ef", {}) or {}
    payload = {
        "tables": [
            {
                "name": t["name"],
                "columns": [c["name"] for c in t.get("columns", [])],
                "kind": t.get("kind"),
            }
            for t in tables
        ],
        "candidates": [
            {
                "table": t["name"],
                "reason": "entidad pequeña con nombre de catálogo",
            }
            for t in candidates
        ],
        "evidence": {
            "processes": [
                {"id": p.get("id"), "name": p.get("name"), "steps": p.get("steps")}
                for p in ef.get("processes", []) or []
            ],
            "rules": [
                {"id": r.get("id"), "statement": r.get("statement")}
                for r in ef.get("business_rules", []) or []
            ],
            "validations": [
                {"id": v.get("id"), "rule": v.get("rule")}
                for v in ef.get("validations", []) or []
            ],
            "fields": [
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "evidence": f.get("evidence"),
                }
                for f in ef.get("fields", []) or []
            ],
        },
    }
    return "CATÁLOGOS A DETECTAR:\n" + json.dumps(payload, ensure_ascii=False)


def _catalog_columns(pk_name: str) -> list[dict]:
    """Columnas de la tabla de catálogo (PK + las de la convención)."""
    from ai.knowledge import load_db_conventions

    spec = (load_db_conventions().get("catalogs", {}) or {}).get(
        "columns"
    ) or _FALLBACK_COLUMNS

    columns: list[dict] = [
        {
            "name": pk_name,
            "logical_type": LogicalType.BIGINT.value,
            "length": None,
            "precision": None,
            "scale": None,
            "nullable": False,
            "default": None,
            "description": "Identificador del elemento del catálogo.",
            "example": "1",
            "is_primary_key": True,
            "is_generated": True,
            "field_ref": None,
            "source_refs": [],
            "type_ambiguous": False,
            "confidence": 0.9,
            "origin": "derived",
        }
    ]
    for spec_col in spec:
        columns.append(
            {
                "name": snake(spec_col["name"]),
                "logical_type": spec_col.get("logical_type", "string"),
                "length": spec_col.get("length"),
                "precision": None,
                "scale": None,
                "nullable": bool(spec_col.get("nullable", True)),
                "default": spec_col.get("default"),
                "description": f"Campo «{spec_col['name']}» del catálogo.",
                "example": None,
                "is_primary_key": False,
                "is_generated": False,
                "field_ref": None,
                "source_refs": [],
                "type_ambiguous": False,
                "confidence": 0.8,
                "origin": "derived",
            }
        )
    return columns


def apply_catalogs(
    tables: list[dict],
    extracted: Optional[dict],
    sources: dict[str, Any],
    engine: str,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Crea las tablas de catálogo y su semilla.

    Devuelve ``(tables, seed_data, observations)``.
    """
    notas: list[dict] = []
    seeds: list[dict] = []
    ef = sources.get("ef", {}) or {}
    validos = {
        i["id"]
        for key in ("processes", "business_rules", "validations", "fields")
        for i in ef.get(key, []) or []
        if i.get("id")
    }
    by_name = {t["name"]: t for t in tables}
    siguiente = len(tables)

    for raw in (extracted or {}).get("catalogs") or []:
        name = snake(raw.get("name") or "")
        if not name:
            continue
        if name in by_name:
            notas.append(
                {
                    "description": f"Catálogo «{name}» no creado.",
                    "reason": "ya existe una tabla con ese nombre en el modelo.",
                }
            )
            continue

        refs = [r for r in raw.get("source_refs") or [] if r in validos]
        if not refs:
            notas.append(
                {
                    "description": f"Catálogo «{name}» descartado.",
                    "reason": (
                        "no cita ninguna referencia real del EF: crear una tabla "
                        "exige base documental (anti-invención)."
                    ),
                }
            )
            continue

        referenced = raw.get("referenced_by") or {}
        parent = by_name.get(snake(referenced.get("table") or ""))
        if parent is None:
            notas.append(
                {
                    "description": f"Catálogo «{name}» descartado.",
                    "reason": (
                        f"la tabla que lo referenciaría "
                        f"(«{referenced.get('table')}») no existe en el modelo."
                    ),
                }
            )
            continue

        siguiente += 1
        pk_name = pk_column_name(singularize(name))
        catalog = {
            "id": f"TBL-{siguiente:03d}",
            "name": name,
            "entity_ref": None,
            "kind": TableKind.CATALOG.value,
            "description": raw.get("description"),
            "columns": _catalog_columns(pk_name),
            "primary_key": {
                "name": constraint_name("primary_key", name, engine),
                "columns": [pk_name],
                "strategy": PrimaryKeyStrategy.SURROGATE.value,
                "rationale": "Catálogo con clave subrogada (convención de la casa).",
                "origin": "derived",
            },
            "foreign_keys": [],
            "unique_constraints": [
                {
                    "id": "",
                    "name": constraint_name(
                        "unique", name, engine, columns=columns_suffix(["codigo"])
                    ),
                    "columns": ["codigo"],
                    "description": "El código del catálogo es único.",
                    "source_refs": refs,
                    "confidence": 0.85,
                    "origin": "derived",
                }
            ],
            "check_constraints": [],
            "indexes": [],
            "estimated_volume": "baja",
            "source_refs": refs,
            "confidence": raw.get("confidence"),
            "origin": "derived",
        }
        tables.append(catalog)
        by_name[name] = catalog

        _link_parent(parent, catalog, referenced, pk_name, refs, engine)
        seed, seed_nota = _build_seed(catalog, raw, refs)
        if seed is not None:
            seeds.append(seed)
        if seed_nota is not None:
            notas.append(seed_nota)

    _number_seeds(seeds)
    number_columns(tables)
    return tables, seeds, notas


def _link_parent(
    parent: dict,
    catalog: dict,
    referenced: dict,
    pk_name: str,
    refs: list[str],
    engine: str,
) -> None:
    """Añade a la tabla padre la columna + FK que apunta al catálogo."""
    column_name = snake(referenced.get("column") or pk_name)
    existente = next(
        (c for c in parent["columns"] if c["name"] == column_name),
        None,
    )
    if existente is None:
        parent["columns"].append(
            {
                "name": column_name,
                "logical_type": LogicalType.BIGINT.value,
                "length": None,
                "precision": None,
                "scale": None,
                "nullable": True,
                "default": None,
                "description": f"Referencia al catálogo {catalog['name']}.",
                "example": "1",
                "is_primary_key": False,
                "is_generated": False,
                "field_ref": None,
                "source_refs": list(refs),
                "type_ambiguous": False,
                "confidence": 0.7,
                "origin": "derived",
            }
        )
    else:
        # La columna ya existía (p. ej. el EF traía `estado`): pasa a ser la FK.
        existente["logical_type"] = LogicalType.BIGINT.value
        existente["length"] = None

    parent["foreign_keys"].append(
        {
            "id": "",
            "name": constraint_name(
                "foreign_key", parent["name"], engine, referenced_table=catalog["name"]
            ),
            "columns": [column_name],
            "references_table": catalog["name"],
            "references_columns": [pk_name],
            "on_delete": ReferentialAction.RESTRICT.value,
            "on_update": ReferentialAction.NO_ACTION.value,
            "relationship_ref": None,
            "rationale": (
                f"El valor de {parent['name']}.{column_name} se administra en el "
                f"catálogo {catalog['name']}."
            ),
            "source_refs": list(refs),
            "confidence": 0.75,
            "origin": "derived",
        }
    )
    # Renumera las FK del esquema completo tras añadir la del catálogo.
    from .relations import _number_foreign_keys

    _number_foreign_keys([parent, catalog])


def _build_seed(
    catalog: dict, raw: dict, refs: list[str]
) -> tuple[Optional[dict], Optional[dict]]:
    """Semilla del catálogo, solo si hay filas **con evidencia** del EF."""
    rows = [r for r in raw.get("rows") or [] if isinstance(r, dict) and r]
    evidence = (raw.get("evidence") or "").strip()

    if not rows:
        return None, {
            "description": f"El catálogo {catalog['name']} se creó sin datos semilla.",
            "reason": (
                "el EF menciona la enumeración pero no enumera sus valores: se "
                "pregunta al DBA en vez de inventarlos."
            ),
        }
    if not evidence:
        return None, {
            "description": (
                f"Se descartaron los {len(rows)} valores semilla de "
                f"{catalog['name']}."
            ),
            "reason": (
                "las filas no citan evidencia textual del EF: un valor inventado "
                "con aspecto de dato real es el peor error posible aquí."
            ),
        }

    disponibles = [c["name"] for c in catalog["columns"] if not c["is_primary_key"]]
    limpias = [{k: v for k, v in row.items() if k in disponibles} for row in rows]
    limpias = [row for row in limpias if row]
    if not limpias:
        return None, {
            "description": f"Semilla de {catalog['name']} descartada.",
            "reason": "ninguna fila usa las columnas del catálogo.",
        }

    # Solo se listan las columnas que las filas traen de verdad. Incluir el resto
    # haría que el INSERT pasara NULL explícito a columnas que tienen DEFAULT
    # (`activo`), y un NULL explícito NO activa el default: la inserción falla.
    presentes = {k for row in limpias for k in row}
    columnas = [c for c in disponibles if c in presentes]

    return {
        "id": "",
        "table_ref": catalog["id"],
        "table": catalog["name"],
        "reason": "Valores del catálogo citados en el EF.",
        "columns": columnas,
        "rows": limpias,
        "source_refs": refs,
        "evidence": evidence,
        "confidence": raw.get("confidence"),
        "origin": "stated",
    }, None


def _number_seeds(seeds: list[dict]) -> None:
    """Numera las semillas con ids estables (``SEED-001``…)."""
    for i, seed in enumerate(seeds, start=1):
        seed["id"] = f"SEED-{i:03d}"


async def run_catalogs(
    llm: LLMClient,
    tables: list[dict],
    sources: dict[str, Any],
    engine: str,
    *,
    authoritative_context: Optional[str] = None,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], list[dict], list[dict], dict]:
    """Detecta catálogos y su semilla.

    Devuelve ``(tables, seed_data, observations, skipped, tokens)``.
    """
    notas: list[dict] = []
    candidates = detect_catalog_candidates(tables)
    for table in candidates:
        notas.append(
            {
                "description": (
                    f"La tabla {table['name']} se reclasificó como catálogo."
                ),
                "reason": (
                    "su nombre y su tamaño corresponden a un catálogo de valores "
                    "administrables, no a una entidad transaccional."
                ),
            }
        )

    system = build_system("catalogs.md", knowledge_block(engine, authoritative_context))
    user = build_catalogs_user(tables, candidates, sources)
    tokens = {"input": estimate_tokens(system + user), "output": 0, "total": 0}
    skipped: list[dict] = []
    extracted: Optional[dict] = None

    model, err = await complete_structured(
        llm,
        system=system,
        user=user,
        schema=CatalogsExtract,
        stage="CATALOGS",
        max_repairs=max_repairs,
    )
    if model is None:
        skipped.append(
            {
                "ref": "CATALOGS",
                "stage": "CATALOGS",
                "reason": f"schema inválido: {err[:150]}",
            }
        )
    else:
        extracted = model.model_dump(mode="json")
        tokens["output"] = estimate_tokens(json.dumps(extracted, ensure_ascii=False))

    tables, seeds, aplicadas = apply_catalogs(tables, extracted, sources, engine)
    tokens["total"] = tokens["input"] + tokens["output"]
    return tables, seeds, notas + aplicadas, skipped, tokens
