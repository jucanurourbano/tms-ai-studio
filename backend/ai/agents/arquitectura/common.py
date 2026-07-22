"""Utilidades compartidas por los nodos del Agente Arquitectura."""

from typing import Optional

from ai.knowledge import glossary_block


def glossary_with_context(authoritative_context: Optional[str] = None) -> str:
    """Glosario logístico, anteponiendo el contexto autoritativo del refine."""
    glossary = glossary_block()
    if authoritative_context:
        return (
            "CONTEXTO AUTORITATIVO (respuestas del Arquitecto, tienen prioridad):\n"
            f"{authoritative_context}\n\n" + glossary
        )
    return glossary


def merge_metrics(state: dict, tokens: dict, skipped: list[dict]) -> dict:
    """Acumula tokens y cuarentena de un nodo sobre las métricas del estado."""
    metrics = dict(state.get("metrics") or {})
    acc = dict(metrics.get("tokens") or {"input": 0, "output": 0, "total": 0})
    for key in ("input", "output", "total"):
        acc[key] = acc.get(key, 0) + tokens.get(key, 0)
    metrics["tokens"] = acc
    metrics["skipped"] = list(metrics.get("skipped") or []) + list(skipped or [])
    return metrics
