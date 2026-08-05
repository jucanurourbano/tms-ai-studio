"""Validación determinista del DDL, en capas y **sin LLM**.

El artefacto de este agente es ejecutable, así que "parece correcto" no basta. Se
valida en capas de coste creciente, y el artefacto declara **cuáles se aplicaron**
(``validation.validator`` / ``validation.executed``): un parseo no se presenta como
si fuera una ejecución contra el motor.

- **L1 — estructural (Python puro).** Sobre ``tables[]``, no sobre el texto: nombres
  únicos, toda tabla con PK, FK que resuelven a tabla y columnas existentes y de
  tipo compatible, índices sobre columnas reales, identificadores dentro del límite
  del motor, tipos traducibles y semilla que respeta las columnas obligatorias.
- **L2 — sintaxis en el dialecto destino (sqlglot).** Parsea cada sentencia con el
  dialecto real, sin base de datos ni red. Detecta además errores del propio
  renderizador, que es donde vivirían: si el SQL generado no parsea, el bug no está
  en el modelo sino en este paquete.
- **L3a — ejecución contra SQLite en memoria** (``smoke.py``, se usa en tests).
- **L3b — ejecución contra el motor real** (opt-in, fuera del pipeline).

Ante un error, el pipeline **no se cae**: el hallazgo entra en ``validation.errors``,
el job termina ``COMPLETED_WITH_WARNINGS`` y el semáforo se queda en rojo. Entregar
un DDL roto avisando es útil; caerse, no.
"""

from typing import Any

import sqlglot

from ai.knowledge import engine_type_map, max_identifier_length

from ..expressions import _sqlglot_dialect
from ..naming import is_reserved

#: Tipos lógicos que pueden emparejarse en una FK (todo lo demás debe coincidir).
_COMPATIBLES = {("integer", "bigint"), ("bigint", "integer")}


def _issue(code: str, message: str, ref: str | None = None) -> dict:
    return {"code": code, "message": message, "ref": ref}


def check_structure(tables: list[dict], seed_data: list[dict], engine: str) -> dict:
    """Capa L1: coherencia del modelo antes de mirar una sola línea de SQL."""
    errors: list[dict] = []
    warnings: list[dict] = []
    por_nombre = {t["name"]: t for t in tables}
    limite = max_identifier_length(engine)
    tipos = engine_type_map(engine)

    # Nombres de tabla únicos (comparando sin distinguir mayúsculas: Oracle y SQL
    # Server no las distinguen y dos tablas "iguales" chocarían al crear).
    vistos: dict[str, str] = {}
    for table in tables:
        clave = table["name"].lower()
        if clave in vistos:
            errors.append(
                _issue(
                    "duplicate_table_name",
                    f"Dos tablas se llaman «{table['name']}».",
                    table["id"],
                )
            )
        vistos[clave] = table["id"]

    identificadores: set[str] = set()
    for table in tables:
        _check_table(
            table,
            por_nombre,
            tipos,
            limite,
            identificadores,
            errors,
            warnings,
        )

    _check_seed(seed_data, por_nombre, errors, warnings)

    checks = {
        "no_duplicate_names": not any(
            e["code"].startswith("duplicate") for e in errors
        ),
        "all_tables_have_pk": not any(e["code"] == "table_without_pk" for e in errors),
        "all_fks_resolve": not any(e["code"].startswith("fk_") for e in errors),
        "types_in_engine_map": not any(
            e["code"] == "type_not_mappable" for e in errors
        ),
        "identifiers_within_limits": not any(
            e["code"] == "identifier_too_long" for e in errors
        ),
        "columns_exist": not any(e["code"] == "unknown_column" for e in errors),
        "seed_respects_constraints": not any(
            e["code"].startswith("seed_") for e in errors
        ),
    }
    return {"errors": errors, "warnings": warnings, "checks": checks}


