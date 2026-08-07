"""Nodo LOAD_SOURCES: única fuente de verdad del Agente API.

Cuatro responsabilidades:

1. **Gate de entrada** (defensivo): el modelo de datos debe estar listo
   (``ready_for_next_stage=true``). El servicio ya lo verificó antes de crear el
   job; aquí se re-verifica porque un refine o un reintento podrían partir de un
   estado distinto.
2. **Contexto consolidado**: del **BD** (la materia prima) las tablas con sus
   columnas, claves, índices, semillas y el destino de las reglas; del **EF** los
   actores, la matriz CRUD, las APIs ya declaradas, las reglas y los procesos; de
   la **Arquitectura** los componentes (que agrupan los recursos), el stack y los
   transversales.
3. **Resolución del estilo de API**: qué se está diseñando y de dónde salió.
4. **Resolución del esquema de seguridad**: cómo se autentica, desde la capa
   ``auth`` del stack.

El Scrum no participa del diseño: se carga solo para completar la trazabilidad de
la cadena en ``source``.
"""

from typing import Any, Optional

from ai.errors import GateError
from ai.knowledge import (
    load_api_conventions,
    load_tech_stack,
    security_scheme_for,
)

#: Capas del ``stack[]`` de Arquitectura que fijan estilo y autenticación.
API_STYLE_LAYER = "api_style"
AUTH_LAYER = "auth"

#: Nombres de producto del allow-list → clave del estilo. Se compara normalizado.
_STYLE_ALIASES = {
    "rest": "rest",
    "restful": "rest",
    "graphql": "graphql",
    "grpc": "grpc",
    "soap": "soap",
}

#: Único estilo que v1 sabe especificar. El resto se **declara y se pregunta**:
#: entregar un documento REST cuando la arquitectura pidió GraphQL sería peor que
#: no entregar nada, porque nadie notaría el desajuste hasta construirlo.
SUPPORTED_STYLE = "rest"


def assert_bd_ready(ready: bool, bd_job_id: str) -> None:
    """Re-verifica el gate de entrada; si no está listo, corta con ``GateError``."""
    if not ready:
        raise GateError(
            f"El modelo de datos {bd_job_id} no está listo para especificar la API: "
            "quedan preguntas bloqueantes al DBA sin responder o el DDL no es "
            "válido. Complétalas o genera un modelo afinado "
            f"(POST /bd/jobs/{bd_job_id}/refine)."
        )


