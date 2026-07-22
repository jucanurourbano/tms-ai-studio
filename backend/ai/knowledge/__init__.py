"""Conocimiento inyectable en los prompts.

- **Glosario logístico** (dominio): términos → definiciones (EF, Scrum, etc.).
- **Stack de la casa** (`tech_stack.yaml`): allow-list por capa que consume el
  nodo STACK del Agente Arquitectura para no proponer exotismos.
"""

from functools import lru_cache
from pathlib import Path

import yaml

_KNOWLEDGE_DIR = Path(__file__).resolve().parent
_GLOSSARY_PATH = _KNOWLEDGE_DIR / "glossary.yaml"
_TECH_STACK_PATH = _KNOWLEDGE_DIR / "tech_stack.yaml"


# --- Glosario logístico ------------------------------------------------------


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


# --- Stack tecnológico de la casa (Agente Arquitectura) ----------------------


@lru_cache
def load_tech_stack() -> dict:
    """Carga el stack estándar de Urbano (allow-list por capa) desde YAML."""
    return yaml.safe_load(_TECH_STACK_PATH.read_text(encoding="utf-8")) or {}


def tech_stack_block() -> str:
    """Renderiza el stack de la casa para inyectar en el prompt de STACK.

    Presenta, por capa, la tecnología por defecto y la lista blanca permitida. El
    agente **solo** puede recomendar tecnologías de estas listas; ante una
    necesidad fuera de ellas, pregunta al Arquitecto (no inventa exotismos).
    """
    data = load_tech_stack()
    layers: dict = data.get("layers", {}) or {}
    status = data.get("status", "desconocido")
    lines = [
        "STACK ESTÁNDAR DE URBANO (allow-list; NO propongas nada fuera de estas "
        f"listas — si falta algo, pregunta al Arquitecto). Estado: {status}.",
    ]
    for layer, cfg in layers.items():
        cfg = cfg or {}
        default = cfg.get("default", "—")
        allowed = ", ".join(cfg.get("allowed", []) or []) or "—"
        lines.append(f"- {layer}: por defecto «{default}»; permitidas: [{allowed}]")
    return "\n".join(lines)
