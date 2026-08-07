"""Utilidades compartidas por los nodos del Agente API."""

from typing import Optional

from ai.knowledge import api_conventions_block, glossary_block


def knowledge_block(authoritative_context: Optional[str] = None) -> str:
    """Conocimiento inyectable de los nodos generativos del Agente API.

    Compone glosario logístico + convenciones de API y antepone el contexto
    autoritativo del refine, que tiene prioridad sobre cualquier otra cosa (son
    respuestas del líder técnico a preguntas concretas).
    """
    block = f"{glossary_block()}\n\n{api_conventions_block()}"
    if authoritative_context:
        return (
            "CONTEXTO AUTORITATIVO (respuestas del líder técnico, tienen prioridad "
            f"sobre todo lo demás):\n{authoritative_context}\n\n{block}"
        )
    return block


def merge_metrics(state: dict, tokens: dict, skipped: list[dict]) -> dict:
    """Acumula tokens y cuarentena de un nodo sobre las métricas del estado."""
    metrics = dict(state.get("metrics") or {})
    acc = dict(metrics.get("tokens") or {"input": 0, "output": 0, "total": 0})
    for key in ("input", "output", "total"):
        acc[key] = acc.get(key, 0) + tokens.get(key, 0)
    metrics["tokens"] = acc
    metrics["skipped"] = list(metrics.get("skipped") or []) + list(skipped or [])
    return metrics
