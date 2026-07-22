"""Fase ASSEMBLE + VALIDATE del Agente Arquitectura.

Ensambla el ``ArchitectureArtifact`` a partir del estado del grafo, calcula
métricas reales y registra los descartes como ``Observation`` (NUNCA silenciosos,
regla heredada del EF). ``validate_artifact`` revalida contra el esquema v1.0.0.
"""

import time
from typing import Any

from pydantic import BaseModel, ValidationError

from ai.agents.ef.schemas.artifact import Observation
from app.dependencies.claude import estimate_cost

from .schemas.artifact import (
    Adr,
    ArchitectQuestion,
    ArchitectureAnalysis,
    ArchitectureArtifact,
    ArchitectureContext,
    ArchitectureMetrics,
    BoundedContext,
    Component,
    Contract,
    Coverage,
    CrossCutting,
    Diagrams,
    Integration,
    Risk,
    ScopeProfile,
    SkippedItem,
    SourceRef,
    StackChoice,
    StyleDecision,
    TokenMetrics,
)


def _map_list(
    raw_items: list, model: type[BaseModel], discards: list[dict], stage: str
) -> list[BaseModel]:
    """Valida cada ítem; los inválidos se descartan dejando una Observation."""
    out: list[BaseModel] = []
    for raw in raw_items or []:
        try:
            out.append(model.model_validate(raw))
        except ValidationError as exc:
            discards.append(
                {
                    "description": (
                        f"Ítem descartado en {stage} "
                        f"(id={raw.get('id') if isinstance(raw, dict) else '?'})."
                    ),
                    "reason": str(exc)[:300],
                }
            )
    return out


def _overall_coverage(coverage: Coverage) -> float:
    """Ratio de cobertura global (épicas + entidades + RNF), 0 si no hay base."""
    denom = coverage.epics_total + coverage.entities_total + coverage.nfr_total
    if denom <= 0:
        return 0.0
    num = coverage.epics_mapped + coverage.entities_mapped + coverage.nfr_addressed
    return round(num / denom, 4)


def assemble_artifact(state: dict[str, Any]) -> tuple[ArchitectureArtifact, bool]:
    """Ensambla el ArchitectureArtifact. Devuelve (artifact, hubo_advertencias)."""
    discards: list[dict] = []

    components = _map_list(state.get("components"), Component, discards, "components")
    stack = _map_list(state.get("stack"), StackChoice, discards, "stack")
    adrs = _map_list(state.get("adrs"), Adr, discards, "adrs")
    integrations = _map_list(
        state.get("integrations"), Integration, discards, "integrations"
    )
    contracts = _map_list(state.get("contracts"), Contract, discards, "contracts")
    cross_cutting = _map_list(
        state.get("cross_cutting"), CrossCutting, discards, "cross_cutting"
    )
    questions = _map_list(
        state.get("questions"), ArchitectQuestion, discards, "questions_for_architect"
    )

    critique = state.get("critique") or {}
    risks = _map_list(critique.get("risks"), Risk, discards, "risks")
    critique_obs = _map_list(
        critique.get("observations"), Observation, discards, "observations"
    )
    coverage = Coverage.model_validate(critique.get("coverage") or {})

    bounded = _map_list(
        state.get("bounded_contexts"), BoundedContext, discards, "bounded_contexts"
    )
    context = ArchitectureContext(
        scope_profile=ScopeProfile.model_validate(state.get("scope_profile") or {}),
        size_class=state.get("size_class") or "M",
        bounded_contexts=bounded,
    )

    style_raw = state.get("style")
    style = StyleDecision.model_validate(style_raw) if style_raw else None

    diagrams = Diagrams.model_validate(state.get("diagrams") or {})

    # Observaciones = crítica + descartes NO silenciosos.
    observations = list(critique_obs)
    idx = len(observations)
    for extra in discards:
        idx += 1
        observations.append(Observation(id=f"OBS-A-{idx:03d}", **extra))

    analysis = ArchitectureAnalysis(
        risks=risks, observations=observations, coverage=coverage
    )

    # Métricas reales.
    metrics_in = dict(state.get("metrics") or {})
    tokens = metrics_in.get("tokens") or {"input": 0, "output": 0, "total": 0}
    duration = max(0.0, time.time() - state.get("started_at", time.time()))
    skipped = metrics_in.get("skipped") or []
    metrics = ArchitectureMetrics(
        tokens=TokenMetrics(**tokens),
        cost=estimate_cost(tokens.get("input", 0), tokens.get("output", 0)),
        duration=round(duration, 3),
        components_total=len(components),
        adrs_total=len(adrs),
        integrations_total=len(integrations),
        coverage=_overall_coverage(coverage),
        skipped=[SkippedItem(**s) for s in skipped],
    )

    artifact = ArchitectureArtifact(
        source=SourceRef(
            scrum_job_id=state.get("scrum_job_id", ""),
            scrum_artifact_hash=state.get("scrum_artifact_hash", ""),
            ef_job_id=state.get("ef_job_id", ""),
            ef_artifact_hash=state.get("ef_artifact_hash", ""),
            ready_snapshot=bool(state.get("scrum_ready", True)),
        ),
        context=context,
        architecture_style=style,
        components=components,
        stack=stack,
        adrs=adrs,
        integrations=integrations,
        contracts=contracts,
        cross_cutting=cross_cutting,
        diagrams=diagrams,
        analysis=analysis,
        questions_for_architect=questions,
        metrics=metrics,
    )

    has_warnings = bool(skipped) or bool(discards)
    return artifact, has_warnings


def validate_artifact(artifact_dict: dict) -> ArchitectureArtifact:
    """VALIDATE: revalida el artefacto contra el esquema v1.0.0."""
    return ArchitectureArtifact.model_validate(artifact_dict)
