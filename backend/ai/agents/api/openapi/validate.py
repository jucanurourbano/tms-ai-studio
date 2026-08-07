"""Validación determinista de la especificación, en capas y **sin LLM**.

El artefacto de este agente lo consumen tres agentes más, así que "parece
correcto" no basta. Se valida en capas de coste creciente, y el artefacto declara
cuáles se aplicaron (``validation.validator`` / ``validation.runtime_checked``):
un parseo no se presenta como si fuera una ejecución.

- **L1 — estructural (Python puro).** Sobre el contrato, no sobre el texto: que las
  referencias resuelvan, que ningún campo exista sin columna, que no haya
  colisiones de ruta, que la semántica HTTP se respete, que **todo endpoint tenga
  una decisión de acceso** y que ninguna regla delegada por el Agente BD se haya
  quedado sin destino.
- **L2 — esquema de OpenAPI 3.1** (``openapi-spec-validator``), sin red.
- **L2b — round-trip**: se re-parsea el YAML emitido y se compara con
  ``endpoints[]``. Caza errores del **renderizador**, que es donde vivirían.
- **L3a — runtime** (``openapi-core``, en tests): ver ``smoke.py``.

Dos cosas que la capa L2 **no** puede hacer por nosotros, y que por eso viven en
L1 (ambas verificadas en ``tests/agents/api/test_openapi_dependency.py``):

1. OpenAPI **3.1 hizo ``responses`` opcional**. Un endpoint que no declara qué
   devuelve pasa la validación de la librería sin una queja.
2. Un ``$ref`` colgante **lanza excepción** en vez de reportarse. L2 la captura y
   la convierte en un error del artefacto: una referencia rota debe reportarse, no
   tumbar el job.

Ante un error, el pipeline **no se cae**: el hallazgo entra en
``validation.errors``, el job termina ``COMPLETED_WITH_WARNINGS`` y el semáforo se
queda en rojo. Entregar una especificación con un defecto señalado es útil;
caerse, no.
"""

import re
from typing import Any, Optional

import yaml
from openapi_spec_validator import OpenAPIV31SpecValidator

#: Métodos que no llevan cuerpo de petición.
_NO_BODY = ("GET", "DELETE")

#: Código de éxito esperado por tipo de operación (semántica HTTP).
_EXPECTED_SUCCESS = {
    "create": 201,
    "nested_create": 201,
    "delete": 204,
    "nested_delete": 204,
}

_PARAM_RE = re.compile(r"\{(\w+)\}")


def _issue(code: str, message: str, ref: Optional[str] = None) -> dict:
    return {"code": code, "message": message, "ref": ref}


def _normalized(path: str) -> str:
    """Ruta con los parámetros anonimizados: ``/x/{a}`` y ``/x/{b}`` colisionan."""
    return _PARAM_RE.sub("{}", path)


# --- L1: estructural -----------------------------------------------------------


