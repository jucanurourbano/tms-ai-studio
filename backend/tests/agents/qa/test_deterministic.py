"""Tests de DATASET, TRACE_MATRIX y EXEC_PLAN (QA4). Todo determinista, sin LLM.

Que estos tres nodos no llamen al modelo es lo que hace **auditable** el plan: la
cobertura y el esfuerzo se pueden recomputar leyendo el artefacto y dan el mismo
número. Si los produjera el LLM, un plan con huecos podría presentarse como completo
y nadie tendría con qué contrastarlo.

El test que más importa aquí es el que distingue ``uncovered`` de ``not_testable``:
un hueco y una decisión declarada se parecen en la cifra de cobertura y son cosas
opuestas para quien tiene que actuar.
"""

import pytest

from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.qa.criterion_map import build_criterion_map
from ai.agents.qa.dataset import build_datasets
from ai.agents.qa.exec_plan import build_execution_plan
from ai.agents.qa.load_sources import extract_sources
from ai.agents.qa.schemas import Dataset, ExecutionPlan, TraceMatrix
from ai.agents.qa.trace_matrix import (
    blocking_coverage_ratio,
    build_trace_matrix,
    uncovered_requirements_risks,
)
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example


def _sources(scrum=None):
    return extract_sources(
        scrum or scrum_example().model_dump(mode="json"),
        ef_example().model_dump(mode="json"),
    )


def _caso(
    cid, criterio, story, *, tipo="functional", minutos=10, epica="EPIC-001", datos=None
):
    return {
        "id": cid,
        "title": f"Caso {cid}",
        "story_ref": story,
        "criterion_ref": criterio,
        "epic_ref": epica,
        "type": tipo,
        "steps": [{"number": 1, "action": "hacer algo"}],
        "expected_result": "algo pasa",
        "priority": "critica",
        "estimated_minutes": minutos,
        "test_data": datos or [],
        "source_refs": [],
    }


# --- TRACE_MATRIX -------------------------------------------------------------


def test_cada_criterio_existente_es_una_fila_tenga_casos_o_no():
    mapa = build_criterion_map(_sources())
    matriz = build_trace_matrix(mapa, [_caso("TC-001", "AC-001", "US-001")], [])
    assert [f["criterion_ref"] for f in matriz["rows"]] == ["AC-001", "AC-002"]
    assert matriz["rows"][0]["status"] == "covered"
    assert matriz["rows"][1]["status"] == "uncovered"


def test_un_hueco_y_una_decision_declarada_no_se_confunden():
    """La distinción que permite saber si falta trabajo o falta una respuesta."""
    mapa = build_criterion_map(_sources())
    matriz = build_trace_matrix(
        mapa,
        [_caso("TC-001", "AC-001", "US-001")],
        [{"criterion_ref": "AC-002", "reason": "no observable", "blocking": True}],
        {"AC-002": "QQ-001"},
    )
    fila = matriz["rows"][1]
    assert fila["status"] == "not_testable"
    assert fila["question_ref"] == "QQ-001"
    # No cuenta como hueco: el hueco es lo que nadie explicó.
    assert matriz["coverage"]["uncovered_criterion_refs"] == []
    assert matriz["coverage"]["not_testable_criterion_refs"] == ["AC-002"]


def test_la_cobertura_se_calcula_sobre_los_criterios_reales():
    mapa = build_criterion_map(_sources())
    matriz = build_trace_matrix(mapa, [_caso("TC-001", "AC-001", "US-001")], [])
    cov = matriz["coverage"]
    assert cov["criteria_total"] == 2
    assert cov["criteria_covered"] == 1
    assert cov["criteria_ratio"] == 0.5
    assert matriz["orphan_criterion_refs"] == ["AC-002"]


def test_la_cadena_requisito_historia_criterio_caso_queda_reconstruida():
    mapa = build_criterion_map(_sources())
    matriz = build_trace_matrix(mapa, [_caso("TC-001", "AC-001", "US-001")], [])
    fila = matriz["rows"][0]
    assert fila["requirement_refs"] == ["REQ-B-001"]
    assert fila["story_ref"] == "US-001"
    assert fila["test_case_ids"] == ["TC-001"]


def test_un_requisito_sin_casos_es_hallazgo_no_advertencia():
    """El negocio lo pidió y nadie lo probará: eso es un riesgo, no una nota."""
    mapa = build_criterion_map(_sources())
    matriz = build_trace_matrix(mapa, [_caso("TC-001", "AC-001", "US-001")], [])
    assert matriz["coverage"]["uncovered_requirement_refs"] == ["REQ-F-001"]
    riesgos = uncovered_requirements_risks(matriz["coverage"])
    assert len(riesgos) == 1
    assert riesgos[0]["severity"] == "alta"
    assert "REQ-F-001" in riesgos[0]["description"]


