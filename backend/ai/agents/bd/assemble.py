"""Fase ASSEMBLE + VALIDATE del Agente BD.

Ensambla el ``DatabaseArtifact`` desde el estado del grafo, calcula métricas
reales y registra los descartes como ``Observation`` (NUNCA silenciosos, regla
heredada del EF). ``validate_artifact`` revalida contra el esquema v1.0.0.

Se escribe completo desde BD2 —aunque varios nodos aún sean stubs— para que cada
bloque posterior solo tenga que poblar su parte del estado: si el ensamblado
creciera bloque a bloque, cada uno tocaría este archivo y el contrato se iría
descubriendo por accidente en vez de estar fijado.
"""

import time
from typing import Any

from pydantic import BaseModel, ValidationError

from ai.agents.ef.schemas.artifact import Observation
from app.dependencies.claude import estimate_cost

from .schemas.artifact import (
    Conventions,
    Coverage,
    DatabaseAnalysis,
    DatabaseArtifact,
    DatabaseMetrics,
    DbaQuestion,
    DdlScript,
    DdlValidation,
    DesignDecision,
    DictionaryEntry,
    ErDiagram,
    Risk,
    RuleMapping,
    SeedData,
    SkippedItem,
    SourceRef,
    Table,
    Target,
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
    """Ratio de cobertura global (entidades + campos + validaciones + reglas)."""
    denom = (
        coverage.entities_total
        + coverage.fields_total
        + coverage.validations_total
        + coverage.rules_total
    )
    if denom <= 0:
        return 0.0
    num = (
        coverage.entities_mapped
        + coverage.fields_mapped
        + coverage.validations_enforced
        + coverage.rules_enforced
    )
    return round(num / denom, 4)


def _build_target(state: dict[str, Any]) -> Target:
    """Motor + convenciones efectivas, tal como los resolvió LOAD_SOURCES."""
    target = dict(state.get("target") or {})
    conventions = target.get("conventions") or {}
    return Target(
        engine=target.get("engine") or "postgresql",
        engine_version=target.get("engine_version"),
        engine_source_ref=target.get("engine_source_ref"),
        engine_decided=bool(target.get("engine_decided", True)),
        conventions=Conventions.model_validate(conventions),
        conventions_source=target.get("conventions_source"),
    )


def _count_constraints(tables: list[Table]) -> int:
    """PK + FK + unique + check de todas las tablas (para las métricas)."""
    total = 0
    for table in tables:
        total += 1 if table.primary_key else 0
        total += len(table.foreign_keys)
        total += len(table.unique_constraints)
        total += len(table.check_constraints)
    return total


def assemble_artifact(state: dict[str, Any]) -> tuple[DatabaseArtifact, bool]:
    """Ensambla el DatabaseArtifact. Devuelve (artifact, hubo_advertencias)."""
    discards: list[dict] = []

    tables = _map_list(state.get("tables"), Table, discards, "tables")
    ddl_scripts = _map_list(
        state.get("ddl_scripts"), DdlScript, discards, "ddl_scripts"
    )
    seed_data = _map_list(state.get("seed_data"), SeedData, discards, "seed_data")
    dictionary = _map_list(
        state.get("data_dictionary"), DictionaryEntry, discards, "data_dictionary"
    )
    decisions = _map_list(
        state.get("design_decisions"), DesignDecision, discards, "design_decisions"
    )
    rule_mappings = _map_list(
        state.get("rule_mappings"), RuleMapping, discards, "rule_mappings"
    )
    questions = _map_list(
        state.get("questions"), DbaQuestion, discards, "questions_for_dba"
    )

    critique = state.get("critique") or {}
    risks = _map_list(critique.get("risks"), Risk, discards, "risks")
    critique_obs = _map_list(
        critique.get("observations"), Observation, discards, "observations"
    )
    coverage = Coverage.model_validate(critique.get("coverage") or {})

    validation = DdlValidation.model_validate(state.get("validation") or {})
    er_diagram = ErDiagram.model_validate(state.get("er_diagram") or {})

    # Observaciones = crítica + correcciones sobre el LLM + descartes. Las tres
    # familias son NO silenciosas por regla del proyecto.
    observations = list(critique_obs)
    idx = len(observations)
    for extra in list(state.get("model_observations") or []) + discards:
        idx += 1
        observations.append(
            Observation(
                id=f"OBS-D-{idx:03d}",
                description=extra.get("description", ""),
                reason=extra.get("reason"),
            )
        )

    analysis = DatabaseAnalysis(
        risks=risks, observations=observations, coverage=coverage
    )

    # Métricas reales.
    metrics_in = dict(state.get("metrics") or {})
    tokens = metrics_in.get("tokens") or {"input": 0, "output": 0, "total": 0}
    duration = max(0.0, time.time() - state.get("started_at", time.time()))
    skipped = metrics_in.get("skipped") or []
    metrics = DatabaseMetrics(
        tokens=TokenMetrics(**tokens),
        cost=estimate_cost(tokens.get("input", 0), tokens.get("output", 0)),
        duration=round(duration, 3),
        tables_total=len(tables),
        columns_total=sum(len(t.columns) for t in tables),
        indexes_total=sum(len(t.indexes) for t in tables),
        constraints_total=_count_constraints(tables),
        seed_rows_total=sum(len(s.rows) for s in seed_data),
        coverage=_overall_coverage(coverage),
        # El DDL solo se declara válido si se validó Y no hay errores.
        ddl_valid=bool(validation.syntax_ok and not validation.errors),
        skipped=[SkippedItem(**s) for s in skipped],
    )

    artifact = DatabaseArtifact(
        source=SourceRef(
            architecture_job_id=state.get("architecture_job_id", ""),
            architecture_artifact_hash=state.get("architecture_artifact_hash", ""),
            scrum_job_id=state.get("scrum_job_id") or None,
            scrum_artifact_hash=state.get("scrum_artifact_hash") or None,
            ef_job_id=state.get("ef_job_id", ""),
            ef_artifact_hash=state.get("ef_artifact_hash", ""),
            ready_snapshot=bool(state.get("architecture_ready", True)),
        ),
        target=_build_target(state),
        tables=tables,
        ddl_scripts=ddl_scripts,
        seed_data=seed_data,
        data_dictionary=dictionary,
        er_diagram=er_diagram,
        design_decisions=decisions,
        rule_mappings=rule_mappings,
        validation=validation,
        analysis=analysis,
        questions_for_dba=questions,
        metrics=metrics,
    )

    has_warnings = bool(skipped) or bool(discards) or bool(validation.errors)
    return artifact, has_warnings


def validate_artifact(artifact_dict: dict) -> DatabaseArtifact:
    """VALIDATE: revalida el artefacto contra el esquema v1.0.0."""
    return DatabaseArtifact.model_validate(artifact_dict)
