"""Tests del contrato ApiArtifact v1.0.0 (API1): validación + round-trip.

Más allá del round-trip, fijan las **invariantes de diseño** que el contrato debe
sostener por sí mismo: que ningún campo expuesto pueda inventarse, que ninguna
exclusión ni descarte sea mudo, y que un alcance de autorización que nadie puede
implementar no pueda pasar por bueno.
"""

import pytest
import yaml
from openapi_spec_validator import OpenAPIV31SpecValidator
from pydantic import ValidationError

from ai.agents.api.schemas import (
    OPENAPI_VERSION,
    SCHEMA_VERSION,
    ApiArtifact,
    ApiRuleEnforcement,
    ApiStyle,
    AuthBasis,
    AuthEffect,
    AuthorizationRule,
    AuthScheme,
    AuthScope,
    EndpointKind,
    HttpMethod,
    LogicalType,
    Origin,
    ResourceExposure,
)
from ai.agents.api.schemas.examples import example_artifact
from ai.agents.bd.schemas.enums import LogicalType as BdLogicalType
from ai.knowledge import api_error_catalog, openapi_type


def test_ejemplo_valido_y_version():
    art = example_artifact()
    assert art.schema_version == SCHEMA_VERSION == "1.0.0"
    assert art.source.ready_snapshot is True
    # Enlace a los CUATRO jobs de la cadena (BD directo; Arquitectura, Scrum y EF
    # transitivos), para poder reproducir la corrida.
    assert art.source.bd_job_id
    assert art.source.architecture_job_id
    assert art.source.scrum_job_id
    assert art.source.ef_job_id
    assert art.target.api_style is ApiStyle.REST
    assert art.target.spec_version == OPENAPI_VERSION == "3.1.0"
    assert art.target.auth.scheme is AuthScheme.BEARER_JWT
    assert len(art.endpoints) >= 1


def test_round_trip_json_estable():
    art = example_artifact()
    dumped = art.model_dump(mode="json")
    reloaded = ApiArtifact.model_validate(dumped)
    assert reloaded.model_dump(mode="json") == dumped


def test_extra_forbid_en_artifact():
    data = example_artifact().model_dump(mode="json")
    data["campo_desconocido"] = "x"
    with pytest.raises(ValidationError):
        ApiArtifact.model_validate(data)


def test_extra_forbid_hasta_el_campo_de_esquema():
    """El structured output es cerrado hasta el último nivel."""
    data = example_artifact().model_dump(mode="json")
    data["schemas"][0]["fields"][0]["inventado"] = True
    with pytest.raises(ValidationError):
        ApiArtifact.model_validate(data)


# --- Anti-invención: todo campo expuesto viene de una columna ----------------


def test_un_campo_sin_columna_ni_calculo_es_invalido():
    """La invariante central del contrato (gemela de `column_ref` obligatorio).

    Un campo que no es una columna ni un cálculo con regla citada no existe en
    ninguna parte del sistema: el Agente Backend intentaría después implementar un
    dato que nadie pidió.
    """
    data = example_artifact().model_dump(mode="json")
    data["schemas"][0]["fields"][0]["column_ref"] = None
    with pytest.raises(ValidationError, match="columna de origen"):
        ApiArtifact.model_validate(data)


def test_un_campo_calculado_debe_citar_la_regla_que_lo_define():
    data = example_artifact().model_dump(mode="json")
    campo = data["schemas"][0]["fields"][0]
    campo["column_ref"] = None
    campo["computed"] = True
    campo["source_refs"] = []
    with pytest.raises(ValidationError, match="invención"):
        ApiArtifact.model_validate(data)


def test_un_campo_calculado_con_regla_si_es_valido():
    """La vía legítima para un dato que no es columna: declararlo y citarlo."""
    data = example_artifact().model_dump(mode="json")
    campo = data["schemas"][0]["fields"][0]
    campo["column_ref"] = None
    campo["computed"] = True
    campo["source_refs"] = ["BR-004"]
    art = ApiArtifact.model_validate(data)
    assert art.schemas[0].fields[0].computed is True


