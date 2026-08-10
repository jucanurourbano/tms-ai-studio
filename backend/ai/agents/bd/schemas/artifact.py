"""Contrato de datos DatabaseArtifact v1.0.0 (Pydantic 2).

Artefacto que produce el Agente BD a partir del ``ArchitectureArtifact`` y del
``EFArtifact`` de origen (resuelto transitivamente): modelo de datos físico,
DDL ejecutable, datos semilla de catálogos, diccionario de datos, diagrama
entidad-relación, decisiones de diseño y preguntas al DBA.

Claves en inglés, valores/descripciones en español. Todo ítem trazable lleva
``id`` y, donde aplique, ``source_refs``, ``confidence`` y ``origin``. Reusa
``TokenMetrics`` / ``SkippedItem`` / ``Observation`` del EF y ``RiskSeverity`` de
Arquitectura.

Dos decisiones del contrato que conviene tener presentes al leerlo:

1. **Doble nivel de tipo (DB2).** Cada columna lleva ``logical_type`` (enum
   cerrado, lo elige el LLM) y ``type`` (la sintaxis del motor, la escribe el
   renderizador). El DDL es válido por construcción y regenerarlo para otro motor
   es un render de coste cero, sin volver a llamar al modelo.
2. **``risks`` vive dentro de ``analysis``**, como en EF/Scrum/Arquitectura, para
   que el hub y el export PDF reutilicen el mismo bloque sin casos especiales.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ai.agents.arquitectura.schemas.enums import RiskSeverity
from ai.agents.ef.schemas.artifact import Observation, SkippedItem, TokenMetrics
from ai.agents.ef.schemas.enums import Audience, Origin, QuestionStatus
from ai.inventory.contract import ReconciliationRef, ReconciliationSummary

from .enums import (
    DbEngine,
    DdlScriptKind,
    DecisionScope,
    DiagramFormat,
    LogicalType,
    NormalizationForm,
    PrimaryKeyStrategy,
    ReferentialAction,
    RuleEnforcement,
    TableKind,
    VolumeEstimate,
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
        origin: Declarado en el EF (``stated``) o inferido (``derived``).
    """

    id: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    origin: Optional[Origin] = None


# --- Fuente (enlace a los jobs Arquitectura + Scrum + EF de origen) ---------


class SourceRef(_Strict):
    """Referencia reproducible a la cadena consumida.

    El job de BD se enlaza a Arquitectura por ``input_job_id`` (predecesor
    directo); Scrum y EF se resuelven transitivamente (dos saltos). Se guardan los
    tres ids + hashes: el Scrum no se usa como insumo de modelado, pero completa
    la trazabilidad de la cadena y permite reproducir la corrida.
    """

    architecture_job_id: str
    architecture_artifact_hash: str
    architecture_schema_version: str = "1.0.0"
    scrum_job_id: Optional[str] = None
    scrum_artifact_hash: Optional[str] = None
    ef_job_id: str
    ef_artifact_hash: str
    ef_schema_version: str = "1.2.0"
    ready_snapshot: bool = True  # gate de Arquitectura verificado al generar


# --- Motor y convenciones efectivas -----------------------------------------


class Conventions(_Strict):
    """Convenciones efectivas aplicadas al modelo (desde ``db_conventions.yaml``).

    Se persisten en el artefacto —y no solo en el YAML— para que el modelo sea
    auditable a posteriori: si mañana el equipo cambia la convención, se sigue
    sabiendo con qué reglas se generó este esquema.
    """

    naming_case: str = "snake_case"
    table_number: str = "plural"
    pk_strategy: PrimaryKeyStrategy = PrimaryKeyStrategy.SURROGATE
    fk_pattern: str = "{referenced_table_singular}_id"
    audit_columns: bool = False
    soft_delete: bool = False
    schema_name: str = ""


class Target(_Strict):
    """Motor destino y de dónde salió la decisión."""

    engine: DbEngine
    engine_version: Optional[str] = None
    #: Ref al ``stack[]`` de Arquitectura que fijó el motor (``STK-...``).
    engine_source_ref: Optional[str] = None
    #: ``False`` si la arquitectura no decidió motor y se usó un fallback. En ese
    #: caso hay una pregunta bloqueante al DBA: el semáforo no se pone verde.
    engine_decided: bool = True
    conventions: Conventions = Field(default_factory=Conventions)
    #: Procedencia y versión de las convenciones (p. ej. ``db_conventions.yaml@v0``).
    conventions_source: Optional[str] = None


