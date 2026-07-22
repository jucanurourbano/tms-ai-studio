"""Nodo LOAD_SOURCES: única fuente de verdad del Agente Arquitectura.

Verifica el gate de entrada (``ready_for_next_stage`` del Scrum) de forma
defensiva y expone el contexto consolidado del par **EF + Scrum**:
- del EF: entidades, relaciones, APIs, reglas, validaciones, requisitos (incl.
  RNF), módulos, procesos, actores;
- del Scrum: épicas, historias, sprints y puntos totales.

Regla dura heredada: **prohibido inventar**. Todo componente/decisión debe tener
base en este contexto; si falta, se pregunta al Arquitecto.
"""

from typing import Any

from ai.errors import GateError


def assert_scrum_ready(scrum_ready: bool, scrum_job_id: str) -> None:
    """Re-verifica el gate de entrada; si no está listo, corta con ``GateError``."""
    if not scrum_ready:
        raise GateError(
            f"El plan Scrum {scrum_job_id} no está listo para diseño de "
            "arquitectura: quedan preguntas bloqueantes al PO sin responder o "
            "falta cobertura. Complétalas o genera un plan afinado "
            f"(POST /scrum/jobs/{scrum_job_id}/refine)."
        )


def extract_sources(
    ef_artifact: dict[str, Any], scrum_artifact: dict[str, Any]
) -> dict[str, Any]:
    """Consolida las dimensiones de EF + Scrum que necesita el diseño técnico."""
    requirements = ef_artifact.get("requirements", {}) or {}
    scrum_metrics = scrum_artifact.get("metrics", {}) or {}
    return {
        "ef": {
            "summary": ef_artifact.get("summary"),
            "requirements": {
                "business": requirements.get("business", []) or [],
                "functional": requirements.get("functional", []) or [],
                "non_functional": requirements.get("non_functional", []) or [],
            },
            "processes": ef_artifact.get("processes", []) or [],
            "business_rules": ef_artifact.get("business_rules", []) or [],
            "validations": ef_artifact.get("validations", []) or [],
            "modules": ef_artifact.get("modules", []) or [],
            "entities": ef_artifact.get("entities", []) or [],
            "relationships": ef_artifact.get("relationships", []) or [],
            "apis": ef_artifact.get("apis", []) or [],
            "actors": ef_artifact.get("actors", []) or [],
        },
        "scrum": {
            "epics": scrum_artifact.get("epics", []) or [],
            "stories": scrum_artifact.get("stories", []) or [],
            "sprints": scrum_artifact.get("sprints", []) or [],
            "points_total": int(scrum_metrics.get("points_total", 0) or 0),
        },
    }


def resolve_ef_hash(
    state_hash: str, scrum_artifact: dict[str, Any], ef_artifact: dict[str, Any]
) -> str:
    """Resuelve el hash del EF: estado > source del Scrum > source del EF."""
    if state_hash:
        return state_hash
    from_scrum = (scrum_artifact.get("source") or {}).get("ef_artifact_hash")
    if from_scrum:
        return from_scrum
    return (ef_artifact.get("source") or {}).get("hash", "")
