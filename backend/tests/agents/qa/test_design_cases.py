"""Tests de CRITERION_MAP, TEST_DESIGN, EDGE_CASES y AUTH_CASES (QA3).

Los tres cortafuegos del agente, cada uno con su test:

1. **CRITERION_MAP** cierra el universo de criterios antes de gastar un token, así
   que un caso no puede nacer de un criterio que no existe.
2. **EDGE_CASES** verifica la **cita verbatim** contra el texto real de la regla. El
   mock propone a propósito una cita parafraseada: debe descartarse. Sin este
   control, la cita sería una formalidad que el modelo rellena solo.
3. **AUTH_CASES** deriva de la matriz sin LLM, y ante una regla ambigua **no genera
   el caso**: lo devuelve como pregunta. Es el caso del enunciado ("un jefe no puede
   ver solicitudes de otro equipo") y el que solo se puede probar cuando existe la
   columna que separa los equipos.
"""

import pytest

from ai.agents.api.schemas.examples import example_artifact as api_example
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.qa.auth_cases import build_auth_cases, priority_with_floor
from ai.agents.qa.common import estimated_minutes, next_id, normalize_steps
from ai.agents.qa.criterion_map import build_criterion_map, criterion_text, entry_for
from ai.agents.qa.edge_cases import (
    api_field_boundaries,
    evidence_matches,
    run_edge_cases,
)
from ai.agents.qa.load_sources import extract_sources
from ai.agents.qa.schemas import QaArtifact, SourceRef, TestCase
from ai.agents.qa.test_design import known_refs, run_test_design
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from ai.orchestrator import build_qa_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from tests.mocks import QaMapLLM

HOY = "2026-08-14"


def _sources(con_api: bool = False):
    return extract_sources(
        scrum_example().model_dump(mode="json"),
        ef_example().model_dump(mode="json"),
        api_example().model_dump(mode="json") if con_api else None,
    )


def _mapa(con_api: bool = False):
    return build_criterion_map(_sources(con_api))


# --- CRITERION_MAP ------------------------------------------------------------


def test_el_mapa_enumera_los_pares_historia_criterio():
    mapa = _mapa()
    assert [(e["story_ref"], e["criterion_ref"]) for e in mapa["entries"]] == [
        ("US-001", "AC-001"),
        ("US-002", "AC-002"),
    ]
    assert mapa["criterion_refs"] == ["AC-001", "AC-002"]


def test_el_mapa_resuelve_las_reglas_citadas_a_su_texto():
    """Con el id solo, el modelo no sabría qué dice la regla que debe probar."""
    entrada = entry_for(_mapa(), "AC-001")
    assert entrada["rules"] == [
        {
            "id": "BR-001",
            "statement": "Un siniestro sin guía asociada no puede registrarse.",
        }
    ]


def test_el_mapa_hereda_la_prioridad_del_moscow():
    mapa = _mapa()
    por_ref = {e["criterion_ref"]: e for e in mapa["entries"]}
    assert por_ref["AC-001"]["case_priority"] == "critica"  # US-001 es must
    assert por_ref["AC-002"]["case_priority"] == "alta"  # US-002 es should


def test_los_criterios_bloqueantes_son_los_de_must_y_should():
    mapa = _mapa()
    assert mapa["blocking_criterion_refs"] == ["AC-001", "AC-002"]


def test_una_historia_could_no_bloquea():
    scrum = scrum_example().model_dump(mode="json")
    scrum["stories"][1]["priority"] = "could"
    mapa = build_criterion_map(
        extract_sources(scrum, ef_example().model_dump(mode="json"))
    )
    assert mapa["blocking_criterion_refs"] == ["AC-001"]


def test_una_historia_sin_criterios_se_declara_no_se_inventa():
    scrum = scrum_example().model_dump(mode="json")
    scrum["stories"][1]["acceptance_criteria"] = []
    mapa = build_criterion_map(
        extract_sources(scrum, ef_example().model_dump(mode="json"))
    )
    assert mapa["stories_without_criteria"] == ["US-002"]
    assert mapa["criterion_refs"] == ["AC-001"]


