"""Tests de la consolidación, CRITIQUE y QUESTION_GEN (QA5).

Lo que estos tests protegen es la **honestidad del plan**, que se juega en tres
sitios: que un recorte no pase por completo, que un duplicado no cuente como
cobertura, y que las preguntas lleguen agrupadas y con el bloqueo puesto donde
importa.

El bloqueo no es simétrico a propósito. Bloquea lo que dejaría al plan certificando
algo que no comprobó —una autorización que nadie precisó, un criterio `must`
imposible de verificar—. No bloquea lo que solo resta cobertura y se ve en la matriz.
"""

import pytest

from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.qa.consolidate import apply_case_cap, find_duplicates
from ai.agents.qa.criterion_map import build_criterion_map
from ai.agents.qa.critique import deterministic_findings, llm_risks
from ai.agents.qa.load_sources import extract_sources
from ai.agents.qa.question_gen import generate_questions
from ai.agents.qa.schemas import QaQuestion, Risk
from ai.agents.qa.trace_matrix import build_trace_matrix
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from tests.mocks import QaMapLLM


def _sources():
    return extract_sources(
        scrum_example().model_dump(mode="json"), ef_example().model_dump(mode="json")
    )


def _caso(cid, criterio="AC-001", *, tipo="functional", pasos=None, datos=None):
    return {
        "id": cid,
        "title": f"Caso {cid}",
        "story_ref": "US-001",
        "criterion_ref": criterio,
        "epic_ref": "EPIC-001",
        "type": tipo,
        "steps": pasos or [{"number": 1, "action": "hacer algo"}],
        "test_data": datos or [],
        "expected_result": "algo pasa",
        "priority": "critica",
        "estimated_minutes": 10,
        "source_refs": [],
    }


# --- Techo de casos -----------------------------------------------------------


def test_por_debajo_del_techo_no_se_toca_nada():
    casos = [_caso(f"TC-00{i}") for i in range(1, 4)]
    salida = apply_case_cap(casos, {"max_cases_per_criterion": 6})
    assert len(salida["test_cases"]) == 3
    assert salida["pruned"] == 0
    assert salida["observations"] == []


def test_el_recorte_nunca_es_silencioso():
    """Un tope callado se leería como cobertura completa."""
    casos = [_caso(f"TC-{i:03d}") for i in range(1, 6)]
    salida = apply_case_cap(casos, {"max_cases_per_criterion": 2})
    assert len(salida["test_cases"]) == 2
    assert salida["pruned"] == 3
    obs = salida["observations"][0]
    assert "techo del plan es 2" in obs["description"]
    # Y dice EXACTAMENTE qué se cayó, no solo cuántos.
    for cid in ("TC-003", "TC-004", "TC-005"):
        assert cid in obs["description"]


def test_al_podar_se_conserva_diversidad_de_tipos():
    """Un funcional, un negativo y un borde informan más que tres funcionales."""
    casos = [
        _caso("TC-001", tipo="functional"),
        _caso("TC-002", tipo="functional"),
        _caso("TC-003", tipo="functional"),
        _caso("TC-004", tipo="negative"),
        _caso("TC-005", tipo="boundary"),
    ]
    salida = apply_case_cap(casos, {"max_cases_per_criterion": 3})
    tipos = {c["type"] for c in salida["test_cases"]}
    assert tipos == {"functional", "negative", "boundary"}


def test_el_techo_es_por_criterio_no_por_plan():
    casos = [_caso("TC-001"), _caso("TC-002"), _caso("TC-003", "AC-002")]
    salida = apply_case_cap(casos, {"max_cases_per_criterion": 2})
    assert len(salida["test_cases"]) == 3  # 2 de AC-001 + 1 de AC-002


# --- Duplicados ---------------------------------------------------------------


def test_dos_casos_con_distinto_titulo_y_mismos_pasos_son_duplicados():
    """Comparar por título dejaría pasar justo los duplicados que cuestan tiempo."""
    a = _caso("TC-001")
    b = _caso("TC-002")
    b["title"] = "Otro título completamente distinto"
    grupos = find_duplicates([a, b])
    assert grupos == [["TC-001", "TC-002"]]


def test_casos_con_datos_distintos_no_son_duplicados():
    a = _caso("TC-001", datos=[{"name": "guia", "value": "1"}])
    b = _caso("TC-002", datos=[{"name": "guia", "value": "2"}])
    assert find_duplicates([a, b]) == []


def test_casos_de_criterios_distintos_no_son_duplicados():
    assert find_duplicates([_caso("TC-001", "AC-001"), _caso("TC-002", "AC-002")]) == []


# --- CRITIQUE determinista ----------------------------------------------------


