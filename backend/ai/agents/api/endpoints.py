"""Nodo ENDPOINTS: materializa las operaciones y añade las acciones de negocio.

Dos mitades con reglas muy distintas:

- **Determinista**: cada operación que RESOURCE_MAP fijó se convierte en un
  endpoint completo (método, ruta, ``operationId``, parámetros, paginación). No
  interviene el modelo: la matriz CRUD del EF ya decidió qué existe.
- **LLM**: las **acciones de negocio** (``POST /siniestros/{id}/cerrar``), única
  ampliación permitida. El modelo entrega un **verbo** y una **cita literal** del
  proceso o la regla que la respalda; Python construye la ruta y **verifica la
  cita** contra el texto original. Una acción cuya evidencia no aparece en el EF se
  descarta entera, con nota.

La verificación de la cita es la pieza que hace que esto no sea un acto de fe. Un
modelo puede parafrasear con convicción; lo que no puede es hacer aparecer una
frase en un documento que no la contiene.
"""

import json
import re
import unicodedata
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .naming import action_path, kebab, operation_id
from .prompts import build_system
from .schemas.extraction import ResourceActionsExtract

#: Plantillas del propósito por tipo de operación. En infinitivo y sin artículos:
#: el español obliga a decidir género para «el/la», y un artículo equivocado en
#: cada endpoint de la documentación se nota más que la ausencia de todos.
_PURPOSE = {
    "list": "Listar {plural}.",
    "read_item": "Obtener {singular} por su identificador.",
    "create": "Registrar {singular}.",
    "update": "Actualizar parcialmente {singular}.",
    "delete": "Eliminar {singular}.",
    "nested_list": "Listar {plural} de {padre}.",
    "nested_create": "Asociar {singular} a {padre}.",
    "nested_delete": "Desasociar {singular} de {padre}.",
}

#: Operaciones cuya respuesta es una página de resultados.
_PAGE_KINDS = ("list", "nested_list")

#: Operaciones que no devuelven cuerpo.
_EMPTY_KINDS = ("delete", "nested_delete")

_PARAM_RE = re.compile(r"\{(\w+)\}")


def _normalize(text: str) -> str:
    """Normaliza para comparar citas: sin acentos, minúsculas, sin puntuación.

    Se comparan las palabras, no los signos: exigir que una coma coincida haría
    fallar citas honestas, y admitir paráfrasis haría inútil la comprobación. El
    punto medio es comparar el texto desnudo.
    """
    limpio = unicodedata.normalize("NFD", text or "")
    limpio = "".join(ch for ch in limpio if unicodedata.category(ch) != "Mn")
    limpio = re.sub(r"[^0-9a-zA-Z]+", " ", limpio.lower())
    return re.sub(r"\s+", " ", limpio).strip()


def _texto_de(item: dict) -> str:
    """Todo el texto de un ítem del EF, para buscar dentro la cita."""
    partes: list[str] = []
    for valor in item.values():
        if isinstance(valor, str):
            partes.append(valor)
        elif isinstance(valor, list):
            partes.extend(v for v in valor if isinstance(v, str))
    return " ".join(partes)


def build_evidence_index(sources: dict[str, Any]) -> dict[str, str]:
    """Índice ``ref -> texto normalizado`` de lo que puede respaldar una acción."""
    ef = sources.get("ef", {}) or {}
    indice: dict[str, str] = {}
    for clave in ("processes", "business_rules", "validations"):
        for item in ef.get(clave, []) or []:
            if item.get("id"):
                indice[item["id"]] = _normalize(_texto_de(item))
    for item in (ef.get("requirements", {}) or {}).get("functional", []) or []:
        if item.get("id"):
            indice[item["id"]] = _normalize(_texto_de(item))
    return indice


# --- Endpoints deterministas --------------------------------------------------


def _purpose(operation: dict, resource: dict, padre: Optional[dict]) -> str:
    plantilla = _PURPOSE.get(operation["kind"], "{plural}.")
    return plantilla.format(
        plural=(resource.get("display_name") or resource["name"]).lower(),
        singular=resource["singular"].replace("-", " "),
        padre=(padre or {}).get("singular", "").replace("-", " ") if padre else "",
    )


