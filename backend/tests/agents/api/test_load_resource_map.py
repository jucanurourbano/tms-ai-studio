"""Tests del grafo API con stubs, del gate, del estilo/seguridad y del andamio (API2).

Los insumos son los artefactos de ejemplo **reales** de BD, EF y Arquitectura, no
fixtures inventados: así los tests comprueban que el agente sabe leer lo que la
cadena produce de verdad.
"""

import pytest

from ai.agents.api.load_sources import (
    assert_bd_ready,
    extract_sources,
    resolve_api_style,
    resolve_auth,
    resolve_conventions,
    resolve_hashes,
)
from ai.agents.api.naming import (
    action_path,
    item_path,
    kebab,
    operation_id,
    resource_path_segment,
    resource_singular,
    schema_name,
)
from ai.agents.api.resource_map import (
    all_operations,
    build_resource_candidates,
    build_resource_map,
    plan_operations,
)
from ai.agents.arquitectura.schemas.examples import (
    example_artifact as arquitectura_example,
)
from ai.agents.bd.schemas.examples import example_artifact as bd_example
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from ai.errors import GateError
from ai.orchestrator import build_api_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from tests.mocks import ApiMapLLM


def _bd_dict():
    return bd_example().model_dump(mode="json")


def _ef_dict():
    return ef_example().model_dump(mode="json")


def _arq_dict():
    return arquitectura_example().model_dump(mode="json")


def _scrum_dict():
    return scrum_example().model_dump(mode="json")


def _sources(**overrides):
    sources = extract_sources(_bd_dict(), _ef_dict(), _arq_dict(), _scrum_dict())
    for key, value in overrides.items():
        sources[key] = value
    return sources


def _base_config():
    # Desde API3, `resources` y `endpoints` llaman al modelo: sin mock, el
    # cortafuegos autouse de conftest corta el test (REGLA DE PRESUPUESTO).
    return {"configurable": {"thread_id": "API-1", "llm": ApiMapLLM()}}


def _base_state(bd_ready: bool = True, **extra):
    state = {
        "job_id": "API-1",
        "bd_job_id": "BD-1",
        "bd_artifact": _bd_dict(),
        "bd_artifact_hash": "bd123",
        "bd_ready": bd_ready,
        "architecture_job_id": "AR-1",
        "architecture_artifact": _arq_dict(),
        "architecture_artifact_hash": "ar123",
        "scrum_job_id": "SC-1",
        "scrum_artifact": _scrum_dict(),
        "scrum_artifact_hash": "sc123",
        "ef_job_id": "EF-1",
        "ef_artifact": _ef_dict(),
        "ef_artifact_hash": "ef123",
    }
    state.update(extra)
    return state


# --- Gate de entrada --------------------------------------------------------


def test_assert_bd_ready_explica_como_desbloquear():
    with pytest.raises(GateError) as exc:
        assert_bd_ready(False, "BD-9")
    mensaje = str(exc.value)
    assert "BD-9" in mensaje
    assert "refine" in mensaje  # dice qué hacer, no solo que falló


async def test_gate_bloquea_modelo_de_datos_no_listo():
    graph = build_api_graph(build_memory_checkpointer())
    with pytest.raises(GateError):
        await graph.ainvoke(_base_state(bd_ready=False), _base_config())


# --- Contexto consolidado ---------------------------------------------------


def test_extract_sources_expone_la_materia_prima():
    sources = _sources()
    # Del modelo de datos: las tablas con todo lo que hará falta para tipar.
    assert [t["id"] for t in sources["bd"]["tables"]] == [
        "TBL-001",
        "TBL-002",
        "TBL-003",
    ]
    # Y el destino que el Agente BD dio a cada regla: es lo que esta API recoge.
    assert sources["bd"]["rule_mappings"]
    # Del EF: actores, matriz CRUD y APIs declaradas.
    assert [a["id"] for a in sources["ef"]["actors"]] == ["ACT-001"]
    assert [c["id"] for c in sources["ef"]["crud"]] == ["CRUD-001"]
    assert [a["id"] for a in sources["ef"]["apis"]] == ["API-001"]
    # De Arquitectura: los componentes que agrupan los recursos.
    assert [c["id"] for c in sources["architecture"]["components"]][:2] == [
        "CMP-001",
        "CMP-002",
    ]
    # El Scrum solo completa la trazabilidad de la cadena.
    assert set(sources["scrum"]) == {"epics"}


