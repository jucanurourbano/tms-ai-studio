"""PdfParser: extrae texto de un PDF (pypdf) y lo estructura en un CIR.

Solo texto: un PDF escaneado (sin texto extraíble) produce ``ScannedPDFError``.
El OCR se difiere a v1.1. Fidelidad: ``degraded`` (sin topología garantizada).
"""

from pathlib import Path
from typing import Union

from pypdf import PdfReader

from ai.errors import ParserError, ScannedPDFError
from ai.tools.cir import CIR

from ._builder import CIRBuilder
from ._heuristics import parse_blocks


class PdfParser:
    """Parser de PDF basado en pypdf (solo texto)."""

    @staticmethod
    def parse(path: Union[str, Path]) -> CIR:
        """Parsea un PDF a CIR. Lanza ScannedPDFError si no hay texto."""
        path = Path(path)
        try:
            reader = PdfReader(str(path))
            pages_text = [(page.extract_text() or "") for page in reader.pages]
        except ScannedPDFError:
            raise
        except Exception as exc:  # pragma: no cover - errores de pypdf
            raise ParserError(f"No se pudo leer el PDF: {exc}") from exc

        if not any(t.strip() for t in pages_text):
            raise ScannedPDFError(
                "El PDF no contiene texto extraíble (posible escaneo). "
                "El OCR se difiere a v1.1."
            )

        builder = CIRBuilder(
            source_type="document", fidelity="degraded", title=path.stem
        )
        builder.add_section(path.stem, level=0)

        for page_num, text in enumerate(pages_text, start=1):
            if not text.strip():
                continue
            for kind, payload in parse_blocks(text):
                if kind == "heading":
                    level, htext = payload
                    builder.add_heading(htext, level=level + 1, page=page_num)
                elif kind == "list":
                    builder.add_list(payload, page=page_num)
                else:
                    builder.add_paragraph(payload, page=page_num)

        return builder.build()
