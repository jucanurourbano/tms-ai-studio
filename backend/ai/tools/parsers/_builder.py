"""Constructor incremental de CIR compartido por los parsers.

Mantiene el orden global y una pila de headings para calcular el ``breadcrumb``
(traza de ancestros) de cada elemento.
"""

from typing import Optional

from ai.tools.cir import (
    CIR,
    CIRElement,
    Coordinates,
    ElementType,
    TableData,
    make_element_id,
)


class CIRBuilder:
    """Acumula elementos del CIR respetando la jerarquía por niveles."""

    def __init__(self, source_type: str, fidelity: str, title: Optional[str] = None):
        self.source_type = source_type
        self.fidelity = fidelity
        self.title = title
        self._order = 0
        self._stack: list[tuple[int, str]] = []  # (level, text) de ancestros
        self._elements: list[CIRElement] = []

    def _next_order(self) -> int:
        o = self._order
        self._order += 1
        return o

    def _breadcrumb(self) -> list[str]:
        return [text for _, text in self._stack]

    def add_section(
        self, text: str, level: int = 0, page: Optional[int] = None
    ) -> None:
        """Agrega una sección (raíz o lógica) y la coloca en la pila."""
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        o = self._next_order()
        self._elements.append(
            CIRElement(
                element_id=make_element_id(o),
                type=ElementType.SECTION,
                order=o,
                breadcrumb=self._breadcrumb(),
                coordinates=Coordinates(index=o, page=page),
                level=level,
                text=text,
            )
        )
        self._stack.append((level, text))

    def add_heading(self, text: str, level: int, page: Optional[int] = None) -> None:
        """Agrega un heading; el breadcrumb son sus ancestros (no se incluye)."""
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        o = self._next_order()
        self._elements.append(
            CIRElement(
                element_id=make_element_id(o),
                type=ElementType.HEADING,
                order=o,
                breadcrumb=self._breadcrumb(),
                coordinates=Coordinates(index=o, page=page),
                level=level,
                text=text,
            )
        )
        self._stack.append((level, text))

    def add_paragraph(self, text: str, page: Optional[int] = None) -> None:
        o = self._next_order()
        self._elements.append(
            CIRElement(
                element_id=make_element_id(o),
                type=ElementType.PARAGRAPH,
                order=o,
                breadcrumb=self._breadcrumb(),
                coordinates=Coordinates(index=o, page=page),
                text=text,
            )
        )

    def add_list(self, items: list[str], page: Optional[int] = None) -> None:
        o = self._next_order()
        self._elements.append(
            CIRElement(
                element_id=make_element_id(o),
                type=ElementType.LIST,
                order=o,
                breadcrumb=self._breadcrumb(),
                coordinates=Coordinates(index=o, page=page),
                items=items,
            )
        )

    def add_table(self, rows: list[list[str]], page: Optional[int] = None) -> None:
        n_rows = len(rows)
        n_cols = max((len(r) for r in rows), default=0)
        o = self._next_order()
        self._elements.append(
            CIRElement(
                element_id=make_element_id(o),
                type=ElementType.TABLE,
                order=o,
                breadcrumb=self._breadcrumb(),
                coordinates=Coordinates(index=o, page=page),
                table=TableData(rows=rows, n_rows=n_rows, n_cols=n_cols),
            )
        )

    def build(self) -> CIR:
        return CIR(
            source_type=self.source_type,
            fidelity=self.fidelity,
            title=self.title,
            elements=self._elements,
        )
