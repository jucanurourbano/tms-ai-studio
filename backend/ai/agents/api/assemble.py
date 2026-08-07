"""Fase ASSEMBLE + VALIDATE del Agente API.

Ensambla el ``ApiArtifact`` desde el estado del grafo, calcula métricas reales y
registra los descartes como ``Observation`` (NUNCA silenciosos, regla heredada del
EF). ``validate_artifact`` revalida contra el esquema v1.0.0.

Una nota sobre el ensamblado: un ítem que no valide contra el contrato **se
descarta con su motivo** en vez de tumbar el job. Suena permisivo y no lo es —
las invariantes que de verdad importan (un campo sin columna, un alcance sin
materializar) ya están dentro del contrato, así que si un ítem cae aquí es porque
violaba una de ellas, y la observación resultante lo dice con el error de
validación completo. Entregar el resto del contrato señalando la pieza rota es
más útil que no entregar nada.
"""

import time
from typing import Any

from pydantic import BaseModel, ValidationError

from ai.agents.ef.schemas.artifact import Observation
from app.dependencies.claude import estimate_cost

from .schemas.artifact import (
    ApiAnalysis,
    ApiArtifact,
    ApiMetrics,
    ApiRuleMapping,
    ApiSchema,
    AuthConfig,
    AuthorizationRule,
    Conventions,
    Coverage,
    Endpoint,
    ErrorEntry,
    OpenApiDocument,
    Resource,
    Risk,
    SkippedItem,
    SourceRef,
    SpecValidation,
    Target,
    TechLeadQuestion,
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


def _build_target(state: dict[str, Any]) -> Target:
    """Estilo, seguridad y convenciones efectivas, tal como los fijó LOAD_SOURCES."""
    target = dict(state.get("target") or {})
    auth = target.get("auth") or {}
    return Target(
        api_style=target.get("api_style") or "rest",
        spec_version=target.get("spec_version") or "3.1.0",
        base_path=target.get("base_path") or "/api/v1",
        auth=AuthConfig(
            scheme=auth.get("scheme") or "bearer_jwt",
            provider=auth.get("provider"),
            source_ref=auth.get("source_ref"),
            decided=bool(auth.get("decided", True)),
        ),
        conventions=Conventions.model_validate(target.get("conventions") or {}),
        conventions_source=target.get("conventions_source"),
    )


def assemble_artifact(state: dict[str, Any]) -> tuple[ApiArtifact, bool]:
    """Ensambla el ApiArtifact. Devuelve ``(artifact, hubo_advertencias)``."""
    discards: list[dict] = []

    resources = _map_list(state.get("resources"), Resource, discards, "resources")
    schemas = _map_list(state.get("schemas"), ApiSchema, discards, "schemas")
    endpoints = _map_list(state.get("endpoints"), Endpoint, discards, "endpoints")
    matriz = _map_list(
        state.get("authorization_matrix"),
        AuthorizationRule,
        discards,
        "authorization_matrix",
    )
    errores = _map_list(
        state.get("error_catalog"), ErrorEntry, discards, "error_catalog"
    )
    rule_mappings = _map_list(
        state.get("rule_mappings"), ApiRuleMapping, discards, "rule_mappings"
    )
    questions = _map_list(
        state.get("questions"), TechLeadQuestion, discards, "questions_for_tech_lead"
    )

    critique = state.get("critique") or {}
    risks = _map_list(critique.get("risks"), Risk, discards, "risks")
    coverage = Coverage.model_validate(critique.get("coverage") or {})

    validation = SpecValidation.model_validate(state.get("validation") or {})
    openapi = OpenApiDocument.model_validate(state.get("openapi") or {})

    # Observaciones = las correcciones que los nodos fueron aplicando sobre las
    # propuestas del modelo + los descartes de este ensamblado. Las dos familias
    # son NO silenciosas por regla del proyecto.
    observations: list[Observation] = []
    for indice, nota in enumerate(state.get("map_observations") or [], start=1):
        observations.append(
            Observation(
                id=f"OBS-{indice:03d}",
                description=nota.get("description", ""),
                reason=nota.get("reason"),
            )
        )
    indice = len(observations)
    for extra in discards:
        indice += 1
        observations.append(
            Observation(
                id=f"OBS-D-{indice:03d}",
                description=extra.get("description", ""),
                reason=extra.get("reason"),
            )
        )

    analysis = ApiAnalysis(risks=risks, observations=observations, coverage=coverage)

    metrics_in = dict(state.get("metrics") or {})
    tokens = metrics_in.get("tokens") or {"input": 0, "output": 0, "total": 0}
    duration = max(0.0, time.time() - state.get("started_at", time.time()))
    skipped = metrics_in.get("skipped") or []
    permitidos = {r.endpoint_ref for r in matriz if r.effect.value == "allow"}
    metrics = ApiMetrics(
        tokens=TokenMetrics(**tokens),
        cost=estimate_cost(tokens.get("input", 0), tokens.get("output", 0)),
        duration=round(duration, 3),
        resources_total=len(resources),
        endpoints_total=len(endpoints),
        schemas_total=len(schemas),
        auth_rules_total=len(matriz),
        coverage=float(critique.get("coverage_ratio") or 0.0),
        # La especificación solo se declara válida si se validó Y no hay errores.
        spec_valid=bool(validation.spec_valid and not validation.errors),
        endpoints_unauthorized=len([e for e in endpoints if e.id not in permitidos]),
        skipped=[SkippedItem(**s) for s in skipped],
    )

    artifact = ApiArtifact(
        source=SourceRef(
            bd_job_id=state.get("bd_job_id", ""),
            bd_artifact_hash=state.get("bd_artifact_hash", ""),
            architecture_job_id=state.get("architecture_job_id") or None,
            architecture_artifact_hash=state.get("architecture_artifact_hash") or None,
            scrum_job_id=state.get("scrum_job_id") or None,
            scrum_artifact_hash=state.get("scrum_artifact_hash") or None,
            ef_job_id=state.get("ef_job_id", ""),
            ef_artifact_hash=state.get("ef_artifact_hash", ""),
            ready_snapshot=bool(state.get("bd_ready", True)),
        ),
        target=_build_target(state),
        resources=resources,
        schemas=schemas,
        endpoints=endpoints,
        authorization_matrix=matriz,
        error_catalog=errores,
        rule_mappings=rule_mappings,
        openapi=openapi,
        validation=validation,
        analysis=analysis,
        questions_for_tech_lead=questions,
        metrics=metrics,
    )

    has_warnings = bool(skipped) or bool(discards) or bool(validation.errors)
    return artifact, has_warnings


def validate_artifact(artifact_dict: dict) -> ApiArtifact:
    """VALIDATE: revalida el artefacto contra el esquema v1.0.0."""
    return ApiArtifact.model_validate(artifact_dict)