def check_structure(
    endpoints: list[dict],
    schemas: list[dict],
    resources: list[dict],
    authorization_matrix: list[dict],
    error_catalog: list[dict],
    *,
    unenforced_delegated_rules: Optional[list[str]] = None,
    base_path: str = "/api/v1",
) -> dict:
    """Coherencia del contrato antes de mirar una sola línea de YAML."""
    errors: list[dict] = []
    warnings: list[dict] = []

    ids_esquemas = {s["id"] for s in schemas}
    ids_errores = {e["id"] for e in error_catalog}
    ids_endpoints = {e["id"] for e in endpoints}
    ids_reglas = {r["id"] for r in authorization_matrix}

    # 1. Las referencias resuelven.
    for endpoint in endpoints:
        for clave in ("request_schema_ref", "response_schema_ref"):
            ref = endpoint.get(clave)
            if ref and ref not in ids_esquemas:
                errors.append(
                    _issue(
                        "schema_ref_missing",
                        f"{endpoint['operation_id']} referencia el esquema {ref}, "
                        "que no existe.",
                        endpoint["id"],
                    )
                )
        for status in endpoint.get("status_codes", []):
            if status.get("error_ref") and status["error_ref"] not in ids_errores:
                errors.append(
                    _issue(
                        "error_ref_missing",
                        f"{endpoint['operation_id']} declara el error "
                        f"{status['error_ref']}, que no está en el catálogo.",
                        endpoint["id"],
                    )
                )
        for ref in endpoint.get("auth_rule_refs", []):
            if ref not in ids_reglas:
                errors.append(
                    _issue(
                        "auth_rule_missing",
                        f"{endpoint['operation_id']} referencia la regla {ref}, "
                        "que no existe.",
                        endpoint["id"],
                    )
                )
    for regla in authorization_matrix:
        if regla["endpoint_ref"] not in ids_endpoints:
            errors.append(
                _issue(
                    "auth_endpoint_missing",
                    f"La regla {regla['id']} apunta a un endpoint inexistente.",
                    regla["id"],
                )
            )

    # 2. Ningún campo existe sin columna detrás.
    for esquema in schemas:
        for field in esquema.get("fields", []):
            if field.get("computed"):
                if not field.get("source_refs"):
                    errors.append(
                        _issue(
                            "computed_field_without_rule",
                            f"El campo calculado {esquema['name']}.{field['name']} "
                            "no cita la regla que lo define.",
                            field["id"],
                        )
                    )
            elif not field.get("column_ref"):
                errors.append(
                    _issue(
                        "field_without_column",
                        f"El campo {esquema['name']}.{field['name']} no tiene "
                        "columna de origen.",
                        field["id"],
                    )
                )

    # 3. Sin colisiones de ruta; ruta estática que ensombrece a una paramétrica.
    vistas: dict[tuple[str, str], str] = {}
    for endpoint in endpoints:
        clave = (endpoint["method"], _normalized(endpoint["path"]))
        if clave in vistas:
            errors.append(
                _issue(
                    "path_collision",
                    f"{endpoint['method']} {endpoint['path']} colisiona con "
                    f"{vistas[clave]}.",
                    endpoint["id"],
                )
            )
        else:
            vistas[clave] = endpoint["operation_id"]
    _check_shadowing(endpoints, warnings)

    # 4. Parámetros de ruta declarados == los de la ruta.
    for endpoint in endpoints:
        en_ruta = set(_PARAM_RE.findall(endpoint["path"]))
        declarados = {
            p["name"] for p in endpoint.get("parameters", []) if p["location"] == "path"
        }
        if en_ruta != declarados:
            errors.append(
                _issue(
                    "path_params_mismatch",
                    f"{endpoint['operation_id']}: la ruta usa {sorted(en_ruta)} y la "
                    f"operación declara {sorted(declarados)}.",
                    endpoint["id"],
                )
            )

    # 5. `operationId` único (lo convierten en nombre de método los generadores).
    por_operation_id: dict[str, str] = {}
    for endpoint in endpoints:
        if endpoint["operation_id"] in por_operation_id:
            errors.append(
                _issue(
                    "duplicate_operation_id",
                    f"El operationId «{endpoint['operation_id']}» se repite.",
                    endpoint["id"],
                )
            )
        por_operation_id[endpoint["operation_id"]] = endpoint["id"]

    # 6. Convenciones de ruta.
    for endpoint in endpoints:
        if not endpoint["path"].startswith(base_path.rstrip("/") + "/"):
            errors.append(
                _issue(
                    "path_prefix",
                    f"{endpoint['path']} no cuelga de {base_path}.",
                    endpoint["id"],
                )
            )
        for segmento in endpoint["path"].split("/"):
            if segmento.startswith("{") or not segmento:
                continue
            if "_" in segmento or segmento != segmento.lower():
                warnings.append(
                    _issue(
                        "path_naming",
                        f"El segmento «{segmento}» de {endpoint['path']} no sigue "
                        "kebab-case en minúsculas.",
                        endpoint["id"],
                    )
                )

    # 7. Todo endpoint tiene una decisión de acceso (fail-closed).
    for endpoint in endpoints:
        if not endpoint.get("auth_rule_refs"):
            errors.append(
                _issue(
                    "endpoint_without_authorization",
                    f"{endpoint['operation_id']} no tiene ninguna regla de "
                    "autorización: ni siquiera una denegación explícita.",
                    endpoint["id"],
                )
            )

    # 8 y 9. Semántica HTTP y códigos obligatorios.
    _check_http(endpoints, errors, warnings)

    # 11. Toda tabla se expone o dice por qué no.
    for recurso in resources:
        if (
            recurso.get("exposure") != "crud"
            and not (recurso.get("exposure_reason") or "").strip()
        ):
            errors.append(
                _issue(
                    "exposure_without_reason",
                    f"El recurso {recurso['name']} no se expone del todo y no dice "
                    "por qué.",
                    recurso["id"],
                )
            )

    # 12. Ninguna regla delegada por el modelo de datos se queda sin destino.
    for ref in unenforced_delegated_rules or []:
        errors.append(
            _issue(
                "delegated_rule_unenforced",
                f"La regla {ref} la delegó el modelo de datos en la aplicación y "
                "ningún endpoint, esquema ni regla de acceso la recoge.",
                ref,
            )
        )

    # 13. Datos personales con un alcance sin resolver.
    _check_pii(endpoints, schemas, authorization_matrix, errors)

    return {"errors": errors, "warnings": warnings}


