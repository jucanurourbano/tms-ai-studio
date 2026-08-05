"""Utilidades compartidas por los nodos del Agente BD."""

from typing import Optional

from ai.knowledge import db_conventions_block, glossary_block


def knowledge_block(engine: str, authoritative_context: Optional[str] = None) -> str:
    """Conocimiento inyectable de los nodos generativos del Agente BD.

    Compone glosario logístico + convenciones de BD y antepone el contexto
    autoritativo del refine, que tiene prioridad sobre cualquier otra cosa (son
    respuestas del DBA a preguntas concretas).
    """
    block = f"{glossary_block()}\n\n{db_conventions_block(engine)}"
    if authoritative_context:
        return (
            "CONTEXTO AUTORITATIVO (respuestas del DBA/Arquitecto, tienen "
            f"prioridad sobre todo lo demás):\n{authoritative_context}\n\n{block}"
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
