"""Carga de prompts versionados del Agente EF (ai/prompts/ef/)."""

from functools import lru_cache
from pathlib import Path

PROMPT_VERSION = "1.0.0"

# ai/agents/ef/prompts.py -> parents[2] = ai ; prompts en ai/prompts/ef
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "ef"


@lru_cache
def load_prompt(name: str) -> str:
    """Lee un archivo de prompt de ai/prompts/ef/."""
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_system(dimension_prompt_file: str, glossary_ctx: str) -> str:
    """Compone el system prompt: base + rol de la dimensión + glosario."""
    base = load_prompt("_base.md")
    dimension = load_prompt(dimension_prompt_file)
    return f"{base}\n\n{dimension}\n\n{glossary_ctx}"


def build_user(context: str, text: str) -> str:
    """Compone el mensaje de usuario con el contexto (breadcrumb) y el fragmento."""
    return f"CONTEXTO (breadcrumb): {context}\n\nFRAGMENTO:\n{text}"