# --- Tablas: columnas, claves, constraints, índices -------------------------


class Column(TracedItem):
    """Columna de una tabla, con su tipo lógico y su tipo físico renderizado."""

    name: str
    ordinal: int
    #: Elegido por el LLM de un enum cerrado (nunca sintaxis SQL).
    logical_type: LogicalType
    #: Sintaxis del motor. Lo escribe el renderizador de DDL, no el modelo; queda
    #: vacío hasta que DDL_GEN lo rellena.
    type: Optional[str] = None
    length: Optional[int] = Field(default=None, ge=1)
    precision: Optional[int] = Field(default=None, ge=1)
    scale: Optional[int] = Field(default=None, ge=0)
    nullable: bool = True
    default: Optional[str] = None
    is_primary_key: bool = False
    #: Generada por el motor (identity/secuencia).
    is_generated: bool = False
    description: Optional[str] = None
    example: Optional[str] = None
    #: Campo del EF que la origina (``FLD-...``); ``None`` si es derivada
    #: (PK subrogada, FK, columna de auditoría).
    field_ref: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)
    #: El EF no permitía deducir el tipo: hay una pregunta ligada. Nunca se
    #: adivina en silencio.
    type_ambiguous: bool = False
    #: Candidata a dato personal (lo marca CRITIQUE; no cifra nada, lo señala).
    pii: bool = False


class PrimaryKey(_Strict):
    """Clave primaria de la tabla."""

    name: str
    columns: list[str] = Field(min_length=1)
    strategy: PrimaryKeyStrategy = PrimaryKeyStrategy.SURROGATE
    rationale: Optional[str] = None
    origin: Optional[Origin] = None


class ForeignKey(TracedItem):
    """Clave foránea derivada de una relación del EF."""

    name: str
    columns: list[str] = Field(min_length=1)
    references_table: str
    references_columns: list[str] = Field(min_length=1)
    on_delete: ReferentialAction = ReferentialAction.RESTRICT
    on_update: ReferentialAction = ReferentialAction.NO_ACTION
    #: Relación del EF que la origina (``REL-...``).
    relationship_ref: Optional[str] = None
    rationale: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)


class UniqueConstraint(TracedItem):
    """Restricción de unicidad (validación del EF o clave natural)."""

    name: str
    columns: list[str] = Field(min_length=1)
    description: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)


class CheckConstraint(TracedItem):
    """Restricción CHECK derivada de una regla o validación del EF."""

    name: str
    #: Expresión con vocabulario SQL restringido (comparadores, IN, BETWEEN,
    #: IS NOT NULL). Sin subconsultas ni funciones propias de un motor.
    expression: str
    description: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)


class Index(TracedItem):
    """Índice justificado por un patrón de acceso real.

    Sin ``rationale`` no se crea: la regla es que no hay índices "por si acaso".
    """

    name: str
    columns: list[str] = Field(min_length=1)
    unique: bool = False
    rationale: str
    #: Refs al patrón de acceso que lo justifica (``API-...``, ``CRUD-...``,
    #: ``US-...``).
    access_pattern_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class Normalization(_Strict):
    """Forma normal y desnormalizaciones **deliberadas** (nunca accidentales)."""

    form: NormalizationForm = NormalizationForm.THIRD
    denormalized: bool = False
    #: Obligatorio cuando ``denormalized`` es ``True`` (lo verifica CRITIQUE).
    rationale: Optional[str] = None


