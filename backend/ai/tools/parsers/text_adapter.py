"""TextToCIRAdapter: convierte texto libre en un CIR.

Detecta párrafos, listas y títulos. Si el texto es plano (sin estructura
detectable), produce un único ``section`` con todo el contenido.
"""

from typing import Optional

from ai.tools.cir import CIR

from ._builder import CIRBuilder
from ._heuristics import has_structure, parse_blocks


class TextToCIRAdapter:
    """Adaptador de texto libre a CIR."""

    @staticmethod
    def adapt(text: str, title: Optional[str] = None) -> CIR:
        """Convierte ``text`` en un CIR (source_type='text')."""
        blocks = parse_blocks(text)
        builder = CIRBuilder(source_type="text", fidelity="full", title=title)

        if not has_structure(blocks):
            # Texto plano: un solo section con todo el contenido.
            builder.add_section(text.strip(), level=0)
            return builder.build()

        # Estructurado: sección raíz + elementos.
        first_heading = next(
            (payload[1] for kind, payload in blocks if kind == "heading"), None
        )
        builder.add_section(title or first_heading or "Documento", level=0)
        for kind, payload in blocks:
            if kind == "heading":
                level, htext = payload
                builder.add_heading(htext, level=level + 1)
            elif kind == "list":
                builder.add_list(payload)
            else:
                builder.add_paragraph(payload)
        return builder.build()
