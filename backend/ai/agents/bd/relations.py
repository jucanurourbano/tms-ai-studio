"""Nodo RELATIONS: materializa las claves foráneas sobre las tablas.

Reparto de trabajo deliberado:

- **Determinista (Python)**: las FK de las relaciones ``1:N`` —incluida la columna
  que hay que añadir a la tabla hija— y las de las tablas puente ``N:M``. Aquí no
  hay nada que opinar: la cardinalidad dicta dónde va la clave.
- **LLM**: solo dos cosas que una regla no puede resolver — qué lado es dueño de la
  FK en una relación ``1:1`` y si alguna acción referencial debería apartarse del
  ``restrict`` por defecto.

Un ``cascade`` propuesto sin citar una regla del EF **se rechaza**: el borrado en
cascada destruye datos y no puede entrar por inferencia.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .naming import constraint_name, fk_column_name
from .prompts import build_system
from .schemas.enums import LogicalType, ReferentialAction
from .schemas.extraction import RelationsExtract
from .tables import number_columns


def build_relations_user(model_map: dict, sources: dict[str, Any]) -> str:
    """Compone el mensaje con lo que queda por decidir (no con todo el modelo)."""
    relations = model_map.get("relations") or {}
    ef = sources.get("ef", {}) or {}
    payload = {
        "one_to_one": [
            {
                "relationship_ref": item["relationship_ref"],
                "name": item.get("name"),
                "candidates": item.get("candidates", []),
            }
            for item in relations.get("needs_owner_decision") or []
        ],
        "foreign_keys": [
            {
                "relationship_ref": fk["relationship_ref"],
                "table": fk["table"],
                "references_table": fk["references_table"],
                "relationship_name": fk.get("relationship_name"),
            }
            for fk in relations.get("foreign_keys") or []
        ],
        "rules": [
            {"id": r.get("id"), "statement": r.get("statement")}
            for r in ef.get("business_rules", [])
        ],
    }
    return "RELACIONES A DECIDIR:\n" + json.dumps(payload, ensure_ascii=False)


def _fk_entry(
    plan: dict, engine: str, on_delete: str, rationale: str, source_refs: list[str]
) -> dict:
    """Construye la FK del artefacto desde su plan determinista."""
    return {
        "id": "",  # se numera al final, sobre el conjunto completo
        "name": constraint_name(
            "foreign_key",
            plan["table"],
            engine,
            referenced_table=plan["references_table"],
        ),
        "columns": [plan["column"]],
        "references_table": plan["references_table"],
        "references_columns": [plan["references_column"]],
        "on_delete": on_delete,
        "on_update": ReferentialAction.NO_ACTION.value,
        "relationship_ref": plan.get("relationship_ref"),
        "rationale": rationale,
        "source_refs": list(source_refs),
        "confidence": plan.get("confidence"),
        "origin": "derived",
    }


def _fk_column(plan: dict, source_refs: list[str]) -> dict:
    """Columna de FK que se añade a la tabla hija (no viene de un campo del EF)."""
    return {
        "name": plan["column"],
        "logical_type": LogicalType.BIGINT.value,
        "length": None,
        "precision": None,
        "scale": None,
        "nullable": False,
        "default": None,
        "description": (
            f"Referencia a {plan['references_table']} "
            f"({plan.get('relationship_name') or plan.get('relationship_ref')})."
        ),
        "example": "1",
        "is_primary_key": False,
        "is_generated": False,
        "field_ref": None,
        "source_refs": list(source_refs),
        "type_ambiguous": False,
        "confidence": plan.get("confidence") or 0.8,
        "origin": "derived",
    }


def _resolve_action(
    decision: Optional[dict], rules: set[str], notas: list[dict], plan: dict
) -> tuple[str, str, list[str]]:
    """Acción referencial efectiva + justificación + refs, validando ``cascade``."""
    base_rationale = (
        f"Relación {plan.get('relationship_ref')} "
        f"({plan.get('relationship_name') or 'sin nombre'}): la clave foránea vive "
        f"en el lado N."
    )
    if decision is None:
        return ReferentialAction.RESTRICT.value, base_rationale, []

    action = decision.get("on_delete") or ReferentialAction.RESTRICT.value
    refs = [r for r in decision.get("source_refs") or [] if r in rules]
    if action == ReferentialAction.CASCADE.value and not refs:
        notas.append(
            {
                "description": (
                    f"Se descartó ON DELETE CASCADE en {plan['table']} → "
                    f"{plan['references_table']}."
                ),
                "reason": (
                    "El borrado en cascada destruye datos y no cita ninguna regla "
                    "del EF que lo justifique: se aplica RESTRICT."
                ),
            }
        )
        return ReferentialAction.RESTRICT.value, base_rationale, []

    rationale = decision.get("rationale") or base_rationale
    return action, rationale, refs


def apply_relations(
    tables: list[dict],
    model_map: dict,
    extracted: Optional[dict],
    sources: dict[str, Any],
    engine: str,
) -> tuple[list[dict], list[dict]]:
    """Aplica las FK sobre las tablas. Devuelve ``(tables, observations)``."""
    notas: list[dict] = []
    relations = model_map.get("relations") or {}
    extracted = extracted or {}
    by_id = {t["id"]: t for t in tables}
    by_name = {t["name"]: t for t in tables}
    rules = {
        r["id"] for r in (sources.get("ef", {}) or {}).get("business_rules", []) or []
    }

    actions = {
        item["relationship_ref"]: item
        for item in extracted.get("referential_actions") or []
    }

    plans = list(relations.get("foreign_keys") or [])
    plans.extend(_one_to_one_plans(relations, extracted, by_name, notas))

    for plan in plans:
        table = by_id.get(plan["table_ref"])
        if table is None:
            continue
        action, rationale, refs = _resolve_action(
            actions.get(plan.get("relationship_ref")), rules, notas, plan
        )
        source_refs = [plan["relationship_ref"], *refs]
        # La columna solo se añade si no existe ya (el EF puede haber declarado el
        # campo de la FK explícitamente, p. ej. `numero_guia`).
        if plan["column"] not in {c["name"] for c in table["columns"]}:
            column = _fk_column(plan, source_refs)
            column["ordinal"] = len(table["columns"]) + 1
            table["columns"].append(column)
        else:
            for column in table["columns"]:
                if column["name"] == plan["column"]:
                    column["nullable"] = False
        table["foreign_keys"].append(
            _fk_entry(plan, engine, action, rationale, source_refs)
        )

    # Tablas puente: sus dos columnas ya existen; solo faltan las FK.
    for junction in relations.get("junction_tables") or []:
        table = by_id.get(junction["id"])
        if table is None:
            continue
        for col in junction.get("columns", []):
            table["foreign_keys"].append(
                _fk_entry(
                    {
                        "table": junction["name"],
                        "column": col["name"],
                        "references_table": col["references_table"],
                        "references_column": col["references_column"],
                        "relationship_ref": junction.get("relationship_ref"),
                        "confidence": 0.85,
                    },
                    engine,
                    ReferentialAction.RESTRICT.value,
                    "Clave foránea de la tabla puente de una relación N:M.",
                    [junction.get("relationship_ref")],
                )
            )

    _number_foreign_keys(tables)
    # Las FK añaden columnas: hay que renumerar para que los ids sigan siendo
    # únicos y correlativos con el orden final del esquema.
    number_columns(tables)
    return tables, notas


def _one_to_one_plans(
    relations: dict, extracted: dict, by_name: dict, notas: list[dict]
) -> list[dict]:
    """Convierte las decisiones de 1:1 del LLM en planes de FK.

    Sin decisión —o con un dueño que no es ninguno de los dos candidatos— no se
    crea la FK: queda para QUESTION_GEN. Modelar el lado equivocado sería peor que
    dejar la relación sin materializar.
    """
    plans: list[dict] = []
    decisions = {
        item["relationship_ref"]: item for item in extracted.get("one_to_one") or []
    }
    for pending in relations.get("needs_owner_decision") or []:
        ref = pending["relationship_ref"]
        decision = decisions.get(ref)
        owner = (decision or {}).get("owner")
        if not owner or owner not in pending.get("candidates", []):
            notas.append(
                {
                    "description": (
                        f"La relación 1:1 {ref} quedó sin materializar en el esquema."
                    ),
                    "reason": (
                        "No se pudo determinar qué lado es dueño de la clave "
                        "foránea: se pregunta al DBA en vez de elegir al azar."
                    ),
                }
            )
            continue

        child = by_name.get(owner)
        other_name = next(c for c in pending["candidates"] if c != owner)
        parent = by_name.get(other_name)
        if child is None or parent is None:
            continue
        parent_pk = next(
            (c["name"] for c in parent["columns"] if c.get("is_primary_key")), None
        )
        if parent_pk is None:
            continue
        plans.append(
            {
                "table_ref": child["id"],
                "table": child["name"],
                "column": fk_column_name(_singular_of(parent["name"])),
                "references_table": parent["name"],
                "references_table_ref": parent["id"],
                "references_column": parent_pk,
                "relationship_ref": ref,
                "relationship_name": pending.get("name"),
                "confidence": (decision or {}).get("confidence"),
                # En 1:1 la FK además es única: lo marca CONSTRAINTS (BD4).
                "one_to_one": True,
            }
        )
    return plans


def _singular_of(table: str) -> str:
    """Singular del nombre de tabla, para nombrar su columna de FK."""
    from .naming import singularize

    return singularize(table)


def _number_foreign_keys(tables: list[dict]) -> None:
    """Numera las FK de todo el esquema con ids estables (``FK-001``…)."""
    counter = 0
    for table in tables:
        for fk in table["foreign_keys"]:
            counter += 1
            fk["id"] = f"FK-{counter:03d}"


async def run_relations(
    llm: LLMClient,
    tables: list[dict],
    model_map: dict,
    sources: dict[str, Any],
    engine: str,
    *,
    authoritative_context: Optional[str] = None,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Materializa las relaciones. Devuelve ``(tables, observations, skipped, tokens)``.

    Si no hay nada que decidir (ni 1:1 ni FK sobre las que opinar) **no se llama al
    LLM**: las FK deterministas se aplican igual y la corrida no gasta tokens.
    """
    relations = model_map.get("relations") or {}
    tokens = {"input": 0, "output": 0, "total": 0}
    skipped: list[dict] = []
    extracted: Optional[dict] = None

    hay_dudas = bool(relations.get("needs_owner_decision")) or bool(
        relations.get("foreign_keys")
    )
    if hay_dudas:
        system = build_system(
            "relations.md", knowledge_block(engine, authoritative_context)
        )
        user = build_relations_user(model_map, sources)
        tokens["input"] = estimate_tokens(system + user)
        model, err = await complete_structured(
            llm,
            system=system,
            user=user,
            schema=RelationsExtract,
            stage="RELATIONS",
            max_repairs=max_repairs,
        )
        if model is None:
            skipped.append(
                {
                    "ref": "RELATIONS",
                    "stage": "RELATIONS",
                    "reason": f"schema inválido: {err[:150]}",
                }
            )
        else:
            extracted = model.model_dump(mode="json")
            tokens["output"] = estimate_tokens(
                json.dumps(extracted, ensure_ascii=False)
            )

    tokens["total"] = tokens["input"] + tokens["output"]
    tables, notas = apply_relations(tables, model_map, extracted, sources, engine)
    return tables, notas, skipped, tokens
