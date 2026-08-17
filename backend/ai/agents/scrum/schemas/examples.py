"""Ejemplos válidos de ScrumArtifact (dominio: siniestros logísticos).

Derivan del ``example_artifact`` del EF (mismos REQ-/PRO-/BR-refs) para ser
reutilizables como fixture en tests de bloques posteriores.

Hay **dos**, y la diferencia importa:

- ``example_artifact()`` es el mínimo con el que un contrato se prueba: dos
  historias, dos criterios. Perfecto para fijar una regla concreta.
- ``example_rich_artifact()`` es un plan **a escala**: tres épicas, siete
  historias con las cuatro prioridades MoSCoW, dependencias que cruzan épicas y
  once criterios. Existe porque hay defectos que un plan de dos historias no
  puede tener —un orden topológico que de verdad ordena, un hueco de cobertura
  que solo avisa frente a otro que bloquea, un techo por criterio que llega a
  podar— y son justo los que el Agente QA tiene que manejar bien.
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


# --- Plan a escala -------------------------------------------------------------


def _criterio(
    cid: str, given: str, when: str, then: str, refs: list[str]
) -> AcceptanceCriterion:
    """Criterio Gherkin con sus refs al EF, para no repetir el andamiaje."""
    return AcceptanceCriterion(
        id=cid,
        format=AcceptanceFormat.GHERKIN,
        given=given,
        when=when,
        then=then,
        source_refs=refs,
        origin=Origin.DERIVED,
    )


def _historia(
    *,
    sid: str,
    goal: str,
    benefit: str,
    epic: str,
    criterios: list[AcceptanceCriterion],
    prioridad: MoscowPriority,
    puntos: StoryPoints,
    requisitos: list[str],
    reglas: list[str] | None = None,
    dependencias: list[str] | None = None,
) -> Story:
    """Historia completa con el andamiaje repetitivo resuelto."""
    return Story(
        id=sid,
        role="operador de siniestros",
        goal=goal,
        benefit=benefit,
        statement=f"Como operador de siniestros quiero {goal} para {benefit}.",
        epic_ref=epic,
        source_refs=StorySourceRefs(
            requirement_refs=requisitos,
            process_refs=["PRO-001"],
            rule_refs=reglas or [],
        ),
        acceptance_criteria=criterios,
        story_points=puntos,
        estimation_rationale="Estimación del plan de demostración.",
        estimation_confidence=0.7,
        priority=prioridad,
        value=4,
        effort=3,
        dependencies=dependencias or [],
        tags=["ef:01EF00000000000000000000EF", epic],
        external_key=f"01EF00000000000000000000EF:{sid}",
        confidence=0.8,
        origin=Origin.DERIVED,
    )


def example_rich_artifact() -> ScrumArtifact:
    """ScrumArtifact v1.0.0 **a escala**: tres épicas, siete historias, once criterios.

    Está construido para que el plan de pruebas que salga de él tenga las formas
    que un plan pequeño no puede tener:

    - **Orden topológico real**: ``EPIC-002`` depende de ``EPIC-001`` a través de
      ``US-004 → US-001``, y ``EPIC-003`` de ``EPIC-002``. Con una sola épica, el
      orden es trivialmente correcto y no prueba nada.
    - **Las cuatro prioridades MoSCoW**, para que un hueco de cobertura en una
      ``could`` se lea como advertencia y el mismo hueco en una ``must`` bloquee
      el semáforo (QA-D5). Con solo ``must`` esa distinción no existe.
    - **Una historia con tres criterios** (``US-002``), que es donde el techo de
      casos por criterio empieza a tener consecuencias visibles.
    - **Un criterio deliberadamente vago** (``AC-011``, "el sistema responde con
      fluidez"): no es un descuido del fixture, es el caso que debe acabar en
      pregunta al QA lead en vez de en un caso de prueba inventado.
    """
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
                title="Registro de siniestros",
                description="Alta de siniestros ligados a su guía de envío.",
                source_refs=["PRO-001"],
                story_ids=["US-001", "US-002"],
                confidence=0.85,
                origin=Origin.DERIVED,
            ),
            Epic(
                id="EPIC-002",
                title="Seguimiento y estados",
                description="Avance del siniestro por sus checkpoints.",
                source_refs=["PRO-001"],
                story_ids=["US-003", "US-004"],
                confidence=0.8,
                origin=Origin.DERIVED,
            ),
            Epic(
                id="EPIC-003",
                title="Recupero y cierre",
                description="Recuperación económica y cierre del siniestro.",
                source_refs=["PRO-001"],
                story_ids=["US-005", "US-006", "US-007"],
                confidence=0.75,
                origin=Origin.DERIVED,
            ),
        ],
        stories=[
            _historia(
                sid="US-001",
                goal="registrar un siniestro asociándolo a su guía",
                benefit="mantener la trazabilidad del evento logístico",
                epic="EPIC-001",
                criterios=[
                    _criterio(
                        "AC-001",
                        "un siniestro nuevo sin guía asociada",
                        "el operador intenta registrarlo",
                        "el sistema exige la guía y no permite guardar",
                        ["BR-001"],
                    )
                ],
                prioridad=MoscowPriority.MUST,
                puntos=StoryPoints.SP_5,
                requisitos=["REQ-B-001"],
                reglas=["BR-001"],
            ),
            _historia(
                sid="US-002",
                goal="informar la fecha y el detalle del siniestro",
                benefit="poder investigar lo ocurrido con datos suficientes",
                epic="EPIC-001",
                criterios=[
                    _criterio(
                        "AC-002",
                        "un siniestro en captura",
                        "el operador informa una fecha futura",
                        "el sistema rechaza la fecha",
                        ["VAL-001"],
                    ),
                    _criterio(
                        "AC-003",
                        "un siniestro en captura",
                        "el operador guarda sin describir lo ocurrido",
                        "el sistema exige la descripción",
                        ["BR-001"],
                    ),
                    _criterio(
                        "AC-004",
                        "un siniestro con guía y fecha válidas",
                        "el operador lo guarda",
                        "el siniestro queda registrado con su número correlativo",
                        ["REQ-B-001"],
                    ),
                ],
                prioridad=MoscowPriority.MUST,
                puntos=StoryPoints.SP_8,
                requisitos=["REQ-B-001"],
                reglas=["BR-001"],
            ),
            _historia(
                sid="US-003",
                goal="cambiar el estado (checkpoint) del siniestro",
                benefit="seguir su avance hasta el recupero",
                epic="EPIC-002",
                criterios=[
                    _criterio(
                        "AC-005",
                        "un siniestro registrado",
                        "el operador actualiza su estado",
                        "el sistema registra el nuevo checkpoint con su fecha",
                        ["REQ-F-001"],
                    )
                ],
                prioridad=MoscowPriority.SHOULD,
                puntos=StoryPoints.SP_3,
                requisitos=["REQ-F-001"],
                dependencias=["US-001"],
            ),
            _historia(
                sid="US-004",
                goal="consultar el historial de estados de un siniestro",
                benefit="saber quién lo movió y cuándo",
                epic="EPIC-002",
                criterios=[
                    _criterio(
                        "AC-006",
                        "un siniestro con varios cambios de estado",
                        "el operador abre su historial",
                        "el sistema lista cada cambio con su autor y su fecha",
                        ["REQ-F-001"],
                    )
                ],
                prioridad=MoscowPriority.SHOULD,
                puntos=StoryPoints.SP_3,
                requisitos=["REQ-F-001"],
                dependencias=["US-003"],
            ),
            _historia(
                sid="US-005",
                goal="registrar el recupero económico del siniestro",
                benefit="cerrar el caso con el monto recuperado",
                epic="EPIC-003",
                criterios=[
                    _criterio(
                        "AC-007",
                        "un siniestro en investigación",
                        "el operador registra el monto recuperado",
                        "el sistema lo guarda y actualiza el estado a recuperado",
                        ["REQ-B-001"],
                    ),
                    _criterio(
                        "AC-008",
                        "un siniestro ya cerrado",
                        "el operador intenta registrar un recupero",
                        "el sistema lo impide",
                        ["BR-001"],
                    ),
                ],
                prioridad=MoscowPriority.MUST,
                puntos=StoryPoints.SP_5,
                requisitos=["REQ-B-001"],
                reglas=["BR-001"],
                dependencias=["US-003"],
            ),
            _historia(
                sid="US-006",
                goal="exportar el listado de siniestros del mes",
                benefit="reportar a la gerencia sin pedirlo a Sistemas",
                epic="EPIC-003",
                criterios=[
                    _criterio(
                        "AC-009",
                        "siniestros registrados en el mes",
                        "el operador exporta el listado",
                        "el sistema entrega un archivo con los siniestros del periodo",
                        ["REQ-F-001"],
                    ),
                    _criterio(
                        "AC-010",
                        "un periodo sin siniestros",
                        "el operador exporta el listado",
                        "el sistema entrega el archivo vacío con sus cabeceras",
                        ["REQ-F-001"],
                    ),
                ],
                prioridad=MoscowPriority.COULD,
                puntos=StoryPoints.SP_3,
                requisitos=["REQ-F-001"],
                dependencias=["US-005"],
            ),
            _historia(
                sid="US-007",
                goal="ver un tablero con los siniestros abiertos",
                benefit="priorizar el trabajo del día",
                epic="EPIC-003",
                criterios=[
                    _criterio(
                        "AC-011",
                        "el tablero de siniestros abiertos",
                        "el operador lo abre",
                        "el sistema responde con fluidez",
                        ["REQ-N-001"],
                    )
                ],
                prioridad=MoscowPriority.WONT,
                puntos=StoryPoints.SP_2,
                requisitos=["REQ-N-001"],
            ),
        ],
        product_backlog=ProductBacklog(
            method=BacklogMethod.MOSCOW,
            ordered_story_ids=[
                "US-001",
                "US-002",
                "US-005",
                "US-003",
                "US-004",
                "US-006",
                "US-007",
            ],
            rationale="MoSCoW: 'must' primero; desempate por valor/esfuerzo.",
        ),
        sprints=[
            Sprint(
                id="SPRINT-1",
                goal="Registrar siniestros con sus datos obligatorios.",
                capacity_points=20,
                total_points=13,
                story_ids=["US-001", "US-002"],
            ),
            Sprint(
                id="SPRINT-2",
                goal="Seguimiento por estados y recupero.",
                capacity_points=20,
                total_points=11,
                story_ids=["US-003", "US-004", "US-005"],
            ),
            Sprint(
                id="SPRINT-3",
                goal="Reportería y tablero.",
                capacity_points=20,
                total_points=5,
                story_ids=["US-006", "US-007"],
            ),
        ],
        unassigned_story_ids=[],
        questions_for_po=[
            PoQuestion(
                id="Q-001",
                question="¿Un siniestro puede estar ligado a más de una guía?",
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
                        "podría cambiar la estimación de EPIC-002."
                    ),
                    severity=RiskSeverity.MEDIA,
                    source_ref="REQ-F-001",
                )
            ],
            observations=[],
            coverage=Coverage(
                requirements_total=3,
                requirements_covered=3,
                coverage_ratio=1.0,
                uncovered_requirement_refs=[],
            ),
        ),
        metrics=ScrumMetrics(
            tokens=TokenMetrics(input=6200, output=3400, total=9600),
            cost=0.0696,
            duration=38.4,
            stories_total=7,
            points_total=29,
            sprints_total=3,
            coverage=1.0,
        ),
    )