def _matriz(casos, no_verificables=None):
    return build_trace_matrix(
        build_criterion_map(_sources()), casos, no_verificables or []
    )


def test_critique_reporta_los_duplicados():
    a, b = _caso("TC-001"), _caso("TC-002")
    hallazgos = deterministic_findings([a, b], _matriz([a, b]), {}, {}, {})
    assert any(
        "mismo caso escrito" in o["description"] for o in hallazgos["observations"]
    )


def test_critique_marca_con_la_maxima_severidad_la_cobertura_incompleta():
    """`RiskSeverity` del ISDF no tiene "crítica": lo más grave que existe es alta."""
    casos = [_caso("TC-001")]
    hallazgos = deterministic_findings(casos, _matriz(casos), {}, {}, {})
    riesgo = [r for r in hallazgos["risks"] if r["id"] == "RSK-COV-001"][0]
    assert riesgo["severity"] == "alta"
    assert "50%" in riesgo["description"]


def test_critique_no_se_queja_si_la_cobertura_bloqueante_esta_completa():
    casos = [_caso("TC-001", "AC-001"), _caso("TC-002", "AC-002")]
    hallazgos = deterministic_findings(casos, _matriz(casos), {}, {}, {})
    assert not [r for r in hallazgos["risks"] if r["id"] == "RSK-COV-001"]


def test_critique_reporta_los_ciclos_del_plan():
    casos = [_caso("TC-001")]
    plan = {"dependency_cycles": [["US-001", "US-002", "US-001"]]}
    hallazgos = deterministic_findings(casos, _matriz(casos), plan, {}, {})
    assert any("ciclo de dependencias" in r["description"] for r in hallazgos["risks"])


def test_critique_reporta_las_refs_que_el_ef_no_reconoce():
    mapa = {"entries": [{"criterion_ref": "AC-001", "unresolved_refs": ["BR-404"]}]}
    hallazgos = deterministic_findings([_caso("TC-001")], _matriz([]), {}, mapa, {})
    assert any("BR-404" in o["description"] for o in hallazgos["observations"])


def test_critique_reporta_la_cuarentena():
    metrics = {"skipped": [{"ref": "AC-002", "stage": "TEST_DESIGN", "reason": "x"}]}
    hallazgos = deterministic_findings([_caso("TC-001")], _matriz([]), {}, {}, metrics)
    assert any("AC-002" in o["description"] for o in hallazgos["observations"])


def test_un_plan_sin_casos_es_riesgo_critico():
    hallazgos = deterministic_findings([], _matriz([]), {}, {}, {})
    assert any(r["id"] == "RSK-EMPTY-001" for r in hallazgos["risks"])


def test_los_riesgos_validan_contra_el_contrato():
    casos = [_caso("TC-001")]
    hallazgos = deterministic_findings(
        casos, _matriz(casos), {"dependency_cycles": [["US-001", "US-001"]]}, {}, {}
    )
    assert [Risk.model_validate(r) for r in hallazgos["risks"]]


# --- CRITIQUE con LLM ---------------------------------------------------------


async def test_el_pase_llm_aporta_riesgos_y_normaliza_la_severidad():
    casos = [_caso("TC-001")]
    plan = {
        "suites": [
            {
                "id": "SUITE-001",
                "epic_ref": "EPIC-001",
                "test_case_ids": ["TC-001"],
                "estimated_minutes": 10,
            }
        ],
        "totals": {},
    }
    riesgos, tokens = await llm_risks(QaMapLLM(), casos, _matriz(casos), plan)
    assert len(riesgos) == 2
    assert riesgos[0]["source_ref"] == "EPIC-001"
    # "apocaliptica" no está en el enum cerrado: cae a media en vez de romper.
    assert riesgos[1]["severity"] == "media"
    assert tokens["total"] > 0
    assert [Risk.model_validate(r) for r in riesgos]


async def test_si_el_modelo_falla_el_nodo_sigue_sin_riesgos():
    """Se pierde matiz, no correctitud: las comprobaciones mecánicas ya corrieron."""

    class Roto:
        async def complete_json(self, *, system: str, user: str) -> str:
            return "no soy json"

    riesgos, tokens = await llm_risks(Roto(), [_caso("TC-001")], _matriz([]), {})
    assert riesgos == []
    assert tokens["total"] > 0  # los tokens gastados se contabilizan igual


# --- QUESTION_GEN -------------------------------------------------------------


def _preguntas(**kwargs):
    base = {
        "not_testable": [],
        "unanchored": [],
        "ambiguous_auth_refs": [],
        "criterion_map": build_criterion_map(_sources()),
        "trace_matrix": _matriz([_caso("TC-001"), _caso("TC-002", "AC-002")]),
    }
    return generate_questions(**(base | kwargs))


