"""Nodos del grafo LangGraph del Agente Scrum.

LOAD_EF (gate + contexto), ASSEMBLE y PERSIST son reales desde el Bloque 2. Los
nodos generativos/deterministas del medio (EPICS…QUESTION_GEN) son stubs que ya
producen estructuras válidas para correr el grafo de extremo a extremo; se
completan en los Bloques 3-5.
"""

import time

from langchain_core.runnables import RunnableConfig

from ai.agents.base.structured import ClaudeLLMClient
from ai.agents.scrum.assemble import assemble_artifact, validate_artifact
from ai.agents.scrum.common import merge_metrics
from ai.agents.scrum.criteria import run_criteria
from ai.agents.scrum.critique import critique as run_critique
from ai.agents.scrum.epics import run_epics
from ai.agents.scrum.estimate import run_estimate
from ai.agents.scrum.load_ef import assert_ef_ready, extract_ef_context
from ai.agents.scrum.prioritize import build_backlog, run_prioritize
from ai.agents.scrum.question_gen import generate_questions
from ai.agents.scrum.sprint_plan import annotate_goals, plan_sprints
from ai.agents.scrum.state import ScrumState
from ai.agents.scrum.stories import run_stories
from app.config.settings import settings


def _llm(config: RunnableConfig):
    """LLM inyectado por config (mock en tests); si no, el cliente real."""
    llm = (config or {}).get("configurable", {}).get("llm")
    return llm if llm is not None else ClaudeLLMClient()


async def node_load_ef(state: ScrumState) -> dict:
    """LOAD_EF: verifica el gate y expone el contexto del EFArtifact."""
    assert_ef_ready(bool(state.get("ef_ready")), state.get("ef_job_id", "?"))
    ef_artifact = state.get("ef_artifact") or {}
    return {
        "ef_context": extract_ef_context(ef_artifact),
        "ef_artifact_hash": state.get("ef_artifact_hash")
        or (ef_artifact.get("source") or {}).get("hash", ""),
        "status": "RUNNING",
        "metrics": dict(state.get("metrics") or {}),
        "errors": [],
        "started_at": time.time(),
    }


# --- EPICS / STORIES / CRITERIA (Bloque 3) ----------------------------------


async def node_epics(state: ScrumState, config: RunnableConfig) -> dict:
    """EPICS: deriva épicas de módulos+procesos del EF (LLM structured)."""
    epics, skipped, tokens = await run_epics(
        _llm(config),
        state.get("ef_context") or {},
        authoritative_context=state.get("authoritative_context"),
    )
    return {"epics": epics, "metrics": merge_metrics(state, tokens, skipped)}