def test_los_hashes_lejanos_se_heredan_del_artefacto_de_bd():
    """Los cuatro artefactos de un flujo declaran los mismos hashes de origen."""
    bd = _bd_dict()
    hashes = resolve_hashes("bd123", "", None, bd)
    assert hashes["bd"] == "bd123"
    assert hashes["ef"] == bd["source"]["ef_artifact_hash"]
    assert hashes["architecture"] == bd["source"]["architecture_artifact_hash"]
    assert hashes["scrum"] == bd["source"]["scrum_artifact_hash"]


# --- Estilo de API ----------------------------------------------------------


def test_estilo_por_defecto_cuando_la_arquitectura_no_decide():
    """El ejemplo de Arquitectura no fija `api_style`: se usa el default y se avisa."""
    resuelto = resolve_api_style(_sources())
    assert resuelto["style"] == "rest"
    assert resuelto["decided"] is False  # nadie lo decidió: habrá pregunta
    assert "no decidió" in resuelto["reason"]


def test_estilo_decidido_por_la_arquitectura():
    sources = _sources()
    sources["architecture"]["stack"] = [
        {"id": "STK-009", "layer": "api_style", "technology": "REST"}
    ]
    resuelto = resolve_api_style(sources)
    assert resuelto["style"] == "rest"
    assert resuelto["decided"] is True
    assert resuelto["supported"] is True
    assert resuelto["source_ref"] == "STK-009"


def test_un_estilo_que_no_sabemos_especificar_se_declara_en_vez_de_fingirse():
    """Si la arquitectura pidió GraphQL, el artefacto lo dice.

    Entregar un documento REST diciendo que se cumplió lo pedido sería el peor
    final posible: nadie notaría el desajuste hasta construirlo.
    """
    sources = _sources()
    sources["architecture"]["stack"] = [
        {"id": "STK-010", "layer": "api_style", "technology": "GraphQL"}
    ]
    resuelto = resolve_api_style(sources)
    assert resuelto["style"] == "graphql"
    assert resuelto["decided"] is True
    assert resuelto["supported"] is False  # → pregunta bloqueante en API7


def test_un_estilo_fuera_del_allow_list_en_la_peticion_se_rechaza():
    with pytest.raises(GateError, match="allow-list"):
        resolve_api_style(_sources(), "carta-a-los-reyes")


# --- Esquema de seguridad ---------------------------------------------------


def test_seguridad_por_defecto_cuando_la_arquitectura_no_decide():
    resuelto = resolve_auth(_sources())
    assert resuelto["decided"] is False
    assert resuelto["scheme"]  # nunca queda sin esquema: se usa el de la casa
    assert "no decidió" in resuelto["reason"]


def test_el_proveedor_del_stack_fija_el_esquema():
    sources = _sources()
    sources["architecture"]["stack"] = [
        {"id": "STK-011", "layer": "auth", "technology": "Keycloak"}
    ]
    resuelto = resolve_auth(sources)
    assert resuelto["decided"] is True
    assert resuelto["provider"] == "Keycloak"
    assert resuelto["scheme"] == "oauth2_oidc"
    assert resuelto["source_ref"] == "STK-011"


def test_las_convenciones_efectivas_reflejan_lo_acordado():
    conv = resolve_conventions()
    assert conv["path_language"] == "es"
    assert conv["property_case"] == "snake_case"
    assert conv["envelope"] == "api_response"
    assert conv["update_verb"] == "PATCH"
    assert conv["pagination"]["limit_param"] == "limit"


# --- Nomenclatura -----------------------------------------------------------


def test_el_segmento_de_ruta_es_la_tabla_en_kebab():
    assert resource_path_segment("siniestros") == "siniestros"
    assert resource_path_segment("siniestro_estados") == "siniestro-estados"
    # No se re-pluraliza lo que ya viene en plural del modelo de datos.
    assert resource_path_segment("guias") == "guias"


def test_el_singular_del_recurso():
    assert resource_singular("siniestros") == "siniestro"
    assert resource_singular("siniestro_estados") == "siniestro-estado"


def test_el_parametro_de_ruta_es_la_columna_pk_tal_cual():
    """La ruta, el esquema y la columna usan la misma palabra."""
    assert item_path("/api/v1", "siniestros", "siniestro_id") == (
        "/api/v1/siniestros/{siniestro_id}"
    )


def test_las_acciones_van_en_infinitivo_y_en_espanol():
    assert action_path("/api/v1", "siniestros", "siniestro_id", "cerrar") == (
        "/api/v1/siniestros/{siniestro_id}/cerrar"
    )


