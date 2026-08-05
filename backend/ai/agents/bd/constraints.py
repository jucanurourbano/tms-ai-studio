"""Nodo CONSTRAINTS: reglas y validaciones del EF → integridad declarativa.

Un *map* por tabla: a cada llamada se le dan solo las reglas (``BR-``) y
validaciones (``VAL-``) que tocan esa tabla, y devuelve las constraints más la
**clasificación de cada regla** (``declarative`` / ``application`` / ``trigger``).

Dos invariantes gobiernan este nodo:

1. **Ninguna regla del EF desaparece.** Toda ``BR-``/``VAL-`` acaba en
   ``rule_mappings`` con un destino, aunque no quepa en el esquema. Si el modelo se
   olvida de clasificar una, Python la registra como no clasificada — visible, para
   que CRITIQUE/QUESTION_GEN la recojan.
2. **Ninguna constraint entra sin validarse.** Las expresiones ``CHECK`` pasan por
   ``expressions.validate_check_expression``; la que no cumple el vocabulario se
   **reclasifica** a ``application`` con su motivo, en vez de generar un DDL que el
   motor rechazaría.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .expressions import (
    REASON_NON_DETERMINISTIC,
    REASON_UNKNOWN_COLUMN,
    validate_check_expression,
)
from .naming import columns_suffix, constraint_name, snake
from .prompts import build_system
from .schemas.enums import RuleEnforcement
from .schemas.extraction import ConstraintsExtract

#: Motivo → explicación en español para la nota del ``rule_mapping``.
_REASON_TEXT = {
    REASON_NON_DETERMINISTIC: (
        "la expresión depende del momento actual (CURRENT_DATE/NOW), que no es "
        "determinista: el motor rechaza el CHECK o lo evalúa solo al insertar"
    ),
    REASON_UNKNOWN_COLUMN: "la expresión cita columnas que no existen en la tabla",
}


def rules_for_table(table: dict, sources: dict[str, Any]) -> tuple[list, list]:
    """Reglas y validaciones del EF que tocan esta tabla.

    Las validaciones se ligan por ``field_ref`` → columna. Las reglas de negocio no
    tienen campo, así que se ofrecen todas: acotarlas por coincidencia de texto
    sería adivinar, y el prompt ya exige citar la regla que se use.
    """
    ef = sources.get("ef", {}) or {}
    field_refs = {
        c.get("field_ref") for c in table.get("columns", []) if c.get("field_ref")
    }
    by_field = {
        c["field_ref"]: c["name"]
        for c in table.get("columns", [])
        if c.get("field_ref")
    }

    validations = [
        {
            "id": v.get("id"),
            "rule": v.get("rule"),
            "field_ref": v.get("field_ref"),
            "column": by_field.get(v.get("field_ref")),
        }
        for v in ef.get("validations", []) or []
        if v.get("field_ref") in field_refs
    ]
    rules = [
        {"id": r.get("id"), "statement": r.get("statement")}
        for r in ef.get("business_rules", []) or []
    ]
    return rules, validations


def build_constraints_user(table: dict, sources: dict[str, Any]) -> str:
    """Compone el mensaje: la tabla ya modelada + sus reglas y validaciones."""
    rules, validations = rules_for_table(table, sources)
    payload = {
        "table": {
            "name": table["name"],
            "columns": [
                {
                    "name": c["name"],
                    "logical_type": c["logical_type"],
                    "nullable": c["nullable"],
                    "is_primary_key": c.get("is_primary_key", False),
                }
                for c in table.get("columns", [])
            ],
            "primary_key": (table.get("primary_key") or {}).get("columns", []),
            "foreign_keys": [
                {
                    "columns": fk["columns"],
                    "references_table": fk["references_table"],
                    "relationship_ref": fk.get("relationship_ref"),
                }
                for fk in table.get("foreign_keys", [])
            ],
        },
        "rules": rules,
        "validations": validations,
    }
    return "TABLA Y REGLAS:\n" + json.dumps(payload, ensure_ascii=False)


def apply_constraints(
    table: dict, extracted: Optional[dict], engine: str
) -> tuple[list[dict], list[dict]]:
    """Aplica las constraints de una tabla. Devuelve ``(rule_mappings, notas)``.

    Muta ``table`` añadiendo unique/check y ajustando ``nullable``.
    """
    notas: list[dict] = []
    mappings: list[dict] = []
    extracted = extracted or {}

    column_names = {c["name"] for c in table.get("columns", [])}
    pk_columns = set((table.get("primary_key") or {}).get("columns", []))
    reclasificadas: dict[str, str] = {}

    # --- UNIQUE ---
    existentes = {tuple(uq["columns"]) for uq in table.get("unique_constraints", [])}
    for raw in extracted.get("unique_constraints") or []:
        cols = [snake(c) for c in raw.get("columns") or []]
        if not cols or not set(cols) <= column_names:
            notas.append(
                {
                    "description": f"UNIQUE descartado en {table['name']}.",
                    "reason": (
                        "cita columnas que no existen en la tabla: "
                        f"{sorted(set(cols) - column_names)}"
                    ),
                }
            )
            continue
        if set(cols) == pk_columns:
            notas.append(
                {
                    "description": f"UNIQUE redundante descartado en {table['name']}.",
                    "reason": "las columnas ya son la clave primaria de la tabla.",
                }
            )
            continue
        if tuple(cols) in existentes:
            continue
        existentes.add(tuple(cols))
        table.setdefault("unique_constraints", []).append(
            {
                "id": "",
                "name": constraint_name(
                    "unique", table["name"], engine, columns=columns_suffix(cols)
                ),
                "columns": cols,
                "description": raw.get("description"),
                "source_refs": list(raw.get("source_refs") or []),
                "confidence": raw.get("confidence"),
                "origin": "derived",
            }
        )

    # --- CHECK (con validación de la expresión) ---
    for raw in extracted.get("check_constraints") or []:
        expression = (raw.get("expression") or "").strip()
        verdict = validate_check_expression(expression, column_names, engine)
        refs = list(raw.get("source_refs") or [])
        if not verdict.ok:
            explicacion = _REASON_TEXT.get(
                verdict.reason, "la expresión no cumple el vocabulario permitido"
            )
            notas.append(
                {
                    "description": (
                        f"CHECK «{expression[:60]}» rechazado en {table['name']}."
                    ),
                    "reason": (
                        f"{explicacion} ({verdict.reason}"
                        f"{': ' + verdict.detail if verdict.detail else ''}). "
                        "La regla pasa a la capa de aplicación."
                    ),
                }
            )
            # La regla no se pierde: se reclasifica.
            for ref in refs:
                reclasificadas[ref] = explicacion
            continue

        suffix = snake(raw.get("suffix") or columns_suffix(sorted(verdict.columns)))
        table.setdefault("check_constraints", []).append(
            {
                "id": "",
                "name": constraint_name("check", table["name"], engine, suffix=suffix),
                "expression": expression,
                "description": raw.get("description"),
                "source_refs": refs,
                "confidence": raw.get("confidence"),
                "origin": "derived",
            }
        )

    # --- NOT NULL ---
    for raw in extracted.get("not_null_columns") or []:
        name = snake(raw.get("column") or "")
        for column in table.get("columns", []):
            if column["name"] == name and column["nullable"]:
                column["nullable"] = False
                column["source_refs"] = list(
                    dict.fromkeys(
                        [
                            *column.get("source_refs", []),
                            *(raw.get("source_refs") or []),
                        ]
                    )
                )

    # --- Clasificación de reglas ---
    for raw in extracted.get("rule_mappings") or []:
        ref = raw.get("rule_ref")
        if not ref:
            continue
        enforcement = raw.get("enforcement") or RuleEnforcement.APPLICATION.value
        note = raw.get("note")
        if ref in reclasificadas:
            # El CHECK que la implementaba se rechazó: manda la realidad.
            enforcement = RuleEnforcement.APPLICATION.value
            note = f"{note or ''} Reclasificada: {reclasificadas[ref]}.".strip()
        mappings.append(
            {
                "id": "",
                "rule_ref": ref,
                "enforcement": enforcement,
                "constraint_ref": None,
                "table_ref": table["id"],
                "note": note,
                "confidence": raw.get("confidence"),
                "origin": "derived",
            }
        )

    return mappings, notas


def link_constraint_refs(tables: list[dict], mappings: list[dict]) -> None:
    """Enlaza cada regla declarativa con la constraint que la implementa.

    Recorre el esquema **entero** de una vez y prefiere la constraint de la misma
    tabla que la regla; solo si no la hay, cualquier otra que cite esa regla. Hacerlo
    tabla a tabla borraba los enlaces ya resueltos al pasar por una tabla sin
    constraints.
    """
    por_tabla_regla: dict[tuple[str, str], str] = {}
    por_regla: dict[str, str] = {}
    for table in tables:
        for group in ("unique_constraints", "check_constraints", "foreign_keys"):
            for item in table.get(group, []):
                for ref in item.get("source_refs", []) or []:
                    por_tabla_regla.setdefault((table["id"], ref), item["id"])
                    por_regla.setdefault(ref, item["id"])

    for mapping in mappings:
        if mapping["enforcement"] != RuleEnforcement.DECLARATIVE.value:
            continue
        ref = mapping["rule_ref"]
        mapping["constraint_ref"] = por_tabla_regla.get(
            (mapping.get("table_ref"), ref)
        ) or por_regla.get(ref)


def add_missing_rule_mappings(
    mappings: list[dict], sources: dict[str, Any]
) -> tuple[list[dict], list[dict]]:
    """Registra las reglas del EF que nadie clasificó. Ninguna se pierde.

    Se marcan como ``application`` porque es el destino conservador (alguien tendrá
    que implementarlas), pero la nota dice **explícitamente** que el modelo no las
    clasificó, para no disfrazar un olvido de decisión.
    """
    notas: list[dict] = []
    ef = sources.get("ef", {}) or {}
    todas = [
        *[r.get("id") for r in ef.get("business_rules", []) or []],
        *[v.get("id") for v in ef.get("validations", []) or []],
    ]
    clasificadas = {m["rule_ref"] for m in mappings}
    for ref in [r for r in todas if r and r not in clasificadas]:
        mappings.append(
            {
                "id": "",
                "rule_ref": ref,
                "enforcement": RuleEnforcement.APPLICATION.value,
                "constraint_ref": None,
                "table_ref": None,
                "note": (
                    "Sin clasificar por el modelo: no se pudo determinar dónde se "
                    "hace cumplir. Queda pendiente de revisión."
                ),
                "confidence": 0.3,
                "origin": "derived",
            }
        )
        notas.append(
            {
                "description": f"La regla {ref} del EF no se clasificó.",
                "reason": (
                    "Ninguna tabla la reclamó: no se pierde, queda registrada como "
                    "pendiente para el DBA."
                ),
            }
        )
    return mappings, notas


def number_constraints(tables: list[dict], mappings: list[dict]) -> None:
    """Numera unique/check y los ``rule_mappings`` con ids estables."""
    uq = ck = 0
    for table in tables:
        for item in table.get("unique_constraints", []):
            uq += 1
            item["id"] = f"UQ-{uq:03d}"
        for item in table.get("check_constraints", []):
            ck += 1
            item["id"] = f"CK-{ck:03d}"
    for i, mapping in enumerate(mappings, start=1):
        mapping["id"] = f"RM-{i:03d}"


async def run_constraints(
    llm: LLMClient,
    tables: list[dict],
    sources: dict[str, Any],
    engine: str,
    *,
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], list[dict], list[dict], dict]:
    """Aplica la integridad declarativa.

    Devuelve ``(tables, rule_mappings, observations, skipped, tokens)``.
    """
    system = build_system(
        "constraints.md", knowledge_block(engine, authoritative_context)
    )
    items = [{"table": t} for t in tables]
    results, skipped, tokens = await run_structured_map(
        llm,
        items,
        build_system=lambda _item: system,
        build_user=lambda item: build_constraints_user(item["table"], sources),
        schema=ConstraintsExtract,
        ref_of=lambda item: item["table"]["id"],
        stage="CONSTRAINTS",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
        max_repairs=max_repairs,
    )

    by_ref = {r["ref"]: r["data"] for r in results}
    mappings: list[dict] = []
    observations: list[dict] = []
    for table in tables:
        table_mappings, notas = apply_constraints(
            table, by_ref.get(table["id"]), engine
        )
        mappings.extend(table_mappings)
        observations.extend(notas)

    mappings, notas = add_missing_rule_mappings(mappings, sources)
    observations.extend(notas)
    number_constraints(tables, mappings)
    link_constraint_refs(tables, mappings)

    return tables, mappings, observations, skipped, tokens