def _check_table(
    table: dict,
    por_nombre: dict,
    tipos: dict,
    limite: int,
    identificadores: set[str],
    errors: list[dict],
    warnings: list[dict],
) -> None:
    """Chequeos de una tabla: columnas, PK, FK, unicidad e índices."""
    columnas = {c["name"]: c for c in table.get("columns", [])}

    if not table.get("columns"):
        errors.append(
            _issue(
                "table_without_columns",
                f"{table['name']} no tiene columnas.",
                table["id"],
            )
        )

    nombres_vistos: set[str] = set()
    for column in table.get("columns", []):
        clave = column["name"].lower()
        if clave in nombres_vistos:
            errors.append(
                _issue(
                    "duplicate_column_name",
                    f"{table['name']}.{column['name']} está repetida.",
                    column.get("id"),
                )
            )
        nombres_vistos.add(clave)

        if column["logical_type"] not in tipos:
            errors.append(
                _issue(
                    "type_not_mappable",
                    (
                        f"{table['name']}.{column['name']}: el motor no tiene tipo "
                        f"para «{column['logical_type']}»."
                    ),
                    column.get("id"),
                )
            )
        if is_reserved(column["name"]):
            warnings.append(
                _issue(
                    "reserved_word",
                    (
                        f"{table['name']}.{column['name']} es una palabra reservada: "
                        "se entrecomilla en el DDL, pero conviene renombrarla."
                    ),
                    column.get("id"),
                )
            )

    # Clave primaria.
    pk = table.get("primary_key")
    if not pk or not pk.get("columns"):
        errors.append(
            _issue(
                "table_without_pk",
                f"{table['name']} no tiene clave primaria.",
                table["id"],
            )
        )
    else:
        for nombre in pk["columns"]:
            if nombre not in columnas:
                errors.append(
                    _issue(
                        "unknown_column",
                        f"La PK de {table['name']} cita «{nombre}», que no existe.",
                        table["id"],
                    )
                )
            elif columnas[nombre].get("nullable"):
                errors.append(
                    _issue(
                        "nullable_pk_column",
                        (
                            f"{table['name']}.{nombre} forma parte de la PK y admite "
                            "nulos."
                        ),
                        columnas[nombre].get("id"),
                    )
                )
        _check_identifier(pk["name"], limite, identificadores, table, errors)

    # Claves foráneas.
    for fk in table.get("foreign_keys", []):
        _check_identifier(fk["name"], limite, identificadores, table, errors)
        destino = por_nombre.get(fk["references_table"])
        if destino is None:
            errors.append(
                _issue(
                    "fk_target_missing",
                    (
                        f"{fk['name']}: la tabla destino «{fk['references_table']}» "
                        "no existe en el modelo."
                    ),
                    fk["id"],
                )
            )
            continue
        destino_columnas = {c["name"]: c for c in destino.get("columns", [])}
        if len(fk["columns"]) != len(fk["references_columns"]):
            errors.append(
                _issue(
                    "fk_arity_mismatch",
                    f"{fk['name']}: distinto número de columnas a cada lado.",
                    fk["id"],
                )
            )
            continue
        for origen, destino_col in zip(fk["columns"], fk["references_columns"]):
            if origen not in columnas:
                errors.append(
                    _issue(
                        "fk_column_missing",
                        f"{fk['name']}: «{origen}» no existe en {table['name']}.",
                        fk["id"],
                    )
                )
                continue
            if destino_col not in destino_columnas:
                errors.append(
                    _issue(
                        "fk_target_column_missing",
                        (
                            f"{fk['name']}: «{destino_col}» no existe en "
                            f"{destino['name']}."
                        ),
                        fk["id"],
                    )
                )
                continue
            tipo_origen = columnas[origen]["logical_type"]
            tipo_destino = destino_columnas[destino_col]["logical_type"]
            if tipo_origen != tipo_destino and (
                (tipo_origen, tipo_destino) not in _COMPATIBLES
            ):
                errors.append(
                    _issue(
                        "fk_type_mismatch",
                        (
                            f"{fk['name']}: {table['name']}.{origen} es "
                            f"{tipo_origen} y {destino['name']}.{destino_col} es "
                            f"{tipo_destino}."
                        ),
                        fk["id"],
                    )
                )
        if fk.get("on_delete") == "set_null":
            obligatorias = [
                c
                for c in fk["columns"]
                if not columnas.get(c, {}).get("nullable", True)
            ]
            if obligatorias:
                errors.append(
                    _issue(
                        "fk_set_null_on_not_null",
                        (
                            f"{fk['name']}: ON DELETE SET NULL sobre columnas "
                            f"obligatorias ({', '.join(obligatorias)})."
                        ),
                        fk["id"],
                    )
                )

    # Unicidad e índices.
    for grupo, etiqueta in (
        (table.get("unique_constraints", []), "UNIQUE"),
        (table.get("indexes", []), "índice"),
    ):
        for item in grupo:
            _check_identifier(item["name"], limite, identificadores, table, errors)
            faltan = [c for c in item["columns"] if c not in columnas]
            if faltan:
                errors.append(
                    _issue(
                        "unknown_column",
                        (
                            f"El {etiqueta} {item['name']} cita columnas "
                            f"inexistentes: {', '.join(faltan)}."
                        ),
                        item.get("id"),
                    )
                )

    if not table.get("indexes") and table.get("foreign_keys"):
        warnings.append(
            _issue(
                "table_without_index",
                f"{table['name']} tiene claves foráneas y ningún índice.",
                table["id"],
            )
        )


