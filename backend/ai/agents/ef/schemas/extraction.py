"""Esquemas de salida estructurada de la fase EXTRACT (por dimensión).

Validan lo que devuelve el LLM antes de consolidar. Son intencionalmente
estrictos en los campos requeridos para disparar el loop de reparación.
"""

from typing import Optional

from pydantic import BaseModel, Field

from .enums import Origin, Priority


class ExtractBase(BaseModel):
    """Campos de trazabilidad comunes a todo ítem extraído."""

    source_ref: Optional[str] = None
    evidence: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    origin: Origin = Origin.STATED


class ReqExtract(ExtractBase):
    text: str
    priority: Optional[Priority] = None


class RequirementsExtract(BaseModel):
    business: list[ReqExtract] = Field(default_factory=list)
    functional: list[ReqExtract] = Field(default_factory=list)
    non_functional: list[ReqExtract] = Field(default_factory=list)


class ActorExtract(ExtractBase):
    name: str
    description: Optional[str] = None
    responsibilities: list[str] = Field(default_factory=list)


class ActorsExtract(BaseModel):
    actors: list[ActorExtract] = Field(default_factory=list)


class ModuleExtract(ExtractBase):
    name: str
    description: Optional[str] = None


class MenuExtract(ExtractBase):
    name: str
    module_ref: Optional[str] = None
    parent_ref: Optional[str] = None
    path: Optional[str] = None


class ModulesMenusExtract(BaseModel):
    modules: list[ModuleExtract] = Field(default_factory=list)
    menus: list[MenuExtract] = Field(default_factory=list)


class ProcessExtract(ExtractBase):
    name: str
    description: Optional[str] = None
    steps: list[str] = Field(default_factory=list)
    actor_refs: list[str] = Field(default_factory=list)


class ProcessesExtract(BaseModel):
    processes: list[ProcessExtract] = Field(default_factory=list)


class RuleExtract(ExtractBase):
    statement: str


class ValExtract(ExtractBase):
    rule: str
    field_ref: Optional[str] = None


class RulesValidationsExtract(BaseModel):
    business_rules: list[RuleExtract] = Field(default_factory=list)
    validations: list[ValExtract] = Field(default_factory=list)


class FieldExtract(ExtractBase):
    name: str
    entity_ref: Optional[str] = None
    data_type: Optional[str] = None
    required: bool = False


class FieldsExtract(BaseModel):
    fields: list[FieldExtract] = Field(default_factory=list)
