"""Render determinista del documento OpenAPI 3.1.

**El LLM no escribe una sola línea de esto.** Igual que el Agente BD renderiza el
DDL desde el modelo estructurado, aquí el documento se construye desde
``resources``/``schemas``/``endpoints``/``authorization_matrix``/``error_catalog``.
Por eso el YAML es válido por construcción, y por eso volver a emitirlo en JSON o
degradarlo a 3.0.3 costaría cero llamadas al modelo.

Dos consecuencias prácticas de que esto sea determinista:

- **Dos corridas del mismo contrato producen el mismo YAML byte a byte.** Las rutas
  y las claves se ordenan siempre igual, así que un diff entre dos versiones del
  documento muestra cambios reales del contrato y no ruido de serialización.
- **El envelope de la casa lo pone el renderizador**, no el modelo. No puede
  olvidarlo en un endpoint ni inventarse otra forma en el siguiente.

Detalles de **3.1** que no son los de 3.0 y que aquí se respetan a propósito: la
nulabilidad va en el propio ``type`` (``[string, "null"]``) y no en un
``nullable: true`` que 3.1 ignoraría en silencio; los ejemplos dentro de un esquema
son ``examples`` (lista); y un binario usa ``contentEncoding``.
"""

import hashlib
from typing import Any, Optional

import yaml

from ai.knowledge import load_api_conventions, openapi_type

#: Nombre del esquema de error en el documento (uno solo, compartido).
ERROR_SCHEMA = "ApiResponseError"

#: Respuestas compartidas por código de estado.
_RESPONSE_NAMES = {
    400: "PeticionInvalida",
    401: "NoAutenticado",
    403: "SinPermiso",
    404: "NoEncontrado",
    409: "Conflicto",
    422: "ValidacionFallida",
    500: "ErrorInterno",
}


def _security_scheme(scheme: str) -> dict:
    """Definición del esquema de seguridad desde las convenciones."""
    esquemas = (load_api_conventions().get("security", {}) or {}).get(
        "schemes", {}
    ) or {}
    cfg = esquemas.get(scheme, {}) or {}
    if cfg.get("type") == "http":
        rendered = {"type": "http", "scheme": cfg.get("scheme", "bearer")}
        if cfg.get("bearer_format"):
            rendered["bearerFormat"] = cfg["bearer_format"]
        return rendered
    if cfg.get("type") == "apiKey":
        return {
            "type": "apiKey",
            "in": cfg.get("in", "header"),
            "name": cfg.get("name", "X-API-Key"),
        }
    if cfg.get("type") == "openIdConnect":
        # Sin URL de descubrimiento conocida no se inventa una: se declara como
        # bearer y la pregunta al líder técnico ya está planteada por LOAD_SOURCES.
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}


def _scheme_key(scheme: str) -> str:
    """Nombre con el que el esquema de seguridad aparece en el documento."""
    return {"api_key": "apiKeyAuth"}.get(scheme, "bearerAuth")


# --- Esquemas de datos ---------------------------------------------------------


def _property(field: dict) -> dict:
    """Propiedad de un esquema desde un campo del contrato.

    El tipo se traduce del ``logical_type`` que ya eligió el modelo de datos; aquí
    no se re-decide nada.
    """
    base = dict(openapi_type(field.get("logical_type") or "string"))
    if field.get("format"):
        base["format"] = field["format"]
    tipo = base.get("type")
    # 3.1: la nulabilidad es parte del tipo. `nullable: true` es de 3.0 y aquí se
    # ignoraría en silencio, produciendo un cliente que no admite nulos.
    if field.get("nullable") and not field.get("required") and tipo:
        base["type"] = [tipo, "null"]
    if field.get("max_length") and base.get("type") in ("string", ["string", "null"]):
        base["maxLength"] = field["max_length"]
    if field.get("enum"):
        base["enum"] = list(field["enum"])
    if field.get("read_only"):
        base["readOnly"] = True
    if field.get("write_only"):
        base["writeOnly"] = True
    if field.get("description"):
        base["description"] = field["description"]
    if field.get("example") is not None:
        base["examples"] = [field["example"]]
    return base


def _data_schema(schema: dict) -> dict:
    """Un ``components.schemas`` desde un esquema del artefacto."""
    propiedades = {f["name"]: _property(f) for f in schema.get("fields", [])}
    requeridos = [f["name"] for f in schema.get("fields", []) if f.get("required")]
    rendered: dict[str, Any] = {"type": "object"}
    if schema.get("description"):
        rendered["description"] = schema["description"]
    rendered["properties"] = propiedades
    if requeridos:
        rendered["required"] = requeridos
    return rendered


def _envelope(data_schema: dict, description: str) -> dict:
    """Envuelve un esquema en el ``ApiResponse`` de la casa (API8)."""
    conv = load_api_conventions().get("envelope", {}) or {}
    return {
        "type": "object",
        "description": description,
        "properties": {
            conv.get("success_field", "success"): {"type": "boolean"},
            conv.get("message_field", "message"): {"type": "string"},
            conv.get("data_field", "data"): data_schema,
        },
        "required": [
            conv.get("success_field", "success"),
            conv.get("message_field", "message"),
            conv.get("data_field", "data"),
        ],
    }