def test_operation_id_y_schema_name_siguen_las_convenciones():
    assert operation_id("list", "siniestros") == "listarSiniestros"
    assert operation_id("read_item", "siniestros") == "obtenerSiniestro"
    assert operation_id("create", "siniestro_estados") == "crearSiniestroEstado"
    assert schema_name("create", "siniestros") == "SiniestroCreate"
    assert schema_name("read", "siniestros") == "Siniestro"
    assert kebab("Número de Guía") == "numero-de-guia"


# --- Andamio: qué recursos existen ------------------------------------------


def test_hay_un_recurso_por_tabla_y_ni_uno_mas():
    """El cortafuegos: los recursos salen del modelo de datos, no de una idea."""
    recursos = build_resource_candidates(_sources())
    assert [r["table_ref"] for r in recursos] == ["TBL-001", "TBL-002", "TBL-003"]
    assert [r["id"] for r in recursos] == ["RES-001", "RES-002", "RES-003"]
    assert [r["segment"] for r in recursos] == [
        "guias",
        "siniestros",
        "siniestro-estados",
    ]


def test_la_exposicion_sale_de_la_naturaleza_de_la_tabla():
    recursos = {r["table_ref"]: r for r in build_resource_candidates(_sources())}
    assert recursos["TBL-002"]["exposure"] == "crud"  # entidad
    catalogo = recursos["TBL-003"]
    assert catalogo["exposure"] == "read_only"
    assert catalogo["exposure_reason"]  # nunca una exclusión muda


def test_el_recurso_se_agrupa_por_el_componente_de_arquitectura():
    """Es lo que dará los `tags` del documento: la API se lee por módulo."""
    recursos = {r["table_ref"]: r for r in build_resource_candidates(_sources())}
    assert recursos["TBL-002"]["component_ref"] == "CMP-001"  # Módulo Siniestros
    assert recursos["TBL-001"]["component_ref"] == "CMP-002"  # Módulo Guías


def test_las_columnas_llegan_con_lo_que_ya_se_sabe_de_ellas():
    recursos = {r["table_ref"]: r for r in build_resource_candidates(_sources())}
    columnas = {c["name"]: c for c in recursos["TBL-002"]["columns"]}
    # La PK la genera el motor: el cliente no la envía nunca.
    assert columnas["siniestro_id"]["read_only"] is True
    assert columnas["siniestro_id"]["required"] is False
    # Un NOT NULL sin default sí es obligatorio al crear.
    assert columnas["fecha_siniestro"]["required"] is True
    assert columnas["monto"]["nullable"] is True
    # Y toda columna trae su ref: es lo que hará imposible inventar un campo.
    assert all(c["column_ref"] for c in recursos["TBL-002"]["columns"])


def test_solo_se_filtra_por_columnas_indexadas():
    """Regla dura: un filtro sin índice es un recorrido de tabla en producción."""
    recursos = {r["table_ref"]: r for r in build_resource_candidates(_sources())}
    filtrables = recursos["TBL-002"]["filterable"]
    assert "estado_id" in filtrables  # participa del índice del modelo
    assert "fecha_siniestro" in filtrables  # idem
    assert "monto" not in filtrables  # sin índice: no se ofrece


# --- Andamio: qué operaciones existen ---------------------------------------


def test_las_operaciones_salen_de_la_matriz_crud():
    """CRUD-001 concede create/read/update sobre ENT-001, pero NO delete."""
    mapa = build_resource_map(_sources())
    siniestros = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    tipos = [op["kind"] for op in siniestros["operations"]]
    assert tipos == ["list", "read_item", "create", "update"]
    assert "delete" not in tipos  # nadie lo autorizó: no se inventa
    assert all(op["actor_refs"] == ["ACT-001"] for op in siniestros["operations"])


def test_sin_celda_crud_no_hay_endpoints_y_se_reporta():
    """La consecuencia incómoda de no inventar, y es deliberada.

    ENT-002 (guías) no tiene celda en la matriz CRUD del EF de ejemplo, así que su
    recurso se queda sin operaciones y el andamio lo enumera para que acabe en una
    pregunta. Rellenar el hueco con un CRUD completo sería inventarle un dueño.
    """
    mapa = build_resource_map(_sources())
    guias = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-001")
    assert guias["operations"] == []
    assert guias["id"] in mapa["resources_without_operations"]


def test_el_catalogo_obtiene_listado_y_la_excepcion_queda_registrada():
    mapa = build_resource_map(_sources())
    catalogo = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-003")
    assert [op["kind"] for op in catalogo["operations"]] == ["list"]
    assert catalogo["operations"][0]["basis"] == "inferred"
    assert catalogo["operations"][0]["actor_refs"] == []  # nacerá denegado
    assert any("catálogo" in o["description"].lower() for o in mapa["observations"])


