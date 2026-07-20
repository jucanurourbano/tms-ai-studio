"""Nodo LOAD_EF: única fuente de verdad del Agente Scrum.

Verifica el gate de entrada (``ready_for_next_stage`` del EF) de forma defensiva
y expone el contexto del ``EFArtifact`` (requisitos funcionales, procesos, reglas,
validaciones, entidades, módulos) que consumen los nodos generativos.

Regla dura heredada del EF: **prohibido inventar requisitos**. Todo lo que se
planifique debe tener base en este contexto.
"""

from typing import Any

from ai.errors import GateError


def assert_ef_ready(ef_ready: bool, ef_job_id: str) -> None:
    """Re-verifica el gate de entrada; si no está listo, corta con ``GateError``."""
    if not ef_ready:
        raise GateError(
            f"El artefacto EF {ef_job_id} no está listo para planificación: "
            "quedan preguntas bloqueantes sin responder. Complétalas o genera "
            f"una versión afinada (POST /ef/jobs/{ef_job_id}/refine)."
        )


def extract_ef_context(ef_artifact: dict[str, Any]) -> dict[str, Any]:
    """Expone las dimensiones del EF que necesita la planificación ágil."""
    requirements = ef_artifact.get("requirements", {}) or {}
    return {
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
        "actors": ef_artifact.get("actors", []) or [],
    }


def functional_requirement_refs(ef_context: dict[str, Any]) -> list[str]:
    """Ids de los requisitos funcionales (base de la cobertura, D5)."""
    return [
        r["id"]
        for r in ef_context.get("requirements", {}).get("functional", [])
        if r.get("id")
    ]
