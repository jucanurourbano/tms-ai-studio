"""Tests de ASSEMBLE/PERSIST y del pipeline completo con LLM falso (QA6).

El test que cierra el agente es ``test_el_pipeline_completo_produce_un_artefacto_valido``:
arranca del ``ScrumArtifact`` de ejemplo real, atraviesa los doce nodos con un LLM
mockeado y comprueba que lo que sale **valida contra el contrato**. Todo lo demás
—cada cortafuegos por separado— ya está cubierto en los bloques anteriores; esto
verifica que las piezas encajan.
"""

import pytest

from ai.agents.api.schemas.examples import example_artifact as api_example
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.qa.assemble import assemble_artifact, validate_artifact
from ai.agents.qa.schemas import QaArtifact
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from ai.orchestrator import build_qa_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from tests.mocks import QaMapLLM

HOY = "2026-08-14"


async def _corre(*, con_api: bool = True, persist=None, extra=None) -> dict:
    graph = build_qa_graph(build_memory_checkpointer())
    estado = {
        "job_id": "01QA000000000000000000QA6",
        "scrum_job_id": "01SC",
        "scrum_artifact": scrum_example().model_dump(mode="json"),
        "scrum_artifact_hash": "f6e5d4c3b2a1",
        "scrum_ready": True,
        "ef_job_id": "01EF",
        "ef_artifact": ef_example().model_dump(mode="json"),
        "ef_artifact_hash": "a1b2c3d4e5f6",
        "started_at": 0.0,
    }
    if con_api:
        estado |= {
            "api_job_id": "01AP",
            "api_artifact": api_example().model_dump(mode="json"),
            "api_artifact_hash": "9f8e7d6c5b4a",
        }
    estado |= extra or {}

    async def _sin_persistir(job_id, artifact, status, metrics):
        """PERSIST inocuo. Se inyecta SIEMPRE, incluso cuando el test no lo mira.

        Sin esto el nodo cae a la BD real y el job no existe en `agent_jobs`, así
        que el fallo llega como violación de clave ajena — un error de fontanería
        que oculta lo que el test estaba comprobando.
        """

    configurable = {
        "thread_id": estado["job_id"],
        "llm": QaMapLLM(),
        "today": HOY,
        "persist": persist or _sin_persistir,
    }
    return await graph.ainvoke(estado, config={"configurable": configurable})


# --- El pipeline completo -----------------------------------------------------


async def test_el_pipeline_completo_produce_un_artefacto_valido():
    salida = await _corre()
    artefacto = validate_artifact(salida["artifact"])
    assert artefacto.schema_version == "1.0.0"
    assert artefacto.test_cases
    assert artefacto.trace_matrix.rows
    assert artefacto.execution_plan.suites
    assert artefacto.metrics.test_cases_total == len(artefacto.test_cases)


async def test_el_artefacto_registra_la_cadena_y_el_contrato_usado():
    salida = await _corre()
    source = validate_artifact(salida["artifact"]).source
    assert source.scrum_job_id == "01SC"
    assert source.ef_job_id == "01EF"
    assert source.api_job_id == "01AP"
    assert source.api_available is True
    assert source.api_absent_reason is None


async def test_sin_contrato_el_artefacto_declara_por_que():
    """ "No hay casos de autorización" y "no se pudo" no pueden leerse igual."""
    salida = await _corre(con_api=False)
    artefacto = validate_artifact(salida["artifact"])
    assert artefacto.source.api_available is False
    assert artefacto.source.api_absent_reason
    assert all(c.type.value != "authorization" for c in artefacto.test_cases)
    assert any("autorización" in o.description for o in artefacto.analysis.observations)


async def test_la_matriz_del_artefacto_enlaza_los_criterios_no_verificables():
    """El contrato exige que una fila `not_testable` cite su pregunta."""
    artefacto = validate_artifact((await _corre())["artifact"])
    no_verificables = [
        f for f in artefacto.trace_matrix.rows if f.status.value == "not_testable"
    ]
    assert no_verificables, "el mock declara AC-002 no verificable"
    ids_de_pregunta = {q.id for q in artefacto.questions_for_qa_lead}
    for fila in no_verificables:
        assert fila.question_ref in ids_de_pregunta