def extract_sources(
    bd_artifact: dict[str, Any],
    ef_artifact: dict[str, Any],
    architecture_artifact: Optional[dict[str, Any]] = None,
    scrum_artifact: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Consolida las dimensiones de BD + EF + Arquitectura que necesita la API."""
    bd_artifact = bd_artifact or {}
    ef_artifact = ef_artifact or {}
    architecture_artifact = architecture_artifact or {}
    scrum_artifact = scrum_artifact or {}
    requirements = ef_artifact.get("requirements", {}) or {}
    return {
        "bd": {
            "target": bd_artifact.get("target", {}) or {},
            "tables": bd_artifact.get("tables", []) or [],
            "seed_data": bd_artifact.get("seed_data", []) or [],
            # Lo que el modelo de datos NO pudo hacer cumplir: es la lista de
            # reglas que esta API tiene que recoger para que no desaparezcan.
            "rule_mappings": bd_artifact.get("rule_mappings", []) or [],
        },
        "ef": {
            "summary": ef_artifact.get("summary"),
            "actors": ef_artifact.get("actors", []) or [],
            "crud": ef_artifact.get("crud", []) or [],
            "apis": ef_artifact.get("apis", []) or [],
            "business_rules": ef_artifact.get("business_rules", []) or [],
            "validations": ef_artifact.get("validations", []) or [],
            "processes": ef_artifact.get("processes", []) or [],
            "entities": ef_artifact.get("entities", []) or [],
            "modules": ef_artifact.get("modules", []) or [],
            "requirements": {
                "functional": requirements.get("functional", []) or [],
                "non_functional": requirements.get("non_functional", []) or [],
            },
        },
        "architecture": {
            "style": (architecture_artifact.get("architecture_style") or {}).get(
                "chosen"
            ),
            "stack": architecture_artifact.get("stack", []) or [],
            "components": architecture_artifact.get("components", []) or [],
            "cross_cutting": architecture_artifact.get("cross_cutting", []) or [],
            "integrations": architecture_artifact.get("integrations", []) or [],
        },
        # Solo trazabilidad de la cadena: el Scrum no alimenta el contrato.
        "scrum": {"epics": scrum_artifact.get("epics", []) or []},
    }


def _normalize_style(value: str) -> Optional[str]:
    """Traduce un nombre de producto a la clave del estilo, o ``None``."""
    key = "".join((value or "").lower().split()).replace("-", "").replace("_", "")
    return _STYLE_ALIASES.get(key)


def _stack_layer(sources: dict[str, Any], layer: str) -> Optional[dict]:
    """Primera elección del stack para una capa, si la arquitectura la decidió."""
    for choice in (sources.get("architecture", {}) or {}).get("stack", []) or []:
        if choice.get("layer") == layer:
            return choice
    return None


def _stack_default(layer: str) -> Optional[str]:
    """Valor por defecto de la capa en ``tech_stack.yaml``."""
    layers = load_tech_stack().get("layers", {}) or {}
    return (layers.get(layer, {}) or {}).get("default")


def resolve_api_style(
    sources: dict[str, Any], override: Optional[str] = None
) -> dict[str, Any]:
    """Decide el estilo de API y **declara de dónde salió**.

    Prioridad: ``override`` explícito → capa ``api_style`` del stack → default de
    ``tech_stack.yaml``.

    ``supported`` distingue "se decidió" de "sabemos hacerlo". Si la arquitectura
    eligió GraphQL, el estilo queda registrado como GraphQL y ``supported=False``:
    el pipeline sigue produciendo la especificación REST —que es trabajo
    aprovechable— pero QUESTION_GEN emite una pregunta **bloqueante** y el semáforo
    no se pone verde. Fingir que se diseñó lo que se pidió sería el peor final.
    """
    if override:
        style = _normalize_style(override)
        if style is None:
            raise GateError(
                f"El estilo de API «{override}» no está en el allow-list de la casa "
                f"({', '.join(sorted(set(_STYLE_ALIASES.values())))}). Revisa "
                "tech_stack.yaml o corrige la petición."
            )
        return {
            "style": style,
            "supported": style == SUPPORTED_STYLE,
            "source_ref": None,
            "decided": True,
            "reason": "Estilo indicado explícitamente en la petición.",
        }

    choice = _stack_layer(sources, API_STYLE_LAYER)
    if choice is not None:
        style = _normalize_style(choice.get("technology") or "")
        if style is not None:
            return {
                "style": style,
                "supported": style == SUPPORTED_STYLE,
                "source_ref": choice.get("id"),
                "decided": True,
                "reason": (
                    f"Estilo decidido por la arquitectura ({choice.get('id')}): "
                    f"{choice.get('technology')}."
                ),
            }
        return {
            "style": SUPPORTED_STYLE,
            "supported": True,
            "source_ref": choice.get("id"),
            "decided": False,
            "reason": (
                f"La arquitectura propone «{choice.get('technology')}», que no está "
                "en el allow-list de estilos de la casa. Se especifica REST y se "
                "pregunta al líder técnico."
            ),
        }

    default = _normalize_style(_stack_default(API_STYLE_LAYER) or "") or SUPPORTED_STYLE
    return {
        "style": default,
        "supported": default == SUPPORTED_STYLE,
        "source_ref": None,
        "decided": False,
        "reason": (
            "La arquitectura no decidió estilo de API: se especifica el default de "
            "tech_stack.yaml y se pregunta al líder técnico."
        ),
    }


def resolve_auth(sources: dict[str, Any]) -> dict[str, Any]:
    """Decide el esquema de seguridad y **declara de dónde salió**.

    Sale de la capa ``auth`` del stack (Keycloak, Azure AD…), traducida a esquema
    por ``api_conventions.yaml``. Si la arquitectura no la decidió, se usa el
    default de la casa con ``decided=False`` + pregunta bloqueante: una API cuyo
    mecanismo de autenticación nadie confirmó no puede darse por lista, porque cada
    endpoint de la matriz de autorización descansa sobre él.
    """
    choice = _stack_layer(sources, AUTH_LAYER)
    if choice is not None and choice.get("technology"):
        provider = choice["technology"]
        return {
            "scheme": security_scheme_for(provider),
            "provider": provider,
            "source_ref": choice.get("id"),
            "decided": True,
            "reason": (
                f"Autenticación decidida por la arquitectura ({choice.get('id')}): "
                f"{provider}."
            ),
        }

    provider = _stack_default(AUTH_LAYER) or ""
    return {
        "scheme": security_scheme_for(provider),
        "provider": provider or None,
        "source_ref": None,
        "decided": False,
        "reason": (
            "La arquitectura no decidió proveedor de autenticación: se usa el "
            "default de tech_stack.yaml y se pregunta al líder técnico."
        ),
    }


def resolve_conventions() -> dict[str, Any]:
    """Convenciones efectivas que se persisten en el artefacto (auditables).

    Se guardan junto al contrato —y no solo en el YAML— para que la especificación
    siga siendo interpretable si mañana el equipo cambia una convención.
    """
    data = load_api_conventions()
    paths = data.get("paths", {}) or {}
    props = data.get("properties", {}) or {}
    page = data.get("pagination", {}) or {}
    sorting = data.get("sorting", {}) or {}
    return {
        "path_language": paths.get("language", "es"),
        "path_case": paths.get("case", "kebab-case"),
        "resource_number": paths.get("number", "plural"),
        "property_case": props.get("case", "snake_case"),
        "envelope": (data.get("envelope", {}) or {}).get("style", "api_response"),
        "update_verb": paths.get("update_verb", "PATCH"),
        "max_nesting": int(paths.get("max_nesting", 1)),
        "pagination": {
            "style": page.get("style", "offset"),
            "limit_param": page.get("limit_param", "limit"),
            "offset_param": page.get("offset_param", "offset"),
            "default_limit": int(page.get("default_limit", 20)),
            "max_limit": int(page.get("max_limit", 100)),
            "items_field": page.get("items_field", "items"),
            "total_field": page.get("total_field", "total"),
        },
        "sort_param": sorting.get("param", "sort"),
        "date_format": props.get("date_format", "rfc3339"),
        "decimal_as_string": bool(props.get("decimal_as_string", True)),
    }


def base_path() -> str:
    """Prefijo de todas las rutas (``/api/v1``), desde las convenciones."""
    return (load_api_conventions().get("paths", {}) or {}).get("prefix", "/api/v1")


def resolve_hashes(
    state_bd_hash: str,
    state_ef_hash: str,
    state_architecture_hash: Optional[str],
    bd_artifact: dict[str, Any],
) -> dict[str, Optional[str]]:
    """Resuelve los hashes de origen: estado > ``source`` del artefacto de arriba.

    El ``DatabaseArtifact`` ya guarda en su ``source`` los hashes de toda la cadena
    que consumió, así que los eslabones lejanos no hay que recalcularlos: se
    heredan, y así los cuatro artefactos de un mismo flujo declaran exactamente los
    mismos valores.
    """
    bd_source = (bd_artifact or {}).get("source") or {}
    return {
        "bd": state_bd_hash or "",
        "ef": state_ef_hash or bd_source.get("ef_artifact_hash") or "",
        "architecture": (
            state_architecture_hash or bd_source.get("architecture_artifact_hash")
        ),
        "scrum": bd_source.get("scrum_artifact_hash"),
    }
