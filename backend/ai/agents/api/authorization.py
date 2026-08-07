"""Nodo AUTHORIZATION: quién puede llamar a cada endpoint, y sobre qué filas.

Es el nodo donde vive el riesgo principal del agente. La regla que lo gobierna
está escrita al principio del diseño y conviene repetirla aquí:

> El peor error posible no es un endpoint de más: es una regla de autorización más
> ancha que la realidad. Un endpoint sobrante se borra en revisión; una
> autorización permisiva por silencio se despliega.

De ahí tres decisiones estructurales, no de estilo:

1. **Fail-closed visible.** Un endpoint que nadie autorizó no se queda con la lista
   de reglas vacía: recibe una regla ``deny`` explícita con ``basis=default_deny``.
   El hueco aparece **en la matriz**, donde alguien lo va a ver, en vez de
   esconderse en una ausencia.
2. **El modelo solo puede restringir.** El esquema de salida no admite ``all``: no
   hay sitio donde escribir "este actor lo ve todo". Una alucinación puede así
   dejar a alguien viendo de menos —que se detecta al usar el sistema— pero nunca
   de más.
3. **Un alcance sin columna que lo materialice es ambiguo, no aproximado.** Si una
   regla dice "solo los de su equipo" y ninguna columna identifica al equipo, la
   regla se marca ambigua y genera pregunta bloqueante. La alternativa —aplicar el
   alcance "más o menos"— es exactamente cómo se filtran datos.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .prompts import build_system
from .schemas.extraction import ResourceScopesExtract

#: Actor comodín de las reglas de denegación por defecto. Se usa cuando **nadie**
#: está autorizado: la fila dice "ningún actor", que es distinto de "no hay fila".
ANY_ACTOR = "*"
ANY_ACTOR_NAME = "Cualquier actor"

#: Operaciones que tocan filas concretas: son las que un alcance puede acotar.
#: Una creación no se acota (todavía no hay fila) y por eso queda fuera.
_SCOPED_KINDS = ("list", "read_item", "update", "delete", "action", "nested_list")


def _observation(description: str, reason: str) -> dict:
    return {"description": description, "reason": reason}


def _rule(
    endpoint_ref: str,
    actor_ref: str,
    *,
    actor_name: Optional[str] = None,
    effect: str = "deny",
    scope: str = "none",
    basis: str = "default_deny",
    expression: Optional[str] = None,
    column_refs: Optional[list[str]] = None,
    ambiguous: bool = False,
    note: Optional[str] = None,
    source_refs: Optional[list[str]] = None,
    confidence: Optional[float] = None,
) -> dict:
    return {
        "id": "",  # lo asigna number_rules
        "endpoint_ref": endpoint_ref,
        "actor_ref": actor_ref,
        "actor_name": actor_name,
        "effect": effect,
        "scope": scope,
        "scope_expression": expression,
        "scope_column_refs": column_refs or [],
        "basis": basis,
        "ambiguous": ambiguous,
        "note": note,
        "source_refs": source_refs or [],
        "confidence": confidence,
        "origin": "derived",
    }


def build_base_matrix(
    endpoints: list[dict], resource_map: dict, actors: list[dict]
) -> list[dict]:
    """Base determinista: una fila por (endpoint × actor) de la matriz CRUD.

    Los actores salen de las operaciones del andamio, que a su vez salieron de las
    celdas CRUD del EF. Aquí no se concede nada nuevo: se traslada.
    """
    nombres = {a["id"]: a.get("name") for a in actors if a.get("id")}
    operaciones = {
        op["operation_id"]: op
        for recurso in resource_map.get("resources", []) or []
        for op in recurso.get("operations", [])
    }

    reglas: list[dict] = []
    for endpoint in endpoints:
        operacion = operaciones.get(endpoint["operation_id"], {})
        actores = operacion.get("actor_refs") or []
        if not actores:
            reglas.append(
                _rule(
                    endpoint["id"],
                    ANY_ACTOR,
                    actor_name=ANY_ACTOR_NAME,
                    effect="deny",
                    basis="default_deny",
                    note=(
                        "Ninguna celda de la matriz CRUD del EF autoriza esta "
                        "operación."
                    ),
                    source_refs=list(operacion.get("source_refs") or []),
                )
            )
            continue
        for actor in actores:
            reglas.append(
                _rule(
                    endpoint["id"],
                    actor,
                    actor_name=nombres.get(actor),
                    effect="allow",
                    scope="all",
                    basis=(
                        "business_rule"
                        if operacion.get("basis") == "business_rule"
                        else "crud_matrix"
                    ),
                    source_refs=list(operacion.get("crud_refs") or [])
                    or list(operacion.get("source_refs") or []),
                    confidence=0.9,
                )
            )
    return reglas


# --- Alcances por fila (LLM) --------------------------------------------------


def build_scopes_user(resource: dict, sources: dict[str, Any]) -> str:
    """Compone el mensaje de un recurso: sus columnas, sus actores y las reglas."""
    ef = sources.get("ef", {}) or {}
    actores = sorted(
        {
            actor
            for op in resource.get("operations", [])
            for actor in (op.get("actor_refs") or [])
        }
    )
    nombres = {a["id"]: a.get("name") for a in ef.get("actors", []) or []}
    payload = {
        "resource": {
            "name": resource.get("name"),
            "singular": resource.get("singular"),
        },
        "columns": [c["name"] for c in resource.get("columns", [])],
        "actors_with_access": [
            {"ref": ref, "name": nombres.get(ref)} for ref in actores
        ],
        "context": {
            "actors": [
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "responsibilities": a.get("responsibilities"),
                }
                for a in ef.get("actors", []) or []
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
    return "RECURSO Y ACTORES:\n" + json.dumps(payload, ensure_ascii=False)


def apply_scopes(
    resource: dict,
    endpoints: list[dict],
    reglas: list[dict],
    propuestas: list[dict],
    refs_validas: set[str],
) -> list[dict]:
    """Aplica los alcances propuestos sobre las reglas ya concedidas.

    Un alcance **nunca crea una regla**: solo acota una que la matriz CRUD ya
    concedió. Si el modelo propone acotar a un actor que no tiene acceso, no hay
    nada que acotar y se descarta.
    """
    notas: list[dict] = []
    columnas = {c["name"]: c for c in resource.get("columns", [])}
    de_este_recurso = {
        e["id"] for e in endpoints if e["resource_ref"] == resource["id"]
    }
    acotables = {
        e["id"]
        for e in endpoints
        if e["resource_ref"] == resource["id"] and e["kind"] in _SCOPED_KINDS
    }

    for propuesta in propuestas:
        actor = propuesta.get("actor_ref")
        citadas = [
            ref for ref in propuesta.get("source_refs") or [] if ref in refs_validas
        ]
        if not citadas:
            notas.append(
                _observation(
                    f"No se aplicó el alcance «{propuesta.get('scope')}» a "
                    f"{actor} en {resource['name']}.",
                    "No cita ninguna regla real del EF; una restricción que nadie "
                    "escribió no existe.",
                )
            )
            continue

        objetivo = [
            r
            for r in reglas
            if r["actor_ref"] == actor
            and r["endpoint_ref"] in acotables
            and r["effect"] == "allow"
        ]
        if not objetivo:
            notas.append(
                _observation(
                    f"No se aplicó el alcance «{propuesta.get('scope')}» a "
                    f"{actor} en {resource['name']}.",
                    (
                        "Ese actor no tiene acceso concedido a ninguna operación "
                        "acotable del recurso: no hay nada que restringir."
                        if actor
                        not in {
                            r["actor_ref"]
                            for r in reglas
                            if r["endpoint_ref"] in de_este_recurso
                        }
                        else "Sus operaciones no actúan sobre filas concretas."
                    ),
                )
            )
            continue

        reales = [n for n in propuesta.get("column_names") or [] if n in columnas]
        inventadas = [
            n for n in propuesta.get("column_names") or [] if n not in columnas
        ]
        if inventadas:
            notas.append(
                _observation(
                    f"Se ignoraron columnas inexistentes en el alcance de {actor} "
                    f"sobre {resource['name']}: {', '.join(inventadas)}.",
                    "El alcance solo puede apoyarse en columnas reales del recurso.",
                )
            )
        column_refs = [
            columnas[n]["column_ref"] for n in reales if columnas[n].get("column_ref")
        ]
        ambiguo = not column_refs

        if ambiguo:
            notas.append(
                _observation(
                    f"El alcance «{propuesta.get('scope')}» de {actor} sobre "
                    f"{resource['name']} quedó pendiente de resolver.",
                    "Ninguna columna del recurso permite aplicarlo: el modelo de "
                    "datos todavía no soporta la regla "
                    f"{', '.join(citadas)}.",
                )
            )

        for regla in objetivo:
            regla["scope"] = propuesta["scope"]
            regla["scope_expression"] = propuesta.get("expression")
            regla["scope_column_refs"] = column_refs
            regla["basis"] = "business_rule"
            regla["ambiguous"] = ambiguo
            regla["source_refs"] = sorted(set(regla["source_refs"]) | set(citadas))
            if propuesta.get("confidence") is not None:
                regla["confidence"] = propuesta["confidence"]
            if ambiguo:
                regla["note"] = (
                    "Restricción declarada en "
                    f"{', '.join(citadas)} que ninguna columna del recurso permite "
                    "aplicar. Pendiente de resolver antes de construir."
                )
    return notas


def number_rules(reglas: list[dict]) -> None:
    """Asigna ids ``AUTH-001…`` en orden reproducible."""
    for posicion, regla in enumerate(reglas, start=1):
        regla["id"] = f"AUTH-{posicion:03d}"


def unauthorized_endpoints(endpoints: list[dict], reglas: list[dict]) -> list[str]:
    """Endpoints sin una sola regla que permita llamarlos.

    Entra en el semáforo: un contrato con un endpoint que nadie puede usar está
    incompleto, aunque el documento sea válido.
    """
    permitidos = {r["endpoint_ref"] for r in reglas if r["effect"] == "allow"}
    return [e["id"] for e in endpoints if e["id"] not in permitidos]


async def run_authorization(
    llm: LLMClient,
    endpoints: list[dict],
    resource_map: dict,
    sources: dict[str, Any],
    *,
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
) -> tuple[list[dict], list[dict], dict, list[dict]]:
    """Construye la matriz completa. Devuelve ``(matriz, skipped, tokens, obs)``."""
    ef = sources.get("ef", {}) or {}
    reglas = build_base_matrix(endpoints, resource_map, ef.get("actors", []) or [])

    candidatos = [
        r
        for r in resource_map.get("resources", []) or []
        if any(op.get("actor_refs") for op in r.get("operations", []))
    ]
    tokens = {"input": 0, "output": 0, "total": 0}
    skipped: list[dict] = []
    observaciones: list[dict] = []

    if candidatos:
        system = build_system(
            "authorization.md", knowledge_block(authoritative_context)
        )
        results, skipped, tokens = await run_structured_map(
            llm,
            candidatos,
            build_system=lambda _: system,
            build_user=lambda item: build_scopes_user(item, sources),
            schema=ResourceScopesExtract,
            ref_of=lambda item: item["id"],
            stage="authorization",
            estimate_tokens=estimate_tokens,
            concurrency=concurrency,
        )
        refs_validas = {
            item["id"]
            for clave in ("business_rules", "validations", "processes")
            for item in ef.get(clave, []) or []
            if item.get("id")
        }
        por_ref = {r["ref"]: r["data"] for r in results}
        for candidato in candidatos:
            propuestas = (por_ref.get(candidato["id"]) or {}).get("scopes", [])
            observaciones.extend(
                apply_scopes(candidato, endpoints, reglas, propuestas, refs_validas)
            )

    number_rules(reglas)
    for endpoint in endpoints:
        endpoint["auth_rule_refs"] = [
            r["id"] for r in reglas if r["endpoint_ref"] == endpoint["id"]
        ]
    return reglas, skipped, tokens, observaciones
