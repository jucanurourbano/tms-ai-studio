"""Contrato de datos ArchitectureArtifact v1.0.0 (Pydantic 2).

Artefacto que produce el Agente Arquitectura a partir del par EF + Scrum de un
mismo flujo: estilo arquitectónico, componentes, stack recomendado, ADRs ligeros,
integraciones externas, contratos entre componentes, requisitos transversales,
diagramas (Mermaid), riesgos y preguntas al Arquitecto.

Claves en inglés, valores/descripciones en español. Todo ítem trazable lleva
``id`` y, donde aplique, ``source_ref(s)``, ``confidence`` y ``origin``. Reusa
``TokenMetrics`` / ``SkippedItem`` / ``Observation`` del Agente EF.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ai.agents.ef.schemas.artifact import Observation, SkippedItem, TokenMetrics
from ai.agents.ef.schemas.enums import Audience, Origin, QuestionStatus

from .enums import (
    AdrStatus,
    ArchitectureStyle,
    ComponentType,
    ContractKind,
    CrossCuttingConcern,
    DiagramFormat,
    IntegrationDirection,
    IntegrationProtocol,
    RiskSeverity,
    SizeClass,
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


# --- Fuente (enlace a los jobs Scrum + EF de origen) ------------------------


class SourceRef(_Strict):
    """Referencia reproducible al par Scrum + EF consumido.

    El job de Arquitectura se enlaza a Scrum por ``input_job_id`` (predecesor
    directo); el EF se resuelve transitivamente. Ambos ids + hashes se guardan
    aquí para reproducibilidad.
    """

    scrum_job_id: str
    scrum_artifact_hash: str
    scrum_schema_version: str = "1.0.0"
    ef_job_id: str
    ef_artifact_hash: str
    ef_schema_version: str = "1.2.0"
    ready_snapshot: bool = True  # gate del Scrum verificado al generar


# --- Contexto (perfil de alcance determinista) ------------------------------


class ScopeProfile(_Strict):
    """Conteos del alcance (base determinista de la recomendación de estilo)."""

    entities: int = 0
    relationships: int = 0
    modules: int = 0
    processes: int = 0
    stories: int = 0
    points_total: int = 0
    integrations_detected: int = 0
    nfr_count: int = 0


class BoundedContext(TracedItem):
    """Contexto acotado candidato (agrupa módulos/procesos afines del EF)."""

    name: str
    source_refs: list[str] = Field(default_factory=list)  # MOD-.../PRO-... del EF


class ArchitectureContext(_Strict):
    """Contexto consolidado: perfil de alcance + clasificación de tamaño."""

    scope_profile: ScopeProfile = Field(default_factory=ScopeProfile)
    size_class: SizeClass = SizeClass.M
    bounded_contexts: list[BoundedContext] = Field(default_factory=list)


# --- Estilo arquitectónico --------------------------------------------------


class StyleDecision(_Strict):
    """Estilo elegido + justificación (respaldado por un ADR)."""

    chosen: ArchitectureStyle
    rationale: str
    adr_ref: Optional[str] = None  # id del ADR que documenta la decisión
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    origin: Optional[Origin] = None


# --- Componentes ------------------------------------------------------------


class ComponentSourceRefs(_Strict):
    """Trazabilidad bidireccional de un componente hacia Scrum (épicas/historias)
    y EF (entidades/APIs/módulos/procesos)."""

    epic_refs: list[str] = Field(default_factory=list)
    story_refs: list[str] = Field(default_factory=list)
    entity_refs: list[str] = Field(default_factory=list)
    api_refs: list[str] = Field(default_factory=list)
    module_refs: list[str] = Field(default_factory=list)
    process_refs: list[str] = Field(default_factory=list)


class Component(TracedItem):
    """Componente/módulo lógico con responsabilidad y dependencias."""

    name: str
    type: ComponentType
    layer: str  # p. ej. "presentación" | "aplicación" | "dominio" | "datos"
    responsibility: str
    source_refs: ComponentSourceRefs = Field(default_factory=ComponentSourceRefs)
    depends_on: list[str] = Field(default_factory=list)  # ids de otros componentes


# --- Stack tecnológico ------------------------------------------------------


class StackChoice(TracedItem):
    """Tecnología recomendada para una capa (desde el allow-list de la casa)."""

    layer: str  # coincide con las capas de tech_stack.yaml
    technology: str
    version: Optional[str] = None
    rationale: str
    alternatives: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)  # RNF-.../reglas


# --- ADRs -------------------------------------------------------------------


class Adr(TracedItem):
    """Architecture Decision Record ligero."""

    title: str
    decision: str
    context: str
    alternatives_considered: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    status: AdrStatus = AdrStatus.PROPOSED
    source_refs: list[str] = Field(default_factory=list)


# --- Integraciones externas -------------------------------------------------


class Integration(TracedItem):
    """Sistema externo detectado en el EF (p. ej. planillas)."""

    name: str
    system: str
    direction: IntegrationDirection
    protocol: IntegrationProtocol = IntegrationProtocol.UNKNOWN
    purpose: str
    data_exchanged: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)  # PRO-.../BR-... del EF
    contract_known: bool = False


# --- Contratos entre componentes --------------------------------------------


class Contract(TracedItem):
    """Contrato entre dos componentes (o componente ↔ integración)."""

    from_ref: str
    to_ref: str
    kind: ContractKind
    description: str
    source_refs: list[str] = Field(default_factory=list)


# --- Requisitos transversales -----------------------------------------------


class CrossCutting(TracedItem):
    """Preocupación transversal derivada de RNF/reglas (auth, auditoría, …)."""

    concern: CrossCuttingConcern
    requirement: str
    approach: str
    source_refs: list[str] = Field(default_factory=list)


# --- Diagramas (Mermaid) ----------------------------------------------------


class Diagram(_Strict):
    """Diagrama representable como código Mermaid (generado deterministamente)."""

    format: DiagramFormat = DiagramFormat.MERMAID
    code: str


class Diagrams(_Strict):
    """Colección de diagramas del artefacto."""

    component: Optional[Diagram] = None  # componentes por capa
    context: Optional[Diagram] = None  # sistema ↔ integraciones/actores


# --- Preguntas al Arquitecto ------------------------------------------------


class ArchitectQuestion(TracedItem):
    """Duda hacia el Arquitecto/Líder Técnico (no se inventa: se pregunta)."""

    question: str
    reason: str
    audience: Audience = Audience.TECNICO
    blocking: bool = False
    linked_to_ref: Optional[str] = None
    status: QuestionStatus = QuestionStatus.PENDIENTE


# --- Análisis ---------------------------------------------------------------


class Risk(TracedItem):
    """Riesgo técnico de la arquitectura propuesta."""

    description: str
    severity: RiskSeverity = RiskSeverity.MEDIA
    mitigation: Optional[str] = None
    source_ref: Optional[str] = None


class Coverage(_Strict):
    """Cobertura de trazabilidad: épicas (Scrum), entidades (EF) y RNF.

    Nunca oculta huecos: expone explícitamente lo no cubierto.
    """

    epics_total: int = 0
    epics_mapped: int = 0
    uncovered_epic_refs: list[str] = Field(default_factory=list)
    entities_total: int = 0
    entities_mapped: int = 0
    uncovered_entity_refs: list[str] = Field(default_factory=list)
    nfr_total: int = 0
    nfr_addressed: int = 0
    uncovered_nfr_refs: list[str] = Field(default_factory=list)


class ArchitectureAnalysis(_Strict):
    """Bloque de análisis del ArchitectureArtifact."""

    risks: list[Risk] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    coverage: Coverage = Field(default_factory=Coverage)


# --- Métricas ---------------------------------------------------------------


class ArchitectureMetrics(_Strict):
    """Métricas reales de la corrida del Agente Arquitectura."""

    tokens: TokenMetrics = Field(default_factory=TokenMetrics)
    cost: float = 0.0  # USD
    duration: float = 0.0  # segundos
    components_total: int = 0
    adrs_total: int = 0
    integrations_total: int = 0
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    skipped: list[SkippedItem] = Field(default_factory=list)


# --- Artefacto raíz ---------------------------------------------------------


class ArchitectureArtifact(_Strict):
    """Artefacto completo del Agente Arquitectura (contrato v1.0.0)."""

    schema_version: str = SCHEMA_VERSION
    source: SourceRef
    context: ArchitectureContext = Field(default_factory=ArchitectureContext)
    architecture_style: Optional[StyleDecision] = None
    components: list[Component] = Field(default_factory=list)
    stack: list[StackChoice] = Field(default_factory=list)
    adrs: list[Adr] = Field(default_factory=list)
    integrations: list[Integration] = Field(default_factory=list)
    contracts: list[Contract] = Field(default_factory=list)
    cross_cutting: list[CrossCutting] = Field(default_factory=list)
    diagrams: Diagrams = Field(default_factory=Diagrams)
    analysis: ArchitectureAnalysis = Field(default_factory=ArchitectureAnalysis)
    questions_for_architect: list[ArchitectQuestion] = Field(default_factory=list)
    metrics: ArchitectureMetrics = Field(default_factory=ArchitectureMetrics)
