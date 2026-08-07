"""Tests de RESOURCES y ENDPOINTS (API3), con el LLM mockeado.

Lo que de verdad se prueba aquí no es que el agente sepa escribir endpoints —eso lo
hace el andamio determinista de API2— sino que sepa **rechazar** lo que el modelo
propone sin base. La puerta que más importa es la de la evidencia: una acción cuya
cita no aparece literalmente en el EF se descarta entera.
"""

from ai.agents.api.endpoints import (
    build_endpoints,
    build_evidence_index,
    merge_actions,
    reconcile_actions,
    run_actions,
)
from ai.agents.api.load_sources import extract_sources, resolve_conventions
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


def _base_state(**extra):
    state = {
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
    state.update(extra)
    return state


def _config():
    return {"configurable": {"thread_id": "API-1", "llm": ApiMapLLM()}}


# --- RESOURCES ---------------------------------------------------------------


async def test_resources_redacta_sin_poder_cambiar_lo_decidido():
    mapa = build_resource_map(_sources())
    recursos, _, _, _ = await run_resources(ApiMapLLM(), mapa, _sources())

    por_tabla = {r["table_ref"]: r for r in recursos}
    siniestros = por_tabla["TBL-002"]
    assert siniestros["display_name"] == "Siniestros"
    assert siniestros["description"]
    # Lo que decide algo sigue viniendo del andamio, no del modelo.
    assert siniestros["name"] == "siniestros"
    assert siniestros["exposure"] == "crud"
    assert siniestros["component_ref"] == "CMP-001"
    assert siniestros["table_ref"] == "TBL-002"


async def test_un_fallo_de_redaccion_no_pierde_el_recurso():
    """El mock responde basura para el catálogo: debe sobrevivir igualmente.

    Perder un recurso porque el modelo no supo describirlo sería absurdo: la
    descripción es lo accesorio, el recurso es el contrato.
    """
    mapa = build_resource_map(_sources())
    recursos, skipped, _, observaciones = await run_resources(
        ApiMapLLM(), mapa, _sources()
    )

    catalogo = next(r for r in recursos if r["table_ref"] == "TBL-003")
    assert catalogo["id"]  # el recurso está
    assert catalogo["display_name"]  # con nombre determinista
    assert catalogo["description"]  # y la descripción de la tabla
    # Pero el fallo queda registrado en cuarentena y como observación.
    assert [s["ref"] for s in skipped] == [catalogo["id"]]
    assert any("modelo de datos" in o["description"] for o in observaciones)


# --- Evidencia: la puerta que importa ----------------------------------------


def test_el_indice_de_evidencia_cubre_procesos_reglas_y_validaciones():
    indice = build_evidence_index(_sources())
    assert "PRO-001" in indice and "BR-001" in indice and "VAL-001" in indice
    # El texto se normaliza para comparar: sin acentos ni puntuación.
    assert "hasta el cierre del siniestro" in indice["PRO-001"]


async def test_de_cuatro_acciones_propuestas_solo_sobrevive_la_que_prueba_lo_que_dice():
    """El corazón de API3.

    El mock propone cuatro acciones sobre siniestros. Tres deben caer: una cita una
    frase que no está en el EF, otra un proceso inventado y la tercera repite una
    ruta ya ocupada. Ninguna cae en silencio.
    """
    sources = _sources()
    mapa = build_resource_map(sources)
    acciones, _, _, observaciones = await run_actions(ApiMapLLM(), mapa, sources)

    siniestros = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    aceptadas = acciones.get(siniestros["id"], [])
    assert [a["path"] for a in aceptadas] == [
        "/api/v1/siniestros/{siniestro_id}/cerrar"
    ]
    assert aceptadas[0]["operation_id"] == "cerrarSiniestro"
    assert aceptadas[0]["rule_refs"] == ["PRO-001"]
    assert aceptadas[0]["actor_refs"] == []  # nace denegada: la autoriza API5

    motivos = " ".join(o["reason"] for o in observaciones)
    assert "no aparece literalmente" in motivos  # la paráfrasis convincente
    assert "no existen en el EF" in motivos  # el ref inventado
    assert "ya está ocupada" in motivos  # la ruta duplicada
    assert len([o for o in observaciones if "descartada" in o["description"]]) == 3


def test_una_parafrasis_convincente_no_pasa_la_puerta():
    """Un modelo puede parafrasear con aplomo; no puede hacer aparecer una frase."""
    sources = _sources()
    mapa = build_resource_map(sources)
    recurso = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    propuesta = [
        {
            "action": "cerrar",
            "purpose": "Cierra el siniestro.",
            "evidence": "el proceso contempla el cierre automático del siniestro",
            "source_refs": ["PRO-001"],
        }
    ]
    aceptadas, notas = reconcile_actions(
        recurso, propuesta, build_evidence_index(sources), set(), "/api/v1"
    )
    assert aceptadas == []
    assert "no aparece literalmente" in notas[0]["reason"]


def test_la_cita_tolera_puntuacion_y_acentos_pero_no_otras_palabras():
    """Se comparan las palabras, no los signos: ni exigente de más ni de menos."""
    sources = _sources()
    mapa = build_resource_map(sources)
    recurso = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-002")
    indice = build_evidence_index(sources)

    con_ruido = [
        {
            "action": "cerrar",
            "purpose": "…",
            "evidence": "HASTA el cierre, del siniestro!",
            "source_refs": ["PRO-001"],
        }
    ]
    aceptadas, _ = reconcile_actions(recurso, con_ruido, indice, set(), "/api/v1")
    assert len(aceptadas) == 1


def test_una_accion_sobre_un_catalogo_no_se_acepta():
    sources = _sources()
    mapa = build_resource_map(sources)
    catalogo = next(r for r in mapa["resources"] if r["table_ref"] == "TBL-003")
    propuesta = [
        {
            "action": "cerrar",
            "purpose": "…",
            "evidence": "hasta el cierre del siniestro",
            "source_refs": ["PRO-001"],
        }
    ]
    aceptadas, notas = reconcile_actions(
        catalogo, propuesta, build_evidence_index(sources), set(), "/api/v1"
    )
    assert aceptadas == []
    assert "no se expone con escritura" in notas[0]["reason"]


# --- Endpoints deterministas --------------------------------------------------


async def _endpoints():
    sources = _sources()
    mapa = build_resource_map(sources)
    recursos, _, _, _ = await run_resources(ApiMapLLM(), mapa, sources)
    acciones, _, _, _ = await run_actions(ApiMapLLM(), mapa, sources)
    merge_actions(mapa, acciones)
    return build_endpoints(mapa, recursos, resolve_conventions())


async def test_los_endpoints_salen_del_andamio_mas_la_accion_aceptada():
    endpoints = await _endpoints()
    assert [(e["method"], e["path"]) for e in endpoints] == [
        ("GET", "/api/v1/siniestros"),
        ("GET", "/api/v1/siniestros/{siniestro_id}"),
        ("POST", "/api/v1/siniestros"),
        ("PATCH", "/api/v1/siniestros/{siniestro_id}"),
        ("POST", "/api/v1/siniestros/{siniestro_id}/cerrar"),
        ("GET", "/api/v1/siniestro-estados"),
    ]
    assert [e["id"] for e in endpoints] == [f"EP-{i:03d}" for i in range(1, 7)]


async def test_lo_que_el_ef_ya_pedia_nace_stated():
    endpoints = await _endpoints()
    creacion = next(e for e in endpoints if e["kind"] == "create")
    assert creacion["ef_api_ref"] == "API-001"
    assert creacion["origin"] == "stated"
    # Y lo demás se declara derivado, sin apropiarse de nada.
    assert all(e["origin"] == "derived" for e in endpoints if not e["ef_api_ref"])


async def test_los_parametros_de_ruta_se_derivan_de_la_propia_ruta():
    """Así es imposible que la ruta declare un parámetro que la operación no documenta."""
    endpoints = await _endpoints()
    detalle = next(e for e in endpoints if e["kind"] == "read_item")
    parametros = [p for p in detalle["parameters"] if p["location"] == "path"]
    assert [p["name"] for p in parametros] == ["siniestro_id"]
    assert parametros[0]["required"] is True
    assert parametros[0]["logical_type"] == "bigint"
    assert parametros[0]["column_ref"] == "COL-0003"


async def test_los_listados_llevan_paginacion_orden_y_solo_filtros_indexados():
    endpoints = await _endpoints()
    listado = next(
        e for e in endpoints if e["kind"] == "list" and e["path"].endswith("siniestros")
    )
    consulta = {p["name"]: p for p in listado["parameters"] if p["location"] == "query"}
    assert "limit" in consulta and "offset" in consulta and "sort" in consulta
    assert consulta["limit"]["logical_type"] == "integer"
    # Filtros: columnas indexadas, nunca la PK (que ya tiene su ruta de detalle).
    assert "estado_id" in consulta
    assert "siniestro_id" not in consulta
    assert "monto" not in consulta  # sin índice
    assert listado["response_kind"] == "page"
    assert listado["paginated"] is True


async def test_el_detalle_y_la_accion_no_llevan_paginacion():
    endpoints = await _endpoints()
    for endpoint in endpoints:
        if endpoint["kind"] in ("read_item", "action", "create", "update"):
            assert endpoint["paginated"] is False
            assert endpoint["filters"] == []
            assert not [p for p in endpoint["parameters"] if p["name"] == "limit"]


async def test_los_propositos_no_inventan_genero():
    """En infinitivo y sin artículos: un «el/la» equivocado se repite en cada ruta."""
    endpoints = await _endpoints()
    propositos = {
        e["kind"]: e["purpose"]
        for e in endpoints
        if "siniestro-estados" not in e["path"]
    }
    assert propositos["list"] == "Listar siniestros."
    assert propositos["read_item"] == "Obtener siniestro por su identificador."
    assert propositos["create"] == "Registrar siniestro."
    assert propositos["update"] == "Actualizar parcialmente siniestro."
    # La acción trae su propósito del modelo, que sí sabe de qué habla.
    assert propositos["action"] == "Cierra el siniestro tras la recuperación."

    # El catálogo cayó en cuarentena al redactarse, así que su propósito usa el
    # nombre determinista. Sigue siendo legible: el fallback no deja un hueco.
    catalogo = next(e for e in endpoints if "siniestro-estados" in e["path"])
    assert catalogo["purpose"] == "Listar siniestro estados."


async def test_lo_que_resuelven_los_bloques_siguientes_queda_vacio():
    """El endpoint nace sin esquemas, sin códigos y **sin autorización**.

    Los esquemas los enlaza SCHEMAS y los códigos los estampa ERRORS; aquí se
    comprueba que ENDPOINTS no se los inventa por su cuenta.
    """
    endpoints = await _endpoints()
    for endpoint in endpoints:
        assert endpoint["request_schema_ref"] is None
        assert endpoint["response_schema_ref"] is None
        assert endpoint["status_codes"] == []
        assert endpoint["auth_rule_refs"] == []


# --- El grafo completo --------------------------------------------------------


async def test_el_grafo_produce_recursos_y_endpoints():
    graph = build_api_graph(build_memory_checkpointer())
    final = await graph.ainvoke(_base_state(), _config())

    assert len(final["resources"]) == 3
    assert len(final["endpoints"]) == 6
    # Las observaciones del andamio y las de los nodos LLM se acumulan, no se pisan.
    motivos = " ".join(o["reason"] for o in final["map_observations"])
    assert "no aparece literalmente" in motivos
    assert "catálogo" in " ".join(
        o["description"].lower() for o in final["map_observations"]
    )
    # Y las métricas acumulan tokens de los dos nodos que llamaron al modelo.
    assert final["metrics"]["tokens"]["total"] > 0
    assert [s["stage"] for s in final["metrics"]["skipped"]] == ["resources"]
