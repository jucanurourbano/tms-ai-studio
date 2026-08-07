"""Tests de SCHEMAS y ERRORS (API4), con el LLM mockeado.

SCHEMAS: el modelo decide solo qué se oculta y qué compone un resumen, y tres
salvaguardas impiden que esas decisiones dejen el contrato inutilizable.

ERRORS: ningún código se copia "por si acaso". Un `409` existe si hay una
restricción de unicidad que lo provoque, y un `404` cambia de significado cuando
el endpoint tiene alcance por filas — que es la razón por la que este nodo corre
después de la matriz de autorización.
"""

from ai.agents.api.endpoints import build_endpoints, merge_actions, run_actions
from ai.agents.api.errors import apply_errors, build_error_catalog, status_codes_for
from ai.agents.api.load_sources import extract_sources, resolve_conventions
from ai.agents.api.payloads import (
    build_resource_schemas,
    reconcile_exposure,
    run_schemas,
)
from ai.agents.api.resource_map import build_resource_map
from ai.agents.api.resources import run_resources
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
    """Recorre RESOURCE_MAP → RESOURCES → ENDPOINTS → SCHEMAS → ERRORS."""
    sources = _sources()
    mapa = build_resource_map(sources)
    recursos, _, _, _ = await run_resources(ApiMapLLM(), mapa, sources)
    acciones, _, _, _ = await run_actions(ApiMapLLM(), mapa, sources)
    merge_actions(mapa, acciones)
    endpoints = build_endpoints(mapa, recursos, resolve_conventions())
    esquemas, _, _, notas = await run_schemas(ApiMapLLM(), mapa, endpoints)
    catalogo = apply_errors(endpoints, mapa, sources, [])
    return sources, mapa, endpoints, esquemas, catalogo, notas


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


# --- SCHEMAS: las tres salvaguardas ------------------------------------------


async def test_ocultar_es_posible_pero_no_a_costa_de_romper_el_contrato():
    """El mock propone ocultar cinco columnas; solo una debe aplicarse.

    Las otras cuatro dejarían el contrato inservible o no corresponden a nada: la
    clave primaria (sin ella no hay detalle), una obligatoria al crear (sin ella no
    hay alta), una inexistente y una sin motivo escrito.
    """
    sources = _sources()
    mapa = build_resource_map(sources)
    siniestros = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    propuesta = {
        "hidden_columns": [
            {"name": "monto", "reason": "Solo se consulta desde liquidaciones."},
            {"name": "siniestro_id", "reason": "Identificador interno."},
            {"name": "fecha_siniestro", "reason": "Ruido."},
            {"name": "columna_fantasma", "reason": "No sirve."},
            {"name": "estado_id", "reason": "   "},
        ],
        "summary_columns": ["fecha_siniestro"],
    }
    ocultas, resumen, notas = reconcile_exposure(siniestros, propuesta)

    assert ocultas == {"monto"}
    motivos = " ".join(n["reason"] for n in notas)
    assert "no se puede pedir el detalle" in motivos  # la PK
    assert "imposible el alta" in motivos  # la obligatoria
    assert "no es una columna del recurso" in motivos  # la inventada
    assert "no se explicó por qué" in motivos.lower()  # la que no se justificó
    assert len(notas) == 4


async def test_el_resumen_siempre_incluye_la_clave_aunque_no_la_pidan():
    sources = _sources()
    mapa = build_resource_map(sources)
    siniestros = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    _, resumen, _ = reconcile_exposure(
        siniestros, {"summary_columns": ["fecha_siniestro", "monto"]}
    )
    assert resumen[0] == "siniestro_id"


def test_un_resumen_demasiado_largo_se_recorta_declarandolo():
    sources = _sources()
    mapa = build_resource_map(sources)
    siniestros = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    todas = [c["name"] for c in siniestros["columns"]]
    _, resumen, notas = reconcile_exposure(siniestros, {"summary_columns": todas * 3})
    assert len(resumen) <= 6
    assert any("no es un resumen" in n["reason"] for n in notas)


