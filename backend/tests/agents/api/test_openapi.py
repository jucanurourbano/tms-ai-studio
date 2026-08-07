"""Tests de OPENAPI_GEN y VALIDATE (API6).

Aquí el documento deja de ser una referencia escrita a mano y pasa a ser la salida
real del agente. Se comprueban tres cosas distintas:

1. Que el render sea **determinista** y respete 3.1 (la nulabilidad en el `type`,
   el envelope de la casa, el orden estable).
2. Que la validación **encuentre** los defectos que L2 no puede ver por sí sola.
3. Que un runtime real (`openapi-core`, capa L3a) sepa **usar** el documento, no
   solo parsearlo.
"""

import json

import yaml
from openapi_spec_validator import OpenAPIV31SpecValidator

from ai.agents.api.authorization import run_authorization
from ai.agents.api.endpoints import build_endpoints, merge_actions, run_actions
from ai.agents.api.errors import apply_errors
from ai.agents.api.load_sources import (
    base_path,
    extract_sources,
    resolve_auth,
    resolve_conventions,
)
from ai.agents.api.openapi.render import (
    _property,
    build_document,
    build_openapi,
    to_yaml,
)
from ai.agents.api.openapi.smoke import check_runtime, sample_payload
from ai.agents.api.openapi.validate import (
    check_round_trip,
    check_spec,
    check_structure,
    validate_spec,
)
from ai.agents.api.payloads import run_schemas
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


def _target():
    auth = resolve_auth(_sources())
    return {
        "api_style": "rest",
        "spec_version": "3.1.0",
        "base_path": base_path(),
        "auth": auth,
        "conventions": resolve_conventions(),
    }


