"""Nodo QUESTION_GEN: preguntas al Arquitecto/Líder Técnico (determinístico).

Fuentes (semáforo acordado): épicas/entidades no cubiertas, **RNF sin atender** e
**integraciones sin contrato conocido** son **bloqueantes**; los ciclos de
dependencia también. Los componentes de baja confianza generan preguntas **no**
bloqueantes. Todas con `audience="tecnico"` (decisiones técnicas del Arquitecto).
"""

from typing import Any


def generate_questions(critique_dict: dict[str, Any]) -> list[dict]:
    """Genera las preguntas al Arquitecto a partir de los hallazgos de CRITIQUE."""
    findings = critique_dict.get("findings", {})
    questions: list[dict] = []
    n = 1

    def _add(question: str, reason: str, *, blocking: bool, ref):
        nonlocal n
        questions.append(
            {
                "id": f"Q-{n:03d}",
                "question": question,
                "reason": reason,
                "audience": "tecnico",
                "blocking": blocking,
                "linked_to_ref": ref,
                "status": "pendiente",
            }
        )
        n += 1

    # 1) Épicas sin componente -> bloqueante.
    for epic in findings.get("uncovered_epic_refs", []):
        _add(
            question=(
                f"La épica {epic} no está cubierta por ningún componente. "
                "¿Qué componente la implementa o está fuera del alcance técnico?"
            ),
            reason="Cobertura incompleta de épicas del Scrum.",
            blocking=True,
            ref=epic,
        )

    # 2) Entidades sin dueño -> bloqueante.
    for entity in findings.get("uncovered_entity_refs", []):
        _add(
            question=(
                f"La entidad {entity} no está asignada a ningún componente. "
                "¿Qué componente la posee?"
            ),
            reason="Entidad del EF sin componente dueño.",
            blocking=True,
            ref=entity,
        )

    # 3) RNF sin transversal -> bloqueante (acuerdo del semáforo).
    for nfr in findings.get("uncovered_nfr_refs", []):
        _add(
            question=(
                f"El requisito no funcional {nfr} no está atendido por ningún "
                "requisito transversal. ¿Cómo debe abordarse?"
            ),
            reason="RNF sin requisito transversal que lo atienda.",
            blocking=True,
            ref=nfr,
        )

    # 4) Integraciones sin contrato -> bloqueante.
    for ig in findings.get("integrations_without_contract", []):
        _add(
            question=(
                f"La integración con {ig.get('name')} no tiene contrato conocido. "
                "¿Qué protocolo/formato expone (REST, archivo, base de datos)?"
            ),
            reason="Integración externa sin contrato definido en el EF.",
            blocking=True,
            ref=ig.get("id"),
        )

    # 5) Ciclos de dependencia entre componentes -> bloqueante.
    for cycle in findings.get("component_cycles", []):
        _add(
            question=(
                "Se detectó una dependencia circular entre componentes ("
                + " -> ".join(cycle)
                + "). ¿Cómo debe romperse?"
            ),
            reason="Las dependencias circulares impiden un diseño en capas limpio.",
            blocking=True,
            ref=cycle[0] if cycle else None,
        )

    # 6) Componentes de baja confianza -> no bloqueante.
    for cid in findings.get("low_confidence_components", []):
        _add(
            question=(
                f"El componente {cid} se derivó con baja confianza. "
                "¿Refleja correctamente la arquitectura deseada?"
            ),
            reason="Componente derivado con baja confianza.",
            blocking=False,
            ref=cid,
        )

    return questions
