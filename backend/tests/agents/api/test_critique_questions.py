"""Tests de CRITIQUE y QUESTION_GEN (API7).

Dos cosas se prueban aquí. La primera: que la cobertura **enumere** lo que falta en
vez de resumirlo a un porcentaje — un 92% no le sirve a nadie para actuar.

La segunda, y más importante: **qué bloquea y qué no**. Si todo bloqueara, el
semáforo no distinguiría nada; si nada bloqueara, no protegería nada.
"""

from ai.agents.api.authorization import run_authorization
from ai.agents.api.critique import (
    build_coverage,
    coverage_ratio,
    detect_findings,
    reconcile_risks,
    run_critique,
)
from ai.agents.api.endpoints import build_endpoints, merge_actions, run_actions
from ai.agents.api.errors import apply_errors
from ai.agents.api.load_sources import extract_sources, resolve_conventions
from ai.agents.api.payloads import run_schemas
from ai.agents.api.question_gen import blocking_refs, generate_questions
from ai.agents.api.resource_map import build_resource_map
from ai.agents.api.resources import run_resources
from ai.agents.api.rule_mapping import run_rule_mapping
from ai.agents.arquitectura.schemas.examples import (
    example_artifact as arquitectura_example,
)
from ai.agents.bd.schemas.examples import example_artifact as bd_example
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from ai.orchestrator import build_api_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from tests.mocks import ApiMapLLM


def _sources():
    return extract_sources(
        bd_example().model_dump(mode="json"),
        ef_example().model_dump(mode="json"),
        arquitectura_example().model_dump(mode="json"),
        scrum_example().model_dump(mode="json"),
    )


async def _contrato():
    sources = _sources()
    mapa = build_resource_map(sources)
    recursos, _, _, _ = await run_resources(ApiMapLLM(), mapa, sources)
    acciones, _, _, _ = await run_actions(ApiMapLLM(), mapa, sources)
    merge_actions(mapa, acciones)
    endpoints = build_endpoints(mapa, recursos, resolve_conventions())
    esquemas, _, _, _ = await run_schemas(ApiMapLLM(), mapa, endpoints)
    matriz, _, _, _ = await run_authorization(ApiMapLLM(), endpoints, mapa, sources)
    apply_errors(endpoints, mapa, sources, matriz)
    mapeos, delegadas, _, _, _ = await run_rule_mapping(
        ApiMapLLM(), endpoints, esquemas, matriz, sources
    )
    return {
        "sources": sources,
        "mapa": mapa,
        "endpoints": endpoints,
        "schemas": esquemas,
        "matriz": matriz,
        "mapeos": mapeos,
        "delegadas": delegadas,
        "target": {
            "auth": {"decided": True},
            "style_supported": True,
            "style_decided": True,
            "api_style": "rest",
        },
    }


async def _findings(**overrides):
    datos = await _contrato()
    coverage = build_coverage(
        datos["mapa"],
        datos["endpoints"],
        datos["mapeos"],
        datos["matriz"],
        datos["sources"],
    )
    findings = detect_findings(
        datos["mapa"],
        datos["endpoints"],
        datos["schemas"],
        datos["matriz"],
        datos["target"],
        coverage,
        datos["delegadas"],
        {},
    )
    findings.update(overrides)
    return datos, coverage, findings


async def _noop_persist(job_id, artifact, status, metrics):
    """PERSIST sin base de datos: los tests del grafo no escriben en Postgres."""
    return None


def _base_state():
    return {
        "job_id": "API-1",
        "bd_job_id": "BD-1",
        "bd_artifact": bd_example().model_dump(mode="json"),
        "bd_artifact_hash": "bd123",
        "bd_ready": True,
        "architecture_job_id": "AR-1",
        "architecture_artifact": arquitectura_example().model_dump(mode="json"),
        "architecture_artifact_hash": "ar123",
        "scrum_job_id": "SC-1",
        "scrum_artifact": scrum_example().model_dump(mode="json"),
        "scrum_artifact_hash": "sc123",
        "ef_job_id": "EF-1",
        "ef_artifact": ef_example().model_dump(mode="json"),
        "ef_artifact_hash": "ef123",
    }


# --- Cobertura ----------------------------------------------------------------


async def test_la_cobertura_enumera_lo_que_falta_no_solo_lo_resume():
    """Un 92% no le sirve a nadie para actuar; «falta guias» sí."""
    _, coverage, _ = await _findings()
    assert coverage["tables_total"] == 3
    assert coverage["tables_exposed"] == 2
    # El recurso sin operaciones aparece con nombre, no como un hueco anónimo.
    assert coverage["unexposed_table_refs"] == ["TBL-001"]
    assert coverage["ef_apis_total"] == 1
    assert coverage["ef_apis_covered"] == 1
    assert coverage["uncovered_api_refs"] == []


