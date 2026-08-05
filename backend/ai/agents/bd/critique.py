"""Nodo CRITIQUE: chequeos deterministas + pase LLM de riesgos.

Primero Python, que es lo reproducible: cobertura hacia el EF (entidades, campos,
validaciones y reglas), tablas huérfanas, columnas candidatas a **dato personal** y
los hallazgos que ya trajeron los nodos anteriores. Después un pase LLM opcional que
solo aporta **riesgos** —volumetría, crecimiento, retención— sin proponer cambios al
modelo.

La cobertura nunca oculta huecos: lo no cubierto se enumera explícitamente, porque
un porcentaje sin la lista de lo que falta es un dato que tranquiliza sin informar.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .naming import snake
from .prompts import build_system
from .schemas.enums import RuleEnforcement, TableKind
from .schemas.extraction import DbCritiqueExtract

#: Fragmentos de nombre que delatan un dato personal. Deliberadamente conservador:
#: marcar de más solo cuesta una pregunta; marcar de menos deja datos sensibles sin
#: señalar en un dominio que maneja personal, papeletas y descuentos.
_PII_HINTS = (
    "nombre",
    "apellido",
    "dni",
    "documento",
    "ruc",
    "correo",
    "email",
    "telefono",
    "celular",
    "direccion",
    "cuenta",
    "cci",
    "sueldo",
    "salario",
    "remuneracion",
    "licencia",
    "placa",
    "firma",
    "foto",
)

#: Por debajo de esta confianza, una tabla o columna merece una segunda mirada.
_LOW_CONFIDENCE = 0.5


def _ids(items: list[dict]) -> list[str]:
    return [i["id"] for i in items or [] if i.get("id")]


def compute_coverage(
    tables: list[dict], rule_mappings: list[dict], sources: dict[str, Any]
) -> dict:
    """Cobertura hacia el EF, con lo no cubierto siempre enumerado."""
    ef = sources.get("ef", {}) or {}
    entity_ids = _ids(ef.get("entities", []))
    field_ids = _ids(ef.get("fields", []))
    validation_ids = _ids(ef.get("validations", []))
    rule_ids = _ids(ef.get("business_rules", []))

    entidades_mapeadas = {t["entity_ref"] for t in tables if t.get("entity_ref")}
    campos_mapeados = {
        c["field_ref"]
        for t in tables
        for c in t.get("columns", [])
        if c.get("field_ref")
    }
    # "Aplicada en el esquema" = declarativa. Las de aplicación/trigger cuentan como
    # NO aplicadas aquí a propósito: el esquema no las hace cumplir, y esconderlo
    # daría una cobertura falsamente tranquilizadora.
    aplicadas = {
        m["rule_ref"]
        for m in rule_mappings
        if m.get("enforcement") == RuleEnforcement.DECLARATIVE.value
    }

    sin_entidad = sorted(set(entity_ids) - entidades_mapeadas)
    sin_campo = sorted(set(field_ids) - campos_mapeados)
    sin_validacion = sorted(set(validation_ids) - aplicadas)
    sin_regla = sorted(set(rule_ids) - aplicadas)

    return {
        "entities_total": len(entity_ids),
        "entities_mapped": len(entity_ids) - len(sin_entidad),
        "uncovered_entity_refs": sin_entidad,
        "fields_total": len(field_ids),
        "fields_mapped": len(field_ids) - len(sin_campo),
        "unmapped_field_refs": sin_campo,
        "validations_total": len(validation_ids),
        "validations_enforced": len(validation_ids) - len(sin_validacion),
        "unenforced_validation_refs": sin_validacion,
        "rules_total": len(rule_ids),
        "rules_enforced": len(rule_ids) - len(sin_regla),
        "unenforced_rule_refs": sin_regla,
    }


def detect_pii(tables: list[dict]) -> list[dict]:
    """Marca y devuelve las columnas candidatas a dato personal.

    No cifra ni transforma nada: **señala**. Decidir el tratamiento (cifrado,
    retención, anonimización) es del DBA y del responsable de datos, no de un
    agente; lo que sí sería un fallo es que nadie lo mencione.
    """
    encontradas: list[dict] = []
    for table in tables:
        for column in table.get("columns", []):
            nombre = snake(column["name"])
            if any(pista in nombre for pista in _PII_HINTS):
                column["pii"] = True
                encontradas.append(
                    {
                        "table": table["name"],
                        "column": column["name"],
                        "ref": column.get("id"),
                    }
                )
    return encontradas


def run_deterministic_checks(
    tables: list[dict],
    rule_mappings: list[dict],
    validation: dict,
    sources: dict[str, Any],
    model_map: dict,
) -> dict:
    """Hallazgos reproducibles del modelo (sin LLM)."""
    coverage = compute_coverage(tables, rule_mappings, sources)
    pii = detect_pii(tables)

    referenciadas = {
        fk["references_table"] for t in tables for fk in t.get("foreign_keys", [])
    }
    huerfanas = [
        t["name"]
        for t in tables
        if not t.get("foreign_keys")
        and t["name"] not in referenciadas
        and t.get("kind") != TableKind.CATALOG.value
        and len(tables) > 1
    ]

    tipos_ambiguos = [
        {
            "table": t["name"],
            "column": c["name"],
            "ref": c.get("id"),
            "required": not c.get("nullable", True),
        }
        for t in tables
        for c in t.get("columns", [])
        if c.get("type_ambiguous")
    ]

    catalogos_sin_semilla = [
        t["name"]
        for t in tables
        if t.get("kind") == TableKind.CATALOG.value
        and not any(
            s.get("table") == t["name"] for s in (sources.get("_seed_data") or [])
        )
    ]

    baja_confianza = [
        {"table": t["name"], "ref": t["id"]}
        for t in tables
        if (t.get("confidence") or 1.0) < _LOW_CONFIDENCE
    ]

    desnormalizadas = [
        {"table": t["name"], "ref": t["id"]}
        for t in tables
        if (t.get("normalization") or {}).get("denormalized")
        and not (t.get("normalization") or {}).get("rationale")
    ]

    relaciones = (model_map or {}).get("relations", {}) or {}
    resumen = (model_map or {}).get("summary", {}) or {}

    return {
        "coverage": coverage,
        "pii_columns": pii,
        "orphan_tables": huerfanas,
        "ambiguous_type_columns": tipos_ambiguos,
        "catalogs_without_seed": catalogos_sin_semilla,
        "low_confidence_tables": baja_confianza,
        "undeclared_denormalization": desnormalizadas,
        "unresolved_one_to_one": list(relaciones.get("needs_owner_decision") or []),
        "orphan_relationships": list(relaciones.get("orphan_relationships") or []),
        "unmapped_field_refs": resumen.get("unmapped_field_refs", []),
        "engine_undecided": not (sources.get("_target") or {}).get(
            "engine_decided", True
        ),
        "ddl_errors": list(validation.get("errors") or []),
        "tables_total": len(tables),
    }


def build_critique_user(findings: dict, tables: list[dict]) -> str:
    """Compone el mensaje del pase LLM: el modelo resumido y lo ya detectado."""
    payload = {
        "tables": [
            {
                "name": t["name"],
                "kind": t.get("kind"),
                "columns": len(t.get("columns", [])),
                "foreign_keys": len(t.get("foreign_keys", [])),
                "indexes": len(t.get("indexes", [])),
                "estimated_volume": t.get("estimated_volume"),
            }
            for t in tables
        ],
        "already_detected": {
            "pii_columns": findings["pii_columns"],
            "orphan_tables": findings["orphan_tables"],
            "coverage": findings["coverage"],
        },
    }
    return "MODELO DE DATOS:\n" + json.dumps(payload, ensure_ascii=False)


def build_observations(findings: dict) -> list[dict]:
    """Observaciones deterministas: lo detectado que no llega a pregunta."""
    observaciones: list[dict] = []
    for tabla in findings["orphan_tables"]:
        observaciones.append(
            {
                "description": f"La tabla {tabla} no participa en ninguna relación.",
                "reason": (
                    "Ni referencia a otra tabla ni es referenciada: conviene "
                    "confirmar que es correcto y no una relación que falta."
                ),
            }
        )
    for item in findings["pii_columns"]:
        observaciones.append(
            {
                "description": (
                    f"{item['table']}.{item['column']} es candidata a dato personal."
                ),
                "reason": (
                    "El modelo no define cifrado ni política de retención: el "
                    "Agente BD lo señala, la decisión es del DBA."
                ),
            }
        )
    for item in findings["undeclared_denormalization"]:
        observaciones.append(
            {
                "description": (
                    f"{item['table']} está desnormalizada sin justificación escrita."
                ),
                "reason": "Una desnormalización deliberada debe declarar su motivo.",
            }
        )
    if findings["tables_total"] == 0:
        observaciones.append(
            {
                "description": "El modelo no tiene ninguna tabla.",
                "reason": "El EF no aportó entidades utilizables.",
            }
        )
    return observaciones


async def run_critique(
    tables: list[dict],
    rule_mappings: list[dict],
    validation: dict,
    sources: dict[str, Any],
    model_map: dict,
    seed_data: list[dict],
    target: dict,
    *,
    llm: Optional[LLMClient] = None,
    engine: str = "postgresql",
    authoritative_context: Optional[str] = None,
    max_repairs: int = 2,
) -> tuple[dict, dict]:
    """Ejecuta la crítica. Devuelve ``(critique, tokens)``.

    ``critique`` lleva ``findings`` (para QUESTION_GEN), ``coverage``,
    ``observations`` y ``risks``.
    """
    # El contexto lleva la semilla y el motor para no cambiar la firma de los
    # chequeos cada vez que uno necesite un dato más del estado.
    contexto = {**sources, "_seed_data": seed_data, "_target": target}
    findings = run_deterministic_checks(
        tables, rule_mappings, validation, contexto, model_map
    )
    observations = build_observations(findings)

    tokens = {"input": 0, "output": 0, "total": 0}
    risks: list[dict] = []
    if llm is not None and tables:
        system = build_system(
            "critique.md", knowledge_block(engine, authoritative_context)
        )
        user = build_critique_user(findings, tables)
        tokens["input"] = estimate_tokens(system + user)
        model, _ = await complete_structured(
            llm,
            system=system,
            user=user,
            schema=DbCritiqueExtract,
            max_repairs=max_repairs,
        )
        if model is not None:
            dumped = model.model_dump(mode="json")
            tokens["output"] = estimate_tokens(json.dumps(dumped, ensure_ascii=False))
            risks = [
                {**risk, "id": f"RISK-{i:03d}", "origin": "derived"}
                for i, risk in enumerate(dumped.get("risks", []), start=1)
            ]

    # Un DDL inválido es un riesgo del modelo, no solo una fila de la validación.
    if findings["ddl_errors"]:
        risks.append(
            {
                "id": f"RISK-{len(risks) + 1:03d}",
                "description": (
                    "El DDL generado no es válido: "
                    f"{len(findings['ddl_errors'])} error(es) estructurales."
                ),
                "severity": "alta",
                "mitigation": (
                    "Revisar los errores de la sección de validación y afinar el "
                    "modelo antes de ejecutarlo."
                ),
                "source_ref": findings["ddl_errors"][0].get("ref"),
                "confidence": 1.0,
                "origin": "derived",
            }
        )

    tokens["total"] = tokens["input"] + tokens["output"]
    return (
        {
            "findings": findings,
            "coverage": findings["coverage"],
            "observations": observations,
            "risks": risks,
        },
        tokens,
    )
