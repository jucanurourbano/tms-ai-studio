"""Fase ASSEMBLE + VALIDATE del Agente Scrum.

Ensambla el ``ScrumArtifact`` a partir del estado del grafo, calcula métricas
reales y registra los descartes como ``Observation`` (NUNCA silenciosos, regla
heredada del EF). ``validate_artifact`` revalida contra el esquema v1.0.0.
"""

import time
from typing import Any

from pydantic import BaseModel, ValidationError

from ai.agents.ef.schemas.artifact import Observation
from app.dependencies.claude import estimate_cost

from .schemas.artifact import (
    Coverage,
    Epic,
    PoQuestion,
    ProductBacklog,
    Risk,
    ScrumAnalysis,
    ScrumArtifact,
    ScrumMetrics,
    SkippedItem,
    SourceRef,
    Sprint,
    Story,
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


def assemble_artifact(state: dict[str, Any]) -> tuple[ScrumArtifact, bool]:
    """Ensambla el ScrumArtifact. Devuelve (artifact, hubo_advertencias)."""
    discards: list[dict] = []

    epics = _map_list(state.get("epics"), Epic, discards, "epics")
    stories = _map_list(state.get("stories"), Story, discards, "stories")
    questions = _map_list(
        state.get("questions"), PoQuestion, discards, "questions_for_po"
    )

    critique = state.get("critique") or {}
    risks = _map_list(critique.get("risks"), Risk, discards, "risks")
    critique_obs = _map_list(
        critique.get("observations"), Observation, discards, "observations"
    )
    coverage = Coverage.model_validate(critique.get("coverage") or {})

    backlog = ProductBacklog.model_validate(state.get("backlog") or {})
    sprints = _map_list(state.get("sprints"), Sprint, discards, "sprints")

    # Observaciones = crítica + descartes NO silenciosos.
    observations = list(critique_obs)
    idx = len(observations)
    for extra in discards:
        idx += 1
        observations.append(Observation(id=f"OBS-A-{idx:03d}", **extra))

    analysis = ScrumAnalysis(risks=risks, observations=observations, coverage=coverage)

    # Métricas reales.
    metrics_in = dict(state.get("metrics") or {})
    tokens = metrics_in.get("tokens") or {"input": 0, "output": 0, "total": 0}
    duration = max(0.0, time.time() - state.get("started_at", time.time()))
    skipped = metrics_in.get("skipped") or []
    points_total = sum(s.story_points or 0 for s in stories)
    metrics = ScrumMetrics(
        tokens=TokenMetrics(**tokens),
        cost=estimate_cost(tokens.get("input", 0), tokens.get("output", 0)),
        duration=round(duration, 3),
        stories_total=len(stories),
        points_total=points_total,
        sprints_total=len(sprints),
        coverage=coverage.coverage_ratio,
        skipped=[SkippedItem(**s) for s in skipped],
    )

    artifact = ScrumArtifact(
        source=SourceRef(
            ef_job_id=state.get("ef_job_id", ""),
            ef_artifact_hash=state.get("ef_artifact_hash", ""),
            ready_snapshot=bool(state.get("ef_ready", True)),
        ),
        epics=epics,
        stories=stories,
        product_backlog=backlog,
        sprints=sprints,
        unassigned_story_ids=list(state.get("unassigned_story_ids") or []),
        questions_for_po=questions,
        analysis=analysis,
        metrics=metrics,
    )

    has_warnings = bool(skipped) or bool(discards)
    return artifact, has_warnings


def validate_artifact(artifact_dict: dict) -> ScrumArtifact:
    """VALIDATE: revalida el artefacto contra el esquema v1.0.0."""
    return ScrumArtifact.model_validate(artifact_dict)
