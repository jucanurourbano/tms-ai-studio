"""Cierre del Agente QA: el pipeline completo contra un plan **a escala**.

``test_assemble.py`` ya recorre los doce nodos, pero sobre el plan mínimo de dos
historias. Este archivo lo recorre sobre ``example_rich_artifact()`` —tres épicas,
siete historias con las cuatro prioridades MoSCoW, dependencias que cruzan épicas
y once criterios— porque hay propiedades que un plan de dos historias **no puede
tener** y que son justo las que este agente debe manejar bien:

- un **orden topológico** que de verdad ordena (con una sola épica es trivial);
- la diferencia entre un hueco que **bloquea** (``must``/``should``) y uno que
  solo avisa (``could``/``wont``), que es el corazón de QA-D5;
- un **techo por criterio** que llega a podar y deja constancia de lo podado;
- y una **cobertura** que se puede recomputar desde el artefacto y tiene que
  cuadrar con lo que la matriz enseña.

Todo con LLM falso (``QaRichLLM``): ni un token de la API real.
"""

from ai.agents.api.schemas.examples import example_artifact as api_example
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.qa.assemble import validate_artifact
from ai.agents.qa.export import cases_csv, trace_csv
from ai.agents.scrum.schemas.examples import example_rich_artifact
from ai.orchestrator import build_qa_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from tests.mocks import QaRichLLM

HOY = "2026-08-14"

#: Criterio deliberadamente vago del plan rico: debe acabar en pregunta.
VAGO = "AC-011"