# --- Nada se excluye ni se descarta en silencio ------------------------------


def test_un_recurso_no_expuesto_debe_decir_por_que():
    data = example_artifact().model_dump(mode="json")
    catalogo = next(r for r in data["resources"] if r["exposure"] != "crud")
    catalogo["exposure_reason"] = "   "
    with pytest.raises(ValidationError, match="motivo"):
        ApiArtifact.model_validate(data)


def test_una_regla_fuera_de_la_api_debe_explicarse():
    data = example_artifact().model_dump(mode="json")
    data["rule_mappings"][0]["enforcement"] = ApiRuleEnforcement.NOT_APPLICABLE.value
    data["rule_mappings"][0]["note"] = None
    with pytest.raises(ValidationError, match="sin explicar"):
        ApiArtifact.model_validate(data)


def test_un_endpoint_de_accion_sin_evidencia_es_invalido():
    """Las acciones son la única ampliación que propone el LLM: deben justificarse.

    Es el mismo trato que reciben los catálogos en el Agente BD, y por la misma
    razón: es el único punto por donde podría entrar algo que nadie pidió.
    """
    data = example_artifact().model_dump(mode="json")
    endpoint = data["endpoints"][0]
    endpoint["kind"] = EndpointKind.ACTION.value
    endpoint["source_refs"] = []
    with pytest.raises(ValidationError, match="no cita el proceso"):
        ApiArtifact.model_validate(data)


# --- Autorización fail-closed ------------------------------------------------


def test_un_alcance_sin_columna_debe_marcarse_ambiguo():
    """El vacío se convierte en pregunta, nunca en un permiso más ancho."""
    with pytest.raises(ValidationError, match="ambigua"):
        AuthorizationRule(
            id="AUTH-999",
            endpoint_ref="EP-002",
            actor_ref="ACT-002",
            effect=AuthEffect.ALLOW,
            scope=AuthScope.OWN_TEAM,
            scope_expression="siniestro.equipo_id = usuario.equipo_id",
            scope_column_refs=[],
            basis=AuthBasis.BUSINESS_RULE,
            ambiguous=False,
        )


def test_un_alcance_con_columna_real_es_valido():
    regla = AuthorizationRule(
        id="AUTH-998",
        endpoint_ref="EP-002",
        actor_ref="ACT-002",
        effect=AuthEffect.ALLOW,
        scope=AuthScope.OWN_TEAM,
        scope_column_refs=["COL-0011"],
        basis=AuthBasis.BUSINESS_RULE,
    )
    assert regla.ambiguous is False


def test_el_alcance_total_no_necesita_columna():
    """`all` no filtra filas: no hay nada que materializar."""
    regla = AuthorizationRule(
        id="AUTH-997",
        endpoint_ref="EP-001",
        actor_ref="ACT-001",
        effect=AuthEffect.ALLOW,
        scope=AuthScope.ALL,
        basis=AuthBasis.CRUD_MATRIX,
    )
    assert regla.ambiguous is False


def test_una_regla_nace_denegando():
    """Fail-closed por defecto: hay que conceder explícitamente."""
    regla = AuthorizationRule(id="AUTH-996", endpoint_ref="EP-001", actor_ref="ACT-003")
    assert regla.effect is AuthEffect.DENY
    assert regla.basis is AuthBasis.DEFAULT_DENY
    assert regla.scope is AuthScope.NONE


def test_un_endpoint_sin_autorizacion_SI_se_puede_representar():
    """A propósito: es un defecto reportable, no un artefacto imposible.

    Un contrato que se negara a construirlo impediría al agente **reportar** el
    hueco, que es justo lo que debe hacer (lo detecta L1 y bloquea el semáforo).
    """
    data = example_artifact().model_dump(mode="json")
    data["endpoints"][0]["auth_rule_refs"] = []
    art = ApiArtifact.model_validate(data)
    assert art.endpoints[0].auth_rule_refs == []


# --- El tipo lo decide el modelo de datos, no la API -------------------------