async def test_el_ratio_del_semaforo_solo_mezcla_lo_que_bloquea():
    """Celdas CRUD, reglas y actores generan preguntas, no bajan el ratio."""
    _, coverage, _ = await _findings()
    # 2 tablas expuestas de 3 + 1 API cubierta de 1 = 3/4.
    assert coverage_ratio(coverage) == 0.75
    assert coverage_ratio({"tables_total": 0, "ef_apis_total": 0}) == 1.0


async def test_los_actores_sin_acceso_se_reportan():
    _, coverage, _ = await _findings()
    assert coverage["actors_total"] == 1
    assert coverage["actors_with_access"] == 1
    assert coverage["actors_without_access"] == []


# --- Hallazgos deterministas ---------------------------------------------------


async def test_se_detecta_lo_que_el_pipeline_fue_dejando_por_el_camino():
    _, _, findings = await _findings()
    # Dos endpoints sin permiso: el catálogo y la acción de negocio.
    assert len(findings["unauthorized_endpoints"]) == 2
    # El alcance por equipo que ninguna columna soporta.
    assert findings["ambiguous_scopes"]
    # El recurso que se quedó sin operaciones por falta de celda CRUD.
    assert findings["resources_without_operations"]
    # La acción cuyo cuerpo de entrada quedó declarado y vacío.
    assert findings["empty_action_inputs"]


async def test_los_topes_de_superficie_avisan_sin_recortar():
    _, _, findings = await _findings()
    assert findings["surface_exceeded"] == []  # seis operaciones, muy por debajo
    assert findings["resource_surface_exceeded"] == []


# --- Riesgos (LLM) -------------------------------------------------------------


async def test_los_riesgos_se_numeran_y_se_limpian_las_referencias_falsas():
    datos = await _contrato()
    critique, _, _, notas = await run_critique(
        ApiMapLLM(),
        datos["mapa"],
        datos["endpoints"],
        datos["schemas"],
        datos["matriz"],
        datos["mapeos"],
        datos["target"],
        datos["sources"],
        unenforced_delegated_rules=datos["delegadas"],
    )
    riesgos = critique["risks"]
    assert [r["id"] for r in riesgos] == ["RISK-001", "RISK-002"]
    # El primero ancla a un endpoint real; el segundo citaba uno inexistente.
    assert riesgos[0]["source_ref"] in {e["id"] for e in datos["endpoints"]}
    assert riesgos[1]["source_ref"] is None
    # El riesgo no se pierde por una referencia mala, pero queda dicho.
    assert riesgos[1]["description"]
    assert any("referencia inexistente" in n["description"] for n in notas)


def test_una_severidad_desconocida_cae_a_media_en_vez_de_romper():
    riesgos, _ = reconcile_risks(
        [{"description": "x", "severity": "catastrofica"}], set()
    )
    assert riesgos[0]["severity"] == "media"


# --- Qué bloquea y qué no ------------------------------------------------------


async def test_lo_que_bloquea_es_lo_que_hace_el_contrato_inservible_o_peligroso():
    datos, _, findings = await _findings()
    preguntas = generate_questions(
        findings, datos["endpoints"], datos["schemas"], datos["mapa"], datos["target"]
    )
    bloqueantes = [q for q in preguntas if q["blocking"]]
    textos = " ".join(q["question"] for q in bloqueantes)

    assert "¿Quién puede llamar" in textos  # endpoints sin autorizar
    assert "limita el acceso por filas" in textos  # alcance no implementable
    assert "¿Quién opera sobre" in textos  # recurso sin operaciones
    assert len(bloqueantes) == 3


async def test_lo_que_no_bloquea_es_lo_que_solo_lo_hace_mejorable():
    datos, _, findings = await _findings()
    preguntas = generate_questions(
        findings, datos["endpoints"], datos["schemas"], datos["mapa"], datos["target"]
    )
    no_bloqueantes = [q for q in preguntas if not q["blocking"]]
    textos = " ".join(q["question"] for q in no_bloqueantes)
    assert "¿Qué datos necesitan" in textos  # el cuerpo de la acción, por definir
    assert all(not q["blocking"] for q in no_bloqueantes)


async def test_un_alcance_ambiguo_bloquea_aunque_no_haya_datos_personales():
    """Aquí se endurece lo que decía el diseño, y a conciencia.

    El diseño lo hacía bloqueante solo con PII. Pero un alcance que no se puede
    aplicar significa que quien construya el endpoint lo construirá SIN
    restricción: un acceso más ancho del que nadie autorizó, haya datos personales
    o no. El agravante de la PII no desaparece — se dice en la propia pregunta.
    """
    datos, _, findings = await _findings(ambiguous_scopes_with_pii=[])
    preguntas = generate_questions(
        findings, datos["endpoints"], datos["schemas"], datos["mapa"], datos["target"]
    )
    alcance = next(q for q in preguntas if "acceso por filas" in q["question"])
    assert alcance["blocking"] is True
    assert "sin restricción alguna" in alcance["reason"]
    assert "datos personales" not in alcance["reason"]


