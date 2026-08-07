"""Tests de AUTHORIZATION y RULE_MAPPING (API5), con el LLM mockeado.

Es el bloque donde vive el riesgo principal del agente, así que casi todos estos
tests comprueban lo mismo desde ángulos distintos: **que nada acabe permitiendo
más de lo que alguien escribió**.

Y el otro asunto: que ninguna regla de negocio se pierda entre el Agente BD y este.
"""

from ai.agents.api.authorization import (
    ANY_ACTOR,
    apply_scopes,
    build_base_matrix,
    run_authorization,
    unauthorized_endpoints,
)
from ai.agents.api.endpoints import build_endpoints, merge_actions, run_actions
from ai.agents.api.errors import apply_errors
from ai.agents.api.load_sources import extract_sources, resolve_conventions
from ai.agents.api.payloads import run_schemas
from ai.agents.api.resource_map import build_resource_map
from ai.agents.api.resources import run_resources
from ai.agents.api.rule_mapping import (
    assign_deterministic,
    bd_verdicts,
    collect_rules,
    orphan_application_rules,
    reconcile_classifications,
    run_rule_mapping,
)
from ai.agents.api.schemas.extraction import ScopeExtract
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


async def _pipeline():
    """Recorre el pipeline hasta RULE_MAPPING con el mock."""
    sources = _sources()
    mapa = build_resource_map(sources)
    recursos, _, _, _ = await run_resources(ApiMapLLM(), mapa, sources)
    acciones, _, _, _ = await run_actions(ApiMapLLM(), mapa, sources)
    merge_actions(mapa, acciones)
    endpoints = build_endpoints(mapa, recursos, resolve_conventions())
    esquemas, _, _, _ = await run_schemas(ApiMapLLM(), mapa, endpoints)
    matriz, _, _, obs_auth = await run_authorization(
        ApiMapLLM(), endpoints, mapa, sources
    )
    apply_errors(endpoints, mapa, sources, matriz)
    mapeos, delegadas, _, _, obs_reglas = await run_rule_mapping(
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
        "observaciones": obs_auth + obs_reglas,
    }


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


# --- Fail-closed --------------------------------------------------------------


def test_el_modelo_no_tiene_donde_escribir_que_alguien_lo_ve_todo():
    """La barrera estructural: el esquema de salida no admite `all` ni `none`.

    No es una instrucción del prompt que el modelo pueda desobedecer: es que no
    existe el campo. Una alucinación puede dejar a alguien viendo de menos —que se
    nota al usar el sistema— pero nunca de más.
    """
    permitidos = ScopeExtract.model_fields["scope"].annotation.__args__
    assert set(permitidos) == {"own", "own_team", "own_branch", "custom"}
    assert "all" not in permitidos


async def test_un_endpoint_que_nadie_autorizo_lleva_una_denegacion_explicita():
    """El hueco aparece EN la matriz, no en una ausencia que nadie mira."""
    datos = await _pipeline()
    catalogo = next(
        e for e in datos["endpoints"] if e["operation_id"] == "listarSiniestroEstados"
    )
    reglas = [r for r in datos["matriz"] if r["endpoint_ref"] == catalogo["id"]]
    assert len(reglas) == 1
    assert reglas[0]["effect"] == "deny"
    assert reglas[0]["basis"] == "default_deny"
    assert reglas[0]["actor_ref"] == ANY_ACTOR
    assert "Ninguna celda" in reglas[0]["note"]


async def test_la_accion_de_negocio_nace_denegada():
    """El EF justifica QUÉ hace la acción, no QUIÉN puede ejecutarla."""
    datos = await _pipeline()
    accion = next(e for e in datos["endpoints"] if e["kind"] == "action")
    reglas = [r for r in datos["matriz"] if r["endpoint_ref"] == accion["id"]]
    assert [r["effect"] for r in reglas] == ["deny"]


async def test_los_endpoints_sin_permiso_se_cuentan_para_el_semaforo():
    datos = await _pipeline()
    sin_permiso = unauthorized_endpoints(datos["endpoints"], datos["matriz"])
    # El catálogo y la acción: dos operaciones que hoy nadie puede llamar.
    assert len(sin_permiso) == 2


def test_la_matriz_base_traslada_la_crud_sin_conceder_nada_nuevo():
    sources = _sources()
    mapa = build_resource_map(sources)
    endpoints = [
        {
            "id": "EP-001",
            "operation_id": "listarSiniestros",
            "resource_ref": "RES-002",
            "kind": "list",
        }
    ]
    reglas = build_base_matrix(endpoints, mapa, sources["ef"]["actors"])
    assert len(reglas) == 1
    assert reglas[0]["actor_ref"] == "ACT-001"
    assert reglas[0]["effect"] == "allow"
    assert reglas[0]["scope"] == "all"
    assert reglas[0]["basis"] == "crud_matrix"
    assert reglas[0]["source_refs"] == ["CRUD-001"]  # la celda que lo respalda