def _check_identifier(
    name: str,
    limite: int,
    vistos: set[str],
    table: dict,
    errors: list[dict],
) -> None:
    """Los nombres de constraint/índice son únicos por esquema en casi todo motor."""
    if len(name) > limite:
        errors.append(
            _issue(
                "identifier_too_long",
                f"«{name}» supera el límite de {limite} caracteres del motor.",
                table["id"],
            )
        )
    clave = name.lower()
    if clave in vistos:
        errors.append(
            _issue(
                "duplicate_constraint_name",
                f"El nombre «{name}» se usa en más de un objeto del esquema.",
                table["id"],
            )
        )
    vistos.add(clave)


def _check_seed(
    seed_data: list[dict],
    por_nombre: dict,
    errors: list[dict],
    warnings: list[dict],
) -> None:
    """La semilla debe caber en su tabla: columnas reales y obligatorias cubiertas."""
    for seed in seed_data:
        table = por_nombre.get(seed.get("table"))
        if table is None:
            errors.append(
                _issue(
                    "seed_table_missing",
                    f"La semilla apunta a «{seed.get('table')}», que no existe.",
                    seed.get("id"),
                )
            )
            continue
        columnas = {c["name"]: c for c in table.get("columns", [])}
        faltan = [c for c in seed.get("columns", []) if c not in columnas]
        if faltan:
            errors.append(
                _issue(
                    "seed_unknown_column",
                    (
                        f"La semilla de {table['name']} cita columnas inexistentes: "
                        f"{', '.join(faltan)}."
                    ),
                    seed.get("id"),
                )
            )
            continue
        no_nulas = {
            c["name"]
            for c in table.get("columns", [])
            if not c.get("nullable", True) and not c.get("is_generated")
        }
        # Una columna NOT NULL puede omitirse si tiene DEFAULT, pero NO puede
        # listarse con valor nulo: un NULL explícito no activa el default y la
        # inserción falla. Por eso la omisión y el nulo explícito se miden distinto.
        sin_default = {
            c["name"]
            for c in table.get("columns", [])
            if c["name"] in no_nulas and c.get("default") is None
        }
        sin_cubrir = sorted(sin_default - set(seed.get("columns", [])))
        for row in seed.get("rows", []):
            nulos = [c for c in seed.get("columns", []) if row.get(c) is None]
            faltantes = sorted(set(sin_cubrir) | (no_nulas & set(nulos)))
            if faltantes:
                errors.append(
                    _issue(
                        "seed_missing_required",
                        (
                            f"Una fila semilla de {table['name']} deja sin valor "
                            f"columnas obligatorias: {', '.join(faltantes)}."
                        ),
                        seed.get("id"),
                    )
                )
                break


def check_syntax(scripts: list[dict], engine: str) -> dict:
    """Capa L2: parsea cada sentencia con el dialecto real del motor."""
    errors: list[dict] = []
    dialect = _sqlglot_dialect(engine)
    for script in scripts:
        for statement in script.get("statements", []):
            try:
                parsed = sqlglot.parse(statement, read=dialect)
            except Exception as exc:  # sqlglot.ParseError y derivados
                errors.append(
                    _issue(
                        "sql_syntax_error",
                        (
                            f"{script['name']}: sintaxis inválida en {dialect} "
                            f"({str(exc)[:120]}). Es un fallo del generador, no "
                            "del modelo."
                        ),
                        script["id"],
                    )
                )
                continue
            if len([s for s in parsed if s is not None]) != 1:
                errors.append(
                    _issue(
                        "sql_multiple_statements",
                        f"{script['name']}: una sentencia contiene varias.",
                        script["id"],
                    )
                )
    return {"errors": errors, "checks": {"syntax_parses": not errors}}


def validate_ddl(
    tables: list[dict],
    seed_data: list[dict],
    scripts: list[dict],
    engine: str,
    *,
    cycles: list[str] | None = None,
) -> dict[str, Any]:
    """Ejecuta L1 + L2 y compone el bloque ``validation`` del artefacto."""
    estructura = check_structure(tables, seed_data, engine)
    sintaxis = check_syntax(scripts, engine)

    errors = estructura["errors"] + sintaxis["errors"]
    warnings = list(estructura["warnings"])

    checks = {**estructura["checks"], **sintaxis["checks"]}
    checks["topological_order_ok"] = not cycles
    if cycles:
        warnings.append(
            _issue(
                "fk_cycle",
                (
                    "Ciclo de claves foráneas entre "
                    f"{', '.join(cycles)}: el esquema se crea igual (las FK van en "
                    "un script aparte), pero si las columnas son obligatorias no se "
                    "podrá insertar la primera fila."
                ),
            )
        )

    return {
        "syntax_ok": not errors,
        "engine": engine,
        "validator": "estructural+sqlglot",
        # L1/L2 no ejecutan nada contra un motor: no se presenta como certificación.
        "executed": False,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }
