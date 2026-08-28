"""Nodo RULE_MAPPING: dónde acaba cada regla del EF, y qué dijo el Agente BD.

Este nodo cierra un círculo que hasta ahora quedaba abierto. El Agente BD clasifica
cada ``BR-``/``VAL-`` como ``declarative`` (la garantiza el esquema),
``application`` (**no puede garantizarla y la delega en el sistema**) o ``trigger``.
Las ``application`` quedaban delegadas a un sistema que todavía no existía.

Aquí se recogen. Y si alguna no encuentra endpoint, esquema ni regla de acceso que
la haga cumplir, se reporta: sería una regla de negocio que desaparece entre dos
agentes sin que nadie lo note, y ese fallo solo se descubre en producción.

El reparto de trabajo es el habitual, pero con una particularidad: **casi todo es
determinista**. Si un endpoint ya cita la regla, si un campo la expresa o si el
modelo de datos la garantiza, no hay nada que preguntarle al modelo. Solo van al
LLM las que quedan sin destino, que son las que exigen juicio.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .prompts import build_system
from .schemas.extraction import RuleMappingsExtract

#: Lo que el Agente BD delegó en la aplicación: si aquí tampoco encuentra destino,
#: la regla desaparece del producto.
BD_APPLICATION = "application"


def _observation(description: str, reason: str) -> dict:
    return {"description": description, "reason": reason}


def _mapping(
    rule_ref: str,
    enforcement: str,
    *,
    endpoint_refs: Optional[list[str]] = None,
    schema_field_refs: Optional[list[str]] = None,
    auth_rule_refs: Optional[list[str]] = None,
    bd_enforcement: Optional[str] = None,
    note: Optional[str] = None,
    confidence: Optional[float] = None,
) -> dict:
    return {
        "id": "",  # lo asigna number_mappings
        "rule_ref": rule_ref,
        "enforcement": enforcement,
        "endpoint_refs": endpoint_refs or [],
        "schema_field_refs": schema_field_refs or [],
        "auth_rule_refs": auth_rule_refs or [],
        "bd_enforcement": bd_enforcement,
        "note": note,
        "confidence": confidence,
        "origin": "derived",
    }


def collect_rules(sources: dict[str, Any]) -> list[dict]:
    """Todas las reglas y validaciones del EF, en orden estable."""
    ef = sources.get("ef", {}) or {}
    reglas = [
        {"id": r["id"], "text": r.get("statement") or ""}
        for r in ef.get("business_rules", []) or []
        if r.get("id")
    ]
    reglas += [
        {"id": v["id"], "text": v.get("rule") or ""}
        for v in ef.get("validations", []) or []
        if v.get("id")
    ]
    reglas.sort(key=lambda r: r["id"])
    return reglas


def bd_verdicts(sources: dict[str, Any]) -> dict[str, str]:
    """Lo que el Agente BD decidió sobre cada regla (``rule_ref -> enforcement``)."""
    return {
        m["rule_ref"]: m.get("enforcement")
        for m in (sources.get("bd", {}) or {}).get("rule_mappings", []) or []
        if m.get("rule_ref")
    }


def assign_deterministic(
    reglas: list[dict],
    endpoints: list[dict],
    schemas: list[dict],
    authorization_matrix: list[dict],
    veredictos: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    """Asigna lo que ya se sabe. Devuelve ``(mapeos, reglas_sin_destino)``.

    El orden de preferencia no es arbitrario: se busca primero dónde se **aplica**
    la regla (endpoint, esquema, autorización) y solo al final se acepta que la
    garantice el modelo de datos. Así una regla que el esquema ya cubre no se
    presenta como responsabilidad de la base de datos.
    """
    por_endpoint: dict[str, list[str]] = {}
    for endpoint in endpoints:
        for ref in endpoint.get("rule_refs") or []:
            por_endpoint.setdefault(ref, []).append(endpoint["id"])

    por_campo: dict[str, list[str]] = {}
    for esquema in schemas:
        for field in esquema.get("fields", []):
            for ref in field.get("source_refs") or []:
                por_campo.setdefault(ref, []).append(field["id"])

    por_auth: dict[str, list[str]] = {}
    for regla in authorization_matrix:
        for ref in regla.get("source_refs") or []:
            por_auth.setdefault(ref, []).append(regla["id"])

    mapeos: list[dict] = []
    huerfanas: list[dict] = []
    for regla in reglas:
        ref = regla["id"]
        veredicto = veredictos.get(ref)
        if ref in por_endpoint:
            mapeos.append(
                _mapping(
                    ref,
                    "endpoint",
                    endpoint_refs=sorted(set(por_endpoint[ref])),
                    bd_enforcement=veredicto,
                    note="La aplica la lógica de la operación que la cita.",
                    confidence=0.85,
                )
            )
        elif ref in por_auth:
            mapeos.append(
                _mapping(
                    ref,
                    "authorization",
                    auth_rule_refs=sorted(set(por_auth[ref])),
                    bd_enforcement=veredicto,
                    note="Restringe quién ve o toca qué.",
                    confidence=0.85,
                )
            )
        elif ref in por_campo:
            mapeos.append(
                _mapping(
                    ref,
                    "schema",
                    schema_field_refs=sorted(set(por_campo[ref])),
                    bd_enforcement=veredicto,
                    note="La expresa el contrato de datos del campo que la cita.",
                    confidence=0.8,
                )
            )
        elif veredicto == "declarative":
            mapeos.append(
                _mapping(
                    ref,
                    "database",
                    bd_enforcement=veredicto,
                    note=(
                        "El modelo de datos ya la garantiza con una restricción; la "
                        "API no la duplica."
                    ),
                    confidence=0.9,
                )
            )
        else:
            huerfanas.append({**regla, "bd_enforcement": veredicto})
    return mapeos, huerfanas


# --- Clasificación de las huérfanas (LLM) -------------------------------------


def build_rule_mapping_user(huerfanas: list[dict], endpoints: list[dict]) -> str:
    payload = {
        "unassigned_rules": huerfanas,
        "endpoints": [
            {
                "id": e["id"],
                "operation_id": e["operation_id"],
                "purpose": e["purpose"],
            }
            for e in endpoints
        ],
    }
    return "REGLAS SIN DESTINO:\n" + json.dumps(payload, ensure_ascii=False)


def reconcile_classifications(
    huerfanas: list[dict], propuestas: list[dict], endpoints: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Aplica la clasificación del modelo. Devuelve ``(mapeos, notas)``."""
    validos = {e["id"] for e in endpoints}
    por_ref = {p.get("rule_ref"): p for p in propuestas}
    mapeos: list[dict] = []
    notas: list[dict] = []

    for regla in huerfanas:
        ref = regla["id"]
        propuesta = por_ref.get(ref)
        if propuesta is None:
            mapeos.append(
                _mapping(
                    ref,
                    "not_applicable",
                    bd_enforcement=regla.get("bd_enforcement"),
                    note="Sin clasificar: no se pudo determinar dónde se aplica.",
                    confidence=0.3,
                )
            )
            continue

        refs = [r for r in propuesta.get("endpoint_refs") or [] if r in validos]
        descartados = [
            r for r in propuesta.get("endpoint_refs") or [] if r not in validos
        ]
        if descartados:
            notas.append(
                _observation(
                    f"Se ignoraron endpoints inexistentes al mapear {ref}: "
                    f"{', '.join(descartados)}.",
                    "Una regla no puede apuntar a una operación que no existe.",
                )
            )

        enforcement = propuesta["enforcement"]
        nota = (propuesta.get("note") or "").strip()
        if enforcement == "endpoint" and not refs:
            # Dice que la aplica un endpoint pero no dice cuál: no es un destino.
            notas.append(
                _observation(
                    f"La regla {ref} se quedó sin destino verificable.",
                    "Se clasificó como aplicada por un endpoint sin citar ninguno.",
                )
            )
            enforcement = "not_applicable"
            nota = nota or "Se indicó un endpoint que no se pudo identificar."
        if enforcement == "not_applicable" and not nota:
            nota = "El modelo no explicó por qué queda fuera de la API."
            notas.append(
                _observation(
                    f"La regla {ref} queda fuera de la API sin explicación.",
                    "Una regla descartada sin motivo es una regla perdida.",
                )
            )

        mapeos.append(
            _mapping(
                ref,
                enforcement,
                endpoint_refs=refs,
                bd_enforcement=regla.get("bd_enforcement"),
                note=nota or None,
                confidence=propuesta.get("confidence"),
            )
        )
    return mapeos, notas