def test_la_cobertura_bloqueante_solo_mira_must_y_should():
    scrum = scrum_example().model_dump(mode="json")
    scrum["stories"][1]["priority"] = "wont"
    mapa = build_criterion_map(_sources(scrum))
    matriz = build_trace_matrix(mapa, [_caso("TC-001", "AC-001", "US-001")], [])
    cov = matriz["coverage"]
    # AC-002 pertenece a una historia `wont`: no entra en el semáforo.
    assert cov["blocking_criteria_total"] == 1
    assert cov["blocking_criteria_covered"] == 1
    assert blocking_coverage_ratio(cov) == 1.0
    # Y sigue apareciendo como hueco: advertencia, no bloqueo.
    assert cov["uncovered_criterion_refs"] == ["AC-002"]


def test_un_plan_sin_criterios_bloqueantes_no_esta_en_rojo_por_eso():
    """Devolver 0.0 dejaría en rojo un plan que no tiene nada que cubrir."""
    assert blocking_coverage_ratio({"blocking_criteria_total": 0}) == 1.0


def test_la_matriz_valida_contra_el_contrato():
    mapa = build_criterion_map(_sources())
    matriz = build_trace_matrix(
        mapa,
        [_caso("TC-001", "AC-001", "US-001")],
        [{"criterion_ref": "AC-002", "reason": "x"}],
        {"AC-002": "QQ-001"},
    )
    validada = TraceMatrix.model_validate(matriz)
    assert validada.coverage.criteria_total == 2


# --- DATASET ------------------------------------------------------------------


def test_los_datasets_se_agrupan_por_entidad():
    casos = [
        _caso(
            "TC-001",
            "AC-001",
            "US-001",
            datos=[
                {
                    "name": "numero_guia",
                    "value": "000123456",
                    "kind": "valid",
                    "field_ref": "FLD-001",
                }
            ],
        )
    ]
    salida = build_datasets(casos, _sources())
    assert len(salida["datasets"]) == 1
    ds = salida["datasets"][0]
    assert ds["entity_ref"] == "ENT-001"  # FLD-001 pertenece a Siniestro
    assert ds["name"] == "Siniestro"
    assert ds["rows"][0]["values"] == {"numero_guia": "000123456"}


def test_las_tres_naturalezas_de_dato_conviven_en_el_dataset():
    casos = [
        _caso(
            "TC-001",
            "AC-001",
            "US-001",
            datos=[
                {
                    "name": "numero_guia",
                    "value": "000123456",
                    "kind": "valid",
                    "field_ref": "FLD-001",
                }
            ],
        ),
        _caso(
            "TC-002",
            "AC-001",
            "US-001",
            tipo="negative",
            datos=[
                {
                    "name": "numero_guia",
                    "value": "",
                    "kind": "invalid",
                    "field_ref": "FLD-001",
                }
            ],
        ),
        _caso(
            "TC-003",
            "AC-001",
            "US-001",
            tipo="boundary",
            datos=[
                {
                    "name": "fecha_siniestro",
                    "value": "2026-08-15",
                    "kind": "boundary",
                    "field_ref": "FLD-002",
                }
            ],
        ),
    ]
    salida = build_datasets(casos, _sources())
    kinds = {r["kind"] for r in salida["datasets"][0]["rows"]}
    assert kinds == {"valid", "invalid", "boundary"}


def test_los_valores_del_dataset_son_los_MISMOS_que_usan_los_casos():
    """El motivo de cosecharlos: dos juegos de valores divergirían."""
    casos = [
        _caso(
            "TC-001",
            "AC-001",
            "US-001",
            datos=[
                {
                    "name": "numero_guia",
                    "value": "000123456",
                    "kind": "valid",
                    "field_ref": "FLD-001",
                }
            ],
        )
    ]
    salida = build_datasets(casos, _sources())
    fila = salida["datasets"][0]["rows"][0]
    assert fila["values"]["numero_guia"] == casos[0]["test_data"][0]["value"]


def test_un_campo_sin_field_ref_se_resuelve_por_nombre_exacto():
    """Los bordes estructurales omiten el field_ref; el nombre sí es exacto."""
    casos = [
        _caso(
            "TC-001",
            "AC-001",
            "US-001",
            tipo="boundary",
            datos=[{"name": "fecha_siniestro", "value": "null", "kind": "boundary"}],
        )
    ]
    salida = build_datasets(casos, _sources())
    assert salida["datasets"][0]["entity_ref"] == "ENT-001"


def test_un_dato_sin_entidad_se_declara_no_se_tira_ni_se_aloja_a_la_fuerza():
    casos = [
        _caso(
            "TC-001",
            "AC-001",
            "US-001",
            datos=[{"name": "campo_desconocido", "value": "x", "kind": "valid"}],
        )
    ]
    salida = build_datasets(casos, _sources())
    assert salida["datasets"] == []
    assert any("campo_desconocido" in o["description"] for o in salida["observations"])