async def test_cuando_hay_datos_personales_la_pregunta_lo_dice():
    datos, _, findings = await _findings(
        ambiguous_scopes=["EP-002"], ambiguous_scopes_with_pii=["EP-002"]
    )
    preguntas = generate_questions(
        findings, datos["endpoints"], datos["schemas"], datos["mapa"], datos["target"]
    )
    alcance = next(q for q in preguntas if "acceso por filas" in q["question"])
    assert "datos personales" in alcance["reason"]
    assert "enseñárselos a quien no debía" in alcance["reason"]


async def test_una_regla_que_desaparece_del_producto_bloquea():
    datos, _, findings = await _findings(
        unenforced_delegated_rules=["BR-007", "BR-008"]
    )
    preguntas = generate_questions(
        findings, datos["endpoints"], datos["schemas"], datos["mapa"], datos["target"]
    )
    regla = next(q for q in preguntas if "hacen cumplir" in q["question"])
    assert regla["blocking"] is True
    assert "desaparecerían del producto" in regla["reason"]
    assert "BR-007, BR-008" in regla["reason"]


async def test_una_autenticacion_sin_decidir_bloquea():
    datos, _, findings = await _findings(auth_undecided=["target"])
    preguntas = generate_questions(
        findings, datos["endpoints"], datos["schemas"], datos["mapa"], datos["target"]
    )
    auth = next(q for q in preguntas if "autenticación" in q["question"])
    assert auth["blocking"] is True
    assert "descansa sobre ese mecanismo" in auth["reason"]


async def test_un_estilo_que_no_sabemos_especificar_bloquea_sin_ocultar_el_trabajo():
    datos, _, findings = await _findings(style_unsupported=["graphql"])
    preguntas = generate_questions(
        findings, datos["endpoints"], datos["schemas"], datos["mapa"], datos["target"]
    )
    estilo = next(q for q in preguntas if "graphql" in q["question"])
    assert estilo["blocking"] is True
    assert "aprovechable" in estilo["reason"]  # no se finge que no se hizo nada


# --- Agrupación ----------------------------------------------------------------


async def test_cuarenta_endpoints_sin_autorizar_son_UNA_pregunta():
    """Un panel con cuarenta preguntas triviales entierra la que importa."""
    datos, _, findings = await _findings(
        unauthorized_endpoints=[f"EP-{i:03d}" for i in range(1, 41)]
    )
    preguntas = generate_questions(
        findings, datos["endpoints"], datos["schemas"], datos["mapa"], datos["target"]
    )
    sobre_permisos = [q for q in preguntas if "¿Quién puede llamar" in q["question"]]
    assert len(sobre_permisos) == 1
    assert "40 sin autorizar" in sobre_permisos[0]["question"]


async def test_el_recorte_de_refs_se_declara_nunca_es_mudo():
    datos, _, findings = await _findings(
        unauthorized_endpoints=[f"EP-{i:03d}" for i in range(1, 41)]
    )
    preguntas = generate_questions(
        findings, datos["endpoints"], datos["schemas"], datos["mapa"], datos["target"]
    )
    pregunta = next(q for q in preguntas if "¿Quién puede llamar" in q["question"])
    assert "y 28 más" in pregunta["reason"]  # 40 - 12 visibles


async def test_las_preguntas_se_numeran_de_forma_estable():
    datos, _, findings = await _findings()
    preguntas = generate_questions(
        findings, datos["endpoints"], datos["schemas"], datos["mapa"], datos["target"]
    )
    assert [q["id"] for q in preguntas] == [
        f"Q-{i:03d}" for i in range(1, len(preguntas) + 1)
    ]
    assert all(q["audience"] == "tecnico" for q in preguntas)
    assert all(q["status"] == "pendiente" for q in preguntas)
    assert blocking_refs(preguntas) == [q["id"] for q in preguntas if q["blocking"]]


async def test_un_contrato_sin_huecos_no_genera_preguntas():
    """El semáforo solo sirve si puede ponerse verde."""
    datos, _, findings = await _findings()
    limpio = {clave: [] for clave in findings}
    preguntas = generate_questions(
        limpio, datos["endpoints"], datos["schemas"], datos["mapa"], datos["target"]
    )
    assert preguntas == []


# --- El grafo completo ---------------------------------------------------------


async def test_el_grafo_produce_critica_y_preguntas():
    graph = build_api_graph(build_memory_checkpointer())
    final = await graph.ainvoke(
        _base_state(),
        {
            "configurable": {
                "thread_id": "API-1",
                "llm": ApiMapLLM(),
                "persist": _noop_persist,
            }
        },
    )

    critique = final["critique"]
    assert critique["coverage"]["unexposed_table_refs"] == ["TBL-001"]
    assert critique["risks"]
    assert final["metrics"]["coverage"] == critique["coverage_ratio"]

    preguntas = final["questions"]
    assert preguntas
    bloqueantes = [q for q in preguntas if q["blocking"]]
    assert bloqueantes  # este flujo NO está listo, y el agente lo dice
    # Y la validación siguió saliendo limpia: los huecos son del EF, no del documento.
    assert final["validation"]["spec_valid"] is True