def orphan_application_rules(mapeos: list[dict]) -> list[str]:
    """Reglas que el modelo de datos delegó y que la API tampoco aplica.

    Es la comprobación que da sentido a este nodo: cada una de estas reglas
    desaparecería del producto. QUESTION_GEN las convierte en pregunta bloqueante.
    """
    return sorted(
        m["rule_ref"]
        for m in mapeos
        if m.get("bd_enforcement") == BD_APPLICATION
        and not (m["endpoint_refs"] or m["schema_field_refs"] or m["auth_rule_refs"])
    )


def number_mappings(mapeos: list[dict]) -> None:
    """Asigna ids ``ARM-001…`` en orden de regla (reproducible)."""
    mapeos.sort(key=lambda m: m["rule_ref"])
    for posicion, mapeo in enumerate(mapeos, start=1):
        mapeo["id"] = f"ARM-{posicion:03d}"


async def run_rule_mapping(
    llm: LLMClient,
    endpoints: list[dict],
    schemas: list[dict],
    authorization_matrix: list[dict],
    sources: dict[str, Any],
    *,
    authoritative_context: Optional[str] = None,
) -> tuple[list[dict], list[str], list[dict], dict, list[dict]]:
    """Mapea todas las reglas del EF.

    Devuelve ``(mapeos, huérfanas_delegadas, skipped, tokens, observaciones)``.
    """
    reglas = collect_rules(sources)
    veredictos = bd_verdicts(sources)
    mapeos, huerfanas = assign_deterministic(
        reglas, endpoints, schemas, authorization_matrix, veredictos
    )

    tokens = {"input": 0, "output": 0, "total": 0}
    skipped: list[dict] = []
    observaciones: list[dict] = []

    if huerfanas:
        system = build_system("rule_mapping.md", knowledge_block(authoritative_context))
        user = build_rule_mapping_user(huerfanas, endpoints)
        modelo, error = await complete_structured(
            llm,
            system=system,
            user=user,
            schema=RuleMappingsExtract,
            stage="rule_mapping",
        )
        tokens["input"] = estimate_tokens(system + user)
        if modelo is None:
            skipped.append(
                {
                    "ref": "rule_mapping",
                    "stage": "rule_mapping",
                    "reason": f"schema inválido tras reparación: {error[:150]}",
                }
            )
            propuestas: list[dict] = []
        else:
            dumped = modelo.model_dump(mode="json")
            tokens["output"] = estimate_tokens(json.dumps(dumped, ensure_ascii=False))
            propuestas = dumped["mappings"]
        nuevos, notas = reconcile_classifications(huerfanas, propuestas, endpoints)
        mapeos.extend(nuevos)
        observaciones.extend(notas)

    tokens["total"] = tokens["input"] + tokens["output"]
    number_mappings(mapeos)

    delegadas = orphan_application_rules(mapeos)
    for ref in delegadas:
        observaciones.append(
            _observation(
                f"La regla {ref} no se hace cumplir en ninguna parte.",
                "El modelo de datos la delegó en la aplicación y la API tampoco la "
                "recoge: desaparecería del producto.",
            )
        )
    return mapeos, delegadas, skipped, tokens, observaciones
