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
            # Texto plano: la sección raíz lleva el RÓTULO y el contenido va en
            # un párrafo. El texto de una SECTION es un título, nunca el cuerpo:
            # ``CIRBuilder`` lo apila como ancestro del breadcrumb y el chunker
            # lo usa como contexto, así que poner aquí el documento entero lo
            # mandaba DOS VECES al modelo (2,00x medido por encima del umbral de
            # single_shot). Era el único ``add_section`` del repositorio que
            # pasaba contenido en vez de un rótulo.
            cuerpo = text.strip()
            if not cuerpo:
                # Documento vacío: ni rótulo ni cuerpo. Un rótulo suelto (el
                # nombre del fichero, p. ej.) se leería después como contenido
                # del documento y sería citable como ``source_ref``.
                builder.add_section("", level=0)
                return builder.build()
            builder.add_section(title or "Documento", level=0)
            builder.add_paragraph(cuerpo)
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