async def _contrato():
    """Recorre el pipeline hasta tener todas las piezas del documento."""
    sources = _sources()
    mapa = build_resource_map(sources)
    recursos, _, _, _ = await run_resources(ApiMapLLM(), mapa, sources)
    acciones, _, _, _ = await run_actions(ApiMapLLM(), mapa, sources)
    merge_actions(mapa, acciones)
    endpoints = build_endpoints(mapa, recursos, resolve_conventions())
    esquemas, _, _, _ = await run_schemas(ApiMapLLM(), mapa, endpoints)
    matriz, _, _, _ = await run_authorization(ApiMapLLM(), endpoints, mapa, sources)
    catalogo = apply_errors(endpoints, mapa, sources, matriz)
    _, delegadas, _, _, _ = await run_rule_mapping(
        ApiMapLLM(), endpoints, esquemas, matriz, sources
    )
    documento, bloque = build_openapi(
        _target(), recursos, esquemas, endpoints, catalogo, sources
    )
    return {
        "sources": sources,
        "mapa": mapa,
        "recursos": recursos,
        "endpoints": endpoints,
        "schemas": esquemas,
        "matriz": matriz,
        "catalogo": catalogo,
        "delegadas": delegadas,
        "documento": documento,
        "bloque": bloque,
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


# --- El documento generado es válido -----------------------------------------


async def test_el_documento_generado_valida_como_openapi_31():
    """La prueba que justifica todo el bloque."""
    datos = await _contrato()
    assert list(OpenAPIV31SpecValidator(datos["documento"]).iter_errors()) == []
    assert datos["documento"]["openapi"] == "3.1.0"


async def test_el_render_es_reproducible_byte_a_byte():
    """Mismo contrato ⇒ mismo YAML: un diff muestra cambios reales, no ruido."""
    datos = await _contrato()
    otra_vez = to_yaml(
        build_document(
            _target(),
            datos["recursos"],
            datos["schemas"],
            datos["endpoints"],
            datos["catalogo"],
            datos["sources"],
        )
    )
    assert otra_vez == datos["bloque"]["content"]
    assert datos["bloque"]["checksum"].startswith("sha256:")
    assert datos["bloque"]["byte_size"] == len(datos["bloque"]["content"].encode())


async def test_todas_las_operaciones_del_contrato_llegan_al_documento():
    datos = await _contrato()
    del_documento = {
        (metodo.upper(), ruta)
        for ruta, ops in datos["documento"]["paths"].items()
        for metodo in ops
    }
    assert del_documento == {(e["method"], e["path"]) for e in datos["endpoints"]}
    assert datos["bloque"]["operations_total"] == len(datos["endpoints"])


async def test_el_envelope_de_la_casa_lo_pone_el_renderizador():
    """El modelo ni lo ve: no puede olvidarlo en un endpoint ni cambiarlo."""
    datos = await _contrato()
    esquemas = datos["documento"]["components"]["schemas"]
    envoltorios = [n for n in esquemas if n.startswith("ApiResponse")]
    assert envoltorios
    for nombre in envoltorios:
        assert set(esquemas[nombre]["required"]) == {"success", "message", "data"}


async def test_los_listados_devuelven_una_pagina_envuelta():
    datos = await _contrato()
    esquemas = datos["documento"]["components"]["schemas"]
    pagina = "PageSiniestroResumen"
    assert set(esquemas[pagina]["required"]) == {"items", "total", "limit", "offset"}
    assert esquemas[pagina]["properties"]["items"]["items"]["$ref"].endswith(
        "SiniestroResumen"
    )
    listado = datos["documento"]["paths"]["/api/v1/siniestros"]["get"]
    ref = listado["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith(f"ApiResponse{pagina}")


async def test_la_nulabilidad_va_en_el_tipo_como_manda_31():
    """`nullable: true` es de 3.0 y en 3.1 se ignoraría en silencio.

    Se comprueba en dos niveles: que el documento generado no arrastre la forma de
    3.0, y que la traducción de un campo opcional produzca la forma correcta.
    """
    datos = await _contrato()
    contenido = datos["bloque"]["content"]
    assert "nullable:" not in contenido
    assert "format: binary" not in contenido

    opcional = _property(
        {
            "name": "monto",
            "logical_type": "decimal",
            "nullable": True,
            "required": False,
            "example": "1500.00",
        }
    )
    assert opcional["type"] == ["string", "null"]
    assert opcional["format"] == "decimal"
    assert opcional["examples"] == ["1500.00"]

    obligatorio = _property(
        {
            "name": "guia_id",
            "logical_type": "bigint",
            "nullable": False,
            "required": True,
        }
    )
    assert obligatorio["type"] == "integer"


async def test_los_recursos_se_agrupan_por_componente_de_arquitectura():
    datos = await _contrato()
    tags = {t["name"] for t in datos["documento"]["tags"]}
    assert "Módulo Siniestros" in tags
    listado = datos["documento"]["paths"]["/api/v1/siniestros"]["get"]
    assert listado["tags"] == ["Módulo Siniestros"]


async def test_la_seguridad_es_global_y_los_errores_se_comparten():
    datos = await _contrato()
    assert datos["documento"]["security"] == [{"bearerAuth": []}]
    assert datos["documento"]["components"]["securitySchemes"]["bearerAuth"]
    respuestas = datos["documento"]["components"]["responses"]
    assert {"NoAutenticado", "SinPermiso"} <= set(respuestas)
    detalle = datos["documento"]["paths"]["/api/v1/siniestros/{siniestro_id}"]["get"]
    assert detalle["responses"]["401"]["$ref"].endswith("NoAutenticado")


async def test_la_creacion_declara_la_cabecera_location():
    datos = await _contrato()
    creacion = datos["documento"]["paths"]["/api/v1/siniestros"]["post"]
    assert "Location" in creacion["responses"]["201"]["headers"]
    assert creacion["requestBody"]["required"] is True


# --- VALIDATE: lo que L2 no puede ver por sí sola ----------------------------


async def test_el_contrato_del_ejemplo_pasa_la_validacion_estructural():
    datos = await _contrato()
    resultado = check_structure(
        datos["endpoints"],
        datos["schemas"],
        datos["mapa"]["resources"],
        datos["matriz"],
        datos["catalogo"],
        unenforced_delegated_rules=datos["delegadas"],
    )
    assert resultado["errors"] == []


def test_una_referencia_a_un_esquema_inexistente_se_reporta():
    resultado = check_structure(
        [
            {
                "id": "EP-001",
                "operation_id": "obtenerX",
                "method": "GET",
                "path": "/api/v1/x/{x_id}",
                "kind": "read_item",
                "response_schema_ref": "SCH-999",
                "status_codes": [{"code": 200}],
                "parameters": [{"name": "x_id", "location": "path"}],
                "auth_rule_refs": ["AUTH-001"],
            }
        ],
        [],
        [],
        [{"id": "AUTH-001", "endpoint_ref": "EP-001"}],
        [],
    )
    assert any(e["code"] == "schema_ref_missing" for e in resultado["errors"])


def test_una_operacion_sin_codigos_la_caza_L1_porque_31_no_lo_hace():
    """El hueco de 3.1 que documentó API0, cubierto aquí."""
    resultado = check_structure(
        [
            {
                "id": "EP-001",
                "operation_id": "listarX",
                "method": "GET",
                "path": "/api/v1/x",
                "kind": "list",
                "status_codes": [],
                "parameters": [],
                "auth_rule_refs": ["AUTH-001"],
            }
        ],
        [],
        [],
        [{"id": "AUTH-001", "endpoint_ref": "EP-001"}],
        [],
    )
    assert any(e["code"] == "missing_status_codes" for e in resultado["errors"])


def test_dos_rutas_que_colisionan_se_reportan_aunque_el_parametro_se_llame_distinto():
    endpoints = [
        {
            "id": f"EP-00{i}",
            "operation_id": f"op{i}",
            "method": "GET",
            "path": ruta,
            "kind": "read_item",
            "status_codes": [{"code": 200}],
            "parameters": [{"name": ruta.split("{")[1][:-1], "location": "path"}],
            "auth_rule_refs": ["AUTH-001"],
        }
        for i, ruta in enumerate(
            ["/api/v1/x/{x_id}", "/api/v1/x/{identificador}"], start=1
        )
    ]
    resultado = check_structure(
        endpoints, [], [], [{"id": "AUTH-001", "endpoint_ref": "EP-001"}], []
    )
    assert any(e["code"] == "path_collision" for e in resultado["errors"])


def test_un_endpoint_sin_decision_de_acceso_es_un_error():
    resultado = check_structure(
        [
            {
                "id": "EP-001",
                "operation_id": "listarX",
                "method": "GET",
                "path": "/api/v1/x",
                "kind": "list",
                "status_codes": [{"code": 200}],
                "parameters": [],
                "auth_rule_refs": [],
            }
        ],
        [],
        [],
        [],
        [],
    )
    assert any(
        e["code"] == "endpoint_without_authorization" for e in resultado["errors"]
    )


def test_datos_personales_con_alcance_sin_resolver_son_un_error():
    """El agravante que convierte una ambigüedad molesta en un riesgo real."""
    resultado = check_structure(
        [
            {
                "id": "EP-001",
                "operation_id": "listarPersonas",
                "method": "GET",
                "path": "/api/v1/personas",
                "kind": "list",
                "response_schema_ref": "SCH-001",
                "status_codes": [{"code": 200}],
                "parameters": [],
                "auth_rule_refs": ["AUTH-001"],
            }
        ],
        [
            {
                "id": "SCH-001",
                "name": "PersonaResumen",
                "fields": [
                    {
                        "id": "SF-001",
                        "name": "dni",
                        "column_ref": "COL-1",
                        "pii": True,
                    }
                ],
            }
        ],
        [],
        [{"id": "AUTH-001", "endpoint_ref": "EP-001", "ambiguous": True}],
        [],
    )
    assert any(e["code"] == "pii_with_ambiguous_scope" for e in resultado["errors"])


def test_una_regla_delegada_sin_destino_llega_hasta_la_validacion():
    resultado = check_structure(
        [], [], [], [], [], unenforced_delegated_rules=["BR-007"]
    )
    fallo = next(
        e for e in resultado["errors"] if e["code"] == "delegated_rule_unenforced"
    )
    assert "BR-007" in fallo["message"]


def test_una_referencia_colgante_se_reporta_en_vez_de_tumbar_el_pipeline():
    """La trampa que documentó API0: `$ref` roto lanza, no devuelve error."""
    documento = {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/a": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/NoExiste"}
                                }
                            },
                        }
                    }
                }
            }
        },
    }
    errores = check_spec(documento)
    assert errores and errores[0]["code"] == "spec_unresolvable"


