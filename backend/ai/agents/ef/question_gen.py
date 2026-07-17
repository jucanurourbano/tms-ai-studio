"""Fase QUESTION_GEN: dudas de Sistemas hacia Procesos (determinístico).

Solo genera preguntas de negocio hacia Procesos. Las decisiones técnicas
internas (p. ej. referencias huérfanas) NO son preguntas: van a observaciones.
"""

from typing import Any


def _to_question(description: str) -> str:
    """Convierte una descripción en una pregunta de negocio."""
    desc = description.rstrip(".")
    return f"¿Podría aclarar lo siguiente?: {desc}."


def generate_questions(
    critique_result: dict[str, Any],
    consolidated: dict[str, Any],
) -> tuple[list[dict], list[dict]]:
    """Devuelve (questions, observaciones_extra).

    - Inconsistencias técnicas (refs huérfanas) -> observaciones (no preguntas).
    - Inconsistencias semánticas / contradicciones -> pregunta negocio (blocking).
    - Faltantes -> pregunta negocio (blocking).
    - Baja confianza -> pregunta negocio (no blocking).
    """
    questions: list[dict] = []
    observations_extra: list[dict] = []
    n = 1

    for inc in critique_result.get("inconsistencies", []):
        if inc.get("kind") == "orphan_ref":
            observations_extra.append(
                {
                    "description": inc["description"],
                    "reason": "Referencia interna a resolver por Sistemas.",
                }
            )
            continue
        ref = (inc.get("conflicting_refs") or [None])[0]
        questions.append(
            {
                "id": f"Q-{n:03d}",
                "question": _to_question(inc["description"]),
                "reason": inc["description"],
                "audience": "negocio",
                "blocking": True,
                "linked_to_ref": ref,
                "status": "pendiente",
            }
        )
        n += 1

    for miss in critique_result.get("missing_info", []):
        questions.append(
            {
                "id": f"Q-{n:03d}",
                "question": _to_question(miss["description"]),
                "reason": miss.get("expected_where") or miss["description"],
                "audience": "negocio",
                "blocking": True,
                "linked_to_ref": None,
                "status": "pendiente",
            }
        )
        n += 1

    for amb in critique_result.get("ambiguities", []):
        questions.append(
            {
                "id": f"Q-{n:03d}",
                "question": _to_question(amb["description"]),
                "reason": amb["description"],
                "audience": "negocio",
                "blocking": False,
                "linked_to_ref": amb.get("source_ref"),
                "status": "pendiente",
            }
        )
        n += 1

    return questions, observations_extra
