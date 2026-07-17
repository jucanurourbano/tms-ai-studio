"""CIR — Canonical Intermediate Representation.

Representación canónica e intermedia de una fuente (documento o texto libre):
una **lista ordenada** de elementos donde la jerarquía se codifica en
``breadcrumb`` (traza de los headings ancestros) y ``level``. Las tablas
conservan su topología completa (filas x columnas).
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ElementType(str, Enum):
    """Tipos de elemento del CIR."""

    SECTION = "section"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"


class Coordinates(BaseModel):
    """Ubicación del elemento en la fuente."""

    model_config = ConfigDict(extra="forbid")

    index: int  # orden global dentro de la fuente
    page: Optional[int] = None  # página (solo PDF)


class TableData(BaseModel):
    """Tabla con topología preservada (filas x columnas)."""

    model_config = ConfigDict(extra="forbid")

    rows: list[list[str]] = Field(default_factory=list)
    n_rows: int = 0
    n_cols: int = 0


class CIRElement(BaseModel):
    """Elemento del CIR."""

    model_config = ConfigDict(extra="forbid")

    element_id: str
    type: ElementType
    order: int
    breadcrumb: list[str] = Field(default_factory=list)
    coordinates: Coordinates
    level: Optional[int] = None  # nivel de heading/section
    text: Optional[str] = None  # heading / paragraph / section
    items: Optional[list[str]] = None  # list
    table: Optional[TableData] = None  # table


class CIR(BaseModel):
    """Documento canónico: elementos ordenados + tipo de fuente."""

    model_config = ConfigDict(extra="forbid")

    source_type: str  # "document" | "text"
    fidelity: Optional[str] = None  # "full" | "partial" | "degraded"
    title: Optional[str] = None
    elements: list[CIRElement] = Field(default_factory=list)

    def headings(self) -> list[CIRElement]:
        """Devuelve los elementos de tipo heading."""
        return [e for e in self.elements if e.type is ElementType.HEADING]

    def tables(self) -> list[CIRElement]:
        """Devuelve los elementos de tipo tabla."""
        return [e for e in self.elements if e.type is ElementType.TABLE]

    def text_content(self) -> str:
        """Concatena el texto de todos los elementos (para estimación/single-shot)."""
        parts: list[str] = []
        for e in self.elements:
            if e.text:
                parts.append(e.text)
            if e.items:
                parts.extend(e.items)
            if e.table:
                for row in e.table.rows:
                    parts.append(" | ".join(row))
        return "\n".join(parts)


def make_element_id(order: int) -> str:
    """Genera un element_id estable a partir del orden (el-0001, ...)."""
    return f"el-{order:04d}"
