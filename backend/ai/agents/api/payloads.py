"""Nodo SCHEMAS: los contratos de datos de cada operación.

(El módulo se llama ``payloads`` y no ``schemas`` porque ``ai/agents/api/schemas/``
ya es el paquete del contrato del artefacto. El nodo del grafo sigue siendo
``SCHEMAS``.)

Híbrido, con el reparto de siempre:

- **Determinista**: la forma de cada esquema. ``create`` lleva las columnas que el
  cliente puede escribir; ``update`` las mismas pero todas opcionales (la
  actualización es parcial); ``read`` todo lo expuesto; ``list_item`` el resumen.
  La obligatoriedad, el tipo, la longitud y el ejemplo salen de la columna: el
  Agente API **no vuelve a decidir tipos**.
- **LLM**: dos decisiones que la máquina no puede tomar sola — qué columnas no
  deben salir y qué campos componen la fila de un listado.

Tres invariantes protegen el resultado, y las tres son de *usabilidad del
contrato*, no de gusto:

1. **La clave primaria no se puede ocultar**: sin identificador, el detalle es
   inalcanzable.
2. **Una columna obligatoria al crear no se puede ocultar**: el alta sería
   imposible de completar.
3. **Un campo sin columna no existe**: el conjunto llega cerrado y lo que el modelo
   nombre de más se descarta con nota.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .naming import schema_name
from .prompts import build_system
from .schemas.extraction import ResourceSchemaExtract

#: Formato del esquema por tipo lógico, cuando el tipo lo determina sin ambigüedad.
_FORMATS = {
    "date": "date",
    "time": "time",
    "timestamp": "date-time",
    "timestamptz": "date-time",
    "uuid": "uuid",
    "decimal": "decimal",
}

#: Tope de campos de un resumen. Un listado con todo no es un resumen.
_MAX_SUMMARY = 6


def _observation(description: str, reason: str) -> dict:
    return {"description": description, "reason": reason}


# --- Decisión de exposición (LLM) ---------------------------------------------


def build_schemas_user(resource: dict) -> str:
    """Compone el mensaje de un recurso: sus columnas y qué operaciones tiene."""
    payload = {
        "resource": {
            "name": resource.get("name"),
            "singular": resource.get("singular"),
        },
        "columns": [
            {
                "name": col.get("name"),
                "logical_type": col.get("logical_type"),
                "read_only": col.get("read_only"),
                "required": col.get("required"),
                "nullable": col.get("nullable"),
                "is_primary_key": col.get("is_primary_key"),
                "is_foreign_key": col.get("is_foreign_key"),
                "pii": col.get("pii"),
                "description": col.get("description"),
            }
            for col in resource.get("columns", [])
        ],
        "operations": [op["kind"] for op in resource.get("operations", [])],
    }
    return "RECURSO Y COLUMNAS:\n" + json.dumps(payload, ensure_ascii=False)


def reconcile_exposure(
    resource: dict, propuesta: Optional[dict]
) -> tuple[set[str], list[str], list[dict]]:
    """Aplica las decisiones del modelo con sus tres salvaguardas.

    Devuelve ``(ocultas, resumen, notas)``.
    """
    columnas = {c["name"]: c for c in resource.get("columns", [])}
    notas: list[dict] = []
    ocultas: set[str] = set()

    for propuesto in (propuesta or {}).get("hidden_columns", []) or []:
        nombre = propuesto.get("name")
        columna = columnas.get(nombre)
        if columna is None:
            notas.append(
                _observation(
                    f"No se ocultó «{nombre}» en {resource['name']}.",
                    "El modelo la nombró pero no es una columna del recurso.",
                )
            )
            continue
        # Primero se juzga la propuesta (¿está justificada?) y después la columna
        # (¿se puede prescindir de ella?). Así el motivo que se reporta es el que
        # el revisor necesita: si nadie explicó por qué, eso es lo que hay que
        # arreglar, aunque además fuera una columna imposible de ocultar.
        if not (propuesto.get("reason") or "").strip():
            notas.append(
                _observation(
                    f"No se ocultó «{nombre}» en {resource['name']}.",
                    "No se explicó por qué debía quedar fuera del contrato.",
                )
            )
            continue
        if columna.get("is_primary_key"):
            notas.append(
                _observation(
                    f"Se conservó «{nombre}» en {resource['name']} pese a la "
                    "propuesta de ocultarla.",
                    "Es la clave primaria: sin ella no se puede pedir el detalle.",
                )
            )
            continue
        if columna.get("required"):
            notas.append(
                _observation(
                    f"Se conservó «{nombre}» en {resource['name']} pese a la "
                    "propuesta de ocultarla.",
                    "Es obligatoria al crear: ocultarla haría imposible el alta.",
                )
            )
            continue
        ocultas.add(nombre)

    visibles = [
        c["name"] for c in resource.get("columns", []) if c["name"] not in ocultas
    ]
    resumen = [
        n for n in (propuesta or {}).get("summary_columns", []) or [] if n in visibles
    ]
    if not resumen:
        resumen = _summary_fallback(resource, visibles)
    else:
        clave = next(
            (c["name"] for c in resource.get("columns", []) if c.get("is_primary_key")),
            None,
        )
        if clave and clave not in resumen:
            resumen.insert(0, clave)
        if len(resumen) > _MAX_SUMMARY:
            notas.append(
                _observation(
                    f"El resumen de {resource['name']} se recortó a "
                    f"{_MAX_SUMMARY} campos.",
                    f"Se propusieron {len(resumen)}; un listado con todo no es un "
                    "resumen. Recortados: "
                    f"{', '.join(resumen[_MAX_SUMMARY:])}.",
                )
            )
            resumen = resumen[:_MAX_SUMMARY]
    return ocultas, resumen, notas


def _summary_fallback(resource: dict, visibles: list[str]) -> list[str]:
    """Resumen sin LLM: la clave, las claves foráneas y lo corto que quede."""
    columnas = {c["name"]: c for c in resource.get("columns", [])}
    resumen = [n for n in visibles if columnas[n].get("is_primary_key")]
    for nombre in visibles:
        if len(resumen) >= 4:
            break
        columna = columnas[nombre]
        if nombre in resumen or columna.get("logical_type") in (
            "text",
            "json",
            "binary",
        ):
            continue
        resumen.append(nombre)
    return resumen


# --- Construcción de esquemas (determinista) ----------------------------------


def _field(column: dict, *, required: bool, read_only: bool) -> dict:
    """Campo de esquema desde una columna. El tipo se hereda, no se re-decide."""
    logical = column.get("logical_type") or "string"
    return {
        "id": "",  # lo asigna number_schema_fields
        "name": column["name"],
        "logical_type": logical,
        "format": _FORMATS.get(logical),
        "required": required,
        "nullable": bool(column.get("nullable", True)),
        "read_only": read_only,
        "write_only": False,
        "max_length": column.get("max_length"),
        "enum": column.get("enum"),
        "description": column.get("description"),
        "example": column.get("example"),
        "column_ref": column.get("column_ref"),
        "table_ref": None,  # lo completa build_schemas con el del recurso
        "computed": False,
        "pii": bool(column.get("pii")),
        "source_refs": list(column.get("source_refs") or []),
        "confidence": None,
        "origin": "derived",
    }


def _schema(
    kind: str, resource: dict, fields: list[dict], description: str, confidence
) -> dict:
    return {
        "id": "",  # lo asigna number_schemas
        "name": schema_name(kind, resource["name"]),
        "kind": kind,
        "resource_ref": resource["id"],
        "description": description,
        "fields": fields,
        "source_refs": [resource["table_ref"]],
        "confidence": confidence,
        "origin": "derived",
    }


def build_resource_schemas(
    resource: dict, ocultas: set[str], resumen: list[str], confidence
) -> list[dict]:
    """Los esquemas de un recurso, según las operaciones que tenga.

    Solo se crea lo que alguna operación va a usar: un esquema de creación para un
    recurso de solo lectura sería ruido en el documento.
    """
    tipos = {op["kind"] for op in resource.get("operations", [])}
    columnas = [c for c in resource.get("columns", []) if c["name"] not in ocultas]
    escribibles = [c for c in columnas if not c.get("read_only")]
    esquemas: list[dict] = []
    singular = resource["singular"].replace("-", " ")

    if {"create", "nested_create"} & tipos:
        esquemas.append(
            _schema(
                "create",
                resource,
                [
                    _field(c, required=bool(c.get("required")), read_only=False)
                    for c in escribibles
                ],
                f"Datos necesarios para registrar {singular}.",
                confidence,
            )
        )
    if "update" in tipos:
        esquemas.append(
            _schema(
                "update",
                resource,
                # Actualización parcial: nada es obligatorio, se envía lo que cambia.
                [_field(c, required=False, read_only=False) for c in escribibles],
                f"Campos modificables de {singular}. Todos opcionales.",
                confidence,
            )
        )
    if {"create", "update", "read_item", "action", "nested_create"} & tipos:
        esquemas.append(
            _schema(
                "read",
                resource,
                [
                    _field(
                        c,
                        required=not c.get("nullable", True),
                        read_only=bool(c.get("read_only")),
                    )
                    for c in columnas
                ],
                resource.get("description") or f"Representación de {singular}.",
                confidence,
            )
        )
    if {"list", "nested_list"} & tipos:
        por_nombre = {c["name"]: c for c in columnas}
        esquemas.append(
            _schema(
                "list_item",
                resource,
                [
                    _field(
                        por_nombre[n],
                        required=not por_nombre[n].get("nullable", True),
                        read_only=bool(por_nombre[n].get("read_only")),
                    )
                    for n in resumen
                    if n in por_nombre
                ],
                f"Vista reducida de {singular} para listados.",
                confidence,
            )
        )
    acciones = sorted(
        (op for op in resource.get("operations", []) if op["kind"] == "action"),
        key=lambda op: op["operation_id"],
    )
    for accion in acciones:
        if not accion.get("request_needed"):
            continue
        # El EF describe la acción pero no qué datos hay que enviarle. Se declara
        # el esquema vacío en vez de inventarle campos: el hueco se ve, y
        # QUESTION_GEN lo convertirá en pregunta.
        esquema = _schema(
            "action_input",
            resource,
            [],
            (
                f"Datos de entrada de «{accion['operation_id']}». **Por definir**: "
                "el EF describe la acción pero no qué información hay que enviar."
            ),
            confidence,
        )
        esquema["name"] = schema_name(
            "action_input", resource["name"], accion=accion.get("action_verb", "")
        )
        esquema["action_verb"] = accion.get("action_verb")
        esquemas.append(esquema)
    return esquemas


def number_schemas(schemas: list[dict]) -> None:
    """Asigna ids ``SCH-001…`` y ``SF-0001…`` en orden reproducible."""
    campo = 0
    for posicion, esquema in enumerate(schemas, start=1):
        esquema["id"] = f"SCH-{posicion:03d}"
        for field in esquema["fields"]:
            campo += 1
            field["id"] = f"SF-{campo:04d}"


def attach_schema_refs(endpoints: list[dict], schemas: list[dict]) -> list[dict]:
    """Enlaza cada endpoint con los esquemas que usa. Devuelve las notas.

    Un endpoint sin esquema de respuesta cuando debería tenerlo no se calla: es un
    contrato incompleto y hay que verlo.
    """
    por_recurso: dict[str, dict[str, dict]] = {}
    for esquema in schemas:
        por_recurso.setdefault(esquema["resource_ref"], {})[esquema["kind"]] = esquema

    notas: list[dict] = []
    for endpoint in endpoints:
        disponibles = por_recurso.get(endpoint["resource_ref"], {})
        kind = endpoint["kind"]
        if kind in ("create", "nested_create"):
            endpoint["request_schema_ref"] = (disponibles.get("create") or {}).get("id")
            endpoint["response_schema_ref"] = (disponibles.get("read") or {}).get("id")
        elif kind == "update":
            endpoint["request_schema_ref"] = (disponibles.get("update") or {}).get("id")
            endpoint["response_schema_ref"] = (disponibles.get("read") or {}).get("id")
        elif kind in ("list", "nested_list"):
            endpoint["response_schema_ref"] = (disponibles.get("list_item") or {}).get(
                "id"
            )
        elif kind == "read_item":
            endpoint["response_schema_ref"] = (disponibles.get("read") or {}).get("id")
        elif kind == "action":
            verbo = endpoint["path"].rsplit("/", 1)[-1]
            entrada = next(
                (
                    e
                    for e in schemas
                    if e["kind"] == "action_input"
                    and e["resource_ref"] == endpoint["resource_ref"]
                    and e.get("action_verb") == verbo
                ),
                None,
            )
            endpoint["request_schema_ref"] = (entrada or {}).get("id")
            endpoint["response_schema_ref"] = (disponibles.get("read") or {}).get("id")

        if endpoint["response_kind"] != "none" and not endpoint["response_schema_ref"]:
            notas.append(
                _observation(
                    f"El endpoint {endpoint['operation_id']} no declara el esquema "
                    "de su respuesta.",
                    "No se pudo construir el esquema del recurso; el contrato queda "
                    "incompleto para quien lo consuma.",
                )
            )
    return notas


async def run_schemas(
    llm: LLMClient,
    resource_map: dict,
    endpoints: list[dict],
    *,
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
) -> tuple[list[dict], list[dict], dict, list[dict]]:
    """Construye todos los esquemas y los enlaza con los endpoints.

    Devuelve ``(schemas, skipped, tokens, observations)``.
    """
    candidatos = [
        r for r in resource_map.get("resources", []) or [] if r.get("operations")
    ]
    if not candidatos:
        return [], [], {"input": 0, "output": 0, "total": 0}, []

    system = build_system("schemas.md", knowledge_block(authoritative_context))
    results, skipped, tokens = await run_structured_map(
        llm,
        candidatos,
        build_system=lambda _: system,
        build_user=build_schemas_user,
        schema=ResourceSchemaExtract,
        ref_of=lambda item: item["id"],
        stage="schemas",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
    )

    por_ref = {r["ref"]: r["data"] for r in results}
    esquemas: list[dict] = []
    observaciones: list[dict] = []
    for candidato in candidatos:
        propuesta = por_ref.get(candidato["id"])
        ocultas, resumen, notas = reconcile_exposure(candidato, propuesta)
        observaciones.extend(notas)
        nuevos = build_resource_schemas(
            candidato, ocultas, resumen, (propuesta or {}).get("confidence")
        )
        for esquema in nuevos:
            for field in esquema["fields"]:
                field["table_ref"] = candidato["table_ref"]
        esquemas.extend(nuevos)

    number_schemas(esquemas)
    observaciones.extend(attach_schema_refs(endpoints, esquemas))
    # `action_verb` es andamiaje para emparejar el esquema con su acción; no
    # pertenece al contrato del artefacto y se retira antes de ensamblarlo.
    for esquema in esquemas:
        esquema.pop("action_verb", None)
    return esquemas, skipped, tokens, observaciones