def test_no_hay_un_segundo_sistema_de_tipos():
    """`LogicalType` es literalmente el del Agente BD, no una copia paralela."""
    assert LogicalType is BdLogicalType


def test_todo_tipo_del_ejemplo_se_traduce_al_esquema_openapi():
    art = example_artifact()
    usados = {f.logical_type for s in art.schemas for f in s.fields}
    usados |= {p.logical_type for e in art.endpoints for p in e.parameters}
    for logical in usados:
        assert openapi_type(logical.value).get("type"), logical.value


# --- Coherencia interna del fixture (anticipa las comprobaciones L1) ---------


def test_ids_unicos_en_cada_coleccion():
    art = example_artifact()
    colecciones = {
        "resources": [r.id for r in art.resources],
        "schemas": [s.id for s in art.schemas],
        "endpoints": [e.id for e in art.endpoints],
        "authorization_matrix": [a.id for a in art.authorization_matrix],
        "error_catalog": [e.id for e in art.error_catalog],
        "rule_mappings": [m.id for m in art.rule_mappings],
    }
    for nombre, ids in colecciones.items():
        assert len(ids) == len(set(ids)), f"ids repetidos en {nombre}"
    campos = [f.id for s in art.schemas for f in s.fields]
    # Un mismo campo se reutiliza entre esquemas (create/read comparten columnas):
    # lo que no puede haber es un id usado para dos campos distintos.
    por_id = {}
    for esquema in art.schemas:
        for campo in esquema.fields:
            previo = por_id.setdefault(campo.id, campo.name)
            assert previo == campo.name, f"{campo.id} nombra dos campos distintos"
    assert campos


def test_todas_las_referencias_del_ejemplo_resuelven():
    art = example_artifact()
    recursos = {r.id for r in art.resources}
    esquemas = {s.id for s in art.schemas}
    reglas_auth = {a.id for a in art.authorization_matrix}
    endpoints = {e.id for e in art.endpoints}
    errores = {e.id for e in art.error_catalog}

    for endpoint in art.endpoints:
        assert endpoint.resource_ref in recursos
        if endpoint.request_schema_ref:
            assert endpoint.request_schema_ref in esquemas
        if endpoint.response_schema_ref:
            assert endpoint.response_schema_ref in esquemas
        for ref in endpoint.auth_rule_refs:
            assert ref in reglas_auth
        for status in endpoint.status_codes:
            if status.error_ref:
                assert status.error_ref in errores
            if status.schema_ref:
                assert status.schema_ref in esquemas

    for regla in art.authorization_matrix:
        assert regla.endpoint_ref in endpoints

    for mapeo in art.rule_mappings:
        assert set(mapeo.endpoint_refs) <= endpoints
        assert set(mapeo.auth_rule_refs) <= reglas_auth


def test_los_errores_del_ejemplo_existen_en_el_catalogo_estandar():
    """El catálogo del artefacto es un subconjunto del de `api_conventions.yaml`."""
    estandar = {e["id"] for e in api_error_catalog()}
    for entrada in example_artifact().error_catalog:
        assert entrada.id in estandar


def test_ninguna_regla_delegada_por_el_bd_se_queda_sin_destino():
    """El círculo que cierra este agente (comprobación L1 nº 12).

    Una regla que el modelo de datos clasificó `application` y que aquí no
    encuentra endpoint, esquema ni regla de acceso desaparecería del sistema.
    """
    for mapeo in example_artifact().rule_mappings:
        if mapeo.bd_enforcement == "application":
            destinos = (
                mapeo.endpoint_refs + mapeo.schema_field_refs + mapeo.auth_rule_refs
            )
            assert destinos, f"{mapeo.rule_ref} quedó sin destino en la API"


def test_el_endpoint_declarado_por_el_ef_nace_stated():
    """Trazabilidad hacia atrás: lo que el EF ya pedía no se presenta como idea nueva."""
    art = example_artifact()
    declarado = next(e for e in art.endpoints if e.ef_api_ref)
    assert declarado.origin is Origin.STATED
    assert declarado.ef_api_ref == "API-001"
    derivados = [e for e in art.endpoints if not e.ef_api_ref]
    assert derivados and all(e.origin is Origin.DERIVED for e in derivados)