def test_sin_propuesta_el_resumen_sale_determinista():
    """Un fallo del modelo no deja el listado sin columnas."""
    sources = _sources()
    mapa = build_resource_map(sources)
    siniestros = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    _, resumen, _ = reconcile_exposure(siniestros, None)
    assert resumen[0] == "siniestro_id"
    assert len(resumen) >= 2


# --- SCHEMAS: la forma de cada esquema ---------------------------------------


async def test_cada_operacion_tiene_el_esquema_que_necesita_y_ninguno_mas():
    _, _, endpoints, esquemas, _, _ = await _pipeline()
    por_recurso: dict[str, list[str]] = {}
    for esquema in esquemas:
        por_recurso.setdefault(esquema["resource_ref"], []).append(esquema["kind"])

    siniestros = next(
        e["resource_ref"] for e in endpoints if e["operation_id"] == "listarSiniestros"
    )
    # Tiene list/read_item/create/update/action → los cuatro esquemas + la entrada
    # de la acción, que el modelo declaró que necesita cuerpo.
    assert sorted(por_recurso[siniestros]) == [
        "action_input",
        "create",
        "list_item",
        "read",
        "update",
    ]
    # El catálogo solo se lista: no se le inventa un esquema de creación.
    catalogo = next(
        e["resource_ref"]
        for e in endpoints
        if e["operation_id"] == "listarSiniestroEstados"
    )
    assert por_recurso[catalogo] == ["list_item"]


async def test_la_creacion_no_pide_lo_que_genera_el_motor():
    _, _, _, esquemas, _, _ = await _pipeline()
    creacion = next(e for e in esquemas if e["kind"] == "create")
    campos = {f["name"] for f in creacion["fields"]}
    assert "siniestro_id" not in campos  # lo genera el motor
    assert "monto" not in campos  # el modelo lo ocultó, con motivo
    assert {"guia_id", "fecha_siniestro"} <= campos
    obligatorios = {f["name"] for f in creacion["fields"] if f["required"]}
    assert obligatorios == {"guia_id", "fecha_siniestro", "estado_id"}


async def test_la_actualizacion_es_parcial_asi_que_nada_es_obligatorio():
    """PATCH: se envía lo que cambia. Exigir campos convertiría el parche en reemplazo."""
    _, _, _, esquemas, _, _ = await _pipeline()
    actualizacion = next(e for e in esquemas if e["kind"] == "update")
    assert actualizacion["fields"]
    assert all(f["required"] is False for f in actualizacion["fields"])


async def test_el_detalle_expone_la_clave_como_solo_lectura():
    _, _, _, esquemas, _, _ = await _pipeline()
    lectura = next(e for e in esquemas if e["kind"] == "read")
    clave = next(f for f in lectura["fields"] if f["name"] == "siniestro_id")
    assert clave["read_only"] is True
    assert clave["required"] is True


async def test_todo_campo_conserva_su_columna_y_su_tipo():
    """La invariante del contrato, comprobada sobre lo que produce el pipeline."""
    _, _, _, esquemas, _, _ = await _pipeline()
    for esquema in esquemas:
        for field in esquema["fields"]:
            assert field["column_ref"], f"{esquema['name']}.{field['name']} sin columna"
            assert field["table_ref"]
            assert field["logical_type"]
            assert field["computed"] is False


def test_los_formatos_se_derivan_del_tipo_no_se_inventan():
    """El formato sale del `logical_type` que ya eligió el modelo de datos."""
    sources = _sources()
    mapa = build_resource_map(sources)
    siniestros = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    esquemas = build_resource_schemas(siniestros, set(), ["siniestro_id"], 0.8)

    lectura = next(e for e in esquemas if e["kind"] == "read")
    por_nombre = {f["name"]: f for f in lectura["fields"]}
    assert por_nombre["fecha_siniestro"]["format"] == "date"  # date
    assert por_nombre["monto"]["format"] == "decimal"  # decimal → cadena
    assert por_nombre["guia_id"]["format"] is None  # bigint no lleva formato


