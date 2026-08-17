"""Export del plan de pruebas a CSV: casos y matriz de trazabilidad.

**CSV para Excel, no "CSV genérico"** (QA-D6). Dos detalles que no son cosméticos:

- Delimitador ``;``. Excel con configuración regional española espera punto y coma;
  con coma abre todo el archivo en una sola columna y quien lo recibe tiene que
  pasar por el asistente de importación. Un export que exige asistente es un export
  que la mitad de la gente abandona.
- **BOM UTF-8** al principio. Sin él, Excel interpreta el archivo como Latin-1 y
  "guía", "número" y "días" salen rotos en la primera columna que alguien mire. El
  BOM es lo que le dice que son UTF-8.

Con eso, un `.csv` se abre de un doble clic y no hace falta ``openpyxl`` ni generar
un `.xlsx` de verdad: cero dependencias nuevas para el mismo resultado práctico.

Los campos multivalor (pasos, datos, ids de casos) se aplanan con separadores
legibles **dentro de la celda**, no en columnas numeradas: una hoja con
``paso_1``…``paso_12`` sería ilegible y además variable según el caso más largo.
"""

import csv
import io
from typing import Any

#: Marca de orden de bytes UTF-8. Es lo que hace que Excel no lea Latin-1.
BOM = "﻿"

#: Delimitador que espera Excel en configuración regional española.
DELIMITER = ";"

_CASE_COLUMNS = (
    ("id", "ID"),
    ("title", "Título"),
    ("type", "Tipo"),
    ("priority", "Prioridad"),
    ("story_ref", "Historia"),
    ("criterion_ref", "Criterio"),
    ("epic_ref", "Épica"),
    ("preconditions", "Precondiciones"),
    ("steps", "Pasos"),
    ("test_data", "Datos de prueba"),
    ("expected_result", "Resultado esperado"),
    ("boundary", "Límite probado"),
    ("evidence", "Evidencia (verbatim)"),
    ("auth_rule", "Regla de autorización"),
    ("automation_hint", "Automatizable por"),
    ("estimated_minutes", "Minutos"),
    ("source_refs", "Trazabilidad"),
    ("origin", "Origen"),
)

_TRACE_COLUMNS = (
    ("requirement_refs", "Requisitos"),
    ("story_ref", "Historia"),
    ("criterion_ref", "Criterio"),
    ("story_priority", "MoSCoW"),
    ("status", "Estado"),
    ("test_case_ids", "Casos"),
    ("question_ref", "Pregunta"),
)


def _render(value: Any) -> str:
    """Aplana un valor a texto de celda."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, list):
        return ", ".join(_render(v) for v in value)
    return str(value)


def _steps(caso: dict[str, Any]) -> str:
    """Pasos numerados en una celda, uno por línea."""
    partes = []
    for paso in caso.get("steps") or []:
        texto = f"{paso.get('number')}. {paso.get('action', '')}"
        if paso.get("expected"):
            texto += f" → {paso['expected']}"
        partes.append(texto)
    return "\n".join(partes)


def _test_data(caso: dict[str, Any]) -> str:
    """Datos de prueba como ``campo = valor (naturaleza)``."""
    partes = []
    for dato in caso.get("test_data") or []:
        nombre = dato.get("name", "")
        valor = dato.get("value", "")
        kind = dato.get("kind")
        partes.append(f"{nombre} = {valor}" + (f" ({kind})" if kind else ""))
    return "\n".join(partes)


def _boundary(caso: dict[str, Any]) -> str:
    """Descripción corta del límite, si el caso es de borde."""
    limite = caso.get("boundary") or {}
    if not limite:
        return ""
    partes = [limite.get("kind") or ""]
    if limite.get("operator") or limite.get("value"):
        partes.append(f"{limite.get('operator') or ''} {limite.get('value') or ''}")
    if limite.get("rule_ref"):
        partes.append(f"({limite['rule_ref']})")
    elif limite.get("api_field_ref"):
        partes.append(f"({limite['api_field_ref']})")
    return " ".join(p.strip() for p in partes if p and p.strip())


def case_rows(artifact: dict[str, Any]) -> list[dict[str, str]]:
    """Filas estructuradas de los casos (misma forma que las del CSV)."""
    filas = []
    for caso in artifact.get("test_cases") or []:
        limite = caso.get("boundary") or {}
        auth = caso.get("auth_context") or {}
        filas.append(
            {
                "id": _render(caso.get("id")),
                "title": _render(caso.get("title")),
                "type": _render(caso.get("type")),
                "priority": _render(caso.get("priority")),
                "story_ref": _render(caso.get("story_ref")),
                "criterion_ref": _render(caso.get("criterion_ref")),
                "epic_ref": _render(caso.get("epic_ref")),
                "preconditions": "\n".join(caso.get("preconditions") or []),
                "steps": _steps(caso),
                "test_data": _test_data(caso),
                "expected_result": _render(caso.get("expected_result")),
                "boundary": _boundary(caso),
                # La cita verbatim viaja al CSV a propósito: es lo que permite a
                # quien ejecuta el caso comprobar que el límite existe de verdad,
                # sin volver al EF.
                "evidence": _render(limite.get("evidence")),
                "auth_rule": _render(auth.get("auth_rule_ref")),
                "automation_hint": _render(caso.get("automation_hint")),
                "estimated_minutes": _render(caso.get("estimated_minutes")),
                "source_refs": _render(caso.get("source_refs")),
                "origin": _render(caso.get("origin")),
            }
        )
    return filas


def trace_rows(artifact: dict[str, Any]) -> list[dict[str, str]]:
    """Filas estructuradas de la matriz de trazabilidad."""
    matriz = artifact.get("trace_matrix") or {}
    return [
        {
            "requirement_refs": _render(fila.get("requirement_refs")),
            "story_ref": _render(fila.get("story_ref")),
            "criterion_ref": _render(fila.get("criterion_ref")),
            "story_priority": _render(fila.get("story_priority")),
            "status": _render(fila.get("status")),
            "test_case_ids": _render(fila.get("test_case_ids")),
            "question_ref": _render(fila.get("question_ref")),
        }
        for fila in matriz.get("rows") or []
    ]


def _to_csv(filas: list[dict[str, str]], columnas: tuple) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=DELIMITER, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([cabecera for _clave, cabecera in columnas])
    for fila in filas:
        writer.writerow([fila.get(clave, "") for clave, _cabecera in columnas])
    return BOM + buffer.getvalue()


def cases_csv(artifact: dict[str, Any]) -> str:
    """CSV de los casos de prueba, listo para abrir en Excel."""
    return _to_csv(case_rows(artifact), _CASE_COLUMNS)


def trace_csv(artifact: dict[str, Any]) -> str:
    """CSV de la matriz de trazabilidad, lista para abrir en Excel."""
    return _to_csv(trace_rows(artifact), _TRACE_COLUMNS)
