"""Conocimiento de dominio inyectable en los prompts (glosario logístico)."""

from functools import lru_cache
from pathlib import Path

import yaml

_GLOSSARY_PATH = Path(__file__).resolve().parent / "glossary.yaml"


@lru_cache
def load_glossary() -> dict[str, str]:
    """Carga el glosario logístico (término -> definición)."""
    data = yaml.safe_load(_GLOSSARY_PATH.read_text(encoding="utf-8")) or {}
    return dict(data.get("terms", {}))


def glossary_block() -> str:
    """Renderiza el glosario como bloque de texto para inyectar en prompts."""
    terms = load_glossary()
    lines = [f"- {term}: {definition}" for term, definition in terms.items()]
    return "GLOSARIO LOGÍSTICO (usa estas definiciones):\n" + "\n".join(lines)
