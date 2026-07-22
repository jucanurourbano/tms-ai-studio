"""Nodos del grafo LangGraph del Agente Arquitectura.

Pipeline completo: LOAD_SOURCES (gate + contexto EF+Scrum) → CONTEXT (scope
determinista) → COMPONENTS/STACK (A3) → ADRS/CONTRACTS/DIAGRAMS (A4) →
CRITIQUE/QUESTION_GEN (A5) → ASSEMBLE/PERSIST. Los nodos generativos usan LLM
inyectable (mock en tests); los diagramas y la cobertura son deterministas.
"""

import time

from langchain_core.runnables import RunnableConfig

from ai.agents.arquitectura.adrs import run_adrs
from ai.agents.arquitectura.assemble import assemble_artifact, validate_artifact
from ai.agents.arquitectura.common import merge_metrics
from ai.agents.arquitectura.components import run_components
from ai.agents.arquitectura.context import build_scope_profile, classify_size
from ai.agents.arquitectura.contracts import run_contracts
from ai.agents.arquitectura.critique import run_critique
from ai.agents.arquitectura.diagrams import build_diagrams
from ai.agents.arquitectura.load_sources import (
    assert_scrum_ready,
    extract_sources,
    resolve_ef_hash,
)
from ai.agents.arquitectura.question_gen import generate_questions
from ai.agents.arquitectura.stack import run_stack
from ai.agents.arquitectura.state import ArchitectureState
from ai.agents.base.structured import ClaudeLLMClient
from app.config.settings import settings


def _llm(config: RunnableConfig):
    """LLM inyectado por config (mock en tests); si no, el cliente real."""
    llm = (config or {}).get("configurable", {}).get("llm")
    return llm if llm is not None else ClaudeLLMClient()


def _adr_valid_refs(
    sources: dict, components: list[dict], stack: list[dict]
) -> set[str]:
    """Refs reales que un ADR puede citar: EF + Scrum + componentes + stack."""
    ef = sources.get("ef", {}) or {}
    scrum = sources.get("scrum", {}) or {}
    reqs = ef.get("requirements", {}) or {}
    valid: set[str] = set()
    for key in (
        "entities",
        "apis",
        "modules",
        "processes",
        "business_rules",
        "validations",
    ):
        valid |= {i["id"] for i in ef.get(key, []) if i.get("id")}
    valid |= {r["id"] for r in reqs.get("non_functional", []) if r.get("id")}
    valid |= {e["id"] for e in scrum.get("epics", []) if e.get("id")}
    valid |= {s["id"] for s in scrum.get("stories", []) if s.get("id")}
    valid |= {c["id"] for c in components if c.get("id")}
    valid |= {s["id"] for s in stack if s.get("id")}
    return valid


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


# --- COMPONENTS / STACK (Bloque A3) -----------------------------------------


async def node_components(state: ArchitectureState, config: RunnableConfig) -> dict:
    """COMPONENTS: deriva componentes desde EF (módulos/entidades/APIs/procesos) y
    Scrum (épicas/historias), con trazabilidad y ``depends_on`` resueltos."""
    components, skipped, tokens = await run_components(
        _llm(config),
        state.get("sources") or {},
        state.get("size_class") or "M",
        authoritative_context=state.get("authoritative_context"),
    )
    return {"components": components, "metrics": merge_metrics(state, tokens, skipped)}


async def node_stack(state: ArchitectureState, config: RunnableConfig) -> dict:
    """STACK: recomienda el stack por capa desde el allow-list de la casa."""
    component_types = sorted(
        {c.get("type") for c in state.get("components") or [] if c.get("type")}
    )
    stack, skipped, tokens = await run_stack(
        _llm(config),
        state.get("sources") or {},
        state.get("size_class") or "M",
        component_types,
        authoritative_context=state.get("authoritative_context"),
    )
    return {"stack": stack, "metrics": merge_metrics(state, tokens, skipped)}


# --- ADRS / CONTRACTS / DIAGRAMS (Bloque A4) --------------------------------


async def node_adrs(state: ArchitectureState, config: RunnableConfig) -> dict:
    """ADRS: estilo (determinista desde size_class) + ADRs adicionales (LLM)."""
    sources = state.get("sources") or {}
    components = state.get("components") or []
    stack = state.get("stack") or []
    adrs, style, skipped, tokens = await run_adrs(
        _llm(config),
        state.get("size_class") or "M",
        state.get("scope_profile") or {},
        components,
        stack,
        _adr_valid_refs(sources, components, stack),
        authoritative_context=state.get("authoritative_context"),
    )
    return {
        "adrs": adrs,
        "style": style,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_contracts(state: ArchitectureState, config: RunnableConfig) -> dict:
    """CONTRACTS: contratos (determinista) + integraciones y transversales (LLM)."""
    contracts, integrations, cross_cutting, skipped, tokens = await run_contracts(
        _llm(config),
        state.get("sources") or {},
        state.get("components") or [],
        authoritative_context=state.get("authoritative_context"),
    )
    return {
        "contracts": contracts,
        "integrations": integrations,
        "cross_cutting": cross_cutting,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_diagrams(state: ArchitectureState) -> dict:
    """DIAGRAMS: Mermaid determinista desde componentes/contratos/integraciones."""
    actors = (state.get("sources") or {}).get("ef", {}).get("actors", []) or []
    diagrams = build_diagrams(
        state.get("components") or [],
        state.get("contracts") or [],
        state.get("integrations") or [],
        actors,
    )
    return {"diagrams": diagrams}


# --- CRITIQUE / QUESTION_GEN (Bloque A5) ------------------------------------


async def node_critique(state: ArchitectureState, config: RunnableConfig) -> dict:
    """CRITIQUE: cobertura (épicas/entidades/RNF) + ciclos + integraciones sin
    contrato + riesgos (pase LLM opcional)."""
    critique_dict, tokens = await run_critique(
        state.get("components") or [],
        state.get("contracts") or [],
        state.get("integrations") or [],
        state.get("cross_cutting") or [],
        state.get("sources") or {},
        llm=_llm(config),
        authoritative_context=state.get("authoritative_context"),
    )
    return {"critique": critique_dict, "metrics": merge_metrics(state, tokens, [])}


async def node_question_gen(state: ArchitectureState) -> dict:
    """QUESTION_GEN: preguntas al Arquitecto (RNF/integraciones/cobertura → bloqueantes)."""
    questions = generate_questions(state.get("critique") or {})
    return {"questions": questions}


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