def test_un_criterio_de_texto_libre_no_se_pierde():
    """Sin Gherkin sigue siendo un criterio: perderlo sería perder cobertura."""
    assert criterion_text({"text": "El listado se ordena por fecha."}) == (
        "El listado se ordena por fecha."
    )
    assert criterion_text({"given": "un siniestro", "then": "se guarda"}) == (
        "Dado un siniestro; Entonces se guarda"
    )


def test_una_ref_citada_que_no_existe_viaja_para_ser_reportada():
    scrum = scrum_example().model_dump(mode="json")
    scrum["stories"][0]["acceptance_criteria"][0]["source_refs"] = ["BR-001", "BR-404"]
    mapa = build_criterion_map(
        extract_sources(scrum, ef_example().model_dump(mode="json"))
    )
    assert entry_for(mapa, "AC-001")["unresolved_refs"] == ["BR-404"]


# --- TEST_DESIGN --------------------------------------------------------------


async def test_test_design_produce_casos_funcionales_y_negativos():
    salida = await run_test_design(QaMapLLM(), _mapa(), _sources())
    tipos = [c["type"] for c in salida["test_cases"]]
    assert tipos == ["functional", "negative"]
    assert all(c["criterion_ref"] == "AC-001" for c in salida["test_cases"])


async def test_los_ids_los_pone_python_y_no_se_repiten():
    salida = await run_test_design(QaMapLLM(), _mapa(), _sources())
    ids = [c["id"] for c in salida["test_cases"]]
    assert ids == ["TC-001", "TC-002"]


async def test_los_pasos_se_numeran_solos():
    salida = await run_test_design(QaMapLLM(), _mapa(), _sources())
    pasos = salida["test_cases"][0]["steps"]
    assert [p["number"] for p in pasos] == [1, 2, 3]


async def test_una_ref_inventada_se_quita_del_caso_con_nota():
    """El caso es correcto salvo la cita: se limpia, no se tira."""
    salida = await run_test_design(QaMapLLM(), _mapa(), _sources())
    negativo = [c for c in salida["test_cases"] if c["type"] == "negative"][0]
    assert negativo["source_refs"] == ["BR-001"]
    assert any("BR-999" in o["description"] for o in salida["observations"])


async def test_la_prioridad_se_hereda_y_el_modelo_no_la_toca():
    salida = await run_test_design(QaMapLLM(), _mapa(), _sources())
    assert {c["priority"] for c in salida["test_cases"]} == {"critica"}


async def test_un_criterio_no_verificable_no_produce_caso_vago():
    """La salida honesta: se declara y va al QA lead, no se rellena."""
    salida = await run_test_design(QaMapLLM(), _mapa(), _sources())
    assert [n["criterion_ref"] for n in salida["not_testable"]] == ["AC-002"]
    assert salida["not_testable"][0]["blocking"] is True
    assert "checkpoint" in salida["not_testable"][0]["reason"]


def test_known_refs_recoge_los_ids_reales_del_ef():
    refs = known_refs(_sources())
    assert {"BR-001", "VAL-001", "FLD-001", "ENT-001", "ACT-001", "REQ-F-001"} <= refs
    assert "BR-999" not in refs


# --- EDGE_CASES: la cita verbatim ---------------------------------------------


def test_evidence_matches_acepta_la_cita_exacta():
    assert evidence_matches(
        "La fecha del siniestro no puede ser futura.",
        "La fecha del siniestro no puede ser futura.",
    )


def test_evidence_matches_tolera_espacios_y_mayusculas():
    """El modelo cambia el espaciado al copiar dentro de un JSON; eso no es inventar."""
    assert evidence_matches(
        "la  fecha del siniestro\nno puede ser futura",
        "La fecha del siniestro no puede ser futura.",
    )