def _path_parameters(operation: dict, resource: dict) -> list[dict]:
    """Parámetros de ruta, **derivados de la propia ruta**.

    Se leen los ``{marcadores}`` del path en vez de reconstruirlos: así es
    imposible que la ruta declare un parámetro que la operación no documenta, que
    es el desajuste que rompe a los generadores de cliente.
    """
    columnas = {c["name"]: c for c in resource.get("columns", [])}
    parametros: list[dict] = []
    for nombre in _PARAM_RE.findall(operation["path"]):
        columna = columnas.get(nombre) or {}
        parametros.append(
            {
                "name": nombre,
                "location": "path",
                "logical_type": columna.get("logical_type") or "string",
                "required": True,
                "description": columna.get("description")
                or f"Identificador de {nombre}.",
                "example": columna.get("example"),
                "column_ref": columna.get("column_ref"),
            }
        )
    return parametros


def _query_parameters(operation: dict, resource: dict, conventions: dict) -> list[dict]:
    """Paginación, orden y filtros de un listado (solo columnas indexadas)."""
    if not operation.get("paginated"):
        return []
    page = conventions.get("pagination", {}) or {}
    columnas = {c["name"]: c for c in resource.get("columns", [])}
    parametros: list[dict] = [
        {
            "name": page.get("limit_param", "limit"),
            "location": "query",
            "logical_type": "integer",
            "required": False,
            "description": (f"Tamaño de página (máximo {page.get('max_limit', 100)})."),
            "example": str(page.get("default_limit", 20)),
            "column_ref": None,
        },
        {
            "name": page.get("offset_param", "offset"),
            "location": "query",
            "logical_type": "integer",
            "required": False,
            "description": "Desplazamiento desde el inicio del listado.",
            "example": "0",
            "column_ref": None,
        },
    ]
    for nombre in resource.get("filterable", []):
        columna = columnas.get(nombre) or {}
        if columna.get("is_primary_key"):
            continue  # el detalle ya se obtiene por su ruta propia
        parametros.append(
            {
                "name": nombre,
                "location": "query",
                "logical_type": columna.get("logical_type") or "string",
                "required": False,
                "description": f"Filtra por {nombre}.",
                "example": columna.get("example"),
                "column_ref": columna.get("column_ref"),
            }
        )
    if resource.get("sortable"):
        parametros.append(
            {
                "name": conventions.get("sort_param", "sort"),
                "location": "query",
                "logical_type": "string",
                "required": False,
                "description": (
                    "Orden de los resultados; prefijo «-» para descendente. "
                    f"Campos: {', '.join(resource['sortable'])}."
                ),
                "example": f"-{resource['sortable'][0]}",
                "column_ref": None,
            }
        )
    return parametros


def build_endpoint(
    operation: dict,
    resource: dict,
    descrito: dict,
    padre: Optional[dict],
    conventions: dict,
) -> dict:
    """Convierte una operación del andamio en un endpoint del artefacto."""
    kind = operation["kind"]
    filtrables = [
        nombre
        for nombre in resource.get("filterable", [])
        if not next(
            (
                c
                for c in resource.get("columns", [])
                if c["name"] == nombre and c.get("is_primary_key")
            ),
            None,
        )
    ]
    return {
        "id": "",  # lo asigna number_endpoints
        "resource_ref": operation["resource_ref"],
        "method": operation["method"],
        "path": operation["path"],
        "operation_id": operation["operation_id"],
        "kind": kind,
        "purpose": _purpose(operation, descrito, padre),
        "description": None,
        "parameters": _path_parameters(operation, resource)
        + _query_parameters(operation, resource, conventions),
        "request_schema_ref": None,  # lo resuelve SCHEMAS (API4)
        "response_schema_ref": None,
        "response_kind": (
            "page"
            if kind in _PAGE_KINDS
            else "none" if kind in _EMPTY_KINDS else "item"
        ),
        "status_codes": [],  # los estampa ERRORS (API4)
        "filters": filtrables if operation.get("paginated") else [],
        "sortable": (
            list(resource.get("sortable", [])) if operation.get("paginated") else []
        ),
        "paginated": bool(operation.get("paginated")),
        "idempotent": bool(operation.get("idempotent")),
        "deprecated": False,
        "auth_rule_refs": [],  # los resuelve AUTHORIZATION (API5)
        "rule_refs": [],
        "ef_api_ref": operation.get("ef_api_ref"),
        "source_refs": list(operation.get("source_refs") or []),
        "confidence": 0.9 if operation.get("basis") == "crud_matrix" else 0.7,
        # Lo que el EF ya declaraba no se presenta como una idea del agente.
        "origin": "stated" if operation.get("ef_api_ref") else "derived",
    }


