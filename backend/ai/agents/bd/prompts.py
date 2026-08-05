"""Carga de prompts versionados del Agente BD (``ai/prompts/bd/``)."""

from functools import lru_cache
from pathlib import Path

PROMPT_VERSION = "1.0.0"

# ai/agents/bd/prompts.py -> parents[2] = ai ; prompts en ai/prompts/bd
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "bd"


@lru_cache
def load_prompt(name: str) -> str:
    """Lee un archivo de prompt de ``ai/prompts/bd/``."""
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_system(dimension_prompt_file: str, context_block: str) -> str:
    """Compone el system prompt: base + rol de la dimensión + bloque de contexto.

    ``context_block`` trae el glosario logístico y las convenciones de BD (con el
    contexto autoritativo del refine antepuesto si aplica), que es donde vive la
    lista cerrada de tipos lógicos.
    """
    base = load_prompt("_base.md")
    dimension = load_prompt(dimension_prompt_file)
    return f"{base}\n\n{dimension}\n\n{context_block}"