# --- Alcances por fila --------------------------------------------------------


async def test_un_alcance_sin_columna_queda_ambiguo_en_vez_de_aproximarse():
    """El caso que este agente existe para no dejar pasar.

    El mock propone limitar por equipo citando una regla real, pero el modelo de
    datos no tiene columna de equipo. Aplicar el alcance "más o menos" es
    exactamente cómo se filtran datos; marcarlo ambiguo es lo que lo convierte en
    una pregunta bloqueante.
    """
    datos = await _pipeline()
    acotadas = [r for r in datos["matriz"] if r["scope"] == "own_team"]
    assert acotadas
    for regla in acotadas:
        assert regla["ambiguous"] is True
        assert regla["scope_column_refs"] == []
        assert "Pendiente de resolver" in regla["note"]
    assert any(
        "quedó pendiente de resolver" in o["description"]
        for o in datos["observaciones"]
    )


async def test_el_alcance_solo_acota_operaciones_que_tocan_filas():
    """Una creación no se acota: todavía no hay fila que filtrar."""
    datos = await _pipeline()
    por_endpoint = {e["id"]: e for e in datos["endpoints"]}
    for regla in datos["matriz"]:
        if regla["scope"] == "own_team":
            assert por_endpoint[regla["endpoint_ref"]]["kind"] != "create"
    creacion = next(e for e in datos["endpoints"] if e["kind"] == "create")
    reglas_creacion = [
        r for r in datos["matriz"] if r["endpoint_ref"] == creacion["id"]
    ]
    assert all(r["scope"] == "all" for r in reglas_creacion)


async def test_un_alcance_sin_regla_citada_se_descarta():
    datos = await _pipeline()
    motivos = " ".join(o["reason"] for o in datos["observaciones"])
    assert "una restricción que nadie escribió no existe" in motivos


async def test_un_alcance_sobre_un_actor_sin_acceso_no_crea_permiso():
    """Un alcance nunca CONCEDE: solo acota lo que la matriz CRUD ya dio.

    Si acotar a un actor desconocido creara su fila, el modelo tendría una vía
    indirecta para conceder accesos. No la tiene.
    """
    datos = await _pipeline()
    assert not [r for r in datos["matriz"] if r["actor_ref"] == "ACT-777"]
    motivos = " ".join(o["reason"] for o in datos["observaciones"])
    assert "no hay nada que restringir" in motivos


def test_una_columna_inventada_en_el_alcance_se_ignora_declarandolo():
    sources = _sources()
    mapa = build_resource_map(sources)
    recurso = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    endpoints = [
        {
            "id": "EP-001",
            "resource_ref": recurso["id"],
            "kind": "list",
            "operation_id": "listarSiniestros",
        }
    ]
    reglas = [
        {
            "id": "AUTH-001",
            "endpoint_ref": "EP-001",
            "actor_ref": "ACT-001",
            "effect": "allow",
            "scope": "all",
            "scope_column_refs": [],
            "source_refs": [],
            "note": None,
        }
    ]
    notas = apply_scopes(
        recurso,
        endpoints,
        reglas,
        [
            {
                "actor_ref": "ACT-001",
                "scope": "own",
                "column_names": ["columna_inventada", "guia_id"],
                "source_refs": ["BR-001"],
            }
        ],
        {"BR-001"},
    )
    # La columna real se usa; la inventada se ignora y queda dicho.
    assert reglas[0]["scope"] == "own"
    assert reglas[0]["scope_column_refs"] == ["COL-0004"]
    assert reglas[0]["ambiguous"] is False
    assert any("columnas inexistentes" in n["description"] for n in notas)


# --- RULE_MAPPING: el círculo que cierra con el Agente BD ---------------------


def test_se_recogen_todas_las_reglas_y_validaciones_del_ef():
    reglas = collect_rules(_sources())
    assert [r["id"] for r in reglas] == ["BR-001", "VAL-001"]
    assert all(r["text"] for r in reglas)


def test_se_lee_el_veredicto_del_agente_bd():
    veredictos = bd_verdicts(_sources())
    assert veredictos  # el modelo de datos ya clasificó cada regla
    assert set(veredictos.values()) <= {"declarative", "application", "trigger"}


def test_lo_que_ya_se_sabe_no_se_le_pregunta_al_modelo():
    """Si un endpoint cita la regla, no hay nada que deliberar."""
    sources = _sources()
    endpoints = [{"id": "EP-004", "rule_refs": ["VAL-001"], "operation_id": "x"}]
    mapeos, huerfanas = assign_deterministic(
        collect_rules(sources), endpoints, [], [], bd_verdicts(sources)
    )
    asignada = next(m for m in mapeos if m["rule_ref"] == "VAL-001")
    assert asignada["enforcement"] == "endpoint"
    assert asignada["endpoint_refs"] == ["EP-004"]
    assert "VAL-001" not in [h["id"] for h in huerfanas]


