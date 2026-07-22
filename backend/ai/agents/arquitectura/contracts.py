"""Nodo CONTRACTS (híbrido): contratos, integraciones y transversales.

- **Determinista**: contratos entre componentes desde ``depends_on``.
- **LLM**: detección de integraciones externas (p. ej. planillas) y derivación de
  requisitos transversales (auth/auditoría/notificaciones…) desde RNF/reglas.
- **Determinista**: contratos externos que enlazan un componente de integración
  con cada integración detectada.

Anti-alucinación: una integración o un transversal sin ninguna referencia real
del EF (proceso/regla/validación/RNF) se descarta a cuarentena.
"""

import json
from typing import Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import glossary_with_context
from .prompts import build_system
from .schemas.extraction import CrossCuttingListExtract, IntegrationsExtract


def _ids(items: list[dict]) -> set[str]:
    return {i["id"] for i in items or [] if i.get("id")}


def _ef_refs(sources: dict) -> dict[str, set[str]]:
    ef = sources.get("ef", {}) or {}
    reqs = ef.get("requirements", {}) or {}
    return {
        "processes": _ids(ef.get("processes", [])),
        "rules": _ids(ef.get("business_rules", [])),
        "validations": _ids(ef.get("validations", [])),
        "modules": _ids(ef.get("modules", [])),
        "nfr": _ids(reqs.get("non_functional", [])),
    }


def build_deterministic_contracts(components: list[dict]) -> list[dict]:
    """Contratos componente→componente a partir de ``depends_on`` (síncronos)."""
    by_id = {c["id"]: c for c in components}
    contracts: list[dict] = []
    for c in components:
        for dep in c.get("depends_on", []):
            if dep not in by_id:
                continue
            contracts.append(
                {
                    "id": f"CON-{len(contracts) + 1:03d}",
                    "from_ref": c["id"],
                    "to_ref": dep,
                    "kind": "sync_api",
                    "description": (f"{c['name']} depende de {by_id[dep]['name']}."),
                    "source_refs": [],
                    "confidence": c.get("confidence"),
                    "origin": "derived",
                }
            )
    return contracts


def _integration_source(components: list[dict]) -> Optional[str]:
    """Elige el componente que origina los contratos externos (tipo integración)."""
    for c in components:
        if c.get("type") == "integration":
            return c["id"]
    return components[0]["id"] if components else None


def build_integrations_user(sources: dict) -> str:
    ef = sources.get("ef", {}) or {}
    payload = {
        "processes": [
            {"id": p.get("id"), "name": p.get("name"), "steps": p.get("steps")}
            for p in ef.get("processes", [])
        ],
        "business_rules": [
            {"id": b.get("id"), "statement": b.get("statement")}
            for b in ef.get("business_rules", [])
        ],
    }
    return "PROCESOS Y REGLAS DEL EF:\n" + json.dumps(payload, ensure_ascii=False)


def build_cross_cutting_user(sources: dict) -> str:
    ef = sources.get("ef", {}) or {}
    reqs = ef.get("requirements", {}) or {}
    payload = {
        "non_functional_requirements": [
            {"id": r.get("id"), "text": r.get("text")}
            for r in reqs.get("non_functional", [])
        ],
        "business_rules": [
            {"id": b.get("id"), "statement": b.get("statement")}
            for b in ef.get("business_rules", [])
        ],
    }
    return "RNF Y REGLAS DEL EF:\n" + json.dumps(payload, ensure_ascii=False)


