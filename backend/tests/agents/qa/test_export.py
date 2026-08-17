"""Tests del export CSV del plan de pruebas (QA7).

El export no es "volcar el JSON en columnas": es el formato en el que un QA lead
recibe el plan y lo trabaja en Excel. Por eso lo que se fija aquí es sobre todo lo
que rompe en la práctica y nadie mira hasta que llega roto:

- el **BOM** (sin él Excel lee Latin-1 y "guía" sale corrupto);
- el delimitador ``;`` (con coma, Excel en configuración española abre todo en una
  sola columna);
- y el **round-trip**: los pasos llevan saltos de línea y los textos llevan comas y
  puntos y coma, así que un CSV mal citado desplaza columnas y el archivo miente
  sin dar ningún error.

También se fija que la **cita verbatim** del límite viaje al CSV: es lo que permite
comprobar que un caso de borde prueba una frontera real y no una inventada.
"""

import csv
import io

from ai.agents.qa.export import (
    BOM,
    DELIMITER,
    case_rows,
    cases_csv,
    trace_csv,
    trace_rows,
)
from ai.agents.qa.schemas.examples import example_artifact


def _artifact() -> dict:
    return example_artifact().model_dump(mode="json")


def _parse(texto: str) -> list[list[str]]:
    """Lee el CSV como lo leería Excel: sin BOM y con ``;``."""
    assert texto.startswith(BOM)
    return list(csv.reader(io.StringIO(texto[len(BOM) :]), delimiter=DELIMITER))


# --- El formato que Excel abre de un doble clic ---------------------------------


def test_el_csv_de_casos_empieza_con_bom():
    """Sin BOM, los acentos salen rotos en la primera columna que alguien mire."""
    assert cases_csv(_artifact()).startswith("﻿")


def test_el_csv_de_la_matriz_empieza_con_bom():
    assert trace_csv(_artifact()).startswith("﻿")


def test_el_delimitador_es_punto_y_coma():
    filas = _parse(cases_csv(_artifact()))
    # Con el delimitador equivocado, la cabecera sería UNA sola celda.
    assert len(filas[0]) > 1
    assert filas[0][0] == "ID"
    assert "Título" in filas[0]


# --- Casos ----------------------------------------------------------------------


def test_hay_una_fila_por_caso_mas_la_cabecera():
    art = _artifact()
    filas = _parse(cases_csv(art))
    assert len(filas) == len(art["test_cases"]) + 1


def test_cada_fila_tiene_tantas_celdas_como_la_cabecera():
    """El candado del round-trip: una celda mal citada desplazaría columnas."""
    filas = _parse(cases_csv(_artifact()))
    ancho = len(filas[0])
    assert {len(f) for f in filas[1:]} == {ancho}


def test_los_pasos_van_numerados_en_una_sola_celda():
    art = _artifact()
    filas = _parse(cases_csv(art))
    cabecera = filas[0]
    columna = cabecera.index("Pasos")
    pasos = filas[1][columna]
    esperados = art["test_cases"][0]["steps"]
    assert pasos.startswith(f"{esperados[0]['number']}. ")
    assert pasos.count("\n") == len(esperados) - 1


def test_la_cita_verbatim_del_limite_viaja_al_csv():
    """Quien ejecuta un caso de borde debe poder verificar el límite sin ir al EF."""
    art = _artifact()
    caso = next(
        c for c in art["test_cases"] if (c.get("boundary") or {}).get("evidence")
    )
    filas = _parse(cases_csv(art))
    columna = filas[0].index("Evidencia (verbatim)")
    fila = next(f for f in filas[1:] if f[0] == caso["id"])
    assert fila[columna] == caso["boundary"]["evidence"]


def test_el_limite_estructural_del_api_cita_su_campo():
    """El borde anclado en el contrato no tiene regla del EF: cita el campo."""
    art = _artifact()
    caso = next(
        c for c in art["test_cases"] if (c.get("boundary") or {}).get("api_field_ref")
    )
    filas = _parse(cases_csv(art))
    columna = filas[0].index("Límite probado")
    fila = next(f for f in filas[1:] if f[0] == caso["id"])
    assert caso["boundary"]["api_field_ref"] in fila[columna]


def test_el_caso_de_autorizacion_lleva_su_regla():
    art = _artifact()
    caso = next(c for c in art["test_cases"] if c["type"] == "authorization")
    filas = _parse(cases_csv(art))
    columna = filas[0].index("Regla de autorización")
    fila = next(f for f in filas[1:] if f[0] == caso["id"])
    assert fila[columna] == caso["auth_context"]["auth_rule_ref"]


def test_las_filas_estructuradas_y_el_csv_dicen_lo_mismo():
    """La UI consume ``rows`` y Excel el ``content``: no pueden divergir."""
    art = _artifact()
    filas_csv = _parse(cases_csv(art))[1:]
    filas = case_rows(art)
    assert len(filas) == len(filas_csv)
    assert [f["id"] for f in filas] == [f[0] for f in filas_csv]


# --- Matriz de trazabilidad -----------------------------------------------------


def test_la_matriz_exporta_una_fila_por_criterio():
    art = _artifact()
    filas = _parse(trace_csv(art))
    assert len(filas) == len(art["trace_matrix"]["rows"]) + 1
    assert filas[0] == [
        "Requisitos",
        "Historia",
        "Criterio",
        "MoSCoW",
        "Estado",
        "Casos",
        "Pregunta",
    ]


def test_la_matriz_enumera_los_casos_de_cada_criterio():
    art = _artifact()
    filas = _parse(trace_csv(art))
    fila = filas[1]
    esperada = art["trace_matrix"]["rows"][0]
    assert fila[2] == esperada["criterion_ref"]
    for tc in esperada["test_case_ids"]:
        assert tc in fila[5]


def test_un_criterio_sin_casos_deja_la_celda_vacia_no_la_omite():
    """El hueco tiene que verse: una fila ausente se leería como cobertura."""
    art = _artifact()
    art["trace_matrix"]["rows"].append(
        {
            "requirement_refs": ["REQ-F-009"],
            "story_ref": "US-009",
            "criterion_ref": "AC-009",
            "story_priority": "could",
            "test_case_ids": [],
            "status": "uncovered",
            "question_ref": None,
        }
    )
    filas = _parse(trace_csv(art))
    hueco = next(f for f in filas[1:] if f[2] == "AC-009")
    assert hueco[4] == "uncovered"
    assert hueco[5] == ""


# --- Robustez del formato -------------------------------------------------------


def test_un_texto_con_delimitador_y_salto_no_desplaza_columnas():
    """El fallo silencioso clásico: el CSV se abre, pero las columnas mienten."""
    art = _artifact()
    art["test_cases"][0]["title"] = 'Registrar; con "comillas"\ny salto de línea'
    filas = _parse(cases_csv(art))
    ancho = len(filas[0])
    assert {len(f) for f in filas[1:]} == {ancho}
    assert filas[1][1] == 'Registrar; con "comillas"\ny salto de línea'


def test_un_artefacto_sin_casos_exporta_solo_la_cabecera():
    """Vacío no es error: es un plan sin casos, y el archivo lo dice."""
    art = _artifact()
    art["test_cases"] = []
    filas = _parse(cases_csv(art))
    assert len(filas) == 1
    assert case_rows(art) == []


def test_la_matriz_de_un_artefacto_sin_matriz_no_revienta():
    filas = trace_rows({})
    assert filas == []
    assert trace_csv({}).startswith(BOM)
