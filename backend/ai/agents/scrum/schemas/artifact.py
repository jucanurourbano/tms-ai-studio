"""Contrato de datos ScrumArtifact v1.0.0 (Pydantic 2).

Artefacto que produce el Agente Scrum a partir de un ``EFArtifact`` listo: épicas,
historias de usuario, criterios de aceptación, estimaciones, backlog priorizado,
plan de sprints y preguntas al Product Owner.

Claves en inglés, valores/descripciones en español. Todo ítem trazable lleva
``id`` y, donde aplique, ``source_ref(s)``, ``confidence`` y ``origin``. Reusa
``TokenMetrics`` / ``SkippedItem`` / ``Observation`` del Agente EF y nace
compatible con ClickUp (``tags`` / ``external_key`` / ``priority``).
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ai.agents.ef.schemas.artifact import Observation, SkippedItem, TokenMetrics
from ai.agents.ef.schemas.enums import Audience, Origin, QuestionStatus

from .enums import (
    AcceptanceFormat,
    BacklogMethod,
    MoscowPriority,
    RiskSeverity,
    StoryPoints,
)

SCHEMA_VERSION = "1.0.0"


class _Strict(BaseModel):
    """Base estricta: prohíbe claves desconocidas (structured output cerrado)."""

    model_config = ConfigDict(extra="forbid")


class TracedItem(_Strict):
    """Ítem trazable con provenance y confianza.

    Atributos:
        id: Identificador estable del ítem (renumerable de forma determinística).
        confidence: Confianza [0, 1] donde aplique.
        origin: Declarado (``stated``) o derivado por inferencia (``derived``).
    """

    id: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    origin: Optional[Origin] = None


# --- Fuente (enlace al job EF de origen) ------------------------------------


class SourceRef(_Strict):
    """Referencia reproducible al ``EFArtifact`` consumido."""

    ef_job_id: str
    ef_artifact_hash: str
    ef_schema_version: str = "1.2.0"
    ready_snapshot: bool = True  # gate del EF verificado al generar


# --- Épicas -----------------------------------------------------------------


class Epic(TracedItem):
    """Épica: agrupa historias derivadas de módulos/procesos del EF."""

    title: str
    description: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)  # MOD-.../PRO-... del EF
    story_ids: list[str] = Field(default_factory=list)


# --- Historias de usuario ---------------------------------------------------


class StorySourceRefs(_Strict):
    """Trazabilidad de una historia hacia el EF (requisitos/procesos/reglas)."""

    requirement_refs: list[str] = Field(default_factory=list)
    process_refs: list[str] = Field(default_factory=list)
    rule_refs: list[str] = Field(default_factory=list)


class AcceptanceCriterion(_Strict):
    """Criterio de aceptación (Gherkin o texto), anclado a reglas/validaciones."""

    id: str
    format: AcceptanceFormat = AcceptanceFormat.GHERKIN
    given: Optional[str] = None
    when: Optional[str] = None
    then: Optional[str] = None
    text: Optional[str] = None  # alternativa cuando no aplica Gherkin
    source_refs: list[str] = Field(default_factory=list)  # BR-.../VAL-... del EF
    origin: Optional[Origin] = None


class Story(TracedItem):
    """Historia de usuario "Como/quiero/para" con trazabilidad total al EF."""

    role: str
    goal: str
    benefit: str
    statement: str  # "Como <rol> quiero <objetivo> para <beneficio>"
    epic_ref: Optional[str] = None
    source_refs: StorySourceRefs = Field(default_factory=StorySourceRefs)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)

    # Estimación (D9: borrador informado por LLM; origin=derived).
    story_points: Optional[StoryPoints] = None
    estimation_rationale: Optional[str] = None
    estimation_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # Priorización (D3: MoSCoW primario + valor/esfuerzo como desempate).
    priority: Optional[MoscowPriority] = None
    value: Optional[int] = Field(default=None, ge=1, le=5)
    effort: Optional[int] = Field(default=None, ge=1, le=5)

    dependencies: list[str] = Field(default_factory=list)  # ids de otras historias

    # --- Campos nacidos compatibles con ClickUp (§7 del diseño) ---
    tags: list[str] = Field(default_factory=list)
    external_key: Optional[str] = None  # clave idempotente estable


# --- Backlog y sprints ------------------------------------------------------


class ProductBacklog(_Strict):
    """Backlog de producto ordenado (lo arma Python tras la priorización)."""

    method: BacklogMethod = BacklogMethod.MOSCOW
    ordered_story_ids: list[str] = Field(default_factory=list)
    rationale: Optional[str] = None


class Sprint(_Strict):
    """Sprint con su capacidad y las historias asignadas (bin-packing determinista)."""

    id: str
    goal: Optional[str] = None
    capacity_points: int = Field(ge=1)
    total_points: int = 0
    story_ids: list[str] = Field(default_factory=list)


# --- Preguntas al Product Owner ---------------------------------------------


class PoQuestion(TracedItem):
    """Duda hacia el Product Owner (no se inventan requisitos: se preguntan)."""

    question: str
    reason: str
    audience: Audience = Audience.NEGOCIO
    blocking: bool = False
    linked_to_ref: Optional[str] = None
    status: QuestionStatus = QuestionStatus.PENDIENTE


# --- Análisis ---------------------------------------------------------------


class Risk(TracedItem):
    """Riesgo del plan de planificación."""

    description: str
    severity: RiskSeverity = RiskSeverity.MEDIA
    source_ref: Optional[str] = None


class Coverage(_Strict):
    """Cobertura de requisitos funcionales por historias (nunca oculta huecos)."""

    requirements_total: int = 0
    requirements_covered: int = 0
    coverage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    uncovered_requirement_refs: list[str] = Field(default_factory=list)


class ScrumAnalysis(_Strict):
    """Bloque de análisis del ScrumArtifact."""

    risks: list[Risk] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    coverage: Coverage = Field(default_factory=Coverage)


# --- Métricas ---------------------------------------------------------------


class ScrumMetrics(_Strict):
    """Métricas reales de la corrida del Agente Scrum."""

    tokens: TokenMetrics = Field(default_factory=TokenMetrics)
    cost: float = 0.0  # USD
    duration: float = 0.0  # segundos
    stories_total: int = 0
    points_total: int = 0
    sprints_total: int = 0
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    skipped: list[SkippedItem] = Field(default_factory=list)


# --- Artefacto raíz ---------------------------------------------------------


class ScrumArtifact(_Strict):
    """Artefacto completo del Agente Scrum (contrato v1.0.0)."""

    schema_version: str = SCHEMA_VERSION
    source: SourceRef
    epics: list[Epic] = Field(default_factory=list)
    stories: list[Story] = Field(default_factory=list)
    product_backlog: ProductBacklog = Field(default_factory=ProductBacklog)
    sprints: list[Sprint] = Field(default_factory=list)
    unassigned_story_ids: list[str] = Field(default_factory=list)
    questions_for_po: list[PoQuestion] = Field(default_factory=list)
    analysis: ScrumAnalysis = Field(default_factory=ScrumAnalysis)
    metrics: ScrumMetrics = Field(default_factory=ScrumMetrics)
