"""Esquemas de *structured output* de los nodos LLM del Agente Scrum.

Son contratos de la SALIDA del modelo (no del artefacto final): se validan con
reparación + cuarentena vía ``ai/agents/base/structured.py``. Las historias/épicas
finales se ensamblan luego con ids estables y trazabilidad completa.
"""

from typing import Optional

from pydantic import BaseModel, Field

from .enums import AcceptanceFormat, MoscowPriority, StoryPoints


class EpicExtract(BaseModel):
    """Una épica propuesta por el LLM (ids/asignación se resuelven en Python)."""

    title: str
    description: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class EpicsExtract(BaseModel):
    """Salida del nodo EPICS."""

    epics: list[EpicExtract] = Field(default_factory=list)


class StoryExtract(BaseModel):
    """Una historia propuesta por el LLM para un requisito funcional."""

    role: str
    goal: str
    benefit: str
    requirement_refs: list[str] = Field(default_factory=list)
    process_refs: list[str] = Field(default_factory=list)
    rule_refs: list[str] = Field(default_factory=list)
    depends_on_requirements: list[str] = Field(default_factory=list)
    epic_hint: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class StoriesExtract(BaseModel):
    """Salida del nodo STORIES (una pasada por requisito funcional)."""

    stories: list[StoryExtract] = Field(default_factory=list)


class CriterionExtract(BaseModel):
    """Un criterio de aceptación propuesto por el LLM."""

    format: AcceptanceFormat = AcceptanceFormat.GHERKIN
    given: Optional[str] = None
    when: Optional[str] = None
    then: Optional[str] = None
    text: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)


class CriteriaExtract(BaseModel):
    """Salida del nodo CRITERIA (una pasada por historia)."""

    acceptance_criteria: list[CriterionExtract] = Field(default_factory=list)


class EstimateExtract(BaseModel):
    """Salida del nodo ESTIMATE (una pasada por historia).

    ``story_points`` usa el enum Fibonacci cerrado (D9): valores fuera de la escala
    disparan el loop de reparación y, si no se corrigen, la cuarentena.
    """

    story_points: StoryPoints
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class PrioritizeExtract(BaseModel):
    """Salida del nodo PRIORITIZE (una pasada por historia).

    El LLM solo clasifica (MoSCoW + valor/esfuerzo); el orden del backlog lo arma
    Python de forma determinista.
    """

    priority: MoscowPriority
    value: int = Field(ge=1, le=5)
    effort: int = Field(ge=1, le=5)
    rationale: Optional[str] = None