async def node_stories(state: ScrumState, config: RunnableConfig) -> dict:
    """STORIES: map por requisito funcional -> historias trazables."""
    stories, skipped, tokens = await run_stories(
        _llm(config),
        state.get("ef_context") or {},
        state.get("epics") or [],
        ef_job_id=state.get("ef_job_id", ""),
        authoritative_context=state.get("authoritative_context"),
        concurrency=settings.EXTRACT_CONCURRENCY,
    )
    # ``epics`` se muta con story_ids dentro de run_stories.
    return {
        "stories": stories,
        "epics": state.get("epics") or [],
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_criteria(state: ScrumState, config: RunnableConfig) -> dict:
    """CRITERIA: map por historia -> criterios de aceptación Gherkin."""
    stories, skipped, tokens = await run_criteria(
        _llm(config),
        state.get("stories") or [],
        state.get("ef_context") or {},
        authoritative_context=state.get("authoritative_context"),
        concurrency=settings.EXTRACT_CONCURRENCY,
    )
    return {"stories": stories, "metrics": merge_metrics(state, tokens, skipped)}


# --- ESTIMATE / PRIORITIZE / SPRINT_PLAN (Bloque 4) -------------------------


async def node_estimate(state: ScrumState, config: RunnableConfig) -> dict:
    """ESTIMATE: story points Fibonacci por historia (LLM, D9)."""
    stories, skipped, tokens = await run_estimate(
        _llm(config),
        state.get("stories") or [],
        authoritative_context=state.get("authoritative_context"),
        concurrency=settings.EXTRACT_CONCURRENCY,
    )
    return {"stories": stories, "metrics": merge_metrics(state, tokens, skipped)}


async def node_prioritize(state: ScrumState, config: RunnableConfig) -> dict:
    """PRIORITIZE: MoSCoW + valor/esfuerzo (LLM) y backlog ordenado (Python)."""
    stories, skipped, tokens = await run_prioritize(
        _llm(config),
        state.get("stories") or [],
        authoritative_context=state.get("authoritative_context"),
        concurrency=settings.EXTRACT_CONCURRENCY,
    )
    backlog = build_backlog(stories)
    return {
        "stories": stories,
        "backlog": backlog,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_sprint_plan(state: ScrumState) -> dict:
    """SPRINT_PLAN: bin-packing determinista por capacidad (D4)."""
    stories = state.get("stories") or []
    backlog = state.get("backlog") or {}
    capacity = state.get("capacity_points") or settings.SCRUM_SPRINT_CAPACITY
    ordered = backlog.get("ordered_story_ids") or [s["id"] for s in stories]

    sprints, unassigned, _obs = plan_sprints(stories, ordered, capacity)
    annotate_goals(sprints, stories)
    return {"sprints": sprints, "unassigned_story_ids": unassigned}


# --- CRITIQUE / QUESTION_GEN (Bloque 5) -------------------------------------


async def node_critique(state: ScrumState, config: RunnableConfig) -> dict:
    """CRITIQUE: cobertura + refs huérfanas + ciclos + capacidad + riesgos (LLM)."""
    critique_llm = (config or {}).get("configurable", {}).get("critique_llm")
    critique_dict, tokens = await run_critique(
        state.get("stories") or [],
        state.get("epics") or [],
        state.get("ef_context") or {},
        state.get("unassigned_story_ids") or [],
        llm=critique_llm,
        authoritative_context=state.get("authoritative_context"),
    )
    return {"critique": critique_dict, "metrics": merge_metrics(state, tokens, [])}


async def node_question_gen(state: ScrumState) -> dict:
    """QUESTION_GEN: preguntas al PO (RF sin cobertura, ciclos, baja confianza)."""
    questions = generate_questions(
        state.get("critique") or {}, state.get("stories") or []
    )
    return {"questions": questions}


# --- ASSEMBLE / PERSIST -----------------------------------------------------


async def node_assemble(state: ScrumState) -> dict:
    """ASSEMBLE + VALIDATE: construye el ScrumArtifact y lo valida (v1.0.0)."""
    artifact, _ = assemble_artifact(state)
    dumped = artifact.model_dump(mode="json")
    validate_artifact(dumped)
    return {"artifact": dumped}


async def node_persist(state: ScrumState, config: RunnableConfig) -> dict:
    """PERSIST: guarda el artefacto y marca COMPLETED[_WITH_WARNINGS].

    La persistencia es inyectable por config (tests sin Postgres); si no se
    inyecta, usa la BD real vía session_scope.
    """
    artifact = state["artifact"]
    metrics = artifact.get("metrics") or {}
    has_warnings = bool(metrics.get("skipped"))
    status = "COMPLETED_WITH_WARNINGS" if has_warnings else "COMPLETED"

    persist = (config or {}).get("configurable", {}).get("persist")
    if persist is not None:
        await persist(state["job_id"], artifact, status, metrics)
    else:  # pragma: no cover - ruta runtime con Postgres real
        from app.dependencies.database import session_scope
        from app.models.agent import JobStatus
        from app.repositories.agent_job_repository import AgentJobRepository

        async with session_scope() as session:
            repo = AgentJobRepository(session)
            await repo.save_artifact(
                state["job_id"], artifact, artifact["schema_version"]
            )
            await repo.update_job_metrics(state["job_id"], metrics)
            await repo.update_job_status(state["job_id"], JobStatus[status])

    return {"status": status}