def _page(item_ref: str, conventions: dict) -> dict:
    """Página de resultados con la forma acordada (API10: offset/limit)."""
    page = conventions.get("pagination", {}) or {}
    return {
        "type": "object",
        "description": "Página de resultados.",
        "properties": {
            page.get("items_field", "items"): {
                "type": "array",
                "items": {"$ref": f"#/components/schemas/{item_ref}"},
            },
            page.get("total_field", "total"): {"type": "integer"},
            page.get("limit_param", "limit"): {"type": "integer"},
            page.get("offset_param", "offset"): {"type": "integer"},
        },
        "required": [
            page.get("items_field", "items"),
            page.get("total_field", "total"),
            page.get("limit_param", "limit"),
            page.get("offset_param", "offset"),
        ],
    }


def _error_schema() -> dict:
    conv = load_api_conventions().get("envelope", {}) or {}
    return {
        "type": "object",
        "description": "Respuesta de error con código estable.",
        "properties": {
            conv.get("success_field", "success"): {"type": "boolean"},
            conv.get("message_field", "message"): {"type": "string"},
            conv.get("data_field", "data"): {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        },
        "required": [
            conv.get("success_field", "success"),
            conv.get("message_field", "message"),
            conv.get("data_field", "data"),
        ],
    }


# --- Operaciones ---------------------------------------------------------------


def _parameter(param: dict) -> dict:
    esquema = dict(openapi_type(param.get("logical_type") or "string"))
    rendered = {
        "name": param["name"],
        "in": param["location"],
        "required": bool(param.get("required")),
        "schema": esquema,
    }
    if param.get("description"):
        rendered["description"] = param["description"]
    if param.get("example") is not None:
        rendered["example"] = param["example"]
    return rendered


def _operation(
    endpoint: dict,
    esquemas_por_id: dict[str, dict],
    tag: Optional[str],
    envueltos: dict[str, str],
) -> dict:
    operacion: dict[str, Any] = {"operationId": endpoint["operation_id"]}
    if tag:
        operacion["tags"] = [tag]
    operacion["summary"] = endpoint["purpose"]
    if endpoint.get("description"):
        operacion["description"] = endpoint["description"]
    if endpoint.get("deprecated"):
        operacion["deprecated"] = True
    if endpoint.get("parameters"):
        operacion["parameters"] = [_parameter(p) for p in endpoint["parameters"]]

    entrada = esquemas_por_id.get(endpoint.get("request_schema_ref") or "")
    if entrada is not None:
        operacion["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{entrada['name']}"}
                }
            },
        }

    respuestas: dict[str, Any] = {}
    for status in endpoint.get("status_codes", []):
        codigo = str(status["code"])
        if status.get("error_ref"):
            nombre = _RESPONSE_NAMES.get(status["code"])
            if nombre:
                respuestas[codigo] = {"$ref": f"#/components/responses/{nombre}"}
                continue
        cuerpo: dict[str, Any] = {
            "description": status.get("description") or "Operación completada."
        }
        envuelto = envueltos.get(endpoint["id"])
        if envuelto and endpoint.get("response_kind") != "none":
            cuerpo["content"] = {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{envuelto}"}
                }
            }
        if endpoint["kind"] in ("create", "nested_create") and status["code"] == 201:
            cuerpo["headers"] = {
                "Location": {
                    "description": "Ruta del recurso creado.",
                    "schema": {"type": "string"},
                }
            }
        respuestas[codigo] = cuerpo
    operacion["responses"] = respuestas
    return operacion


# --- Documento completo --------------------------------------------------------


def _title(sources: dict[str, Any]) -> str:
    """Título del documento, desde el resumen del EF si lo hay."""
    resumen = (sources.get("ef", {}) or {}).get("summary") or ""
    if not resumen:
        return "API del sistema"
    primera = resumen.split(".")[0].strip()
    return f"API — {primera}" if primera else "API del sistema"


def _tags(resources: list[dict], sources: dict[str, Any]) -> tuple[list[dict], dict]:
    """Agrupación por componente de Arquitectura. Devuelve ``(tags, por_recurso)``."""
    componentes = {
        c["id"]: c
        for c in (sources.get("architecture", {}) or {}).get("components", []) or []
        if c.get("id")
    }
    por_recurso: dict[str, str] = {}
    vistos: dict[str, str] = {}
    for recurso in resources:
        componente = componentes.get(recurso.get("component_ref") or "")
        nombre = (
            componente.get("name")
            if componente
            else (recurso.get("display_name") or recurso["name"])
        )
        por_recurso[recurso["id"]] = nombre
        if nombre not in vistos:
            vistos[nombre] = (
                componente.get("responsibility")
                if componente
                else recurso.get("description")
            ) or ""
    tags = [
        (
            {"name": nombre, "description": descripcion}
            if descripcion
            else {"name": nombre}
        )
        for nombre, descripcion in sorted(vistos.items())
    ]
    return tags, por_recurso


