"""Esquemas de *structured output* de los nodos LLM del Agente BD.

Son contratos de la **salida del modelo**, no del artefacto final: se validan con
reparación + cuarentena vía ``ai/agents/base/structured.py``, y los ids estables,
la trazabilidad y el tipo físico se resuelven después en Python.

Obsérvese que en ninguno de estos esquemas hay un campo donde quepa SQL: el modelo
elige ``LogicalType`` y nada más. Es la barrera que hace imposible que se cuele la
sintaxis de un motor en el DDL de otro.
"""

from typing import Optional

from pydantic import BaseModel, Field

from ai.agents.arquitectura.schemas.enums import RiskSeverity

from .enums import (
    LogicalType,
    PrimaryKeyStrategy,
    ReferentialAction,
    RuleEnforcement,
)


class ColumnExtract(BaseModel):
    """Una columna completada por el LLM (nombre y orden los fija Python)."""

    name: str
    logical_type: LogicalType
    length: Optional[int] = Field(default=None, ge=1)
    precision: Optional[int] = Field(default=None, ge=1)
    scale: Optional[int] = Field(default=None, ge=0)
    nullable: bool = True
    default: Optional[str] = None
    description: Optional[str] = None
    example: Optional[str] = None
    #: El modelo puede confirmar la ambigüedad heredada o declarar una nueva.
    type_ambiguous: bool = False
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class PrimaryKeyExtract(BaseModel):
    """Clave primaria propuesta por el LLM (el nombre lo pone la convención)."""

    columns: list[str] = Field(default_factory=list)
    strategy: PrimaryKeyStrategy = PrimaryKeyStrategy.SURROGATE
    rationale: Optional[str] = None


class TableExtract(BaseModel):
    """Salida del map de TABLES: **una** tabla completada.

    No incluye ``name``: la tabla que se completa es la que se envió en el prompt,
    y aceptar un nombre de vuelta abriría la puerta a que el modelo renombrara o
    inventara tablas.
    """

    description: Optional[str] = None
    primary_key: Optional[PrimaryKeyExtract] = None
    columns: list[ColumnExtract] = Field(default_factory=list)


class OneToOneOwnerExtract(BaseModel):
    """Lado dueño de la FK en una relación 1:1 (``owner=None`` ⇒ no hay lado claro)."""

    relationship_ref: str
    owner: Optional[str] = None
    rationale: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ReferentialActionExtract(BaseModel):
    """Acción referencial propuesta para una FK ya existente."""

    relationship_ref: str
    on_delete: ReferentialAction = ReferentialAction.RESTRICT
    rationale: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RelationsExtract(BaseModel):
    """Salida del nodo RELATIONS (solo lo que no es determinista)."""

    one_to_one: list[OneToOneOwnerExtract] = Field(default_factory=list)
    referential_actions: list[ReferentialActionExtract] = Field(default_factory=list)


# --- CONSTRAINTS (BD4) -------------------------------------------------------


class UniqueConstraintExtract(BaseModel):
    """Restricción de unicidad propuesta (el nombre lo pone la convención)."""

    columns: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CheckConstraintExtract(BaseModel):
    """CHECK propuesto. ``expression`` se valida contra un vocabulario restringido.

    ``suffix`` es solo el trozo final del nombre: el completo lo compone Python con
    el patrón de la casa, para que el modelo no pueda producir un identificador
    inválido ni demasiado largo para el motor.
    """

    suffix: Optional[str] = None
    expression: str
    description: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class NotNullExtract(BaseModel):
    """Columna que una regla del EF obliga a ser obligatoria."""

    column: str
    source_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RuleMappingExtract(BaseModel):
    """Dónde se hace cumplir una regla/validación del EF."""

    rule_ref: str
    enforcement: RuleEnforcement = RuleEnforcement.APPLICATION
    note: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ConstraintsExtract(BaseModel):
    """Salida del map de CONSTRAINTS (una tabla)."""

    unique_constraints: list[UniqueConstraintExtract] = Field(default_factory=list)
    check_constraints: list[CheckConstraintExtract] = Field(default_factory=list)
    not_null_columns: list[NotNullExtract] = Field(default_factory=list)
    rule_mappings: list[RuleMappingExtract] = Field(default_factory=list)


# --- INDEXES (BD4) -----------------------------------------------------------


class IndexExtract(BaseModel):
    """Índice justificado por un patrón de acceso real del EF."""

    table: str
    columns: list[str] = Field(default_factory=list)
    unique: bool = False
    rationale: str
    access_pattern_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class IndexesExtract(BaseModel):
    """Salida del nodo INDEXES (una sola llamada para todo el esquema)."""

    indexes: list[IndexExtract] = Field(default_factory=list)


# --- CATALOGS (BD4) ----------------------------------------------------------


class CatalogReferenceExtract(BaseModel):
    """Tabla y columna que referenciarán al catálogo."""

    table: str
    column: str


class CatalogExtract(BaseModel):
    """Catálogo detectado con sus valores semilla **citados** en el EF."""

    name: str
    description: Optional[str] = None
    referenced_by: Optional[CatalogReferenceExtract] = None
    #: Filas literales del EF. Vacío es una respuesta legítima: se crea la tabla y
    #: se pregunta al DBA por los valores (nunca se inventan).
    rows: list[dict] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    evidence: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CatalogsExtract(BaseModel):
    """Salida del nodo CATALOGS."""

    catalogs: list[CatalogExtract] = Field(default_factory=list)


# --- CRITIQUE (BD6) ----------------------------------------------------------


class DbRiskExtract(BaseModel):
    """Riesgo del modelo de datos propuesto por el pase LLM de crítica."""

    description: str
    severity: RiskSeverity = RiskSeverity.MEDIA
    mitigation: Optional[str] = None
    source_ref: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class DbCritiqueExtract(BaseModel):
    """Salida del pase LLM de CRITIQUE: solo riesgos, sin cambios al modelo."""

    risks: list[DbRiskExtract] = Field(default_factory=list)
