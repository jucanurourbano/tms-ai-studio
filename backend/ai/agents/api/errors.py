"""Nodo ERRORS (determinista): qué puede responder cada endpoint.

Sin LLM. Los códigos de estado no son una opinión: salen de la semántica HTTP, del
catálogo de ``api_conventions.yaml`` y —lo interesante— **de las restricciones que
el Agente BD puso en el modelo de datos**. Una tabla con una restricción de
unicidad puede devolver ``409``; una sin ella, no. Así el contrato de errores es
tan real como el esquema que lo respalda, en vez de una lista copiada en todos los
endpoints por si acaso.

**Por qué este nodo va después de AUTHORIZATION.** No es por el ``403`` —con
seguridad global, todo endpoint autenticado puede devolverlo— sino por el ``404``:
cuando un actor tiene un alcance por filas, un registro fuera de su alcance debe
responder **404 y no 403**. Decir "existe pero no puedes verlo" ya filtra que
existe, que es justo lo que el alcance pretendía ocultar. Para saber si un endpoint
está en ese caso hay que mirar la matriz de autorización, y por eso se mira aquí.
"""

from typing import Any, Optional

from ai.knowledge import (
    api_error,
    api_error_catalog,
    constraint_error_id,
    success_status,
)

#: Operaciones que actúan sobre un registro concreto (pueden no encontrarlo).
_ADDRESSED = ("read_item", "update", "delete", "action", "nested_delete")

#: Operaciones que escriben y por tanto pueden violar una restricción.
_WRITES = ("create", "update", "action", "nested_create")

#: Alcances que filtran filas: con ellos, "no encontrado" y "sin permiso" se
#: responden igual para no revelar la existencia del registro.
_ROW_SCOPES = ("own", "own_team", "own_branch", "custom")


def _status(code: int, description: str, **extra) -> dict:
    entrada = {"code": code, "description": description}
    entrada.update({k: v for k, v in extra.items() if v})
    return entrada


def _table_of(resource: dict, tables: dict[str, dict]) -> dict:
    return tables.get(resource.get("table_ref") or "", {})


def _scoped_endpoints(authorization_matrix: list[dict]) -> set[str]:
    """Endpoints cuyo acceso está acotado por filas para algún actor."""
    return {
        regla["endpoint_ref"]
        for regla in authorization_matrix or []
        if regla.get("scope") in _ROW_SCOPES
    }


def status_codes_for(
    endpoint: dict,
    resource: dict,
    table: dict,
    *,
    acotado: bool,
    auth_required: bool = True,
) -> tuple[list[dict], list[str]]:
    """Códigos de un endpoint. Devuelve ``(status_codes, refs_del_catalogo)``."""
    kind = endpoint["kind"]
    codigos: list[dict] = []
    usados: list[str] = []

    exito = success_status(kind)
    codigos.append(
        _status(
            exito,
            _success_description(kind, resource),
            schema_ref=endpoint.get("response_schema_ref"),
        )
    )

    if auth_required:
        for ref in ("ERR-401", "ERR-403"):
            entrada = api_error(ref)
            if entrada:
                codigos.append(
                    _status(entrada["status"], entrada["message"], error_ref=ref)
                )
                usados.append(ref)

    if kind in _ADDRESSED:
        entrada = api_error("ERR-404")
        descripcion = entrada.get("message", "No encontrado.")
        if acotado:
            # El alcance por filas se protege también aquí: si respondiéramos 403,
            # el actor sabría que el registro existe.
            descripcion += (
                " Se responde igual cuando el registro queda fuera del alcance del "
                "actor, para no revelar su existencia."
            )
        codigos.append(_status(404, descripcion, error_ref="ERR-404"))
        usados.append("ERR-404")

    if kind in _WRITES:
        if table.get("unique_constraints"):
            ref = constraint_error_id("unique")
            entrada = api_error(ref)
            codigos.append(
                _status(entrada["status"], entrada["message"], error_ref=ref)
            )
            usados.append(ref)
        if _tiene_validaciones(table, endpoint):
            ref = constraint_error_id("check")
            entrada = api_error(ref)
            codigos.append(
                _status(entrada["status"], entrada["message"], error_ref=ref)
            )
            usados.append(ref)

    entrada = api_error("ERR-500")
    if entrada:
        codigos.append(_status(500, entrada["message"], error_ref="ERR-500"))
        usados.append("ERR-500")

    return codigos, usados