def test_la_fila_de_frontera_conserva_su_anclaje():
    anchor = {
        "rule_ref": "VAL-001",
        "kind": "max",
        "anchor_source": "ef_text",
        "evidence": "La fecha del siniestro no puede ser futura.",
    }
    caso = _caso(
        "TC-003",
        "AC-001",
        "US-001",
        tipo="boundary",
        datos=[
            {
                "name": "fecha_siniestro",
                "value": "2026-08-15",
                "kind": "boundary",
                "field_ref": "FLD-002",
            }
        ],
    )
    caso["boundary"] = anchor
    salida = build_datasets([caso], _sources())
    fila = salida["datasets"][0]["rows"][0]
    assert fila["anchor"]["evidence"] == anchor["evidence"]
    assert fila["expectation"] == "Se rechaza por VAL-001."


def test_los_datasets_validan_contra_el_contrato():
    casos = [
        _caso(
            "TC-001",
            "AC-001",
            "US-001",
            datos=[
                {
                    "name": "numero_guia",
                    "value": "000123456",
                    "kind": "valid",
                    "field_ref": "FLD-001",
                }
            ],
        )
    ]
    salida = build_datasets(casos, _sources())
    assert [Dataset.model_validate(d) for d in salida["datasets"]]


# --- EXEC_PLAN ----------------------------------------------------------------


def test_una_suite_por_epica_con_su_esfuerzo():
    casos = [
        _caso("TC-001", "AC-001", "US-001", minutos=15),
        _caso("TC-002", "AC-002", "US-002", minutos=12),
    ]
    plan = build_execution_plan(casos, _sources())
    assert len(plan["suites"]) == 1  # el fixture tiene una sola épica
    suite = plan["suites"][0]
    assert suite["epic_ref"] == "EPIC-001"
    assert suite["test_case_ids"] == ["TC-001", "TC-002"]
    assert suite["estimated_minutes"] == 27
    assert plan["totals"]["manual_minutes"] == 27


def test_el_orden_respeta_las_dependencias_entre_historias():
    """US-002 depende de US-001: su suite va después."""
    scrum = scrum_example().model_dump(mode="json")
    scrum["epics"] = [
        {"id": "EPIC-001", "title": "Registro", "story_ids": ["US-001"]},
        {"id": "EPIC-002", "title": "Seguimiento", "story_ids": ["US-002"]},
    ]
    scrum["stories"][1]["epic_ref"] = "EPIC-002"
    casos = [
        _caso("TC-001", "AC-001", "US-001", epica="EPIC-001"),
        _caso("TC-002", "AC-002", "US-002", epica="EPIC-002"),
    ]
    plan = build_execution_plan(casos, _sources(scrum))
    ids = {s["epic_ref"]: s["id"] for s in plan["suites"]}
    assert plan["order"].index(ids["EPIC-001"]) < plan["order"].index(ids["EPIC-002"])
    segunda = [s for s in plan["suites"] if s["epic_ref"] == "EPIC-002"][0]
    assert segunda["depends_on_suite_ids"] == [ids["EPIC-001"]]


def test_los_ciclos_se_reportan_y_el_plan_sigue_existiendo():
    """Tumbar el job dejaría al equipo sin plan por un defecto del Scrum."""
    scrum = scrum_example().model_dump(mode="json")
    scrum["stories"][0]["dependencies"] = ["US-002"]  # ciclo con US-002 -> US-001
    plan = build_execution_plan([_caso("TC-001", "AC-001", "US-001")], _sources(scrum))
    assert plan["dependency_cycles"]
    assert plan["suites"]
    assert plan["order"]


def test_un_caso_sin_epica_no_se_cuelga_de_la_primera():
    casos = [
        _caso("TC-001", "AC-001", "US-001"),
        _caso("TC-002", "AC-002", "US-002", epica=None),
    ]
    plan = build_execution_plan(casos, _sources())
    sin_epica = [s for s in plan["suites"] if s["epic_ref"] is None]
    assert len(sin_epica) == 1
    assert sin_epica[0]["test_case_ids"] == ["TC-002"]


def test_los_totales_desglosan_por_tipo_y_prioridad():
    casos = [
        _caso("TC-001", "AC-001", "US-001"),
        _caso("TC-002", "AC-001", "US-001", tipo="negative"),
        _caso("TC-003", "AC-001", "US-001", tipo="boundary"),
    ]
    plan = build_execution_plan(casos, _sources())
    assert plan["totals"]["by_type"] == {"functional": 1, "negative": 1, "boundary": 1}
    assert plan["totals"]["by_priority"] == {"critica": 3}
    assert plan["totals"]["cases_total"] == 3


def test_las_sesiones_se_calculan_solo_si_hay_capacidad_declarada():
    casos = [_caso("TC-001", "AC-001", "US-001", minutos=100)]
    sin = build_execution_plan(casos, _sources())
    assert sin["totals"]["estimated_sessions"] is None
    con = build_execution_plan(
        casos, _sources(), target={"manual_capacity_minutes": 60}
    )
    # 100 minutos en sesiones de 60: dos. Media sesión pendiente sigue siendo una.
    assert con["totals"]["estimated_sessions"] == 2


def test_el_plan_valida_contra_el_contrato():
    plan = build_execution_plan([_caso("TC-001", "AC-001", "US-001")], _sources())
    validado = ExecutionPlan.model_validate(plan)
    assert validado.totals.cases_total == 1
