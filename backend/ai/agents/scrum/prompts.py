"""Carga de prompts versionados del Agente Scrum (ai/prompts/scrum/)."""

from functools import lru_cache
from pathlib import Path

PROMPT_VERSION = "1.0.0"

# ai/agents/scrum/prompts.py -> parents[2] = ai ; prompts en ai/prompts/scrum
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "scrum"


@lru_cache
def load_prompt(name: str) -> str:
    """Lee un archivo de prompt de ai/prompts/scrum/."""
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_system(dimension_prompt_file: str, glossary_ctx: str) -> str:
    """Compone el system prompt: base + rol de la dimensión + glosario."""
    base = load_prompt("_base.md")
    dimension = load_prompt(dimension_prompt_file)
    return f"{base}\n\n{dimension}\n\n{glossary_ctx}"