def test_evidence_matches_rechaza_la_parafrasis():
    """Lo que el control existe para atrapar: una cita que suena bien y no está."""
    assert not evidence_matches(
        "La fecha no puede ser anterior a 2020.",
        "La fecha del siniestro no puede ser futura.",
    )


def test_evidence_matches_rechaza_lo_vacio():
    assert not evidence_matches("", "La fecha no puede ser futura.")
    assert not evidence_matches("algo", "")


async def test_edge_cases_conserva_el_limite_citado_y_descarta_la_parafrasis():
    salida = await run_edge_cases(QaMapLLM(), _mapa(), _sources(), today=HOY)
    assert len(salida["test_cases"]) == 1
    caso = salida["test_cases"][0]
    assert caso["type"] == "boundary"
    assert caso["boundary"]["kind"] == "max"
    assert caso["boundary"]["anchor_source"] == "ef_text"
    assert caso["boundary"]["evidence"] == "La fecha del siniestro no puede ser futura."
    # El límite parafraseado no produjo caso: produjo pregunta.
    assert len(salida["unanchored"]) == 1
    assert salida["unanchored"][0]["rule_ref"] == "VAL-001"
    assert "verbatim" in salida["unanchored"][0]["reason"]
    assert any(
        "no está en el texto" in o["description"] for o in salida["observations"]
    )


async def test_el_dato_invalido_del_borde_es_el_primero_que_falla():
    salida = await run_edge_cases(QaMapLLM(), _mapa(), _sources(), today=HOY)
    dato = salida["test_cases"][0]["test_data"][0]
    assert dato["value"] == "2026-08-15"  # el día siguiente a HOY, no una fecha lejana
    assert dato["kind"] == "boundary"


async def test_un_limite_de_una_regla_no_citada_no_se_puede_verificar():
    """Si el criterio no menciona la regla, no hay texto contra el que comparar."""

    class LimiteHuerfano:
        async def complete_json(self, *, system: str, user: str) -> str:
            import json as _json

            if "Diseñador de casos de borde" not in system:
                return "{}"
            return _json.dumps(
                {
                    "boundaries": [
                        {
                            "rule_ref": "VAL-777",
                            "kind": "max",
                            "evidence": "El monto máximo es 5000.",
                            "invalid_value": "5001",
                        }
                    ]
                }
            )

    salida = await run_edge_cases(LimiteHuerfano(), _mapa(), _sources(), today=HOY)
    assert salida["test_cases"] == []
    assert salida["unanchored"][0]["rule_ref"] == "VAL-777"


async def test_los_ids_de_borde_continuan_la_numeracion():
    salida = await run_edge_cases(
        QaMapLLM(), _mapa(), _sources(), today=HOY, used_ids={"TC-001", "TC-002"}
    )
    assert salida["test_cases"][0]["id"] == "TC-003"


# --- EDGE_CASES: el límite estructural del contrato de API --------------------


def test_el_campo_requerido_del_api_produce_limite_sin_cita():
    """Un dato duro del contrato se sostiene solo: no necesita verbatim."""
    sources = _sources(con_api=True)
    limites = api_field_boundaries(entry_for(_mapa(True), "AC-001"), sources)
    requeridos = [l for l in limites if l["kind"] == "required"]
    assert requeridos, "fecha_siniestro es required en el contrato de API"
    assert requeridos[0]["anchor_source"] == "api_field"
    assert requeridos[0]["api_field_ref"]
    assert "evidence" not in requeridos[0]


def test_sin_contrato_de_api_no_hay_limites_estructurales():
    assert api_field_boundaries(entry_for(_mapa(), "AC-001"), _sources()) == []


# --- AUTH_CASES ---------------------------------------------------------------


def test_sin_contrato_de_api_no_hay_casos_de_autorizacion():
    salida = build_auth_cases(_mapa(), _sources())
    assert salida["test_cases"] == []
    assert salida["ambiguous_auth_refs"] == []