def number_endpoints(endpoints: list[dict]) -> None:
    """Asigna ids ``EP-001…`` y ``PRM-0001…`` en orden reproducible.

    Los parámetros se numeran aquí y no al construirlos porque su id es **global**:
    dos endpoints distintos pueden declarar un parámetro con el mismo nombre, y el
    id tiene que distinguirlos para que una referencia apunte a uno solo.
    """
    parametro = 0
    for posicion, endpoint in enumerate(endpoints, start=1):
        endpoint["id"] = f"EP-{posicion:03d}"
        for param in endpoint.get("parameters", []):
            parametro += 1
            param["id"] = f"PRM-{parametro:04d}"


# --- Acciones de negocio (LLM) ------------------------------------------------


def build_actions_user(resource: dict, sources: dict[str, Any]) -> str:
    """Compone el mensaje de un recurso: qué operaciones ya tiene y qué dice el EF."""
    ef = sources.get("ef", {}) or {}
    payload = {
        "resource": {
            "name": resource.get("name"),
            "singular": resource.get("singular"),
            "entity_ref": resource.get("entity_ref"),
        },
        "existing_operations": [op["kind"] for op in resource.get("operations", [])],
        "context": {
            "processes": [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "description": p.get("description"),
                    "steps": p.get("steps"),
                }
                for p in ef.get("processes", []) or []
            ],
            "business_rules": [
                {"id": r.get("id"), "statement": r.get("statement")}
                for r in ef.get("business_rules", []) or []
            ],
            "validations": [
                {"id": v.get("id"), "rule": v.get("rule")}
                for v in ef.get("validations", []) or []
            ],
        },
    }
    return "RECURSO Y CONTEXTO:\n" + json.dumps(payload, ensure_ascii=False)


def reconcile_actions(
    resource: dict,
    propuestas: list[dict],
    evidencias: dict[str, str],
    ocupados: set[tuple[str, str]],
    base: str,
) -> tuple[list[dict], list[dict]]:
    """Filtra las acciones propuestas. Devuelve ``(aceptadas, notas)``.

    Cuatro puertas, todas con nota; ninguna acción se descarta en silencio:

    1. El recurso debe admitir escritura y tener ruta de detalle.
    2. Los ``source_refs`` deben existir en el EF.
    3. La ``evidence`` debe aparecer **literalmente** en el texto de esos refs.
    4. El verbo no puede chocar con una ruta ya ocupada.
    """
    aceptadas: list[dict] = []
    notas: list[dict] = []

    for propuesta in propuestas:
        verbo = kebab(propuesta.get("action") or "")
        etiqueta = f"«{propuesta.get('action')}» sobre {resource['name']}"

        if resource.get("exposure") != "crud" or not resource.get("addressable"):
            notas.append(
                {
                    "description": f"Acción {etiqueta} descartada.",
                    "reason": (
                        "El recurso no se expone con escritura o no tiene ruta de "
                        "detalle, así que la acción no tendría dónde aplicarse."
                    ),
                }
            )
            continue

        if not verbo:
            notas.append(
                {
                    "description": f"Acción {etiqueta} descartada.",
                    "reason": "No se propuso un verbo utilizable para la ruta.",
                }
            )
            continue

        conocidos = [
            ref for ref in propuesta.get("source_refs") or [] if ref in evidencias
        ]
        if not conocidos:
            notas.append(
                {
                    "description": f"Acción {etiqueta} descartada.",
                    "reason": (
                        "Cita referencias que no existen en el EF: "
                        f"{', '.join(propuesta.get('source_refs') or []) or 'ninguna'} "
                        "(anti-invención)."
                    ),
                }
            )
            continue

        cita = _normalize(propuesta.get("evidence") or "")
        respaldo = " ".join(evidencias[ref] for ref in conocidos)
        if not cita or cita not in respaldo:
            notas.append(
                {
                    "description": f"Acción {etiqueta} descartada.",
                    "reason": (
                        "La evidencia citada no aparece literalmente en el texto de "
                        f"{', '.join(conocidos)}: no se puede confirmar que el EF "
                        "pida esta operación."
                    ),
                }
            )
            continue

        ruta = action_path(base, resource["segment"], resource["pk_column"], verbo)
        if ("POST", ruta) in ocupados:
            notas.append(
                {
                    "description": f"Acción {etiqueta} descartada.",
                    "reason": f"La ruta {ruta} ya está ocupada por otra operación.",
                }
            )
            continue

        ocupados.add(("POST", ruta))
        aceptadas.append(
            {
                "kind": "action",
                "method": "POST",
                "path": ruta,
                "operation_id": operation_id("action", resource["name"], accion=verbo),
                "action_verb": verbo,
                "resource_ref": resource["id"],
                "actor_refs": [],  # los resuelve AUTHORIZATION: nace denegada
                "basis": "business_rule",
                "crud_refs": [],
                "ef_api_ref": None,
                "source_refs": [*conocidos, *resource["source_refs"]],
                "paginated": False,
                "idempotent": False,
                "purpose": propuesta.get("purpose") or f"Ejecuta {verbo}.",
                "evidence": propuesta.get("evidence"),
                "request_needed": bool(propuesta.get("request_needed")),
                "rule_refs": conocidos,
                "confidence": propuesta.get("confidence"),
            }
        )
    return aceptadas, notas