def test_la_api_declarada_por_el_ef_se_reconoce_en_vez_de_duplicarse():
    """API-001 es POST /api/v1/siniestros: coincide con la creación ya planificada.

    Marcarla en vez de añadir una segunda operación es lo que permite que el
    artefacto diga `origin=stated`: lo que el analista ya pidió no se presenta
    después como una idea del agente.
    """
    mapa = build_resource_map(_sources())
    siniestros = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    creaciones = [op for op in siniestros["operations"] if op["kind"] == "create"]
    assert len(creaciones) == 1
    assert creaciones[0]["ef_api_ref"] == "API-001"
    assert "API-001" in creaciones[0]["source_refs"]


def test_una_api_del_ef_sin_respaldo_en_la_matriz_nace_sin_actores():
    """El EF es fuente legítima, pero no concede permisos por sí solo."""
    sources = _sources()
    sources["ef"]["apis"] = sources["ef"]["apis"] + [
        {
            "id": "API-009",
            "method": "DELETE",
            "path": "/api/v1/siniestros/{siniestro_id}",
            "entity_ref": "ENT-001",
        }
    ]
    mapa = build_resource_map(sources)
    siniestros = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    borrado = next(op for op in siniestros["operations"] if op["kind"] == "delete")
    assert borrado["ef_api_ref"] == "API-009"
    assert borrado["basis"] == "ef_api"
    assert borrado["actor_refs"] == []  # denegado hasta que alguien lo confirme
    assert any("API-009" in o["description"] for o in mapa["observations"])


def test_una_api_del_ef_sin_tabla_se_reporta_como_huerfana():
    sources = _sources()
    sources["ef"]["apis"] = [
        {
            "id": "API-020",
            "method": "GET",
            "path": "/api/v1/inventos",
            "entity_ref": "ENT-999",
        }
    ]
    mapa = build_resource_map(sources)
    assert [h["api_ref"] for h in mapa["orphan_ef_apis"]] == ["API-020"]


def test_una_celda_crud_sin_tabla_se_reporta():
    sources = _sources()
    sources["ef"]["crud"] = sources["ef"]["crud"] + [
        {
            "id": "CRUD-099",
            "entity_ref": "ENT-777",
            "actor_ref": "ACT-001",
            "read": True,
        }
    ]
    mapa = build_resource_map(sources)
    assert [c["crud_ref"] for c in mapa["orphan_crud"]] == ["CRUD-099"]


def test_las_rutas_del_andamio_respetan_las_convenciones():
    mapa = build_resource_map(_sources())
    for operacion in all_operations(mapa):
        assert operacion["path"].startswith("/api/v1/")
        segmento = operacion["path"].split("/")[3]
        assert "_" not in segmento  # kebab-case en la ruta
    ids = [op["operation_id"] for op in all_operations(mapa)]
    assert len(ids) == len(set(ids))  # únicos: los consumen los generadores


def test_no_hay_colisiones_de_metodo_y_ruta():
    mapa = build_resource_map(_sources())
    claves = [(op["method"], op["path"]) for op in all_operations(mapa)]
    assert len(claves) == len(set(claves))


def test_un_segmento_reservado_se_reporta():
    """Un recurso llamado `health` chocaría con la ruta del propio servicio."""
    sources = _sources()
    tablas = sources["bd"]["tables"]
    tablas[0] = {**tablas[0], "name": "health"}
    mapa = build_resource_map(sources)
    assert any("reservado" in o["description"] for o in mapa["observations"])


def test_una_tabla_puente_no_es_un_recurso_de_primer_nivel():
    """Su identificador no significa nada para el negocio: cuelga de su padre."""
    sources = _sources()
    sources["bd"]["tables"] = sources["bd"]["tables"] + [
        {
            "id": "TBL-004",
            "name": "guia_siniestros",
            "kind": "junction",
            "columns": [
                {"id": "COL-0020", "name": "guia_id", "logical_type": "bigint"},
                {"id": "COL-0021", "name": "siniestro_id", "logical_type": "bigint"},
            ],
            "primary_key": {"name": "pk", "columns": ["guia_id", "siniestro_id"]},
            "foreign_keys": [
                {
                    "id": "FK-010",
                    "name": "fk_guia",
                    "columns": ["guia_id"],
                    "references_table": "guias",
                    "references_columns": ["guia_id"],
                }
            ],
        }
    ]
    mapa = build_resource_map(sources)
    puente = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-004")
    assert puente["exposure"] == "nested_only"
    assert puente["exposure_reason"]
    assert puente["parent_resource_ref"] == "RES-001"  # guias
    assert puente["addressable"] is False  # PK compuesta: no hay ruta de detalle


