"""Nodos del grafo LangGraph del Agente Scrum.

LOAD_EF (gate + contexto), ASSEMBLE y PERSIST son reales desde el Bloque 2. Los
nodos generativos/deterministas del medio (EPICS…QUESTION_GEN) son stubs que ya
producen estructuras válidas para correr el grafo de extremo a extremo; se
completan en los Bloques 3-5.
"""

import time

from langchain_core.runnables import RunnableConfig

from ai.agents.scrum.assemble import assemble_artifact, validate_artifact
from ai.agents.scrum.load_ef import assert_ef_ready, extract_ef_context
from ai.agents.scrum.state import ScrumState


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
    """EPICS (stub B2): sin épicas todavía."""
    return {"epics": list(state.get("epics") or [])}


async def node_stories(state: ScrumState, config: RunnableConfig) -> dict:
    """STORIES (stub B2): sin historias todavía."""
    return {"stories": list(state.get("stories") or [])}


async def node_criteria(state: ScrumState, config: RunnableConfig) -> dict:
    """CRITERIA (stub B2): los criterios se adjuntan a cada historia."""
    return {"stories": list(state.get("stories") or [])}


# --- ESTIMATE / PRIORITIZE / SPRINT_PLAN (Bloque 4) -------------------------


async def node_estimate(state: ScrumState, config: RunnableConfig) -> dict:
    """ESTIMATE (stub B2)."""
    return {"stories": list(state.get("stories") or [])}


async def node_prioritize(state: ScrumState, config: RunnableConfig) -> dict:
    """PRIORITIZE (stub B2): backlog vacío por defecto."""
    return {"backlog": dict(state.get("backlog") or {})}


async def node_sprint_plan(state: ScrumState) -> dict:
    """SPRINT_PLAN (stub B2): sin sprints todavía."""
    return {
        "sprints": list(state.get("sprints") or []),
        "unassigned_story_ids": list(state.get("unassigned_story_ids") or []),
    }


# --- CRITIQUE / QUESTION_GEN (Bloque 5) -------------------------------------


async def node_critique(state: ScrumState, config: RunnableConfig) -> dict:
    """CRITIQUE (stub B2): sin hallazgos todavía."""
    return {"critique": dict(state.get("critique") or {})}


async def node_question_gen(state: ScrumState) -> dict:
    """QUESTION_GEN (stub B2): sin preguntas al PO todavía."""
    return {"questions": list(state.get("questions") or [])}


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
