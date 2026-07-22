"""Nodo ADRS: decisión de estilo (determinista) + ADRs adicionales (LLM).

El **estilo arquitectónico lo fija Python** a partir del ``size_class`` (base
reproducible; sesgo hacia monolito modular). El LLM redacta ADRs adicionales
(stack, estructura) que se anclan a referencias reales. El ADR de estilo es
siempre ``ADR-001`` y respalda el campo ``architecture_style``.
"""

import json
from typing import Optional

from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import glossary_with_context
from .prompts import build_system
from .schemas.enums import ArchitectureStyle
from .schemas.extraction import AdrsExtract

# Estilo por tamaño (determinista). Serverless no se auto-elige: solo por refine.
_STYLE_BY_SIZE = {
    "S": ArchitectureStyle.MODULAR_MONOLITH,
    "M": ArchitectureStyle.MODULAR_MONOLITH,
    "L": ArchitectureStyle.MICROSERVICES,
}
_STYLE_CONFIDENCE = {"S": 0.85, "M": 0.8, "L": 0.6}


def choose_style(size_class: str) -> ArchitectureStyle:
    """Elige el estilo de forma determinista según el tamaño del alcance."""
    return _STYLE_BY_SIZE.get(size_class, ArchitectureStyle.MODULAR_MONOLITH)


def _style_adr(size_class: str, scope_profile: dict) -> dict:
    """ADR-001 determinista que documenta la decisión de estilo."""
    style = choose_style(size_class)
    if style == ArchitectureStyle.MODULAR_MONOLITH:
        decision = (
            "Construir la solución como un monolito modular con módulos de "
            "dominio bien delimitados."
        )
        consequences = [
            "+ Simplicidad operativa y despliegue único.",
            "+ Menor costo de coordinación para un solo equipo (Sistemas).",
            "- Escalado independiente por módulo limitado.",
        ]
    else:
        decision = "Adoptar una arquitectura de microservicios por contextos acotados."
        consequences = [
            "+ Escalado y despliegue independientes por servicio.",
            "- Mayor complejidad operativa (observabilidad, despliegue, datos).",
        ]
    context = (
        f"El alcance se clasificó como tamaño «{size_class}» "
        f"(entidades={scope_profile.get('entities', 0)}, "
        f"módulos={scope_profile.get('modules', 0)}, "
        f"historias={scope_profile.get('stories', 0)}, "
        f"integraciones={scope_profile.get('integrations_detected', 0)}). "
        "La recomendación prioriza la simplicidad salvo señales fuertes de escala."
    )
    return {
        "id": "ADR-001",
        "title": f"Estilo arquitectónico: {style.value}",
        "decision": decision,
        "context": context,
        "alternatives_considered": ["modular_monolith", "microservices", "serverless"],
        "consequences": consequences,
        "status": "proposed",
        "source_refs": [],
        "confidence": _STYLE_CONFIDENCE.get(size_class, 0.7),
        "origin": "derived",
    }


def build_style_decision(size_class: str) -> dict:
    """Campo ``architecture_style`` del artefacto (respaldado por ADR-001)."""
    style = choose_style(size_class)
    rationale = (
        f"Alcance tamaño «{size_class}»: se recomienda «{style.value}» "
        "priorizando simplicidad operativa (ver ADR-001)."
    )
    return {
        "chosen": style.value,
        "rationale": rationale,
        "adr_ref": "ADR-001",
        "confidence": _STYLE_CONFIDENCE.get(size_class, 0.7),
        "origin": "derived",
    }


def build_adrs_user(size_class: str, components: list[dict], stack: list[dict]) -> str:
    """Contexto para que el LLM proponga ADRs adicionales (stack/estructura)."""
    payload = {
        "size_class": size_class,
        "chosen_style": choose_style(size_class).value,
        "components": [
            {"id": c.get("id"), "name": c.get("name"), "type": c.get("type")}
            for c in components
        ],
        "stack": [
            {
                "id": s.get("id"),
                "layer": s.get("layer"),
                "technology": s.get("technology"),
            }
            for s in stack
        ],
    }
    return "CONTEXTO PARA ADRS:\n" + json.dumps(payload, ensure_ascii=False)


async def run_adrs(
    llm: LLMClient,
    size_class: str,
    scope_profile: dict,
    components: list[dict],
    stack: list[dict],
    valid_refs: set[str],
    *,
    authoritative_context: Optional[str] = None,
    max_repairs: int = 2,
) -> tuple[list[dict], dict, list[dict], dict]:
    """Genera ADRs y la decisión de estilo. Devuelve (adrs, style, skipped, tokens)."""
    glossary_ctx = glossary_with_context(authoritative_context)
    system = build_system("adrs.md", glossary_ctx)
    user = build_adrs_user(size_class, components, stack)

    tokens = {"input": 0, "output": 0, "total": 0}
    skipped: list[dict] = []
    tokens["input"] += estimate_tokens(system + user)

    # ADR de estilo: SIEMPRE presente y determinista (ancla del semáforo).
    adrs: list[dict] = [_style_adr(size_class, scope_profile)]
    style = build_style_decision(size_class)

    model, err = await complete_structured(
        llm, system=system, user=user, schema=AdrsExtract, max_repairs=max_repairs
    )
    if model is None:
        skipped.append(
            {"ref": "ADRS", "stage": "ADRS", "reason": f"schema inválido: {err[:150]}"}
        )
        tokens["total"] = tokens["input"]
        return adrs, style, skipped, tokens

    for adr in model.adrs:
        refs = [r for r in adr.source_refs if r in valid_refs]
        item = {
            "id": f"ADR-{len(adrs) + 1:03d}",
            "title": adr.title,
            "decision": adr.decision,
            "context": adr.context,
            "alternatives_considered": adr.alternatives_considered,
            "consequences": adr.consequences,
            "status": "proposed",
            "source_refs": refs,
            "confidence": adr.confidence,
            "origin": "derived",
        }
        tokens["output"] += estimate_tokens(json.dumps(item, ensure_ascii=False))
        adrs.append(item)

    tokens["total"] = tokens["input"] + tokens["output"]
    return adrs, style, skipped, tokens