def _check_shadowing(endpoints: list[dict], warnings: list[dict]) -> None:
    """Ruta estática que compite con una hermana paramétrica del mismo nivel."""
    por_metodo: dict[str, list[str]] = {}
    for endpoint in endpoints:
        por_metodo.setdefault(endpoint["method"], []).append(endpoint["path"])
    for metodo, rutas in por_metodo.items():
        for ruta in rutas:
            partes = ruta.split("/")
            if not partes or partes[-1].startswith("{"):
                continue
            hermana = "/".join(partes[:-1]) + "/{id}"
            if any(_normalized(o) == _normalized(hermana) for o in rutas):
                warnings.append(
                    _issue(
                        "path_shadowing",
                        f"{metodo} {ruta} convive con una ruta paramétrica hermana; "
                        "la estática debe resolverse primero en el enrutador.",
                    )
                )


def _check_http(
    endpoints: list[dict], errors: list[dict], warnings: list[dict]
) -> None:
    """Semántica HTTP y códigos que toda operación debe declarar."""
    for endpoint in endpoints:
        codigos = {s["code"] for s in endpoint.get("status_codes", [])}
        if not codigos:
            # 3.1 hizo `responses` opcional, así que esto NO lo caza la librería.
            errors.append(
                _issue(
                    "missing_status_codes",
                    f"{endpoint['operation_id']} no declara qué devuelve.",
                    endpoint["id"],
                )
            )
            continue
        if endpoint["method"] in _NO_BODY and endpoint.get("request_schema_ref"):
            errors.append(
                _issue(
                    "body_on_bodyless_method",
                    f"{endpoint['operation_id']} es {endpoint['method']} y declara "
                    "cuerpo de petición.",
                    endpoint["id"],
                )
            )
        esperado = _EXPECTED_SUCCESS.get(endpoint["kind"])
        if esperado and esperado not in codigos:
            errors.append(
                _issue(
                    "unexpected_success_code",
                    f"{endpoint['operation_id']} debería declarar {esperado}.",
                    endpoint["id"],
                )
            )
        if endpoint.get("paginated"):
            nombres = {
                p["name"]
                for p in endpoint.get("parameters", [])
                if p["location"] == "query"
            }
            if not nombres:
                warnings.append(
                    _issue(
                        "list_without_pagination",
                        f"{endpoint['operation_id']} es un listado sin parámetros de "
                        "paginación.",
                        endpoint["id"],
                    )
                )
        if endpoint.get("response_kind") != "none" and not endpoint.get(
            "response_schema_ref"
        ):
            warnings.append(
                _issue(
                    "response_without_schema",
                    f"{endpoint['operation_id']} no declara el esquema de su "
                    "respuesta.",
                    endpoint["id"],
                )
            )


def _check_pii(
    endpoints: list[dict],
    schemas: list[dict],
    authorization_matrix: list[dict],
    errors: list[dict],
) -> None:
    """Datos personales viajando por un endpoint con el alcance sin resolver.

    Es el agravante que convierte una ambigüedad molesta en un riesgo real: si
    nadie sabe qué filas puede ver un actor y la respuesta lleva datos de personas,
    el error por defecto sería enseñárselos a quien no debía.
    """
    con_pii = {
        s["id"] for s in schemas if any(f.get("pii") for f in s.get("fields", []))
    }
    ambiguos = {r["endpoint_ref"] for r in authorization_matrix if r.get("ambiguous")}
    for endpoint in endpoints:
        if (
            endpoint["id"] in ambiguos
            and endpoint.get("response_schema_ref") in con_pii
        ):
            errors.append(
                _issue(
                    "pii_with_ambiguous_scope",
                    f"{endpoint['operation_id']} expone datos personales y su "
                    "alcance de acceso está sin resolver.",
                    endpoint["id"],
                )
            )


# --- L2 y L2b: el documento ----------------------------------------------------