async def _corre(*, con_api: bool = True, overrides: dict | None = None) -> dict:
    graph = build_qa_graph(build_memory_checkpointer())
    estado = {
        "job_id": "01QA00000000000000000RICH",
        "scrum_job_id": "01SC",
        "scrum_artifact": example_rich_artifact().model_dump(mode="json"),
        "scrum_artifact_hash": "r1c2h3p4l5a6",
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
    if overrides:
        estado["target_overrides"] = overrides

    async def _sin_persistir(job_id, artifact, status, metrics):
        """PERSIST inocuo: sin esto el nodo caería en la BD real."""

    return await graph.ainvoke(
        estado,
        config={
            "configurable": {
                "thread_id": estado["job_id"],
                "llm": QaRichLLM(),
                "today": HOY,
                "persist": _sin_persistir,
            }
        },
    )


async def _artefacto(**kwargs):
    return validate_artifact((await _corre(**kwargs))["artifact"])


# --- El plan completo ----------------------------------------------------------


async def test_el_plan_a_escala_produce_un_artefacto_valido():
    a = await _artefacto()
    assert a.schema_version == "1.0.0"
    # Once criterios, y de cada uno salen casos salvo del declarado no verificable.
    assert len(a.trace_matrix.rows) == 11
    assert len(a.test_cases) >= 18
    assert a.metrics.test_cases_total == len(a.test_cases)


async def test_cada_caso_esta_anclado_a_un_criterio_que_existe():
    """El cortafuegos anti-invención, comprobado sobre el conjunto entero."""
    a = await _artefacto()
    criterios = {f.criterion_ref for f in a.trace_matrix.rows}
    for caso in a.test_cases:
        assert caso.criterion_ref in criterios, caso.id


async def test_hay_casos_de_los_cuatro_tipos():
    """Un plan que solo tuviera funcionales sería el defecto clásico del agente."""
    a = await _artefacto()
    tipos = {c.type.value for c in a.test_cases}
    assert tipos == {"functional", "negative", "boundary", "authorization"}


async def test_todo_caso_de_borde_trae_su_limite_anclado_en_evidencia():
    a = await _artefacto()
    bordes = [c for c in a.test_cases if c.type.value == "boundary"]
    assert bordes
    for caso in bordes:
        limite = caso.boundary
        assert limite is not None
        if limite.anchor_source.value == "ef_text":
            # La cita tiene que estar VERBATIM en el texto de la regla del EF.
            assert limite.evidence
            assert limite.rule_ref
        else:
            assert limite.api_field_ref


# --- Lo que solo se ve a escala ------------------------------------------------


async def test_el_orden_de_las_suites_respeta_las_dependencias_entre_epicas():
    """EPIC-002 depende de EPIC-001 (US-003→US-001) y EPIC-003 de EPIC-002."""
    a = await _artefacto()
    plan = a.execution_plan
    assert plan.dependency_cycles == []
    epica_de_suite = {s.id: s.epic_ref for s in plan.suites}
    orden = [epica_de_suite[sid] for sid in plan.order]
    assert orden.index("EPIC-001") < orden.index("EPIC-002")
    assert orden.index("EPIC-002") < orden.index("EPIC-003")


async def test_un_hueco_en_must_should_bloquea_y_en_could_wont_solo_avisa():
    """El corazón de QA-D5, que un plan de dos historias `must` no puede mostrar."""
    a = await _artefacto()
    cobertura = a.trace_matrix.coverage

    # El criterio vago es de US-007, que es `wont`: queda sin cubrir…
    fila_vaga = next(f for f in a.trace_matrix.rows if f.criterion_ref == VAGO)
    assert fila_vaga.status.value == "not_testable"
    assert fila_vaga.story_priority.value == "wont"

    # …y por eso NO cuenta contra la cobertura que entra en el semáforo.
    assert cobertura.criteria_covered < cobertura.criteria_total
    assert cobertura.blocking_criteria_covered == cobertura.blocking_criteria_total


async def test_el_criterio_no_verificable_acaba_en_pregunta_no_en_caso():
    """La salida correcta ante un criterio vago es preguntar, no inventar."""
    a = await _artefacto()
    assert all(c.criterion_ref != VAGO for c in a.test_cases)
    fila = next(f for f in a.trace_matrix.rows if f.criterion_ref == VAGO)
    assert fila.question_ref in {q.id for q in a.questions_for_qa_lead}


async def test_la_cobertura_se_puede_recomputar_desde_la_matriz():
    """El artefacto no puede decir una cobertura que sus propias filas desmientan."""
    a = await _artefacto()
    c = a.trace_matrix.coverage
    cubiertas = [f for f in a.trace_matrix.rows if f.status.value == "covered"]
    assert c.criteria_total == len(a.trace_matrix.rows)
    assert c.criteria_covered == len(cubiertas)
    assert round(c.criteria_ratio, 6) == round(c.criteria_covered / c.criteria_total, 6)
    # Y la del semáforo, restringida a must/should.
    bloqueantes = [
        f for f in a.trace_matrix.rows if f.story_priority.value in ("must", "should")
    ]
    assert c.blocking_criteria_total == len(bloqueantes)


async def test_el_esfuerzo_del_plan_es_la_suma_de_sus_suites():
    a = await _artefacto()
    plan = a.execution_plan
    assert plan.totals.manual_minutes == sum(s.estimated_minutes for s in plan.suites)
    assert plan.totals.cases_total == len(a.test_cases)
    assert sum(plan.totals.by_type.values()) == len(a.test_cases)


async def test_dos_corridas_del_mismo_plan_dan_el_mismo_esfuerzo():
    """QA-D8: los minutos salen de una tabla, no de una estimación del modelo."""
    primera = await _artefacto()
    segunda = await _artefacto()
    assert (
        primera.execution_plan.totals.manual_minutes
        == segunda.execution_plan.totals.manual_minutes
    )


async def test_el_techo_por_criterio_poda_y_lo_deja_por_escrito():
    """Un tope silencioso se leería como cobertura completa."""
    completo = await _artefacto()
    podado = await _artefacto(overrides={"max_cases_per_criterion": 1})
    assert len(podado.test_cases) < len(completo.test_cases)
    assert podado.metrics.pruned_cases > 0
    assert any(
        "podado" in o.description.lower() or "techo" in o.description.lower()
        for o in podado.analysis.observations
    )


async def test_la_capacidad_declarada_se_traduce_en_sesiones():
    a = await _artefacto(overrides={"manual_capacity_minutes": 120})
    sesiones = a.execution_plan.totals.estimated_sessions
    assert sesiones is not None
    assert sesiones == -(-a.execution_plan.totals.manual_minutes // 120)


# --- Sin contrato de API -------------------------------------------------------


async def test_sin_contrato_el_plan_a_escala_lo_declara_y_pierde_solo_lo_suyo():
    """Sin contrato se pierde lo que el contrato aportaba, no el plan entero.

    Y lo que aportaba son DOS cosas, no una: los casos de autorización —que sin la
    matriz serían una suposición sobre quién ve qué— y los bordes anclados en un
    campo **estructurado** del contrato (``required``, ``max_length``, ``enum``),
    que es la vía que prevalece cuando existe (QA-D2). Lo que sale del EF no se
    toca: los funcionales, los negativos y los bordes citados verbatim son los
    mismos con contrato y sin él.
    """
    con = await _artefacto()
    sin = await _artefacto(con_api=False)
    assert sin.source.api_available is False
    assert sin.source.api_absent_reason
    assert all(c.type.value != "authorization" for c in sin.test_cases)

    def del_ef(artefacto):
        return [
            c
            for c in artefacto.test_cases
            if c.type.value in ("functional", "negative")
            or (c.boundary and c.boundary.anchor_source.value == "ef_text")
        ]

    assert len(del_ef(sin)) == len(del_ef(con)) > 0
    # Y lo que se perdió está contado, no desaparecido en silencio.
    assert any(
        "autorización" in o.description.lower() for o in sin.analysis.observations
    )


# --- Los exports del plan a escala ---------------------------------------------


async def test_los_exports_del_plan_a_escala_cuadran_con_el_artefacto():
    a = await _artefacto()
    datos = a.model_dump(mode="json")
    casos = cases_csv(datos).splitlines()
    matriz = trace_csv(datos).splitlines()
    # Las líneas no son filas cuando hay saltos dentro de una celda (los pasos),
    # así que lo que se comprueba es que cada id aparezca en su archivo.
    for caso in a.test_cases:
        assert caso.id in "\n".join(casos)
    for fila in a.trace_matrix.rows:
        assert fila.criterion_ref in "\n".join(matriz)
