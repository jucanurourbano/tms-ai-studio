"""Fase INTERPRET: genera systems_interpretation (determinístico).

Traduce el "qué me pide Procesos" al lenguaje de Sistemas y deja explícitos los
supuestos de interpretación (derivados del glosario logístico).
"""

from typing import Any, Optional

from ai.knowledge import load_glossary


def _searchable_text(consolidated: dict, summary: Optional[str]) -> str:
    """Junta el texto relevante del modelo para buscar términos del glosario."""
    parts: list[str] = [summary or ""]
    reqs = consolidated.get("requirements", {})
    for cat in ("business", "functional", "non_functional"):
        parts += [r.get("text", "") for r in reqs.get(cat, [])]
    for actor in consolidated.get("actors", []):
        parts += [actor.get("name", ""), actor.get("description", "") or ""]
    for proc in consolidated.get("processes", []):
        parts += [proc.get("name", "")] + list(proc.get("steps", []) or [])
    for rule in consolidated.get("business_rules", []):
        parts.append(rule.get("statement", ""))
    for val in consolidated.get("validations", []):
        parts.append(val.get("rule", ""))
    for field in consolidated.get("fields", []):
        parts.append(field.get("name", ""))
    return " \n ".join(p for p in parts if p).lower()


def interpret(
    consolidated: dict[str, Any],
    inferred: dict[str, Any],
    summary: Optional[str] = None,
) -> dict[str, Any]:
    """Construye systems_interpretation de forma determinística."""
    reqs = consolidated.get("requirements", {})
    business = reqs.get("business", [])
    functional = reqs.get("functional", [])

    # what_process_requests: resumen o unión de requisitos de negocio.
    if summary:
        what = summary
    elif business:
        what = "Procesos requiere: " + " ".join(r["text"] for r in business[:3])
    else:
        what = "(no se identificó una petición explícita de Procesos)"

    # scope_for_systems: cada requisito funcional (o de negocio) con su ref.
    base_reqs = functional or business
    scope = [
        {
            "id": f"SCOPE-{i:03d}",
            "description": r["text"],
            "requirement_refs": [r["id"]],
        }
        for i, r in enumerate(base_reqs, start=1)
    ]

    # interpretation_assumptions: términos del glosario detectados en el modelo.
    text = _searchable_text(consolidated, summary)
    assumptions = []
    n = 1
    for term, definition in load_glossary().items():
        if term.lower() in text:
            assumptions.append(
                {
                    "id": f"SUP-{n:03d}",
                    "assumption": (f"Se asume que '{term}' se refiere a {definition}."),
                    "rationale": "Glosario logístico del dominio.",
                    "origin": "derived",
                    "confidence": 0.8,
                }
            )
            n += 1

    return {
        "what_process_requests": what,
        "scope_for_systems": scope,
        "apparent_out_of_scope": [],
        "interpretation_assumptions": assumptions,
    }