class Table(TracedItem):
    """Tabla del modelo físico."""

    name: str
    schema_name: Optional[str] = None
    #: Entidad del EF que la origina (``ENT-...``). ``None`` solo si ``kind`` no
    #: es ``entity`` (puente/catálogo/auditoría).
    entity_ref: Optional[str] = None
    kind: TableKind = TableKind.ENTITY
    description: Optional[str] = None
    columns: list[Column] = Field(default_factory=list)
    primary_key: Optional[PrimaryKey] = None
    foreign_keys: list[ForeignKey] = Field(default_factory=list)
    unique_constraints: list[UniqueConstraint] = Field(default_factory=list)
    check_constraints: list[CheckConstraint] = Field(default_factory=list)
    indexes: list[Index] = Field(default_factory=list)
    estimated_volume: VolumeEstimate = VolumeEstimate.DESCONOCIDA
    normalization: Normalization = Field(default_factory=Normalization)
    source_refs: list[str] = Field(default_factory=list)
    #: Veredicto de la fase RECONCILE (INV4). ``None`` = no se reconcilió (no hay
    #: inventario, o el artefacto es anterior al módulo): retrocompatible.
    reconciliation: Optional[ReconciliationRef] = None


# --- DDL ---------------------------------------------------------------------


class DdlScript(_Strict):
    """Script DDL renderizado de forma determinista (nunca escrito por el LLM)."""

    id: str
    #: Orden de ejecución (1 = primero). Respeta las dependencias entre objetos.
    order: int
    name: str
    kind: DdlScriptKind
    engine: DbEngine
    #: Sentencias individuales (lo que valida el parseo con sqlglot).
    statements: list[str] = Field(default_factory=list)
    #: Texto completo del script, listo para copiar o descargar.
    sql: str = ""
    source_refs: list[str] = Field(default_factory=list)


# --- Datos semilla -----------------------------------------------------------


class SeedData(TracedItem):
    """Filas semilla de un catálogo, con la evidencia del EF que las respalda.

    Solo se emiten valores **citados** en el EF: ``evidence`` es la cita verbatim.
    Un catálogo sin valores citados se queda sin semilla y genera una pregunta.
    """

    table_ref: str
    table: str
    reason: Optional[str] = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    evidence: Optional[str] = None


# --- Diccionario de datos ----------------------------------------------------


class DictionaryEntry(_Strict):
    """Fila del diccionario de datos (una por columna).

    Se **deriva** de ``tables[]``: no hay una segunda versión del contenido ni una
    pasada extra al LLM (las descripciones y ejemplos vienen ya de TABLES).
    """

    id: str
    table: str
    column: str
    type: str
    nullable: bool
    #: ``PK`` | ``FK`` | ``UQ`` | ``—`` (o combinación, p. ej. ``PK,FK``).
    key: str = "—"
    description: Optional[str] = None
    example: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)
    origin: Optional[Origin] = None


# --- Diagrama entidad-relación ----------------------------------------------


class ErDiagram(_Strict):
    """Diagrama entidad-relación (Mermaid ``erDiagram``, generado determinista)."""

    format: DiagramFormat = DiagramFormat.MERMAID
    code: str = ""


# --- Decisiones de diseño de datos ------------------------------------------


class DesignDecision(TracedItem):
    """Decisión de diseño de datos (ADR ligero del ámbito BD)."""

    title: str
    decision: str
    rationale: str
    alternatives_considered: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    scope: DecisionScope = DecisionScope.GLOBAL
    table_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


# --- Reglas del EF y dónde se hacen cumplir ---------------------------------


class RuleMapping(TracedItem):
    """Destino de una regla/validación del EF.

    Existe para que la cobertura de reglas sea auditable: toda ``BR-``/``VAL-``
    del EF aparece aquí con su destino, aunque no haya acabado en una constraint.
    """

    #: Ref del EF (``BR-...`` / ``VAL-...``).
    rule_ref: str
    enforcement: RuleEnforcement
    #: Constraint que la implementa (``CK-...``/``UQ-...``), si es declarativa.
    constraint_ref: Optional[str] = None
    table_ref: Optional[str] = None
    note: Optional[str] = None


# --- Validación determinista del DDL ----------------------------------------


class ValidationIssue(_Strict):
    """Hallazgo de la validación del DDL (sin LLM)."""

    #: Código estable y accionable (``fk_target_missing``, ``table_without_pk``…).
    code: str
    message: str
    ref: Optional[str] = None


