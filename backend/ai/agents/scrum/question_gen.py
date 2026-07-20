"""Nodo QUESTION_GEN: preguntas al Product Owner (determinístico).

Fuentes (D5 y diseño): requisitos funcionales sin cobertura (bloqueante),
dependencias circulares (bloqueante), estimaciones de baja confianza (no
bloqueante) e historias ambiguas (no bloqueante). Lo técnico interno (refs
huérfanas, capacidad) ya quedó como observación en CRITIQUE.
"""

from typing import Any


def generate_questions(
    critique_dict: dict[str, Any], stories: list[dict]
) -> list[dict]:
    """Genera las preguntas al PO a partir de los hallazgos de CRITIQUE."""
    findings = critique_dict.get("findings", {})
    questions: list[dict] = []
    n = 1
    asked_stories: set[str] = set()

    def _add(question: str, reason: str, *, audience: str, blocking: bool, ref):
        nonlocal n
        questions.append(
            {
                "id": f"Q-{n:03d}",
                "question": question,
                "reason": reason,
                "audience": audience,
                "blocking": blocking,
                "linked_to_ref": ref,
                "status": "pendiente",
            }
        )
        n += 1

    # 1) RF sin cobertura -> bloqueante (negocio).
    for rf in findings.get("uncovered_requirement_refs", []):
        _add(
            question=(
                f"El requisito funcional {rf} no quedó cubierto por ninguna "
                "historia. ¿Debe planificarse o está fuera del alcance?"
            ),
            reason="Cobertura incompleta de requisitos funcionales.",
            audience="negocio",
            blocking=True,
            ref=rf,
        )

    # 2) Dependencias circulares -> bloqueante (técnico).
    for cycle in findings.get("cycles", []):
        _add(
            question=(
                "Se detectó una dependencia circular entre historias ("
                + " -> ".join(cycle)
                + "). ¿Cómo debe romperse?"
            ),
            reason="Las dependencias circulares impiden planificar el orden.",
            audience="tecnico",
            blocking=True,
            ref=cycle[0] if cycle else None,
        )

    # 3) Estimaciones de baja confianza -> no bloqueante (negocio).
    for sid in findings.get("low_confidence_estimates", []):
        asked_stories.add(sid)
        _add(
            question=(
                f"La estimación de la historia {sid} es una sugerencia con baja "
                "confianza. ¿La confirmas o la ajustas?"
            ),
            reason="Estimación sugerida con baja confianza (borrador informado).",
            audience="negocio",
            blocking=False,
            ref=sid,
        )

    # 4) Historias ambiguas -> no bloqueante (negocio); sin duplicar con (3).
    for sid in findings.get("ambiguous_stories", []):
        if sid in asked_stories:
            continue
        _add(
            question=(
                f"La historia {sid} tiene baja confianza de derivación. ¿Refleja "
                "correctamente lo que necesita el negocio?"
            ),
            reason="Historia derivada con baja confianza.",
            audience="negocio",
            blocking=False,
            ref=sid,
        )

    return questions
