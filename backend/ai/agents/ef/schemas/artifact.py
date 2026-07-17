"""Contrato de datos EFArtifact v1.2.0 (Pydantic 2).

Artefacto que produce el Agente EF: la traducción del "qué me pide Procesos"
al lenguaje de Sistemas. Claves en inglés, valores/descripciones en español.

Todo ítem trazable lleva ``id`` y, donde aplique, ``source_ref``, ``evidence``
(verbatim), ``confidence`` y ``origin`` (``stated`` | ``derived``).
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    Audience,
    Cardinality,
    HttpMethod,
    Origin,
    Priority,
    QuestionStatus,
    SourceFidelity,
    SourceType,
)

SCHEMA_VERSION = "1.2.0"


class _Strict(BaseModel):
    """Base estricta: prohíbe claves desconocidas (structured output cerrado)."""

    model_config = ConfigDict(extra="forbid")


class TracedItem(_Strict):
    """Ítem trazable con provenance y confianza.

    Atributos:
        id: Identificador estable del ítem (renumerable de forma determinística).
        source_ref: Referencia a la fuente (element_id del CIR / chunk).
        evidence: Cita textual (verbatim) que sustenta el ítem.
        confidence: Confianza [0, 1] donde aplique.
        origin: Declarado (``stated``) o derivado por inferencia (``derived``).
    """

    id: str
    source_ref: Optional[str] = None
    evidence: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    origin: Optional[Origin] = None


# --- Fuente -----------------------------------------------------------------


class SourceInfo(_Strict):
    """Metadatos de la fuente analizada."""

    type: SourceType
    hash: str
    fidelity: SourceFidelity
    filename: Optional[str] = None


# --- Requisitos -------------------------------------------------------------


class Requirement(TracedItem):
    """Requisito (de negocio, funcional o no funcional)."""

    text: str
    priority: Optional[Priority] = None


class RequirementsBlock(_Strict):
    """Requisitos agrupados por categoría."""

    business: list[Requirement] = Field(default_factory=list)
    functional: list[Requirement] = Field(default_factory=list)
    non_functional: list[Requirement] = Field(default_factory=list)


# --- Elementos del dominio funcional ---------------------------------------


class Actor(TracedItem):
    """Actor/rol que participa en el proceso."""

    name: str
    description: Optional[str] = None
    responsibilities: list[str] = Field(default_factory=list)


class Module(TracedItem):
    """Módulo funcional del sistema."""

    name: str
    description: Optional[str] = None


class Menu(TracedItem):
    """Opción de menú (posible jerarquía vía ``parent_ref``)."""

    name: str
    module_ref: Optional[str] = None
    parent_ref: Optional[str] = None
    path: Optional[str] = None


class Process(TracedItem):
    """Proceso de negocio con sus pasos y actores involucrados."""

    name: str
    description: Optional[str] = None
    steps: list[str] = Field(default_factory=list)
    actor_refs: list[str] = Field(default_factory=list)


class BusinessRule(TracedItem):
    """Regla de negocio."""

    statement: str


class ValidationRule(TracedItem):
    """Validación sobre un campo o conjunto de campos."""

    rule: str
    field_ref: Optional[str] = None


class FieldDef(TracedItem):
    """Campo de datos (atributo)."""

    name: str
    entity_ref: Optional[str] = None
    data_type: Optional[str] = None
    required: bool = False


# --- Modelo de datos (inferido) --------------------------------------------


class Entity(TracedItem):
    """Entidad de datos. ``origin`` es obligatorio aquí (stated|derived)."""

    name: str
    description: Optional[str] = None
    origin: Origin


class Relationship(TracedItem):
    """Relación entre dos entidades con su cardinalidad."""

    source_entity_ref: str
    target_entity_ref: str
    cardinality: Cardinality
    name: Optional[str] = None


class CrudMatrixEntry(TracedItem):
    """Fila de la matriz CRUD: qué actor opera sobre qué entidad."""

    entity_ref: str
    actor_ref: Optional[str] = None
    module_ref: Optional[str] = None
    create: bool = False
    read: bool = False
    update: bool = False
    delete: bool = False


class ApiEndpoint(TracedItem):
    """Endpoint de API inferido a partir del modelo."""

    method: HttpMethod
    path: str
    description: Optional[str] = None
    entity_ref: Optional[str] = None


# --- Interpretación de Sistemas --------------------------------------------


class ScopeItem(_Strict):
    """Alcance interpretado, con referencias a los requisitos que lo sustentan."""

    id: Optional[str] = None
    description: str
    requirement_refs: list[str] = Field(default_factory=list)
    reason: Optional[str] = None


class Assumption(TracedItem):
    """Supuesto de interpretación. ``id`` con formato SUP-001, SUP-002, ..."""

    id: str = Field(pattern=r"^SUP-\d{3,}$")
    assumption: str
    rationale: Optional[str] = None


class SystemsInterpretation(_Strict):
    """El "qué me pide Procesos" traducido al lenguaje de Sistemas."""

    what_process_requests: str
    scope_for_systems: list[ScopeItem] = Field(default_factory=list)
    apparent_out_of_scope: list[ScopeItem] = Field(default_factory=list)
    interpretation_assumptions: list[Assumption] = Field(default_factory=list)


# --- Análisis crítico -------------------------------------------------------


class Ambiguity(TracedItem):
    """Ambigüedad detectada en la fuente."""

    description: str


class MissingInfo(TracedItem):
    """Información faltante y dónde se esperaría encontrarla."""

    description: str
    expected_where: Optional[str] = None


class Inconsistency(TracedItem):
    """Inconsistencia entre ítems, con las referencias en conflicto."""

    description: str
    conflicting_refs: list[str] = Field(default_factory=list)


class Observation(TracedItem):
    """Observación. También registra descartes NO silenciosos del assembler."""

    description: str
    reason: Optional[str] = None


class Analysis(_Strict):
    """Bloque de análisis crítico del artefacto."""

    ambiguities: list[Ambiguity] = Field(default_factory=list)
    missing_info: list[MissingInfo] = Field(default_factory=list)
    inconsistencies: list[Inconsistency] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)


# --- Preguntas al analista --------------------------------------------------


class Question(TracedItem):
    """Duda de Sistemas hacia Procesos, en lenguaje de negocio."""

    question: str
    reason: str
    audience: Audience
    blocking: bool = False
    linked_to_ref: Optional[str] = None
    status: QuestionStatus = QuestionStatus.PENDIENTE


# --- Métricas ---------------------------------------------------------------


class TokenMetrics(_Strict):
    """Desglose de tokens (necesario para calcular costo in/out)."""

    input: int = 0
    output: int = 0
    total: int = 0


class SkippedItem(_Strict):
    """Ítem/chunk en cuarentena (nunca tumba el job; siempre queda registrado)."""

    ref: str
    stage: str
    reason: str


class Metrics(_Strict):
    """Métricas reales de la corrida."""

    tokens: TokenMetrics = Field(default_factory=TokenMetrics)
    cost: float = 0.0  # USD
    duration: float = 0.0  # segundos
    chunks_total: int = 0
    chunks_skipped: int = 0
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    skipped: list[SkippedItem] = Field(default_factory=list)


# --- Artefacto raíz ---------------------------------------------------------


class EFArtifact(_Strict):
    """Artefacto completo del Agente EF (contrato v1.2.0)."""

    schema_version: str = SCHEMA_VERSION
    source: SourceInfo
    summary: str
    requirements: RequirementsBlock = Field(default_factory=RequirementsBlock)
    actors: list[Actor] = Field(default_factory=list)
    modules: list[Module] = Field(default_factory=list)
    menus: list[Menu] = Field(default_factory=list)
    processes: list[Process] = Field(default_factory=list)
    business_rules: list[BusinessRule] = Field(default_factory=list)
    validations: list[ValidationRule] = Field(default_factory=list)
    fields: list[FieldDef] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    crud: list[CrudMatrixEntry] = Field(default_factory=list)
    apis: list[ApiEndpoint] = Field(default_factory=list)
    systems_interpretation: SystemsInterpretation
    analysis: Analysis = Field(default_factory=Analysis)
    questions_for_analyst: list[Question] = Field(default_factory=list)
    metrics: Metrics = Field(default_factory=Metrics)
