"""Nodos del grafo LangGraph del Agente QA.

Bloque QA3: LOAD_SOURCES, CRITERION_MAP, TEST_DESIGN, EDGE_CASES y AUTH_CASES
están completos; el resto son **stubs** que devuelven vacío para que el grafo corra
de extremo a extremo. Cada bloque posterior sustituye su stub:

- QA4 → ``dataset``, ``trace_matrix``, ``exec_plan``
- QA5 → ``critique``, ``question_gen``
- QA6 → ``assemble``, ``persist``
"""

from datetime import date

from langchain_core.runnables import RunnableConfig

from ai.agents.base.structured import ClaudeLLMClient
from ai.agents.qa.auth_cases import build_auth_cases
from ai.agents.qa.common import merge_metrics
from ai.agents.qa.criterion_map import build_criterion_map
from ai.agents.qa.dataset import build_datasets
from ai.agents.qa.edge_cases import run_edge_cases
from ai.agents.qa.exec_plan import build_execution_plan
from ai.agents.qa.load_sources import (
    assert_scrum_ready,
    extract_sources,
    resolve_api_availability,
    resolve_hashes,
    resolve_target,
)
from ai.agents.qa.state import QaState
from ai.agents.qa.test_design import run_test_design
from ai.agents.qa.trace_matrix import build_trace_matrix, uncovered_requirements_risks


def _llm(config: RunnableConfig):
    """LLM inyectado por config (mock en tests); si no, el cliente real."""
    llm = (config or {}).get("configurable", {}).get("llm")
    return llm if llm is not None else ClaudeLLMClient()


def _today(config: RunnableConfig) -> str:
    """Fecha de hoy, inyectable por config para que los bordes sean reproducibles."""
    inyectada = (config or {}).get("configurable", {}).get("today")
    return inyectada or date.today().isoformat()


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
    """CRITERION_MAP: andamio determinista de pares (historia, criterio).

    Cortafuegos anti-invención: fija el universo de criterios **antes** de gastar un
    token. Una historia sin criterios se declara aquí y acaba en pregunta.
    """
    mapa = build_criterion_map(state.get("sources") or {})
    observaciones = list(state.get("map_observations") or [])
    for story_ref in mapa.get("stories_without_criteria", []):
        observaciones.append(
            {
                "description": (
                    f"La historia {story_ref} no tiene criterios de aceptación, así "
                    "que no se diseñaron casos para ella."
                ),
                "reason": "Historia sin criterios: no se inventa uno para cubrirla.",
                "source_ref": story_ref,
            }
        )
    return {"criterion_map": mapa, "map_observations": observaciones}


async def node_test_design(state: QaState, config: RunnableConfig) -> dict:
    """TEST_DESIGN: casos funcionales y negativos por criterio (LLM *map*)."""
    salida = await run_test_design(
        _llm(config),
        state.get("criterion_map") or {},
        state.get("sources") or {},
        target=state.get("target"),
        authoritative_context=state.get("authoritative_context"),
    )
    return {
        "test_cases": salida["test_cases"],
        "not_testable": salida["not_testable"],
        "map_observations": list(state.get("map_observations") or [])
        + salida["observations"],
        "metrics": merge_metrics(state, salida["tokens"], salida["skipped"]),
    }


async def node_edge_cases(state: QaState, config: RunnableConfig) -> dict:
    """EDGE_CASES: casos de borde, cada uno con su cita verbatim verificada."""
    casos = list(state.get("test_cases") or [])
    salida = await run_edge_cases(
        _llm(config),
        state.get("criterion_map") or {},
        state.get("sources") or {},
        today=_today(config),
        used_ids={c["id"] for c in casos},
        target=state.get("target"),
        authoritative_context=state.get("authoritative_context"),
    )
    return {
        "test_cases": casos + salida["test_cases"],
        "unanchored": salida["unanchored"],
        "map_observations": list(state.get("map_observations") or [])
        + salida["observations"],
        "metrics": merge_metrics(state, salida["tokens"], salida["skipped"]),
    }


async def node_auth_cases(state: QaState) -> dict:
    """AUTH_CASES: casos de autorización derivados de la matriz (sin LLM)."""
    casos = list(state.get("test_cases") or [])
    salida = build_auth_cases(
        state.get("criterion_map") or {},
        state.get("sources") or {},
        used_ids={c["id"] for c in casos},
        target=state.get("target"),
    )
    return {
        "test_cases": casos + salida["test_cases"],
        "ambiguous_auth_refs": salida["ambiguous_auth_refs"],
        "map_observations": list(state.get("map_observations") or [])
        + salida["observations"],
    }


async def node_dataset(state: QaState) -> dict:
    """DATASET: datos reutilizables por entidad, cosechados de los casos (sin LLM)."""
    salida = build_datasets(state.get("test_cases") or [], state.get("sources") or {})
    return {
        "datasets": salida["datasets"],
        "map_observations": list(state.get("map_observations") or [])
        + salida["observations"],
    }


async def node_trace_matrix(state: QaState) -> dict:
    """TRACE_MATRIX: matriz y cobertura, deterministas.

    Se construye **antes** de QUESTION_GEN, así que los criterios no verificables
    todavía no tienen id de pregunta. ASSEMBLE vuelve a cerrar el enlace una vez que
    las preguntas existen: el contrato exige que una fila ``not_testable`` cite la
    suya, y aquí aún no hay ninguna que citar.
    """
    matriz = build_trace_matrix(
        state.get("criterion_map") or {},
        state.get("test_cases") or [],
        state.get("not_testable") or [],
    )
    return {
        "trace_matrix": matriz,
        "risks": list(state.get("risks") or [])
        + uncovered_requirements_risks(matriz["coverage"]),
    }


async def node_exec_plan(state: QaState) -> dict:
    """EXEC_PLAN: suites por épica, orden topológico y esfuerzo (sin LLM)."""
    plan = build_execution_plan(
        state.get("test_cases") or [],
        state.get("sources") or {},
        target=state.get("target"),
    )
    return {"execution_plan": plan}


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