class DdlValidation(_Strict):
    """Resultado de la validación determinista del DDL.

    ``checks`` es un mapa nombre → resultado para poder pintarlo tal cual en el
    hub y en el PDF. ``executed`` distingue "parseado" de "ejecutado contra un
    motor": no se presenta como certificación lo que solo fue un parseo.
    """

    syntax_ok: bool = False
    engine: Optional[DbEngine] = None
    #: Capas aplicadas (p. ej. ``estructural+sqlglot``).
    validator: Optional[str] = None
    executed: bool = False
    checks: dict[str, bool] = Field(default_factory=dict)
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


# --- Preguntas al DBA -------------------------------------------------------


class DbaQuestion(TracedItem):
    """Duda hacia el DBA/Arquitecto (no se inventa: se pregunta).

    Las preguntas se **agrupan por clase de vacío**: 40 columnas sin longitud
    producen una pregunta con los refs enumerados en ``reason``, no 40 preguntas.
    """

    question: str
    reason: str
    audience: Audience = Audience.TECNICO
    blocking: bool = False
    linked_to_ref: Optional[str] = None
    status: QuestionStatus = QuestionStatus.PENDIENTE


# --- Análisis ---------------------------------------------------------------


class Risk(TracedItem):
    """Riesgo del modelo de datos propuesto."""

    description: str
    severity: RiskSeverity = RiskSeverity.MEDIA
    mitigation: Optional[str] = None
    source_ref: Optional[str] = None


class Coverage(_Strict):
    """Cobertura de trazabilidad hacia el EF. Nunca oculta huecos.

    Solo la cobertura de **entidades** entra en el semáforo; campos, validaciones
    y reglas generan preguntas (mismo criterio que los RNF en Arquitectura).
    """

    entities_total: int = 0
    entities_mapped: int = 0
    uncovered_entity_refs: list[str] = Field(default_factory=list)
    fields_total: int = 0
    fields_mapped: int = 0
    unmapped_field_refs: list[str] = Field(default_factory=list)
    validations_total: int = 0
    validations_enforced: int = 0
    unenforced_validation_refs: list[str] = Field(default_factory=list)
    rules_total: int = 0
    rules_enforced: int = 0
    unenforced_rule_refs: list[str] = Field(default_factory=list)


class DatabaseAnalysis(_Strict):
    """Bloque de análisis del DatabaseArtifact."""

    risks: list[Risk] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    coverage: Coverage = Field(default_factory=Coverage)


# --- Métricas ---------------------------------------------------------------


class DatabaseMetrics(_Strict):
    """Métricas reales de la corrida del Agente BD."""

    tokens: TokenMetrics = Field(default_factory=TokenMetrics)
    cost: float = 0.0  # USD
    duration: float = 0.0  # segundos
    tables_total: int = 0
    columns_total: int = 0
    indexes_total: int = 0
    constraints_total: int = 0
    seed_rows_total: int = 0
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    #: Espejo de ``validation.syntax_ok`` sin errores: entra en el semáforo.
    ddl_valid: bool = False
    skipped: list[SkippedItem] = Field(default_factory=list)


# --- Artefacto raíz ---------------------------------------------------------


class DatabaseArtifact(_Strict):
    """Artefacto completo del Agente BD (contrato v1.0.0)."""

    schema_version: str = SCHEMA_VERSION
    source: SourceRef
    target: Target
    tables: list[Table] = Field(default_factory=list)
    ddl_scripts: list[DdlScript] = Field(default_factory=list)
    seed_data: list[SeedData] = Field(default_factory=list)
    data_dictionary: list[DictionaryEntry] = Field(default_factory=list)
    er_diagram: ErDiagram = Field(default_factory=ErDiagram)
    design_decisions: list[DesignDecision] = Field(default_factory=list)
    rule_mappings: list[RuleMapping] = Field(default_factory=list)
    validation: DdlValidation = Field(default_factory=DdlValidation)
    analysis: DatabaseAnalysis = Field(default_factory=DatabaseAnalysis)
    questions_for_dba: list[DbaQuestion] = Field(default_factory=list)
    metrics: DatabaseMetrics = Field(default_factory=DatabaseMetrics)
    #: Resumen de la reconciliación contra el inventario (INV4). Opcional.
    reconciliation: Optional[ReconciliationSummary] = None