def test_sin_vacios_no_hay_preguntas():
    assert _preguntas()["questions"] == []


def test_la_autorizacion_ambigua_siempre_bloquea():
    """El peor caso del agente: un permiso que nadie precisó."""
    salida = _preguntas(ambiguous_auth_refs=["AUTH-002"])
    pregunta = salida["questions"][0]
    assert pregunta["blocking"] is True
    assert pregunta["linked_to_ref"] == "AUTH-002"
    assert "adivinando" in pregunta["reason"]


def test_treinta_criterios_no_verificables_son_UNA_pregunta():
    """Treinta preguntas parecidas se contestan en bloque y sin leer."""
    no_verificables = [
        {"criterion_ref": f"AC-{i:03d}", "reason": "no observable", "blocking": False}
        for i in range(1, 31)
    ]
    salida = _preguntas(not_testable=no_verificables)
    assert len(salida["questions"]) == 1
    texto = salida["questions"][0]["question"]
    # Enumera los primeros y dice cuántos faltan: truncar en silencio haría creer
    # que el problema es más pequeño.
    assert "y 18 más" in texto


def test_un_criterio_no_verificable_de_una_must_bloquea():
    salida = _preguntas(
        not_testable=[{"criterion_ref": "AC-001", "reason": "x", "blocking": True}]
    )
    assert salida["questions"][0]["blocking"] is True


def test_un_criterio_no_verificable_de_una_wont_no_bloquea():
    salida = _preguntas(
        not_testable=[{"criterion_ref": "AC-009", "reason": "x", "blocking": False}]
    )
    assert salida["questions"][0]["blocking"] is False


def test_el_enlace_criterio_pregunta_queda_disponible_para_la_matriz():
    """El contrato exige que una fila `not_testable` cite su pregunta."""
    salida = _preguntas(
        not_testable=[{"criterion_ref": "AC-002", "reason": "x", "blocking": True}]
    )
    assert salida["questions_by_criterion"]["AC-002"] == salida["questions"][0]["id"]


def test_un_limite_sin_anclar_pregunta_pero_no_bloquea():
    """El caso no existe y eso se ve en la matriz: no hace falta parar el plan."""
    salida = _preguntas(
        unanchored=[{"criterion_ref": "AC-001", "rule_ref": "VAL-001", "reason": "x"}]
    )
    pregunta = salida["questions"][0]
    assert pregunta["blocking"] is False
    assert "VAL-001" in pregunta["question"]
    assert "inventado" in pregunta["reason"]


def test_una_historia_sin_criterios_bloquea():
    scrum = scrum_example().model_dump(mode="json")
    scrum["stories"][1]["acceptance_criteria"] = []
    mapa = build_criterion_map(
        extract_sources(scrum, ef_example().model_dump(mode="json"))
    )
    salida = generate_questions(
        not_testable=[],
        unanchored=[],
        ambiguous_auth_refs=[],
        criterion_map=mapa,
        trace_matrix=build_trace_matrix(mapa, [_caso("TC-001")], []),
    )
    sin_criterios = [q for q in salida["questions"] if "US-002" in q["question"]][0]
    assert sin_criterios["blocking"] is True


def test_un_hueco_sin_explicar_bloquea_si_es_de_una_must_o_should():
    salida = _preguntas(trace_matrix=_matriz([_caso("TC-001")]))
    hueco = [q for q in salida["questions"] if "sin ningún caso" in q["question"]][0]
    assert hueco["blocking"] is True
    assert "AC-002" in hueco["question"]


def test_las_preguntas_validan_contra_el_contrato():
    salida = _preguntas(
        ambiguous_auth_refs=["AUTH-002"],
        not_testable=[{"criterion_ref": "AC-002", "reason": "x", "blocking": True}],
        unanchored=[{"rule_ref": "VAL-001", "reason": "x"}],
    )
    preguntas = [QaQuestion.model_validate(q) for q in salida["questions"]]
    # Ambigua + no verificable + límite sin anclar. No hay cuarta: la matriz base
    # tiene los dos criterios cubiertos, así que no hay hueco que preguntar.
    assert len(preguntas) == 3
    assert all(q.audience.value == "tecnico" for q in preguntas)
    assert all(q.status.value == "pendiente" for q in preguntas)


def test_los_ids_de_pregunta_son_estables_y_ordenados():
    salida = _preguntas(
        ambiguous_auth_refs=["AUTH-002"],
        not_testable=[{"criterion_ref": "AC-002", "reason": "x", "blocking": True}],
    )
    assert [q["id"] for q in salida["questions"]][:2] == ["QQ-001", "QQ-002"]