async def test_la_accion_declara_su_entrada_por_definir_en_vez_de_inventarla():
    """El EF describe la acción pero no qué datos lleva: el hueco se declara.

    Inventarle campos sería el error clásico del agente: un contrato que parece
    completo y que el Agente Backend implementaría tal cual.
    """
    _, _, endpoints, esquemas, _, _ = await _pipeline()
    entrada = next(e for e in esquemas if e["kind"] == "action_input")
    assert entrada["fields"] == []
    assert "Por definir" in entrada["description"]
    accion = next(e for e in endpoints if e["kind"] == "action")
    assert accion["request_schema_ref"] == entrada["id"]


async def test_los_endpoints_quedan_enlazados_con_sus_esquemas():
    _, _, endpoints, esquemas, _, _ = await _pipeline()
    por_id = {e["id"]: e for e in esquemas}
    por_op = {e["operation_id"]: e for e in endpoints}

    creacion = por_op["crearSiniestro"]
    assert por_id[creacion["request_schema_ref"]]["kind"] == "create"
    assert por_id[creacion["response_schema_ref"]]["kind"] == "read"

    listado = por_op["listarSiniestros"]
    assert listado["request_schema_ref"] is None
    assert por_id[listado["response_schema_ref"]]["kind"] == "list_item"

    detalle = por_op["obtenerSiniestro"]
    assert por_id[detalle["response_schema_ref"]]["kind"] == "read"


async def test_los_ids_de_esquemas_y_campos_son_estables():
    _, _, _, esquemas, _, _ = await _pipeline()
    assert [e["id"] for e in esquemas] == [
        f"SCH-{i:03d}" for i in range(1, len(esquemas) + 1)
    ]
    campos = [f["id"] for e in esquemas for f in e["fields"]]
    assert campos == [f"SF-{i:04d}" for i in range(1, len(campos) + 1)]


# --- ERRORS -------------------------------------------------------------------


async def test_el_409_existe_solo_donde_hay_una_restriccion_que_lo_provoque():
    """Un código copiado en todos los endpoints no informa de nada."""
    sources, mapa, endpoints, _, _, _ = await _pipeline()
    por_op = {e["operation_id"]: e for e in endpoints}

    # `guias` tiene una clave natural única (uq_guias_numero); `siniestros` no.
    creacion_siniestro = {s["code"] for s in por_op["crearSiniestro"]["status_codes"]}
    assert 409 not in creacion_siniestro

    recursos = {r["id"]: r for r in mapa["resources"]}
    tablas = {t["id"]: t for t in sources["bd"]["tables"]}
    guias = next(r for r in mapa["resources"].__iter__() if r["table_ref"] == "TBL-001")
    codigos, _ = status_codes_for(
        {"kind": "create", "id": "EP-X", "response_schema_ref": None},
        guias,
        tablas["TBL-001"],
        acotado=False,
    )
    assert 409 in {c["code"] for c in codigos}
    assert recursos  # el andamio sigue disponible para el resto de nodos


async def test_los_codigos_de_exito_siguen_la_semantica_http():
    _, _, endpoints, _, _, _ = await _pipeline()
    por_op = {e["operation_id"]: e for e in endpoints}
    assert por_op["crearSiniestro"]["status_codes"][0]["code"] == 201
    assert por_op["listarSiniestros"]["status_codes"][0]["code"] == 200
    assert por_op["obtenerSiniestro"]["status_codes"][0]["code"] == 200
    assert por_op["actualizarSiniestro"]["status_codes"][0]["code"] == 200


