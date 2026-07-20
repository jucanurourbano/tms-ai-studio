"""Ejemplo válido de ScrumArtifact (dominio: siniestros logísticos).

Deriva del ``example_artifact`` del EF (mismos REQ-/PRO-/BR-refs) para ser
reutilizable como fixture en tests de bloques posteriores.
"""

# Reusa TokenMetrics del EF.
from ai.agents.ef.schemas.artifact import TokenMetrics  # noqa: E402
from ai.agents.ef.schemas.enums import Audience, Origin  # noqa: E402

from .artifact import (
    AcceptanceCriterion,
    Coverage,
    Epic,
    PoQuestion,
    ProductBacklog,
    Risk,
    ScrumAnalysis,
    ScrumArtifact,
    ScrumMetrics,
    SourceRef,
    Sprint,
    Story,
    StorySourceRefs,
)
from .enums import (
    AcceptanceFormat,
    BacklogMethod,
    MoscowPriority,
    RiskSeverity,
    StoryPoints,
)


def example_artifact() -> ScrumArtifact:
    """Devuelve un ScrumArtifact v1.0.0 válido de ejemplo (siniestros)."""
    return ScrumArtifact(
        source=SourceRef(
            ef_job_id="01EF00000000000000000000EF",
            ef_artifact_hash="a1b2c3d4e5f6",
            ef_schema_version="1.2.0",
            ready_snapshot=True,
        ),
        epics=[
            Epic(
                id="EPIC-001",
                title="Gestión de Siniestros",
                description="Registro y seguimiento de siniestros ligados a guías.",
                source_refs=["MOD-001", "PRO-001"],
                story_ids=["US-001", "US-002"],
                confidence=0.8,
                origin=Origin.DERIVED,
            )
        ],
        stories=[
            Story(
                id="US-001",
                role="operador de siniestros",
                goal="registrar un siniestro asociándolo a su guía",
                benefit="mantener trazabilidad del evento logístico",
                statement=(
                    "Como operador de siniestros quiero registrar un siniestro "
                    "asociándolo a su guía para mantener trazabilidad del evento."
                ),
                epic_ref="EPIC-001",
                source_refs=StorySourceRefs(
                    requirement_refs=["REQ-B-001"],
                    process_refs=["PRO-001"],
                    rule_refs=["BR-001"],
                ),
                acceptance_criteria=[
                    AcceptanceCriterion(
                        id="AC-001",
                        format=AcceptanceFormat.GHERKIN,
                        given="un siniestro nuevo sin guía asociada",
                        when="el operador intenta registrarlo",
                        then="el sistema exige la guía y no permite guardar",
                        source_refs=["BR-001"],
                        origin=Origin.DERIVED,
                    )
                ],
                story_points=StoryPoints.SP_5,
                estimation_rationale=(
                    "Alta por CRUD con validación de guía y máquina de estados."
                ),
                estimation_confidence=0.6,
                priority=MoscowPriority.MUST,
                value=5,
                effort=3,
                dependencies=[],
                tags=["ef:01EF00000000000000000000EF", "REQ-B-001", "EPIC-001"],
                external_key="01EF00000000000000000000EF:US-001",
                confidence=0.8,
                origin=Origin.DERIVED,
            ),
            Story(
                id="US-002",
                role="operador de siniestros",
                goal="cambiar el estado (checkpoint) del siniestro",
                benefit="seguir el avance hasta el recupero",
                statement=(
                    "Como operador de siniestros quiero cambiar el estado del "
                    "siniestro para seguir su avance hasta el recupero."
                ),
                epic_ref="EPIC-001",
                source_refs=StorySourceRefs(
                    requirement_refs=["REQ-F-001"],
                    process_refs=["PRO-001"],
                    rule_refs=[],
                ),
                acceptance_criteria=[
                    AcceptanceCriterion(
                        id="AC-002",
                        format=AcceptanceFormat.GHERKIN,
                        given="un siniestro registrado",
                        when="el operador actualiza su estado",
                        then="el sistema registra el nuevo checkpoint",
                        source_refs=["REQ-F-001"],
                        origin=Origin.DERIVED,
                    )
                ],
                story_points=StoryPoints.SP_3,
                estimation_rationale="Transición de estado simple sobre entidad existente.",
                estimation_confidence=0.7,
                priority=MoscowPriority.SHOULD,
                value=4,
                effort=2,
                dependencies=["US-001"],
                tags=["ef:01EF00000000000000000000EF", "REQ-F-001", "EPIC-001"],
                external_key="01EF00000000000000000000EF:US-002",
                confidence=0.75,
                origin=Origin.DERIVED,
            ),
        ],
        product_backlog=ProductBacklog(
            method=BacklogMethod.MOSCOW,
            ordered_story_ids=["US-001", "US-002"],
            rationale="MoSCoW: 'must' primero; desempate por valor/esfuerzo.",
        ),
        sprints=[
            Sprint(
                id="SPRINT-1",
                goal="Registrar y dar seguimiento a siniestros.",
                capacity_points=20,
                total_points=8,
                story_ids=["US-001", "US-002"],
            )
        ],
        unassigned_story_ids=[],
        questions_for_po=[
            PoQuestion(
                id="Q-001",
                question=(
                    "¿Un siniestro puede estar ligado a más de una guía a la vez?"
                ),
                reason="La cardinalidad guía–siniestro afecta el modelo de datos.",
                audience=Audience.NEGOCIO,
                blocking=False,
                linked_to_ref="US-001",
            )
        ],
        analysis=ScrumAnalysis(
            risks=[
                Risk(
                    id="RISK-001",
                    description=(
                        "La máquina de estados del siniestro no está detallada; "
                        "podría cambiar la estimación de US-002."
                    ),
                    severity=RiskSeverity.MEDIA,
                    source_ref="REQ-F-001",
                )
            ],
            observations=[],
            coverage=Coverage(
                requirements_total=2,
                requirements_covered=2,
                coverage_ratio=1.0,
                uncovered_requirement_refs=[],
            ),
        ),
        metrics=ScrumMetrics(
            tokens=TokenMetrics(input=1500, output=1000, total=2500),
            cost=0.0195,
            duration=10.2,
            stories_total=2,
            points_total=8,
            sprints_total=1,
            coverage=1.0,
        ),
    )
