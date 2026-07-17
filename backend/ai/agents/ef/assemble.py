"""Fase ASSEMBLE + VALIDATE: construye el EFArtifact y calcula métricas reales.

- Cada ítem inválido que se descarta deja una Observation con id y motivo
  (los descartes NUNCA son silenciosos).
- Autoverifica ítems `stated` sin evidencia (deja Observation, no descarta).
- Calcula métricas: tokens/costo/duración/coverage y cuarentena (skipped).
"""

import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.dependencies.claude import estimate_cost

from .schemas.artifact import (
    Actor,
    Ambiguity,
    Analysis,
    ApiEndpoint,
    BusinessRule,
    CrudMatrixEntry,
    EFArtifact,
    Entity,
    FieldDef,
    Inconsistency,
    Menu,
    Metrics,
    MissingInfo,
    Module,
    Observation,
    Process,
    Question,
    Relationship,
    Requirement,
    RequirementsBlock,
    SkippedItem,
    SourceInfo,
    SystemsInterpretation,
    TokenMetrics,
    ValidationRule,
)

_STATED = "stated"


def _map_list(
    raw_items: list[dict], model: type[BaseModel], discards: list[dict], stage: str
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
                        f"Ítem descartado en {stage} (id={raw.get('id')})."
                    ),
                    "reason": str(exc)[:300],
                }
            )
    return out


def _no_evidence_observations(sections: list[tuple[str, list]]) -> list[dict]:
    """Autoverificación: ítems 'stated' sin evidencia verbatim."""
    obs: list[dict] = []
    for stage, items in sections:
        for item in items:
            origin = getattr(item, "origin", None)
            evidence = getattr(item, "evidence", None)
            origin_val = origin.value if origin is not None else None
            if origin_val == _STATED and not evidence:
                obs.append(
                    {
                        "description": (
                            f"Ítem 'stated' sin evidencia en {stage}: {item.id}."
                        ),
                        "reason": "Autoverificación: falta cita verbatim.",
                    }
                )
    return obs


def assemble_artifact(state: dict[str, Any]) -> tuple[EFArtifact, bool]:
    """Ensambla el EFArtifact. Devuelve (artifact, hubo_advertencias)."""
    consolidated = state.get("consolidated_model") or {}
    inferred = state.get("inferred_model") or {}
    critique = state.get("critique") or {}
    si = state.get("systems_interpretation") or {"what_process_requests": "(pendiente)"}
    source = state["source"]
    metrics_in = dict(state.get("metrics") or {})

    discards: list[dict] = []

    reqs = consolidated.get("requirements", {})
    requirements = RequirementsBlock(
        business=_map_list(reqs.get("business"), Requirement, discards, "req.business"),
        functional=_map_list(
            reqs.get("functional"), Requirement, discards, "req.functional"
        ),
        non_functional=_map_list(
            reqs.get("non_functional"), Requirement, discards, "req.non_functional"
        ),
    )
    actors = _map_list(consolidated.get("actors"), Actor, discards, "actors")
    modules = _map_list(consolidated.get("modules"), Module, discards, "modules")
    menus = _map_list(consolidated.get("menus"), Menu, discards, "menus")
    processes = _map_list(consolidated.get("processes"), Process, discards, "processes")
    business_rules = _map_list(
        consolidated.get("business_rules"), BusinessRule, discards, "business_rules"
    )
    validations = _map_list(
        consolidated.get("validations"), ValidationRule, discards, "validations"
    )
    fields = _map_list(
        inferred.get("fields") or consolidated.get("fields"),
        FieldDef,
        discards,
        "fields",
    )
    entities = _map_list(inferred.get("entities"), Entity, discards, "entities")
    relationships = _map_list(
        inferred.get("relationships"), Relationship, discards, "relationships"
    )
    crud = _map_list(inferred.get("crud"), CrudMatrixEntry, discards, "crud")
    apis = _map_list(inferred.get("apis"), ApiEndpoint, discards, "apis")

    # Análisis: quitar la clave interna 'kind' de las inconsistencias.
    inconsistencies_raw = [
        {k: v for k, v in i.items() if k != "kind"}
        for i in critique.get("inconsistencies", [])
    ]
    ambiguities = _map_list(critique.get("ambiguities"), Ambiguity, discards, "amb")
    missing_info = _map_list(
        critique.get("missing_info"), MissingInfo, discards, "miss"
    )
    inconsistencies = _map_list(inconsistencies_raw, Inconsistency, discards, "inc")
    critique_obs = _map_list(critique.get("observations"), Observation, discards, "obs")

    questions = _map_list(state.get("questions"), Question, discards, "questions")

    # Autoverificación de evidencia sobre secciones 'stated'.
    no_ev = _no_evidence_observations(
        [
            ("req.business", requirements.business),
            ("req.functional", requirements.functional),
            ("actors", actors),
            ("processes", processes),
            ("business_rules", business_rules),
        ]
    )

    # Observaciones = crítica + descartes (NO silenciosos) + autoverificación.
    observations = list(critique_obs)
    idx = len(observations)
    for extra in discards + no_ev:
        idx += 1
        observations.append(Observation(id=f"OBS-A-{idx:03d}", **extra))

    analysis = Analysis(
        ambiguities=ambiguities,
        missing_info=missing_info,
        inconsistencies=inconsistencies,
        observations=observations,
    )

    try:
        interpretation = SystemsInterpretation.model_validate(si)
    except ValidationError:
        interpretation = SystemsInterpretation(
            what_process_requests=si.get("what_process_requests", "(pendiente)")
        )

    # Métricas reales.
    tokens = metrics_in.get("tokens") or {"input": 0, "output": 0, "total": 0}
    duration = max(0.0, time.time() - state.get("started_at", time.time()))
    skipped = metrics_in.get("skipped") or []
    metrics = Metrics(
        tokens=TokenMetrics(**tokens),
        cost=estimate_cost(tokens.get("input", 0), tokens.get("output", 0)),
        duration=round(duration, 3),
        chunks_total=metrics_in.get("chunks_total", 0),
        chunks_skipped=metrics_in.get("chunks_skipped", 0),
        coverage=metrics_in.get("coverage", 1.0),
        skipped=[SkippedItem(**s) for s in skipped],
    )

    summary = state.get("summary") or si.get("what_process_requests") or "(sin resumen)"

    artifact = EFArtifact(
        source=SourceInfo(
            type=source["source_type"],
            hash=source["content_hash"],
            fidelity=(state.get("cir") or {}).get("fidelity") or "full",
            filename=source.get("filename"),
        ),
        summary=summary,
        requirements=requirements,
        actors=actors,
        modules=modules,
        menus=menus,
        processes=processes,
        business_rules=business_rules,
        validations=validations,
        fields=fields,
        entities=entities,
        relationships=relationships,
        crud=crud,
        apis=apis,
        systems_interpretation=interpretation,
        analysis=analysis,
        questions_for_analyst=questions,
        metrics=metrics,
    )

    has_warnings = bool(skipped)
    return artifact, has_warnings


def validate_artifact(artifact_dict: dict) -> EFArtifact:
    """VALIDATE: revalida el artefacto contra el esquema v1.2.0."""
    return EFArtifact.model_validate(artifact_dict)
