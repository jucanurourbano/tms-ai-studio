"""Construcción del "contexto autoritativo" del ciclo de afinamiento.

Toma las validaciones respondidas (``confirmado`` | ``corregido``) del resumen de
un job y las serializa como bloque de texto con prioridad, que los nodos
generativos anteponen al glosario. Compartido por EF y Scrum.
"""

from typing import Optional


def answered_validations(summary: dict) -> list[dict]:
    """Filtra las validaciones respondidas y con texto (``confirmado``/``corregido``)."""
    return [
        v
        for v in summary.get("validations", [])
        if v.get("status") in ("confirmado", "corregido") and v.get("respuesta")
    ]


def build_authoritative_context(summary: dict) -> Optional[str]:
    """Devuelve el bloque de contexto autoritativo, o ``None`` si no hay respuestas."""
    answered = answered_validations(summary)
    if not answered:
        return None
    return "\n".join(
        f"- {v['target_type']} {v['target_id']}: {v['respuesta']}" for v in answered
    )
