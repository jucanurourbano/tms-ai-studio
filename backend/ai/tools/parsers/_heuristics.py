"""Heurísticas para estructurar texto plano en bloques (PDF y texto libre).

Detecta títulos (markdown ``#`` o líneas cortas en MAYÚSCULAS), listas
(``-``, ``*``, ``•`` o ``1.``) y párrafos.
"""

import re

_HEADING_MD = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+?)\s*$")

# Un "bloque" es una tupla (kind, payload):
#   ("heading", (level, text)) | ("list", [items]) | ("paragraph", text)
Block = tuple


def _is_caps_heading(line: str) -> bool:
    """Línea corta en mayúsculas → probable título."""
    s = line.strip()
    if not (0 < len(s) <= 60):
        return False
    if not any(c.isalpha() for c in s):
        return False
    return s == s.upper()


def _split_blocks(text: str) -> list[str]:
    """Separa el texto en bloques por líneas en blanco."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.split(r"\n\s*\n", normalized)
    return [b.strip("\n") for b in raw if b.strip()]


def parse_blocks(text: str) -> list[Block]:
    """Convierte texto plano en una lista de bloques tipados."""
    blocks: list[Block] = []
    for raw in _split_blocks(text):
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        if not lines:
            continue

        # Lista: todas las líneas son ítems de lista.
        list_items = [_LIST_ITEM.match(ln) for ln in lines]
        if all(m is not None for m in list_items):
            blocks.append(("list", [m.group(1).strip() for m in list_items]))
            continue

        # Título markdown o línea única en mayúsculas.
        if len(lines) == 1:
            md = _HEADING_MD.match(lines[0])
            if md:
                blocks.append(("heading", (len(md.group(1)), md.group(2).strip())))
                continue
            if _is_caps_heading(lines[0]):
                blocks.append(("heading", (1, lines[0].strip())))
                continue

        # Párrafo (une líneas con espacio).
        blocks.append(("paragraph", " ".join(ln.strip() for ln in lines)))
    return blocks


def has_structure(blocks: list[Block]) -> bool:
    """Indica si se detectaron títulos o listas (no es texto plano)."""
    return any(kind in ("heading", "list") for kind, _ in blocks)
