"""Nodo CRITIQUE: cobertura que enumera lo que falta, y riesgos.

La parte determinista **nunca resume un hueco a un porcentaje**: junto a cada
ratio va la lista de lo que quedó fuera. Un "92% de cobertura" no le sirve a nadie
para actuar; "falta el recurso guias y el endpoint API-004" sí.

La parte LLM aporta lo que un chequeo automático no ve: riesgos de diseño del
contrato. Tiene prohibido repetir lo ya detectado, que es la forma habitual en que
un crítico automático se vuelve ruido.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.knowledge import load_api_conventions
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .prompts import build_system
from .schemas.extraction import ApiRisksExtract

_SEVERITIES = ("alta", "media", "baja")


def _observation(description: str, reason: str) -> dict:
    return {"description": description, "reason": reason}


def build_coverage(
    resource_map: dict,
    endpoints: list[dict],
    rule_mappings: list[dict],
    authorization_matrix: list[dict],
    sources: dict[str, Any],
) -> dict:
    """Cobertura hacia el modelo de datos y el EF, con los huecos enumerados."""
    ef = sources.get("ef", {}) or {}
    recursos = resource_map.get("resources", []) or []

    expuestos = [r for r in recursos if r.get("operations")]
    sin_exponer = [
        r["table_ref"]
        for r in recursos
        if not r.get("operations") and r.get("table_ref")
    ]

    apis = [a for a in ef.get("apis", []) or [] if a.get("id")]
    cubiertas = {e["ef_api_ref"] for e in endpoints if e.get("ef_api_ref")}
    sin_cubrir = [a["id"] for a in apis if a["id"] not in cubiertas]

    celdas = [c for c in ef.get("crud", []) or [] if c.get("id")]
    celdas_usadas = {
        ref
        for recurso in recursos
        for operacion in recurso.get("operations", [])
        for ref in operacion.get("crud_refs") or []
    }
    celdas_sin_usar = [c["id"] for c in celdas if c["id"] not in celdas_usadas]

    reglas_con_destino = {
        m["rule_ref"]
        for m in rule_mappings
        if m.get("endpoint_refs")
        or m.get("schema_field_refs")
        or m.get("auth_rule_refs")
        or m.get("enforcement") == "database"
    }
    reglas = [m["rule_ref"] for m in rule_mappings]
    reglas_sin_destino = [r for r in reglas if r not in reglas_con_destino]

    actores = [a["id"] for a in ef.get("actors", []) or [] if a.get("id")]
    con_acceso = {
        r["actor_ref"] for r in authorization_matrix if r.get("effect") == "allow"
    }
    sin_acceso = [a for a in actores if a not in con_acceso]

    return {
        "tables_total": len(recursos),
        "tables_exposed": len(expuestos),
        "unexposed_table_refs": sorted(sin_exponer),
        "ef_apis_total": len(apis),
        "ef_apis_covered": len(apis) - len(sin_cubrir),
        "uncovered_api_refs": sorted(sin_cubrir),
        "crud_cells_total": len(celdas),
        "crud_cells_covered": len(celdas) - len(celdas_sin_usar),
        "uncovered_crud_refs": sorted(celdas_sin_usar),
        "rules_total": len(reglas),
        "rules_enforced": len(reglas) - len(reglas_sin_destino),
        "unenforced_rule_refs": sorted(reglas_sin_destino),
        "actors_total": len(actores),
        "actors_with_access": len([a for a in actores if a in con_acceso]),
        "actors_without_access": sorted(sin_acceso),
    }


def coverage_ratio(coverage: dict) -> float:
    """Ratio único del semáforo: tablas expuestas + APIs del EF cubiertas.

    Son las dos coberturas que entran al gate. Las demás (celdas CRUD, reglas,
    actores) generan preguntas y no se mezclan aquí, para que el número no
    diluya lo que sí bloquea.
    """
    total = coverage["tables_total"] + coverage["ef_apis_total"]
    if not total:
        return 1.0
    cubierto = coverage["tables_exposed"] + coverage["ef_apis_covered"]
    return round(cubierto / total, 4)


def detect_findings(
    resource_map: dict,
    endpoints: list[dict],
    schemas: list[dict],
    authorization_matrix: list[dict],
    target: dict,
    coverage: dict,
    unenforced_delegated_rules: list[str],
    validation: dict,
) -> dict:
    """Todo lo que el sistema detecta por su cuenta, agrupado por clase de vacío.

    Devuelve un diccionario cuyas claves consume QUESTION_GEN. Cada valor es la
    lista de refs afectados: agrupar aquí es lo que evita que el panel acabe con
    cuarenta preguntas triviales que entierran la que importa.
    """
    permitidos = {
        r["endpoint_ref"] for r in authorization_matrix if r.get("effect") == "allow"
    }
    ambiguos = {r["endpoint_ref"] for r in authorization_matrix if r.get("ambiguous")}
    con_pii = {
        s["id"] for s in schemas if any(f.get("pii") for f in s.get("fields", []))
    }

    limites = load_api_conventions().get("limits", {}) or {}
    tope_total = int(limites.get("warn_endpoints_total", 80))
    tope_recurso = int(limites.get("warn_endpoints_per_resource", 12))
    por_recurso: dict[str, int] = {}
    for endpoint in endpoints:
        por_recurso[endpoint["resource_ref"]] = (
            por_recurso.get(endpoint["resource_ref"], 0) + 1
        )

    return {
        "unauthorized_endpoints": [
            e["id"] for e in endpoints if e["id"] not in permitidos
        ],
        "ambiguous_scopes": sorted(ambiguos),
        "ambiguous_scopes_with_pii": sorted(
            e["id"]
            for e in endpoints
            if e["id"] in ambiguos and e.get("response_schema_ref") in con_pii
        ),
        "resources_without_operations": list(
            resource_map.get("resources_without_operations") or []
        ),
        "uncovered_ef_apis": coverage["uncovered_api_refs"],
        "uncovered_crud_cells": coverage["uncovered_crud_refs"],
        "unenforced_delegated_rules": list(unenforced_delegated_rules or []),
        "actors_without_access": coverage["actors_without_access"],
        "empty_action_inputs": [
            s["id"]
            for s in schemas
            if s["kind"] == "action_input" and not s.get("fields")
        ],
        "orphan_ef_apis": [
            h["api_ref"] for h in resource_map.get("orphan_ef_apis") or []
        ],
        "orphan_crud": [c["crud_ref"] for c in resource_map.get("orphan_crud") or []],
        "auth_undecided": [] if target.get("auth", {}).get("decided") else ["target"],
        "style_unsupported": (
            [] if target.get("style_supported", True) else [target.get("api_style", "")]
        ),
        "style_undecided": [] if target.get("style_decided") else ["target"],
        "spec_errors": [e["code"] for e in (validation or {}).get("errors", [])],
        "surface_exceeded": (
            [f"{len(endpoints)} operaciones"] if len(endpoints) > tope_total else []
        ),
        "resource_surface_exceeded": sorted(
            ref for ref, total in por_recurso.items() if total > tope_recurso
        ),
    }


# --- Riesgos (LLM) -------------------------------------------------------------


def build_critique_user(
    endpoints: list[dict], schemas: list[dict], findings: dict, coverage: dict
) -> str:
    con_pii = {
        s["id"] for s in schemas if any(f.get("pii") for f in s.get("fields", []))
    }
    detectado = [
        f"{clave}: {', '.join(map(str, refs))}"
        for clave, refs in sorted(findings.items())
        if refs
    ]
    payload = {
        "summary": {
            "resources": coverage["tables_total"],
            "endpoints": len(endpoints),
            "schemas": len(schemas),
            "unauthorized_endpoints": len(findings["unauthorized_endpoints"]),
            "ambiguous_scopes": len(findings["ambiguous_scopes"]),
        },
        "detected": detectado,
        "endpoints": [
            {
                "id": e["id"],
                "operation_id": e["operation_id"],
                "purpose": e["purpose"],
                "exposes_pii": e.get("response_schema_ref") in con_pii,
            }
            for e in endpoints
        ],
    }
    return "CONTRATO CONSOLIDADO:\n" + json.dumps(payload, ensure_ascii=False)


def reconcile_risks(
    propuestos: list[dict], refs_validas: set[str]
) -> tuple[list[dict], list[dict]]:
    """Numera los riesgos y limpia las referencias que no existen."""
    riesgos: list[dict] = []
    notas: list[dict] = []
    for propuesto in propuestos:
        ref = propuesto.get("source_ref")
        if ref and ref not in refs_validas:
            notas.append(
                _observation(
                    f"Se limpió una referencia inexistente en un riesgo: {ref}.",
                    "El riesgo se conserva sin ancla en vez de apuntar a algo que "
                    "no existe.",
                )
            )
            ref = None
        severidad = propuesto.get("severity")
        riesgos.append(
            {
                "id": f"RISK-{len(riesgos) + 1:03d}",
                "description": propuesto["description"],
                "severity": severidad if severidad in _SEVERITIES else "media",
                "mitigation": propuesto.get("mitigation"),
                "source_ref": ref,
                "confidence": propuesto.get("confidence"),
                "origin": "derived",
            }
        )
    return riesgos, notas


async def run_critique(
    llm: LLMClient,
    resource_map: dict,
    endpoints: list[dict],
    schemas: list[dict],
    authorization_matrix: list[dict],
    rule_mappings: list[dict],
    target: dict,
    sources: dict[str, Any],
    *,
    unenforced_delegated_rules: Optional[list[str]] = None,
    validation: Optional[dict] = None,
    authoritative_context: Optional[str] = None,
) -> tuple[dict, list[dict], dict, list[dict]]:
    """Cobertura + hallazgos + riesgos. Devuelve ``(critique, skipped, tokens, obs)``."""
    coverage = build_coverage(
        resource_map, endpoints, rule_mappings, authorization_matrix, sources
    )
    findings = detect_findings(
        resource_map,
        endpoints,
        schemas,
        authorization_matrix,
        target,
        coverage,
        unenforced_delegated_rules or [],
        validation or {},
    )

    system = build_system("critique.md", knowledge_block(authoritative_context))
    user = build_critique_user(endpoints, schemas, findings, coverage)
    modelo, error = await complete_structured(
        llm,
        system=system,
        user=user,
        schema=ApiRisksExtract,
        stage="critique",
    )
    tokens = {"input": estimate_tokens(system + user), "output": 0}
    skipped: list[dict] = []
    riesgos: list[dict] = []
    notas: list[dict] = []

    if modelo is None:
        skipped.append(
            {
                "ref": "critique",
                "stage": "critique",
                "reason": f"schema inválido tras reparación: {error[:150]}",
            }
        )
    else:
        dumped = modelo.model_dump(mode="json")
        tokens["output"] = estimate_tokens(json.dumps(dumped, ensure_ascii=False))
        refs_validas = (
            {e["id"] for e in endpoints}
            | {s["id"] for s in schemas}
            | {r["id"] for r in authorization_matrix}
            | {r["id"] for r in resource_map.get("resources", []) or []}
        )
        riesgos, notas = reconcile_risks(dumped["risks"], refs_validas)

    tokens["total"] = tokens["input"] + tokens["output"]
    critique = {
        "coverage": coverage,
        "coverage_ratio": coverage_ratio(coverage),
        "findings": findings,
        "risks": riesgos,
    }
    return critique, skipped, tokens, notas