def test_una_regla_que_el_modelo_de_datos_garantiza_no_se_duplica_en_la_api():
    sources = _sources()
    mapeos, _ = assign_deterministic(
        collect_rules(sources), [], [], [], {"BR-001": "declarative"}
    )
    asignada = next(m for m in mapeos if m["rule_ref"] == "BR-001")
    assert asignada["enforcement"] == "database"
    assert "no la duplica" in asignada["note"]


def test_el_veredicto_del_bd_viaja_pegado_al_mapeo():
    """Es lo que permite detectar la regla que ambos dieron por hecho que aplicaba
    el otro."""
    sources = _sources()
    mapeos, _ = assign_deterministic(
        collect_rules(sources),
        [{"id": "EP-001", "rule_refs": ["VAL-001"], "operation_id": "x"}],
        [],
        [],
        {"VAL-001": "application"},
    )
    asignada = next(m for m in mapeos if m["rule_ref"] == "VAL-001")
    assert asignada["bd_enforcement"] == "application"


def test_una_regla_delegada_por_el_bd_y_no_recogida_por_la_api_se_denuncia():
    """La comprobación que da sentido a este nodo.

    El modelo de datos dijo "yo no puedo con esta". Si la API tampoco la recoge, la
    regla desaparece del producto y nadie se entera hasta producción.
    """
    mapeos = [
        {
            "rule_ref": "BR-007",
            "bd_enforcement": "application",
            "endpoint_refs": [],
            "schema_field_refs": [],
            "auth_rule_refs": [],
        },
        {
            "rule_ref": "BR-008",
            "bd_enforcement": "application",
            "endpoint_refs": ["EP-001"],
            "schema_field_refs": [],
            "auth_rule_refs": [],
        },
        {
            "rule_ref": "BR-009",
            "bd_enforcement": "declarative",
            "endpoint_refs": [],
            "schema_field_refs": [],
            "auth_rule_refs": [],
        },
    ]
    assert orphan_application_rules(mapeos) == ["BR-007"]


def test_decir_que_la_aplica_un_endpoint_sin_citarlo_no_es_un_destino():
    huerfanas = [{"id": "BR-005", "text": "…", "bd_enforcement": "application"}]
    mapeos, notas = reconcile_classifications(
        huerfanas,
        [{"rule_ref": "BR-005", "enforcement": "endpoint", "endpoint_refs": []}],
        [{"id": "EP-001"}],
    )
    assert mapeos[0]["enforcement"] == "not_applicable"
    assert any("sin destino verificable" in n["description"] for n in notas)


def test_dejar_una_regla_fuera_sin_explicar_deja_rastro():
    huerfanas = [{"id": "BR-006", "text": "…", "bd_enforcement": None}]
    mapeos, notas = reconcile_classifications(
        huerfanas,
        [{"rule_ref": "BR-006", "enforcement": "not_applicable"}],
        [],
    )
    assert mapeos[0]["note"]  # nunca queda sin motivo
    assert any("sin explicación" in n["description"] for n in notas)


def test_una_regla_que_el_modelo_no_clasifico_no_se_pierde():
    huerfanas = [{"id": "BR-010", "text": "…", "bd_enforcement": "application"}]
    mapeos, _ = reconcile_classifications(huerfanas, [], [])
    assert len(mapeos) == 1
    assert mapeos[0]["enforcement"] == "not_applicable"
    assert "Sin clasificar" in mapeos[0]["note"]


async def test_toda_regla_del_ef_acaba_con_un_mapeo():
    datos = await _pipeline()
    reglas = {r["id"] for r in collect_rules(datos["sources"])}
    mapeadas = {m["rule_ref"] for m in datos["mapeos"]}
    assert reglas == mapeadas
    assert [m["id"] for m in datos["mapeos"]] == [
        f"ARM-{i:03d}" for i in range(1, len(datos["mapeos"]) + 1)
    ]


# --- El grafo completo --------------------------------------------------------


async def test_el_grafo_produce_matriz_y_mapeo_de_reglas():
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

    assert final["authorization_matrix"]
    assert final["rule_mappings"]
    # Todo endpoint queda enlazado con sus reglas: ninguno sin decisión de acceso.
    for endpoint in final["endpoints"]:
        assert endpoint["auth_rule_refs"], endpoint["operation_id"]
    assert final["metrics"]["endpoints_unauthorized"] == 2
    # Y el 404 del detalle ya refleja el alcance, porque ERRORS corre después.
    detalle = next(
        e for e in final["endpoints"] if e["operation_id"] == "obtenerSiniestro"
    )
    no_encontrado = next(s for s in detalle["status_codes"] if s["code"] == 404)
    assert "fuera del alcance" in no_encontrado["description"]