def test_la_regla_ambigua_no_produce_caso_sino_pregunta():
    """El corazón de QA-D7: en la banda de duda no se adivina, se pregunta."""
    salida = build_auth_cases(_mapa(True), _sources(con_api=True))
    assert "AUTH-002" in salida["ambiguous_auth_refs"]
    citadas = {c["auth_context"]["auth_rule_ref"] for c in salida["test_cases"]}
    assert "AUTH-002" not in citadas
    assert any("AUTH-002" in o["description"] for o in salida["observations"])


def test_las_reglas_no_ambiguas_producen_sus_casos():
    salida = build_auth_cases(_mapa(True), _sources(con_api=True))
    citadas = {c["auth_context"]["auth_rule_ref"] for c in salida["test_cases"]}
    assert citadas == {"AUTH-001", "AUTH-003", "AUTH-004"}
    assert all(c["type"] == "authorization" for c in salida["test_cases"])


def test_el_alcance_acotado_produce_el_caso_cruzado():
    """El ejemplo del enunciado, cuando la columna SÍ existe."""
    sources = _sources(con_api=True)
    for regla in sources["api"]["authorization_matrix"]:
        if regla["id"] == "AUTH-002":
            regla["ambiguous"] = False
            regla["scope_column_refs"] = ["COL-0099"]
    salida = build_auth_cases(_mapa(True), sources)
    cruzado = [
        c
        for c in salida["test_cases"]
        if c["auth_context"]["auth_rule_ref"] == "AUTH-002"
    ][0]
    assert "otro equipo" in cruzado["title"]
    assert cruzado["auth_context"]["scope"] == "own_team"
    assert cruzado["auth_context"]["expected_status"] == 403
    assert cruzado["auth_context"]["negative"] is True
    assert cruzado["auth_context"]["scope_column_refs"] == ["COL-0099"]


def test_una_regla_deny_produce_el_caso_de_rechazo():
    sources = _sources(con_api=True)
    sources["api"]["authorization_matrix"] = [
        {
            "id": "AUTH-900",
            "endpoint_ref": "EP-001",
            "actor_name": "Auditor",
            "effect": "deny",
            "scope": "none",
        }
    ]
    salida = build_auth_cases(_mapa(True), sources)
    caso = salida["test_cases"][0]
    assert caso["auth_context"]["expected_status"] == 403
    assert caso["auth_context"]["negative"] is True


def test_el_suelo_de_prioridad_de_autorizacion():
    """Un fallo de autorización es de seguridad: nunca baja de alta (QA-D4)."""
    assert priority_with_floor("baja") == "alta"
    assert priority_with_floor("media") == "alta"
    assert priority_with_floor("alta") == "alta"
    assert priority_with_floor("critica") == "critica"


def test_los_casos_de_autorizacion_siempre_citan_un_criterio_real():
    """El contrato lo exige, y sin criterio el caso no podría existir."""
    mapa = _mapa(True)
    salida = build_auth_cases(mapa, _sources(con_api=True))
    validos = set(mapa["criterion_refs"])
    assert salida["test_cases"]
    for caso in salida["test_cases"]:
        assert caso["criterion_ref"] in validos


# --- Esfuerzo determinista ----------------------------------------------------


def test_el_esfuerzo_es_reproducible_y_no_lo_estima_el_modelo():
    assert estimated_minutes("functional", "critica") == 15  # 10 * 1.5
    assert estimated_minutes("negative", "critica") == 9  # 6 * 1.5
    assert estimated_minutes("boundary", "alta") == 6  # 5 * 1.2
    assert estimated_minutes("authorization", "critica") == 12  # 8 * 1.5


def test_medio_minuto_siempre_sube():
    """`round()` haría 7.5→8 y 6.5→6: dos cálculos iguales con resultados distintos."""
    assert estimated_minutes("boundary", "critica") == 8  # 5 * 1.5 = 7.5