def build_document(
    target: dict,
    resources: list[dict],
    schemas: list[dict],
    endpoints: list[dict],
    error_catalog: list[dict],
    sources: dict[str, Any],
) -> dict:
    """Construye el documento OpenAPI 3.1 como ``dict`` (sin serializar)."""
    conventions = target.get("conventions") or {}
    esquemas_por_id = {s["id"]: s for s in schemas}
    tags, tag_por_recurso = _tags(resources, sources)

    componentes_schemas: dict[str, Any] = {}
    for esquema in schemas:
        componentes_schemas[esquema["name"]] = _data_schema(esquema)

    # Envoltorios: uno por forma de respuesta realmente usada, no uno por si acaso.
    envueltos: dict[str, str] = {}
    for endpoint in endpoints:
        esquema = esquemas_por_id.get(endpoint.get("response_schema_ref") or "")
        if esquema is None or endpoint.get("response_kind") == "none":
            continue
        if endpoint["response_kind"] == "page":
            page_name = f"Page{esquema['name']}"
            componentes_schemas.setdefault(
                page_name, _page(esquema["name"], conventions)
            )
            envoltorio = f"ApiResponse{page_name}"
            componentes_schemas.setdefault(
                envoltorio,
                _envelope(
                    {"$ref": f"#/components/schemas/{page_name}"},
                    "Respuesta con una página de resultados.",
                ),
            )
        else:
            envoltorio = f"ApiResponse{esquema['name']}"
            componentes_schemas.setdefault(
                envoltorio,
                _envelope(
                    {"$ref": f"#/components/schemas/{esquema['name']}"},
                    "Respuesta con un único recurso.",
                ),
            )
        envueltos[endpoint["id"]] = envoltorio

    componentes_schemas[ERROR_SCHEMA] = _error_schema()

    respuestas: dict[str, Any] = {}
    for entrada in error_catalog:
        nombre = _RESPONSE_NAMES.get(entrada["status"])
        if not nombre or nombre in respuestas:
            continue
        respuestas[nombre] = {
            "description": entrada.get("when") or entrada["message"],
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{ERROR_SCHEMA}"}
                }
            },
        }

    paths: dict[str, Any] = {}
    for endpoint in sorted(endpoints, key=lambda e: (e["path"], e["method"])):
        tag = tag_por_recurso.get(endpoint["resource_ref"])
        paths.setdefault(endpoint["path"], {})[endpoint["method"].lower()] = _operation(
            endpoint, esquemas_por_id, tag, envueltos
        )

    auth = target.get("auth") or {}
    clave = _scheme_key(auth.get("scheme") or "bearer_jwt")

    documento: dict[str, Any] = {
        "openapi": target.get("spec_version") or "3.1.0",
        "info": {
            "title": _title(sources),
            "version": "1.0.0",
            "description": (
                "Contrato generado por el Agente API del ISDF a partir del modelo "
                "de datos y el análisis funcional."
            ),
        },
        # El servidor es la raíz **a propósito**: las rutas de `paths` ya llevan el
        # prefijo completo (`/api/v1/siniestros`), que es como viajan en el
        # artefacto y como se ven en el hub. Declarar además `url: /api/v1` haría
        # que la URL efectiva fuera `/api/v1/api/v1/siniestros`. El validador de
        # esquema no ve ese error —es semántico, no sintáctico— y lo encontró la
        # capa L3a al pedirle a un runtime real que resolviera una operación.
        "servers": [{"url": "/", "description": "Servidor de la aplicación."}],
    }
    if tags:
        documento["tags"] = tags
    documento["security"] = [{clave: []}]
    documento["paths"] = dict(sorted(paths.items()))
    documento["components"] = {
        "securitySchemes": {
            clave: _security_scheme(auth.get("scheme") or "bearer_jwt")
        },
        "schemas": dict(sorted(componentes_schemas.items())),
        "responses": dict(sorted(respuestas.items())),
    }
    return documento


def to_yaml(document: dict) -> str:
    """Serializa el documento con orden estable (mismo contrato ⇒ mismo YAML)."""
    return yaml.safe_dump(
        document,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    )


def build_openapi(
    target: dict,
    resources: list[dict],
    schemas: list[dict],
    endpoints: list[dict],
    error_catalog: list[dict],
    sources: dict[str, Any],
) -> tuple[dict, dict]:
    """Documento + el bloque ``openapi`` del artefacto. Devuelve ``(doc, bloque)``."""
    documento = build_document(
        target, resources, schemas, endpoints, error_catalog, sources
    )
    contenido = to_yaml(documento)
    return documento, {
        "format": "yaml",
        "spec_version": documento["openapi"],
        "content": contenido,
        "operations_total": sum(len(ops) for ops in documento["paths"].values()),
        "byte_size": len(contenido.encode("utf-8")),
        "checksum": "sha256:" + hashlib.sha256(contenido.encode("utf-8")).hexdigest(),
    }
