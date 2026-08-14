"""Nodos del grafo LangGraph del Agente QA.

Bloque QA2: LOAD_SOURCES (gate + carga de la cadena + declaración de la
dependencia opcional del contrato de API) está completo; el resto son **stubs**
que devuelven vacío para que el grafo corra de extremo a extremo y el contrato
quede fijado desde el principio. Cada bloque posterior sustituye su stub:

- QA3 → ``criterion_map``, ``test_design``, ``edge_cases``, ``auth_cases``
- QA4 → ``dataset``, ``trace_matrix``, ``exec_plan``
- QA5 → ``critique``, ``question_gen``
- QA6 → ``assemble``, ``persist``
"""

from ai.agents.qa.load_sources import (
    assert_scrum_ready,
    extract_sources,
    resolve_api_availability,
    resolve_hashes,
    resolve_target,
)
from ai.agents.qa.state import QaState


async def node_load_sources(state: QaState) -> dict:
    """LOAD_SOURCES: gate del plan, contexto consolidado y umbrales efectivos."""
    assert_scrum_ready(bool(state.get("scrum_ready")), state.get("scrum_job_id", "?"))

    scrum_artifact = state.get("scrum_artifact") or {}
    ef_artifact = state.get("ef_artifact") or {}
    api_artifact = state.get("api_artifact") or {}

    disponibilidad = resolve_api_availability(
        state.get("api_job_id"), api_artifact, state.get("api_artifact_hash")
    )
    # Si el contrato no es utilizable, no entra al contexto: así ningún nodo
    # posterior puede derivar un caso de autorización de una fuente a medias.
    usable = api_artifact if disponibilidad["available"] else {}
    sources = extract_sources(scrum_artifact, ef_artifact, usable)

    observaciones: list[dict] = []
    if not disponibilidad["available"]:
        observaciones.append(
            {
                "description": (
                    "No se diseñaron casos de autorización. "
                    f"{disponibilidad['reason']}"
                ),
                "reason": "Dependencia opcional ausente (contrato de API).",
            }
        )

    return {
        "sources": sources,
        "target": resolve_target(),
        "api_available": disponibilidad["available"],
        "api_absent_reason": disponibilidad["reason"],
        "hashes": resolve_hashes(
            state.get("scrum_artifact_hash", ""),
            state.get("ef_artifact_hash", ""),
            state.get("api_artifact_hash"),
            disponibilidad["available"],
        ),
        "map_observations": observaciones,
    }


async def node_criterion_map(state: QaState) -> dict:
    """CRITERION_MAP (QA3): andamio determinista de pares (historia, criterio)."""
    return {"criterion_map": {}}


async def node_test_design(state: QaState) -> dict:
    """TEST_DESIGN (QA3): casos funcionales y negativos por criterio (LLM)."""
    return {"test_cases": []}


async def node_edge_cases(state: QaState) -> dict:
    """EDGE_CASES (QA3): casos de borde anclados en evidencia (LLM)."""
    return {}


async def node_auth_cases(state: QaState) -> dict:
    """AUTH_CASES (QA3): casos de autorización derivados de la matriz (sin LLM)."""
    return {}


async def node_dataset(state: QaState) -> dict:
    """DATASET (QA4): datos reutilizables por entidad."""
    return {"datasets": []}


async def node_trace_matrix(state: QaState) -> dict:
    """TRACE_MATRIX (QA4): matriz y cobertura, deterministas."""
    return {"trace_matrix": {}}


async def node_exec_plan(state: QaState) -> dict:
    """EXEC_PLAN (QA4): suites por épica, orden topológico y esfuerzo."""
    return {"execution_plan": {}}


async def node_critique(state: QaState) -> dict:
    """CRITIQUE (QA5): cobertura, duplicados y criterios huérfanos."""
    return {"risks": [], "observations": []}


async def node_question_gen(state: QaState) -> dict:
    """QUESTION_GEN (QA5): preguntas al QA lead (agrupadas por clase de vacío)."""
    return {"questions": []}


async def node_assemble(state: QaState) -> dict:
    """ASSEMBLE (QA6): arma y valida el QaArtifact."""
    return {"artifact": {}}


async def node_persist(state: QaState) -> dict:
    """PERSIST (QA6): guarda artefacto, validaciones y métricas."""
    return {}