def test_next_id_salta_los_ocupados():
    assert next_id("TC", {"TC-001", "TC-002"}) == "TC-003"
    assert next_id("TC", set()) == "TC-001"


def test_normalize_steps_numera_desde_uno():
    pasos = normalize_steps([{"action": "a"}, {"action": "b", "expected": "c"}])
    assert [p["number"] for p in pasos] == [1, 2]
    assert pasos[1]["expected"] == "c"


# --- El grafo completo hasta AUTH_CASES ---------------------------------------


async def _corre(con_api: bool) -> dict:
    graph = build_qa_graph(build_memory_checkpointer())
    estado = {
        "job_id": "01QA0000000000000000000QA3",
        "scrum_job_id": "01SC",
        "scrum_artifact": scrum_example().model_dump(mode="json"),
        "scrum_artifact_hash": "f6e5d4c3b2a1",
        "scrum_ready": True,
        "ef_job_id": "01EF",
        "ef_artifact": ef_example().model_dump(mode="json"),
        "ef_artifact_hash": "a1b2c3d4e5f6",
    }
    if con_api:
        estado |= {
            "job_id": "01QA0000000000000000000QA4",
            "api_job_id": "01AP",
            "api_artifact": api_example().model_dump(mode="json"),
            "api_artifact_hash": "9f8e7d6c5b4a",
        }
    return await graph.ainvoke(
        estado,
        config={
            "configurable": {
                "thread_id": estado["job_id"],
                "llm": QaMapLLM(),
                "today": HOY,
            }
        },
    )


async def test_el_grafo_acumula_los_tres_tipos_de_caso():
    salida = await _corre(con_api=True)
    tipos = {c["type"] for c in salida["test_cases"]}
    assert tipos == {"functional", "negative", "boundary", "authorization"}
    # Ids únicos a lo largo de los tres nodos que los generan.
    ids = [c["id"] for c in salida["test_cases"]]
    assert len(ids) == len(set(ids))


async def test_el_grafo_sin_api_no_trae_autorizacion():
    salida = await _corre(con_api=False)
    assert all(c["type"] != "authorization" for c in salida["test_cases"])
    assert salida["ambiguous_auth_refs"] == []


async def test_los_casos_del_grafo_validan_contra_el_contrato():
    """La prueba de fuego: lo que produce el pipeline entra en el artefacto real."""
    salida = await _corre(con_api=True)
    casos = [TestCase.model_validate(c) for c in salida["test_cases"]]
    assert casos
    artefacto = QaArtifact(
        source=SourceRef(
            scrum_job_id="01SC",
            scrum_artifact_hash="h1",
            ef_job_id="01EF",
            ef_artifact_hash="h2",
            api_job_id="01AP",
            api_artifact_hash="h3",
            api_available=True,
        ),
        test_cases=casos,
    )
    assert len(artefacto.test_cases) == len(salida["test_cases"])


async def test_el_grafo_registra_la_historia_sin_criterios():
    graph = build_qa_graph(build_memory_checkpointer())
    scrum = scrum_example().model_dump(mode="json")
    scrum["stories"][1]["acceptance_criteria"] = []
    salida = await graph.ainvoke(
        {
            "job_id": "01QA0000000000000000000QA5",
            "scrum_job_id": "01SC",
            "scrum_artifact": scrum,
            "scrum_artifact_hash": "h",
            "scrum_ready": True,
            "ef_job_id": "01EF",
            "ef_artifact": ef_example().model_dump(mode="json"),
            "ef_artifact_hash": "h",
        },
        config={
            "configurable": {
                "thread_id": "01QA0000000000000000000QA5",
                "llm": QaMapLLM(),
                "today": HOY,
            }
        },
    )
    assert any(
        "US-002" in (o.get("source_ref") or "") for o in salida["map_observations"]
    )
