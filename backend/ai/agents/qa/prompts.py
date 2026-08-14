"""Carga de prompts versionados del Agente QA (``ai/prompts/qa/``)."""

from functools import lru_cache
from pathlib import Path

PROMPT_VERSION = "1.0.0"

# ai/agents/qa/prompts.py -> parents[2] = ai ; prompts en ai/prompts/qa
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "qa"


@lru_cache
def load_prompt(name: str) -> str:
    """Lee un archivo de prompt de ``ai/prompts/qa/``."""
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_system(dimension_prompt_file: str, context_block: str) -> str:
    """Compone el system prompt: base + rol del nodo + bloque de contexto.

    ``context_block`` trae el glosario logístico (con el contexto autoritativo del
    refine antepuesto si aplica). Nunca lleva el artefacto completo: el modelo
    trabaja sobre **un** criterio por llamada, y lo que no ve no lo puede reasignar.
    """
    base = load_prompt("_base.md")
    rol = load_prompt(dimension_prompt_file)
    return f"{base}\n\n---\n\n{rol}\n\n---\n\n{context_block}"
