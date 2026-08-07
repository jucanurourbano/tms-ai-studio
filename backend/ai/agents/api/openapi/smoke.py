"""Capa L3a: que un runtime real pueda **usar** el documento, no solo parsearlo.

Es el análogo de la prueba de humo contra SQLite del Agente BD, y existe por la
misma razón: el Agente BD descubrió con ella un bug del generador que la validación
de sintaxis no veía. Que un documento cumpla el esquema de OpenAPI no garantiza que
una librería cliente sepa resolver sus referencias y validar una respuesta real
contra él.

Vive fuera del pipeline y se usa desde los tests. ``openapi-core`` es dependencia
**solo de test**: la validación en tiempo de ejecución no debe depender de ella.

Limitación declarada: se comprueba una petición y una respuesta **sintéticas**,
construidas con los ejemplos de los propios campos. Prueba que el documento es
navegable y que sus esquemas aceptan datos con la forma que dicen aceptar; no
prueba el sistema. Por eso el artefacto solo pone ``runtime_checked=True`` cuando
esta capa se ejecuta, y nunca la presenta como una certificación del servicio.
"""

from typing import Any, Optional


def build_spec(document: dict):
    """Construye el objeto ``OpenAPI`` de ``openapi-core`` (import perezoso)."""
    from openapi_core import OpenAPI

    return OpenAPI.from_dict(document)


def _sample(field_schema: dict) -> Any:
    """Valor sintético coherente con el tipo declarado en el esquema."""
    ejemplos = field_schema.get("examples")
    if ejemplos:
        valor = ejemplos[0]
        tipos = field_schema.get("type")
        tipos = tipos if isinstance(tipos, list) else [tipos]
        if "integer" in tipos and not isinstance(valor, int):
            return 1
        return valor
    tipos = field_schema.get("type")
    tipos = tipos if isinstance(tipos, list) else [tipos]
    if "integer" in tipos:
        return 1
    if "number" in tipos:
        return 1.0
    if "boolean" in tipos:
        return True
    if "array" in tipos:
        return []
    if "object" in tipos:
        return {}
    return "x"


def sample_payload(document: dict, schema_name: str) -> dict:
    """Cuerpo de ejemplo que cumple un esquema del documento.

    Solo se rellenan las propiedades **requeridas**: es lo mínimo que un cliente
    tendría que enviar, y por tanto lo que interesa comprobar.
    """
    esquema = (document.get("components", {}).get("schemas") or {}).get(schema_name, {})
    requeridos = esquema.get("required") or []
    propiedades = esquema.get("properties") or {}
    return {nombre: _sample(propiedades.get(nombre, {})) for nombre in requeridos}


def check_runtime(
    document: dict,
    method: str,
    path: str,
    *,
    status: int = 200,
    body: Optional[dict] = None,
) -> list[str]:
    """Valida una respuesta sintética contra el documento. Devuelve los errores.

    Lista vacía = un runtime real navegó el documento, encontró la operación y
    aceptó una respuesta con la forma declarada.
    """
    import json

    from openapi_core.testing import MockRequest, MockResponse

    try:
        spec = build_spec(document)
        request = MockRequest("http://servidor", method.lower(), path)
        response = MockResponse(
            json.dumps(body if body is not None else {}).encode("utf-8"),
            status_code=status,
        )
        spec.validate_response(request, response)
    except Exception as exc:  # noqa: BLE001 - el fallo es el resultado del test
        return [f"{type(exc).__name__}: {exc}"[:300]]
    return []