async def test_solo_las_operaciones_dirigidas_a_un_registro_declaran_404():
    _, _, endpoints, _, _, _ = await _pipeline()
    por_op = {e["operation_id"]: e for e in endpoints}
    assert 404 in {s["code"] for s in por_op["obtenerSiniestro"]["status_codes"]}
    assert 404 in {s["code"] for s in por_op["cerrarSiniestro"]["status_codes"]}
    # Un listado no puede "no encontrar": devuelve una página vacía.
    assert 404 not in {s["code"] for s in por_op["listarSiniestros"]["status_codes"]}


async def test_todo_endpoint_declara_401_403_y_500():
    _, _, endpoints, _, _, _ = await _pipeline()
    for endpoint in endpoints:
        codigos = {s["code"] for s in endpoint["status_codes"]}
        assert {401, 403, 500} <= codigos, endpoint["operation_id"]


async def test_el_404_cambia_de_significado_cuando_el_acceso_esta_acotado():
    """La razón por la que ERRORS corre DESPUÉS de AUTHORIZATION.

    Con alcance por filas, responder 403 diría "existe pero no puedes verlo", que
    revela justo lo que el alcance quería ocultar. Se responde 404 y se documenta.
    """
    sources, mapa, endpoints, _, _, _ = await _pipeline()
    detalle = next(e for e in endpoints if e["operation_id"] == "obtenerSiniestro")

    apply_errors(endpoints, mapa, sources, [])
    sin_alcance = next(s for s in detalle["status_codes"] if s["code"] == 404)[
        "description"
    ]

    apply_errors(
        endpoints,
        mapa,
        sources,
        [{"endpoint_ref": detalle["id"], "scope": "own_team"}],
    )
    con_alcance = next(s for s in detalle["status_codes"] if s["code"] == 404)[
        "description"
    ]

    assert "fuera del alcance" not in sin_alcance
    assert "fuera del alcance" in con_alcance
    assert "no revelar su existencia" in con_alcance


async def test_el_catalogo_solo_lista_lo_que_algun_endpoint_puede_devolver():
    _, _, _, _, catalogo, _ = await _pipeline()
    ids = {e["id"] for e in catalogo}
    assert {"ERR-401", "ERR-403", "ERR-404", "ERR-422", "ERR-500"} <= ids
    # Nadie declara 409 en este flujo (siniestros no tiene clave única): no aparece.
    assert "ERR-409" not in ids
    # Y va ordenado por estado, que es como se lee.
    assert [e["status"] for e in catalogo] == sorted(e["status"] for e in catalogo)


def test_el_catalogo_enlaza_el_error_con_la_restriccion_que_lo_causa():
    """Se puede ir del 409 a la clave única que lo provoca."""
    tablas = bd_example().model_dump(mode="json")["tables"]
    catalogo = build_error_catalog({"ERR-409", "ERR-422"}, tablas)
    conflicto = next(e for e in catalogo if e["id"] == "ERR-409")
    assert conflicto["source_refs"]  # los UQ- del modelo
    validacion = next(e for e in catalogo if e["id"] == "ERR-422")
    assert validacion["source_refs"]  # los CK- del modelo


# --- El grafo completo --------------------------------------------------------


async def test_el_grafo_produce_esquemas_y_codigos():
    graph = build_api_graph(build_memory_checkpointer())
    final = await graph.ainvoke(
        _base_state(), {"configurable": {"thread_id": "API-1", "llm": ApiMapLLM()}}
    )

    assert final["schemas"]
    assert final["error_catalog"]
    assert all(e["status_codes"] for e in final["endpoints"])
    assert all(
        e["response_schema_ref"] or e["response_kind"] == "none"
        for e in final["endpoints"]
    )
    # Las salvaguardas de exposición dejaron su rastro en las observaciones.
    motivos = " ".join(o["reason"] for o in final["map_observations"])
    assert "no se puede pedir el detalle" in motivos
    assert [s["stage"] for s in final["metrics"]["skipped"]] == ["resources"]
