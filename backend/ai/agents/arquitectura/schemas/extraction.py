"""Esquemas de *structured output* de los nodos LLM del Agente Arquitectura.

Son contratos de la SALIDA del modelo (no del artefacto final): se validan con
reparación + cuarentena vía ``ai/agents/base/structured.py``. Los ids estables y
la trazabilidad final se resuelven luego en Python.
"""

from typing import Optional

from pydantic import BaseModel, Field

from .enums import (
    ComponentType,
    CrossCuttingConcern,
    IntegrationDirection,
    IntegrationProtocol,
)


class ComponentExtract(BaseModel):
    """Un componente propuesto por el LLM (ids/dependencias se resuelven en Python).

    ``depends_on`` referencia otros componentes por **nombre** (los que el propio
    modelo define en esta misma respuesta); Python los mapea a ids ``CMP-…``.
    """

    name: str
    type: ComponentType
    layer: str
    responsibility: str
    epic_refs: list[str] = Field(default_factory=list)
    story_refs: list[str] = Field(default_factory=list)
    entity_refs: list[str] = Field(default_factory=list)
    api_refs: list[str] = Field(default_factory=list)
    module_refs: list[str] = Field(default_factory=list)
    process_refs: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)  # nombres de componentes
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ComponentsExtract(BaseModel):
    """Salida del nodo COMPONENTS."""

    components: list[ComponentExtract] = Field(default_factory=list)


class StackChoiceExtract(BaseModel):
    """Una recomendación de stack propuesta por el LLM para una capa."""

    layer: str
    technology: str
    version: Optional[str] = None
    rationale: str
    alternatives: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class StackExtract(BaseModel):
    """Salida del nodo STACK (recomendación por capa desde el allow-list)."""

    stack: list[StackChoiceExtract] = Field(default_factory=list)


class AdrExtract(BaseModel):
    """Un ADR propuesto por el LLM (ids/estilo se resuelven en Python)."""

    title: str
    decision: str
    context: str
    alternatives_considered: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class AdrsExtract(BaseModel):
    """Salida del nodo ADRS (ADRs adicionales al de estilo, que fija Python)."""

    adrs: list[AdrExtract] = Field(default_factory=list)


class IntegrationExtract(BaseModel):
    """Una integración externa detectada por el LLM en el EF."""

    name: str
    system: str
    direction: IntegrationDirection = IntegrationDirection.OUTBOUND
    protocol: IntegrationProtocol = IntegrationProtocol.UNKNOWN
    purpose: str
    data_exchanged: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)
    contract_known: bool = False
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class IntegrationsExtract(BaseModel):
    """Salida del sub-paso de detección de integraciones (nodo CONTRACTS)."""

    integrations: list[IntegrationExtract] = Field(default_factory=list)


class CrossCuttingExtract(BaseModel):
    """Un requisito transversal propuesto por el LLM (auth, auditoría, …)."""

    concern: CrossCuttingConcern
    requirement: str
    approach: str
    source_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CrossCuttingListExtract(BaseModel):
    """Salida del sub-paso de transversales (nodo CONTRACTS)."""

    cross_cutting: list[CrossCuttingExtract] = Field(default_factory=list)
