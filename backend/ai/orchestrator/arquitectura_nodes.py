"""Nodos del grafo LangGraph del Agente Arquitectura.

LOAD_SOURCES (gate + contexto consolidado), CONTEXT (scope profile determinista),
ASSEMBLE y PERSIST son reales desde el Bloque A2. Los nodos generativos del medio
(COMPONENTS…QUESTION_GEN) son *stubs* que dejan pasar el estado para correr el
grafo de extremo a extremo; se completan en los Bloques A3-A5.
"""

import time

from langchain_core.runnables import RunnableConfig

from ai.agents.arquitectura.assemble import assemble_artifact, validate_artifact
from ai.agents.arquitectura.context import build_scope_profile, classify_size
from ai.agents.arquitectura.load_sources import (
    assert_scrum_ready,
    extract_sources,
    resolve_ef_hash,
)
from ai.agents.arquitectura.state import ArchitectureState
from app.config.settings import settings


async def node_load_sources(state: ArchitectureState) -> dict:
    """LOAD_SOURCES: verifica el gate del Scrum y consolida el contexto EF+Scrum."""
    assert_scrum_ready(bool(state.get("scrum_ready")), state.get("scrum_job_id", "?"))
    ef_artifact = state.get("ef_artifact") or {}
    scrum_artifact = state.get("scrum_artifact") or {}
    return {
        "sources": extract_sources(ef_artifact, scrum_artifact),
        "scrum_artifact_hash": state.get("scrum_artifact_hash") or "",
        "ef_artifact_hash": resolve_ef_hash(
            state.get("ef_artifact_hash", ""), scrum_artifact, ef_artifact
        ),
        "status": "RUNNING",
        "metrics": dict(state.get("metrics") or {}),
        "errors": [],
        "started_at": time.time(),
    }


async def node_context(state: ArchitectureState) -> dict:
    """CONTEXT: perfil de alcance determinista + clasificación de tamaño."""
    profile = build_scope_profile(state.get("sources") or {})
    size = classify_size(
        profile, settings.ARCH_SIZE_SMALL_MAX, settings.ARCH_SIZE_LARGE_MIN
    )
    return {"scope_profile": profile, "size_class": size, "bounded_contexts": []}


# --- COMPONENTS / STACK / ADRS / CONTRACTS / DIAGRAMS (stubs A3-A4) ---------


async def node_components(state: ArchitectureState) -> dict:
    """COMPONENTS (stub A3): derivará componentes desde módulos/entidades/épicas."""
    return {"components": []}


async def node_stack(state: ArchitectureState) -> dict:
    """STACK (stub A3): recomendará stack por capa desde el allow-list de la casa."""
    return {"stack": []}


async def node_adrs(state: ArchitectureState) -> dict:
    """ADRS (stub A4): sintetizará las decisiones de arquitectura."""
    return {"adrs": []}


async def node_contracts(state: ArchitectureState) -> dict:
    """CONTRACTS (stub A4): contratos, integraciones y transversales."""
    return {"contracts": [], "integrations": [], "cross_cutting": []}


async def node_diagrams(state: ArchitectureState) -> dict:
    """DIAGRAMS (stub A4): generará Mermaid determinista desde componentes."""
    return {"diagrams": {}}


# --- CRITIQUE / QUESTION_GEN (stubs A5) -------------------------------------


async def node_critique(state: ArchitectureState) -> dict:
    """CRITIQUE (stub A5): cobertura + refs huérfanas + ciclos + riesgos."""
    return {"critique": {}}


async def node_question_gen(state: ArchitectureState) -> dict:
    """QUESTION_GEN (stub A5): preguntas al Arquitecto desde los vacíos."""
    return {"questions": []}


# --- ASSEMBLE / PERSIST -----------------------------------------------------


async def node_assemble(state: ArchitectureState) -> dict:
    """ASSEMBLE + VALIDATE: construye el ArchitectureArtifact y lo valida (v1.0.0)."""
    artifact, _ = assemble_artifact(state)
    dumped = artifact.model_dump(mode="json")
    validate_artifact(dumped)
    return {"artifact": dumped}


async def node_persist(state: ArchitectureState, config: RunnableConfig) -> dict:
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