async def test_las_metricas_traen_coste_y_tokens_reales():
    artefacto = validate_artifact((await _corre())["artifact"])
    assert artefacto.metrics.tokens.total > 0
    assert artefacto.metrics.cost > 0
    assert artefacto.metrics.manual_minutes > 0


async def test_las_observaciones_recogen_los_descartes_de_todo_el_pipeline():
    """Regla del proyecto: ningún descarte es silencioso."""
    artefacto = validate_artifact((await _corre())["artifact"])
    descripciones = " ".join(o.description for o in artefacto.analysis.observations)
    # La ref inventada por el mock (BR-999) y el límite parafraseado (VAL-001).
    assert "BR-999" in descripciones
    assert "no está en el texto" in descripciones


async def test_el_semaforo_del_artefacto_refleja_las_preguntas_bloqueantes():
    artefacto = validate_artifact((await _corre())["artifact"])
    bloqueantes = [q for q in artefacto.questions_for_qa_lead if q.blocking]
    assert bloqueantes
    assert artefacto.metrics.blocking_questions_total == len(bloqueantes)


# --- PERSIST ------------------------------------------------------------------


async def test_persist_guarda_y_marca_el_estado():
    guardado = {}

    async def fake_persist(job_id, artifact, status, metrics):
        guardado.update(
            {
                "job_id": job_id,
                "status": status,
                "cases": len(artifact["test_cases"]),
                "metrics": metrics,
            }
        )

    salida = await _corre(persist=fake_persist)
    assert guardado["job_id"] == "01QA000000000000000000QA6"
    assert guardado["status"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS")
    assert guardado["cases"] == len(salida["artifact"]["test_cases"])


async def test_un_plan_con_casos_podados_no_pasa_por_completed_limpio():
    """El equipo tiene que enterarse de que el plan no salió íntegro."""
    guardado = {}

    async def fake_persist(job_id, artifact, status, metrics):
        guardado["status"] = status

    await _corre(
        persist=fake_persist,
        extra={"target_overrides": {"max_cases_per_criterion": 1}},
    )
    assert guardado["status"] == "COMPLETED_WITH_WARNINGS"


# --- ASSEMBLE aislado ---------------------------------------------------------


def test_un_item_invalido_se_descarta_y_el_resto_del_plan_se_entrega():
    """Entregar 1 caso bueno señalando el roto es más útil que no entregar nada."""
    estado = {
        "scrum_job_id": "01SC",
        "scrum_artifact_hash": "h1",
        "ef_job_id": "01EF",
        "ef_artifact_hash": "h2",
        "api_available": False,
        "api_absent_reason": "sin contrato",
        "test_cases": [
            {
                "id": "TC-001",
                "title": "Bueno",
                "story_ref": "US-001",
                "criterion_ref": "AC-001",
                "type": "functional",
                "steps": [{"number": 1, "action": "hacer"}],
                "expected_result": "pasa",
            },
            # Sin `steps`: el contrato lo rechaza (un caso sin pasos no prueba nada).
            {
                "id": "TC-002",
                "title": "Roto",
                "story_ref": "US-001",
                "criterion_ref": "AC-001",
                "type": "functional",
                "steps": [],
                "expected_result": "pasa",
            },
        ],
    }
    artefacto, avisos = assemble_artifact(estado)
    assert [c.id for c in artefacto.test_cases] == ["TC-001"]
    assert avisos is True
    assert any("TC-002" in o.description for o in artefacto.analysis.observations)


def test_un_caso_de_autorizacion_sin_contrato_se_descarta_diciendo_por_que():
    """El cortafuegos funcionando no debe leerse como un bug del ensamblado."""
    estado = {
        "scrum_job_id": "01SC",
        "scrum_artifact_hash": "h1",
        "ef_job_id": "01EF",
        "ef_artifact_hash": "h2",
        "api_available": False,
        "api_absent_reason": "sin contrato",
        "test_cases": [
            {
                "id": "TC-009",
                "title": "Autorización huérfana",
                "story_ref": "US-001",
                "criterion_ref": "AC-001",
                "type": "authorization",
                "steps": [{"number": 1, "action": "invocar"}],
                "expected_result": "403",
                "auth_context": {
                    "auth_rule_ref": "AUTH-001",
                    "endpoint_ref": "EP-001",
                },
            }
        ],
    }
    artefacto, _ = assemble_artifact(estado)
    assert artefacto.test_cases == []
    assert any(
        "suposición con la autoridad de un caso de prueba" in (o.reason or "")
        for o in artefacto.analysis.observations
    )


def test_una_matriz_invalida_se_entrega_vacia_y_se_dice():
    """Antes que una cobertura que nadie calculó, ninguna cobertura."""
    estado = {
        "scrum_job_id": "01SC",
        "scrum_artifact_hash": "h1",
        "ef_job_id": "01EF",
        "ef_artifact_hash": "h2",
        "api_available": False,
        "api_absent_reason": "sin contrato",
        # `criteria_covered` > `criteria_total`: cobertura imposible.
        "trace_matrix": {"coverage": {"criteria_total": 1, "criteria_covered": 5}},
    }
    artefacto, avisos = assemble_artifact(estado)
    assert artefacto.trace_matrix.rows == []
    assert avisos is True
    assert any(
        "matriz de trazabilidad no validó" in o.description
        for o in artefacto.analysis.observations
    )


def test_el_artefacto_ensamblado_hace_round_trip():
    artefacto, _ = assemble_artifact(
        {
            "scrum_job_id": "01SC",
            "scrum_artifact_hash": "h1",
            "ef_job_id": "01EF",
            "ef_artifact_hash": "h2",
            "api_available": False,
            "api_absent_reason": "sin contrato",
        }
    )
    datos = artefacto.model_dump(mode="json")
    assert QaArtifact.model_validate(datos).model_dump(mode="json") == datos


# --- H2: el reloj de QA -------------------------------------------------------


async def test_la_duracion_del_plan_es_un_numero_de_segundos_plausible():
    """H2. Las dos corridas reales de QA reportan **56 años** de duración.

    Los otros cinco agentes fijan ``started_at`` en su primer nodo; ``qa_nodes``
    no lo hacía en ninguno, así que el ensamblador restaba contra ``0.0`` y
    obtenía el *epoch* entero. El ``state.get("started_at", time.time())`` no
    salvaba nada porque la clave **llega presente** con ``0.0`` —este mismo
    arnés la pasa así—: el default nunca entra, el fallback estaba escrito para
    el caso que no ocurre.

    Entra con el control de gasto porque la duración es el otro eje de "qué me
    costó esto", y medir el antes/después de un recorte con un reloj roto no
    sirve.
    """
    salida = await _corre()
    duracion = salida["artifact"]["metrics"]["duration"]
    assert 0.0 <= duracion < 300.0, (
        f"La duración del plan es {duracion} s. Si es del orden de 1e9, "
        "`started_at` volvió a quedarse sin fijar en LOAD_SOURCES."
    )


async def test_el_primer_nodo_fija_el_reloj_aunque_llegue_en_cero():
    """El arreglo, visto sobre la causa: LOAD_SOURCES pisa el ``0.0`` de entrada.

    Comprobar solo la duración dejaría pasar un arreglo hecho en el ensamblador
    (un `if not started_at`), que taparía el síntoma en QA y dejaría a los otros
    cinco agentes con el mismo fallback escrito para el caso que no ocurre.
    """
    import time

    from ai.agents.qa.schemas.examples import example_artifact  # noqa: F401
    from ai.orchestrator.qa_nodes import node_load_sources

    antes = time.time()
    salida = await node_load_sources(
        {
            "scrum_ready": True,
            "scrum_job_id": "01SC",
            "scrum_artifact": scrum_example().model_dump(mode="json"),
            "ef_artifact": ef_example().model_dump(mode="json"),
            "started_at": 0.0,
        }
    )
    assert antes <= salida["started_at"] <= time.time()