def _tiene_validaciones(table: dict, endpoint: dict) -> bool:
    """¿Hay algo que validar en el cuerpo de esta operación?

    Un ``422`` sin nada que pueda fallar es ruido en el contrato. Se declara si el
    modelo de datos tiene restricciones de comprobación o columnas obligatorias, o
    si la operación lleva cuerpo.
    """
    if table.get("check_constraints"):
        return True
    if any(not c.get("nullable", True) for c in table.get("columns", []) or []):
        return True
    return bool(endpoint.get("request_schema_ref"))


def _success_description(kind: str, resource: dict) -> str:
    singular = resource["singular"].replace("-", " ")
    plural = (resource.get("display_name") or resource["name"]).lower()
    return {
        "list": f"Listado paginado de {plural}.",
        "nested_list": f"Listado paginado de {plural}.",
        "read_item": f"Detalle de {singular}.",
        "create": f"Registro de {singular} creado.",
        "nested_create": f"Asociación de {singular} creada.",
        "update": f"Registro de {singular} actualizado.",
        "delete": f"Registro de {singular} eliminado.",
        "nested_delete": "Asociación eliminada.",
        "action": "Operación ejecutada.",
    }.get(kind, "Operación completada.")


def build_error_catalog(usados: set[str], tables: list[dict]) -> list[dict]:
    """Catálogo del artefacto: **solo** los errores que algún endpoint declara.

    Copiar el catálogo entero haría creer que todos pueden ocurrir. Cada entrada
    arrastra además las restricciones del modelo que la motivan, para poder ir del
    ``409`` a la clave única que lo provoca.
    """
    refs_unicas = [
        uq["id"]
        for table in tables
        for uq in table.get("unique_constraints", []) or []
        if uq.get("id")
    ]
    refs_check = [
        ck["id"]
        for table in tables
        for ck in table.get("check_constraints", []) or []
        if ck.get("id")
    ]

    catalogo: list[dict] = []
    for entrada in api_error_catalog():
        if entrada["id"] not in usados:
            continue
        item = {
            "id": entrada["id"],
            "status": entrada["status"],
            "code": entrada["code"],
            "message": entrada["message"],
            "when": entrada.get("when"),
            "source_refs": [],
        }
        if entrada["id"] == constraint_error_id("unique"):
            item["source_refs"] = refs_unicas
        elif entrada["id"] == constraint_error_id("check"):
            item["source_refs"] = refs_check
        catalogo.append(item)
    catalogo.sort(key=lambda e: (e["status"], e["id"]))
    return catalogo


def apply_errors(
    endpoints: list[dict],
    resource_map: dict,
    sources: dict[str, Any],
    authorization_matrix: Optional[list[dict]] = None,
    *,
    auth_required: bool = True,
) -> list[dict]:
    """Estampa los códigos de cada endpoint y devuelve el catálogo usado."""
    recursos = {r["id"]: r for r in resource_map.get("resources", []) or []}
    tablas = {t["id"]: t for t in (sources.get("bd", {}) or {}).get("tables", []) or []}
    acotados = _scoped_endpoints(authorization_matrix or [])

    usados: set[str] = set()
    for endpoint in endpoints:
        recurso = recursos.get(endpoint["resource_ref"], {})
        codigos, refs = status_codes_for(
            endpoint,
            recurso,
            _table_of(recurso, tablas),
            acotado=endpoint["id"] in acotados,
            auth_required=auth_required,
        )
        endpoint["status_codes"] = codigos
        usados.update(refs)

    return build_error_catalog(usados, list(tablas.values()))
