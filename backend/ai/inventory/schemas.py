"""Esquemas de la extracción de conocimiento desde documentos (INV3).

Son el *structured output* del pase LLM: lo que el modelo puede decir sobre un
documento que describe un sistema **ya existente**.

Regla que gobierna todo el archivo: **cada elemento extraído lleva su
``source_ref`` y su ``evidence`` verbatim**, exactamente como en el EF. Un módulo
del inventario sin cita es una afirmación sobre un sistema de producción que nadie
puede rastrear hasta el documento — y contra ese dato reconcilian después tres
agentes de diseño. Sin evidencia, el error se propaga sin dejar rastro.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExtractedItem(BaseModel):
    """Base de todo lo extraído: trazabilidad obligatoria."""

    model_config = ConfigDict(extra="forbid")

    #: ``element_id`` del CIR del que sale (``el-0007``). Es lo que permite volver
    #: al párrafo exacto del documento.
    source_ref: str
    #: Fragmento VERBATIM que lo respalda. No un resumen: el texto tal cual.
    evidence: str
    confidence: float = Field(ge=0.0, le=1.0)
    #: ``stated`` = lo dice el documento; ``derived`` = deducido de lo que dice.
    origin: Literal["stated", "derived"]


class ExtractedEntity(ExtractedItem):
    """Una entidad de negocio que el documento describe como existente."""

    name: str
    description: Optional[str] = None
    #: Atributos mencionados. NO es un modelo de datos: es lo que el texto nombra.
    attributes: list[str] = Field(default_factory=list)


class ExtractedFunctionality(ExtractedItem):
    """Una funcionalidad que el sistema descrito ya ofrece."""

    name: str
    description: Optional[str] = None


class ExtractedModule(ExtractedItem):
    """Un módulo o componente funcional del sistema descrito."""

    name: str
    description: Optional[str] = None
    #: Nombres de funcionalidades y entidades que el documento asocia al módulo.
    functionalities: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class ExtractedDecision(ExtractedItem):
    """Una decisión técnica o de negocio que el documento deja tomada.

    Es lo que más valor tiene y lo que más fácil se pierde: "se migrará a Aurora",
    "los reportes serán asíncronos". Sin registrarlas, el Agente Arquitectura las
    volvería a decidir desde cero, quizá de otra forma.
    """

    title: str
    rationale: Optional[str] = None


class KnowledgeExtract(BaseModel):
    """Salida completa del pase de extracción sobre un fragmento del documento."""

    model_config = ConfigDict(extra="forbid")

    modules: list[ExtractedModule] = Field(default_factory=list)
    entities: list[ExtractedEntity] = Field(default_factory=list)
    functionalities: list[ExtractedFunctionality] = Field(default_factory=list)
    decisions: list[ExtractedDecision] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """``True`` si el fragmento no aportó nada (es un resultado legítimo)."""
        return not (
            self.modules or self.entities or self.functionalities or self.decisions
        )