async def run_contracts(
    llm: LLMClient,
    sources: dict,
    components: list[dict],
    *,
    authoritative_context: Optional[str] = None,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], list[dict], list[dict], dict]:
    """Devuelve (contracts, integrations, cross_cutting, skipped, tokens)."""
    glossary_ctx = glossary_with_context(authoritative_context)
    refs = _ef_refs(sources)
    skipped: list[dict] = []
    tokens = {"input": 0, "output": 0, "total": 0}

    contracts = build_deterministic_contracts(components)

    # --- Integraciones externas (LLM) ---
    int_system = build_system("integrations.md", glossary_ctx)
    int_user = build_integrations_user(sources)
    tokens["input"] += estimate_tokens(int_system + int_user)
    int_model, int_err = await complete_structured(
        llm,
        system=int_system,
        user=int_user,
        schema=IntegrationsExtract,
        max_repairs=max_repairs,
    )
    integrations: list[dict] = []
    if int_model is None:
        skipped.append(
            {
                "ref": "INTEGRATIONS",
                "stage": "CONTRACTS",
                "reason": f"schema inválido: {int_err[:150]}",
            }
        )
    else:
        allowed = refs["processes"] | refs["rules"] | refs["modules"]
        for ig in int_model.integrations:
            valid = [r for r in ig.source_refs if r in allowed]
            if not valid:
                skipped.append(
                    {
                        "ref": f"INT-src:{ig.name[:40]}",
                        "stage": "CONTRACTS",
                        "reason": "integración sin source_ref real del EF (anti-alucinación)",
                    }
                )
                continue
            item = {
                "id": f"INT-{len(integrations) + 1:03d}",
                "name": ig.name,
                "system": ig.system,
                "direction": ig.direction.value,
                "protocol": ig.protocol.value,
                "purpose": ig.purpose,
                "data_exchanged": ig.data_exchanged,
                "source_refs": valid,
                "contract_known": ig.contract_known,
                "confidence": ig.confidence,
                "origin": "derived",
            }
            tokens["output"] += estimate_tokens(json.dumps(item, ensure_ascii=False))
            integrations.append(item)

    # Contratos externos: componente de integración -> cada integración detectada.
    src = _integration_source(components)
    if src is not None:
        for ig in integrations:
            contracts.append(
                {
                    "id": f"CON-{len(contracts) + 1:03d}",
                    "from_ref": src,
                    "to_ref": ig["id"],
                    "kind": "external",
                    "description": f"Integración con {ig['name']}.",
                    "source_refs": ig["source_refs"],
                    "confidence": ig.get("confidence"),
                    "origin": "derived",
                }
            )

    # --- Requisitos transversales (LLM) ---
    xc_system = build_system("cross_cutting.md", glossary_ctx)
    xc_user = build_cross_cutting_user(sources)
    tokens["input"] += estimate_tokens(xc_system + xc_user)
    xc_model, xc_err = await complete_structured(
        llm,
        system=xc_system,
        user=xc_user,
        schema=CrossCuttingListExtract,
        max_repairs=max_repairs,
    )
    cross_cutting: list[dict] = []
    if xc_model is None:
        skipped.append(
            {
                "ref": "CROSS_CUTTING",
                "stage": "CONTRACTS",
                "reason": f"schema inválido: {xc_err[:150]}",
            }
        )
    else:
        allowed = refs["nfr"] | refs["rules"] | refs["validations"]
        for xc in xc_model.cross_cutting:
            valid = [r for r in xc.source_refs if r in allowed]
            if not valid:
                skipped.append(
                    {
                        "ref": f"XC-src:{xc.concern.value}",
                        "stage": "CONTRACTS",
                        "reason": "transversal sin source_ref real del EF (anti-alucinación)",
                    }
                )
                continue
            item = {
                "id": f"XC-{len(cross_cutting) + 1:03d}",
                "concern": xc.concern.value,
                "requirement": xc.requirement,
                "approach": xc.approach,
                "source_refs": valid,
                "confidence": xc.confidence,
                "origin": "derived",
            }
            tokens["output"] += estimate_tokens(json.dumps(item, ensure_ascii=False))
            cross_cutting.append(item)

    tokens["total"] = tokens["input"] + tokens["output"]
    return contracts, integrations, cross_cutting, skipped, tokens
