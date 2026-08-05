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

from .enums import LogicalType, PrimaryKeyStrategy, ReferentialAction


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
