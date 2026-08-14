"""Utilidades compartidas por los nodos del Agente QA."""

from typing import Any, Optional

from ai.knowledge import glossary_block

from .schemas.artifact import DEFAULT_MINUTES_BY_TYPE, DEFAULT_PRIORITY_FACTOR


def knowledge_block(authoritative_context: Optional[str] = None) -> str:
    """Conocimiento inyectable de los nodos generativos del Agente QA.

    Compone el glosario logístico y antepone el contexto autoritativo del refine,
    que tiene prioridad sobre cualquier otra cosa (son respuestas del QA lead a
    preguntas concretas).
    """
    block = glossary_block()
    if authoritative_context:
        return (
            "CONTEXTO AUTORITATIVO (respuestas del QA lead, tienen prioridad sobre "
            f"todo lo demás):\n{authoritative_context}\n\n{block}"
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


def estimated_minutes(
    case_type: str, priority: str, target: Optional[dict[str, Any]] = None
) -> int:
    """Esfuerzo manual de un caso: tabla por tipo × factor por prioridad (QA-D8).

    Determinista a propósito. Pedirle la estimación al modelo haría que dos corridas
    del mismo plan dieran totales distintos, y el número que el equipo usa para
    planificar dejaría de ser comparable entre versiones.
    """
    target = target or {}
    minutos = (target.get("minutes_by_type") or DEFAULT_MINUTES_BY_TYPE).get(
        case_type, 10
    )
    factor = (target.get("priority_factor") or DEFAULT_PRIORITY_FACTOR).get(
        priority, 1.0
    )
    # `int(... + 0.5)` en vez de `round()`: el redondeo bancario de Python haría que
    # 7.5 → 8 y 6.5 → 6, y dos casos con el mismo cálculo darían minutos distintos
    # según el valor. Aquí medio minuto siempre sube.
    return max(1, int(minutos * factor + 0.5))


def next_id(prefix: str, used: set[str]) -> str:
    """Siguiente id libre con el prefijo dado (``TC-001``, ``TC-002``…).

    Los ids los pone Python, no el modelo: dos llamadas concurrentes del *map*
    propondrían el mismo ``TC-001`` sin saberlo.
    """
    n = 1
    while f"{prefix}-{n:03d}" in used:
        n += 1
    return f"{prefix}-{n:03d}"


def normalize_steps(steps: list[dict]) -> list[dict]:
    """Numera los pasos de 1 a N (el modelo propone acciones, no numeración)."""
    return [
        {
            "number": i,
            "action": paso.get("action", ""),
            "expected": paso.get("expected"),
        }
        for i, paso in enumerate(steps or [], start=1)
    ]