def test_el_round_trip_caza_una_operacion_que_no_llego_al_documento():
    """El bug del renderizador que ninguna otra capa vería."""
    yaml_text = yaml.safe_dump({"paths": {"/api/v1/x": {"get": {}}}})
    endpoints = [
        {"method": "GET", "path": "/api/v1/x"},
        {"method": "POST", "path": "/api/v1/x"},
    ]
    problemas = check_round_trip(yaml_text, endpoints)
    assert any(p["code"] == "operation_not_rendered" for p in problemas)


async def test_la_validacion_completa_del_ejemplo_sale_limpia():
    datos = await _contrato()
    validacion = validate_spec(
        datos["documento"],
        datos["bloque"]["content"],
        datos["endpoints"],
        datos["schemas"],
        datos["mapa"]["resources"],
        datos["matriz"],
        datos["catalogo"],
        unenforced_delegated_rules=datos["delegadas"],
    )
    assert validacion["spec_valid"] is True, validacion["errors"]
    assert all(validacion["checks"].values())
    assert validacion["validator"] == "estructural+openapi-spec-validator"
    # Parseado no es ejecutado: hasta que corra L3a, esto es False.
    assert validacion["runtime_checked"] is False


# --- L3a: un runtime real sabe usar el documento -----------------------------


async def test_un_runtime_real_valida_una_respuesta_contra_el_documento():
    """La prueba de humo: `openapi-core` navega el documento y acepta la respuesta.

    No prueba el sistema —no hay sistema— sino que el documento es navegable y sus
    esquemas aceptan datos con la forma que dicen aceptar. Por eso el artefacto
    solo declara `runtime_checked` cuando esta capa corre.
    """
    datos = await _contrato()
    documento = datos["documento"]

    envoltorio = next(
        n
        for n in documento["components"]["schemas"]
        if n.startswith("ApiResponse") and n.endswith("Siniestro")
    )
    cuerpo = sample_payload(documento, envoltorio)
    cuerpo["data"] = sample_payload(documento, "Siniestro")

    errores = check_runtime(
        documento, "GET", "/api/v1/siniestros/1", status=200, body=cuerpo
    )
    assert errores == [], errores


async def test_el_runtime_rechaza_una_respuesta_que_no_cumple_el_contrato():
    """Si aceptara cualquier cosa, la capa L3a no probaría nada."""
    datos = await _contrato()
    errores = check_runtime(
        datos["documento"],
        "GET",
        "/api/v1/siniestros/1",
        status=200,
        body={"esto": "no es el envelope"},
    )
    assert errores


# --- El grafo completo --------------------------------------------------------


async def test_el_grafo_produce_un_documento_valido():
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

    assert final["openapi"]["content"].startswith("openapi: 3.1.0")
    assert final["openapi"]["operations_total"] == len(final["endpoints"])
    assert final["validation"]["spec_valid"] is True, final["validation"]["errors"]
    assert final["metrics"]["spec_valid"] is True
    # Y el YAML del artefacto es exactamente lo que se validó.
    documento = yaml.safe_load(final["openapi"]["content"])
    assert list(OpenAPIV31SpecValidator(documento).iter_errors()) == []
    assert json.loads(json.dumps(documento))  # serializable tal cual