def test_el_catalogo_se_expone_solo_en_lectura_y_lo_justifica():
    catalogo = next(r for r in example_artifact().resources if r.table_ref == "TBL-003")
    assert catalogo.exposure is ResourceExposure.READ_ONLY
    assert "catálogo" in (catalogo.exposure_reason or "").lower()
    assert catalogo.entity_ref is None  # no es una entidad del EF


def test_los_filtros_solo_usan_columnas_indexadas():
    """Regla dura: un filtro sin índice es una consulta lenta en producción."""
    listado = next(
        e
        for e in example_artifact().endpoints
        if e.kind is EndpointKind.LIST and e.filters
    )
    # `estado_id` participa del índice ix_siniestros_estado_fecha del modelo.
    assert listado.filters == ["estado_id"]
    assert listado.paginated is True


# --- El documento OpenAPI del ejemplo es real --------------------------------


def test_el_documento_del_ejemplo_es_un_openapi_31_valido():
    """Referencia viva de lo que tendrá que renderizar OPENAPI_GEN (API6)."""
    doc = yaml.safe_load(example_artifact().openapi.content)
    assert doc["openapi"] == "3.1.0"
    assert list(OpenAPIV31SpecValidator(doc).iter_errors()) == []


def test_el_documento_no_usa_construcciones_de_openapi_30():
    """`nullable: true` es de 3.0; en 3.1 la nulabilidad va en el propio `type`.

    La librería no lo caza (en JSON Schema es una clave desconocida y se ignora),
    así que un documento con `nullable` pasaría la validación y produciría un
    cliente generado que no admite nulos. Queda fijado aquí.
    """
    contenido = example_artifact().openapi.content
    assert "nullable:" not in contenido
    assert "format: binary" not in contenido
    assert "type: [string, 'null']" in contenido  # la forma correcta en 3.1


def test_el_documento_declara_el_envelope_y_la_seguridad_de_la_casa():
    doc = yaml.safe_load(example_artifact().openapi.content)
    envelope = doc["components"]["schemas"]["ApiResponseSiniestro"]
    assert set(envelope["required"]) == {"success", "message", "data"}
    assert doc["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert doc["security"] == [{"bearerAuth": []}]


def test_las_operaciones_del_documento_coinciden_con_los_endpoints():
    """Round-trip de contenido: el YAML y `endpoints[]` cuentan lo mismo.

    Es la comprobación L2b en miniatura. Si el renderizador se dejara una
    operación, el artefacto diría una cosa y el entregable otra.
    """
    art = example_artifact()
    doc = yaml.safe_load(art.openapi.content)
    del_documento = {
        (metodo.upper(), ruta)
        for ruta, operaciones in doc["paths"].items()
        for metodo in operaciones
    }
    del_artefacto = {(e.method.value, e.path) for e in art.endpoints}
    assert del_documento == del_artefacto
    assert art.openapi.operations_total == len(art.endpoints)


def test_todo_operation_id_del_documento_es_unico_y_esta_en_el_artefacto():
    art = example_artifact()
    doc = yaml.safe_load(art.openapi.content)
    ids = [
        op["operationId"]
        for operaciones in doc["paths"].values()
        for op in operaciones.values()
    ]
    assert len(ids) == len(set(ids))
    assert set(ids) == {e.operation_id for e in art.endpoints}


def test_las_rutas_respetan_las_convenciones_acordadas():
    """Dominio en español, prefijo /api/v1, kebab-case y plural (API6)."""
    art = example_artifact()
    for endpoint in art.endpoints:
        assert endpoint.path.startswith("/api/v1/")
        segmento = endpoint.path.split("/")[3]
        assert segmento.islower()
        assert "_" not in segmento  # kebab-case, no snake_case, en la ruta
    # Y el verbo de actualización acordado es PATCH, no PUT.
    assert art.target.conventions.update_verb is HttpMethod.PATCH
    assert art.target.conventions.property_case == "snake_case"