async def run_actions(
    llm: LLMClient,
    resource_map: dict,
    sources: dict[str, Any],
    *,
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
) -> tuple[dict[str, list[dict]], list[dict], dict, list[dict]]:
    """Propone acciones de negocio para los recursos que admiten escritura.

    Devuelve ``(acciones_por_recurso, skipped, tokens, observaciones)``.
    """
    candidatos = [
        r
        for r in resource_map.get("resources", []) or []
        if r.get("exposure") == "crud" and r.get("addressable")
    ]
    if not candidatos:
        return {}, [], {"input": 0, "output": 0, "total": 0}, []

    context_block = knowledge_block(authoritative_context)
    system = build_system("endpoints.md", context_block)
    evidencias = build_evidence_index(sources)
    base = resource_map.get("base_path") or "/api/v1"

    results, skipped, tokens = await run_structured_map(
        llm,
        candidatos,
        build_system=lambda _: system,
        build_user=lambda item: build_actions_user(item, sources),
        schema=ResourceActionsExtract,
        ref_of=lambda item: item["id"],
        stage="endpoints",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
    )

    ocupados = {
        (op["method"], op["path"])
        for recurso in resource_map.get("resources", []) or []
        for op in recurso.get("operations", [])
    }
    por_ref = {r["ref"]: r["data"] for r in results}
    acciones: dict[str, list[dict]] = {}
    observaciones: list[dict] = []
    for candidato in candidatos:
        propuestas = (por_ref.get(candidato["id"]) or {}).get("actions", [])
        aceptadas, notas = reconcile_actions(
            candidato, propuestas, evidencias, ocupados, base
        )
        observaciones.extend(notas)
        if aceptadas:
            acciones[candidato["id"]] = aceptadas
    return acciones, skipped, tokens, observaciones


# --- Ensamblado ----------------------------------------------------------------


def merge_actions(resource_map: dict, acciones: dict[str, list[dict]]) -> None:
    """Incorpora las acciones aceptadas al andamio, **en el mismo sitio que el CRUD**.

    Sin esto, las acciones vivirían solo en la lista de endpoints y los nodos que
    leen el andamio —SCHEMAS para el cuerpo de entrada, ERRORS para los códigos—
    no las verían. Una operación en dos sitios distintos es una operación que
    tarde o temprano se trata de dos formas distintas.
    """
    for recurso in resource_map.get("resources", []) or []:
        nuevas = acciones.get(recurso["id"])
        if nuevas:
            recurso.setdefault("operations", []).extend(nuevas)


def build_endpoints(
    resource_map: dict, resources: list[dict], conventions: dict
) -> list[dict]:
    """Todos los endpoints del andamio, incluidas las acciones ya incorporadas."""
    descritos = {r["id"]: r for r in resources}
    por_id = {r["id"]: r for r in resource_map.get("resources", []) or []}

    endpoints: list[dict] = []
    for candidato in resource_map.get("resources", []) or []:
        padre = por_id.get(candidato.get("parent_resource_ref") or "")
        descrito = descritos.get(candidato["id"], candidato)
        for operacion in candidato.get("operations", []):
            endpoint = build_endpoint(
                operacion, candidato, descrito, padre, conventions
            )
            if operacion["kind"] == "action":
                endpoint["purpose"] = operacion["purpose"]
                endpoint["rule_refs"] = list(operacion.get("rule_refs") or [])
                endpoint["confidence"] = operacion.get("confidence") or 0.6
            endpoints.append(endpoint)

    number_endpoints(endpoints)
    return endpoints