def check_spec(document: dict) -> list[dict]:
    """L2: el documento contra el esquema de OpenAPI 3.1, sin red.

    La llamada va envuelta a propósito: un ``$ref`` colgante **lanza** en vez de
    salir por ``iter_errors()``, y una referencia rota debe reportarse, no tumbar
    el pipeline.
    """
    try:
        return [
            _issue("spec_invalid", error.message, "/".join(str(p) for p in error.path))
            for error in OpenAPIV31SpecValidator(document).iter_errors()
        ]
    except Exception as exc:  # noqa: BLE001 - se reporta, no se propaga
        return [
            _issue(
                "spec_unresolvable",
                f"El documento no se pudo validar: {exc}"[:300],
            )
        ]


def check_round_trip(yaml_text: str, endpoints: list[dict]) -> list[dict]:
    """L2b: lo que dice el artefacto y lo que dice el YAML deben coincidir.

    Si el renderizador se dejara una operación, el artefacto contaría una cosa y el
    entregable otra. Es el bug que ninguna otra capa vería.
    """
    try:
        documento = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        return [_issue("yaml_invalid", f"El YAML emitido no parsea: {exc}"[:300])]

    del_documento = {
        (metodo.upper(), ruta)
        for ruta, operaciones in (documento.get("paths") or {}).items()
        for metodo in operaciones
    }
    del_artefacto = {(e["method"], e["path"]) for e in endpoints}
    faltan = del_artefacto - del_documento
    sobran = del_documento - del_artefacto
    problemas: list[dict] = []
    for metodo, ruta in sorted(faltan):
        problemas.append(
            _issue("operation_not_rendered", f"{metodo} {ruta} no llegó al documento.")
        )
    for metodo, ruta in sorted(sobran):
        problemas.append(
            _issue(
                "operation_not_in_artifact",
                f"El documento declara {metodo} {ruta}, que no está en el contrato.",
            )
        )
    return problemas


def validate_spec(
    document: dict,
    yaml_text: str,
    endpoints: list[dict],
    schemas: list[dict],
    resources: list[dict],
    authorization_matrix: list[dict],
    error_catalog: list[dict],
    *,
    unenforced_delegated_rules: Optional[list[str]] = None,
    base_path: str = "/api/v1",
) -> dict:
    """Aplica L1 + L2 + L2b y compone el bloque ``validation`` del artefacto."""
    from openapi_spec_validator import __version__ as validator_version

    estructural = check_structure(
        endpoints,
        schemas,
        resources,
        authorization_matrix,
        error_catalog,
        unenforced_delegated_rules=unenforced_delegated_rules,
        base_path=base_path,
    )
    errores_spec = check_spec(document)
    errores_round = check_round_trip(yaml_text, endpoints)

    errores = estructural["errors"] + errores_spec + errores_round
    codigos = {e["code"] for e in errores}

    checks = {
        "refs_resolve": not (
            codigos
            & {
                "schema_ref_missing",
                "error_ref_missing",
                "auth_rule_missing",
                "auth_endpoint_missing",
            }
        ),
        "fields_have_column": not (
            codigos & {"field_without_column", "computed_field_without_rule"}
        ),
        "no_path_collisions": "path_collision" not in codigos,
        "path_params_match": "path_params_mismatch" not in codigos,
        "unique_operation_ids": "duplicate_operation_id" not in codigos,
        "path_conventions": "path_prefix" not in codigos,
        "all_endpoints_authorized": "endpoint_without_authorization" not in codigos,
        "http_semantics": not (
            codigos
            & {
                "missing_status_codes",
                "body_on_bodyless_method",
                "unexpected_success_code",
            }
        ),
        "exposure_justified": "exposure_without_reason" not in codigos,
        "delegated_rules_enforced": "delegated_rule_unenforced" not in codigos,
        "pii_scope_resolved": "pii_with_ambiguous_scope" not in codigos,
        "spec_schema": not (codigos & {"spec_invalid", "spec_unresolvable"}),
        "round_trip": not (
            codigos
            & {"operation_not_rendered", "operation_not_in_artifact", "yaml_invalid"}
        ),
    }

    return {
        "spec_valid": not errores,
        "validator": "estructural+openapi-spec-validator",
        "validator_version": validator_version,
        # Lo pone la capa L3a, que corre en tests: no se presenta como
        # certificación lo que solo fue un parseo.
        "runtime_checked": False,
        "checks": checks,
        "errors": errores,
        "warnings": estructural["warnings"],
    }