def _sources_con_puente(**crud_del_padre):
    """Fuentes con una tabla puente guias↔siniestros y permisos sobre el padre."""
    sources = _sources()
    sources["bd"]["tables"] = sources["bd"]["tables"] + [
        {
            "id": "TBL-004",
            "name": "guia_siniestros",
            "kind": "junction",
            "columns": [
                {"id": "COL-0020", "name": "guia_id", "logical_type": "bigint"},
                {"id": "COL-0021", "name": "siniestro_id", "logical_type": "bigint"},
            ],
            "primary_key": {"name": "pk", "columns": ["guia_id", "siniestro_id"]},
            "foreign_keys": [
                {
                    "id": "FK-010",
                    "name": "fk_guia",
                    "columns": ["guia_id"],
                    "references_table": "guias",
                    "references_columns": ["guia_id"],
                }
            ],
        }
    ]
    sources["ef"]["crud"] = sources["ef"]["crud"] + [
        {
            "id": "CRUD-002",
            "entity_ref": "ENT-002",
            "actor_ref": "ACT-001",
            **crud_del_padre,
        }
    ]
    return sources


def test_la_tabla_puente_hereda_los_permisos_de_su_padre():
    """Quien puede leer una guía ve con qué está relacionada; quien la edita, enlaza.

    No se inventa un actor propio para la tabla puente: el EF nunca habla de ella.
    """
    mapa = build_resource_map(_sources_con_puente(read=True, update=True))
    puente = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-004")
    tipos = [op["kind"] for op in puente["operations"]]
    assert tipos == ["nested_list", "nested_create", "nested_delete"]
    assert all(op["actor_refs"] == ["ACT-001"] for op in puente["operations"])

    rutas = {op["kind"]: op["path"] for op in puente["operations"]}
    assert rutas["nested_list"] == "/api/v1/guias/{guia_id}/guia-siniestros"
    # Para desenlazar hace falta la clave del OTRO extremo, no la del padre.
    assert rutas["nested_delete"] == (
        "/api/v1/guias/{guia_id}/guia-siniestros/{siniestro_id}"
    )


def test_sin_permiso_de_edicion_en_el_padre_no_se_puede_enlazar():
    mapa = build_resource_map(_sources_con_puente(read=True))
    puente = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-004")
    assert [op["kind"] for op in puente["operations"]] == ["nested_list"]


# --- El grafo corre de extremo a extremo ------------------------------------


async def test_el_grafo_corre_completo_con_los_stubs():
    """El pipeline entero es recorrible; lo que aún no existe devuelve vacío."""
    graph = build_api_graph(build_memory_checkpointer())
    final = await graph.ainvoke(_base_state(), _base_config())

    assert final["status"] == "COMPLETED"
    assert final["target"]["api_style"] == "rest"
    assert final["target"]["base_path"] == "/api/v1"
    assert final["target"]["conventions"]["property_case"] == "snake_case"
    assert final["target"]["conventions_source"].endswith("api_conventions.yaml@v0")
    # El andamio está construido y sus exclusiones viajan hacia el artefacto.
    assert len(final["resource_map"]["resources"]) == 3
    assert final["map_observations"]
    # Y el único stub que queda sigue vacío: API8 lo sustituye.
    assert final["artifact"] == {}


async def test_el_orden_del_pipeline_pone_errors_despues_de_authorization():
    """ERRORS necesita saber si hay algo que pueda denegar para estampar el 403."""
    from ai.orchestrator.api_graph import _NODES

    nombres = [nombre for nombre, _ in _NODES]
    assert nombres.index("authorization") < nombres.index("errors")
    assert nombres.index("errors") < nombres.index("openapi_gen")
    assert nombres.index("resource_map") < nombres.index("resources")
    assert nombres[0] == "load_sources"
    assert nombres[-1] == "persist"


def test_plan_operations_no_toca_lo_que_no_se_expone():
    recursos = build_resource_candidates(_sources())
    catalogo = next(r for r in recursos if r["table_ref"] == "TBL-003")
    oculto = {**catalogo, "exposure": "none"}
    operaciones, _ = plan_operations(oculto, [], "/api/v1")
    assert operaciones == []
