"""Conocimiento inyectable en los prompts.

- **Glosario logístico** (dominio): términos → definiciones (EF, Scrum, etc.).
- **Stack de la casa** (`tech_stack.yaml`): allow-list por capa que consume el
  nodo STACK del Agente Arquitectura para no proponer exotismos.
- **Convenciones de BD** (`db_conventions.yaml`): naming, claves, auditoría y el
  **mapa de tipos por motor** que consume el Agente BD. Doble uso: los bloques
  de naming/claves se inyectan en los prompts, mientras que `types`/`identity`
  son contrato del renderizador de DDL en Python (el LLM nunca escribe SQL).
"""

from functools import lru_cache
from pathlib import Path

import yaml

_KNOWLEDGE_DIR = Path(__file__).resolve().parent
_GLOSSARY_PATH = _KNOWLEDGE_DIR / "glossary.yaml"
_TECH_STACK_PATH = _KNOWLEDGE_DIR / "tech_stack.yaml"
_DB_CONVENTIONS_PATH = _KNOWLEDGE_DIR / "db_conventions.yaml"


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


# --- Convenciones de base de datos (Agente BD) -------------------------------

#: Motores relacionales soportados por el mapa de tipos (los de `tech_stack`).
DB_ENGINES = ("postgresql", "sqlserver", "oracle", "mysql")


@lru_cache
def load_db_conventions() -> dict:
    """Carga las convenciones de modelado físico de BD desde YAML."""
    return yaml.safe_load(_DB_CONVENTIONS_PATH.read_text(encoding="utf-8")) or {}


@lru_cache
def engine_type_map(engine: str) -> dict[str, str]:
    """Mapa ``logical_type`` → tipo físico **de ese motor**.

    Es el contrato del renderizador de DDL: el LLM elige el ``logical_type`` de un
    enum cerrado y esta tabla lo traduce. Un ``logical_type`` ausente aquí es un
    error de programación (el enum y el YAML deben ir a la par), no un caso a
    adivinar en tiempo de ejecución.
    """
    types: dict = load_db_conventions().get("types", {}) or {}
    return {
        logical: (per_engine or {})[engine]
        for logical, per_engine in types.items()
        if engine in (per_engine or {})
    }


@lru_cache
def identity_clause(engine: str) -> str:
    """Cláusula de columna autoincremental del motor (PK subrogada)."""
    return (load_db_conventions().get("identity", {}) or {}).get(engine, "")


@lru_cache
def default_schema(engine: str) -> str:
    """Esquema por defecto del motor (``public``/``dbo``; vacío si no aplica)."""
    return (load_db_conventions().get("schema", {}) or {}).get(engine) or ""


@lru_cache
def max_identifier_length(engine: str) -> int:
    """Largo máximo de identificador del motor (para truncar de forma segura)."""
    limits = (load_db_conventions().get("naming", {}) or {}).get(
        "max_identifier_length", {}
    ) or {}
    return int(limits.get(engine, 63))


@lru_cache
def type_synonyms() -> dict[str, tuple[str, ...]]:
    """Sinónimos en español del EF → ``logical_type`` (normalización de tipos)."""
    raw: dict = load_db_conventions().get("type_synonyms", {}) or {}
    return {logical: tuple(words or ()) for logical, words in raw.items()}


def db_conventions_block(engine: str) -> str:
    """Renderiza las convenciones de BD para inyectar en los prompts del Agente BD.

    Incluye SOLO lo que el LLM debe respetar al nombrar y decidir (naming, claves,
    auditoría, defaults y los ``logical_type`` admitidos). El mapa de tipos físicos
    **no** se inyecta a propósito: el modelo no escribe SQL, elige un tipo lógico
    y Python lo traduce (así no puede colar sintaxis de otro motor).
    """
    data = load_db_conventions()
    naming = data.get("naming", {}) or {}
    keys = data.get("keys", {}) or {}
    audit = data.get("audit", {}) or {}
    defaults = data.get("defaults", {}) or {}
    logical_types = ", ".join((data.get("types", {}) or {}).keys()) or "—"
    decimal = defaults.get("decimal", {}) or {}
    lines = [
        "CONVENCIONES DE BASE DE DATOS DE URBANO (son obligatorias; no improvises "
        f"otro estilo). Estado: {data.get('status', 'desconocido')}.",
        f"- Motor destino: {engine}.",
        f"- Nomenclatura: {naming.get('case', 'snake_case')}; "
        f"tablas en {naming.get('tables', 'plural')}.",
        f"- PK: patrón «{naming.get('pk_column', '{table_singular}_id')}», "
        f"estrategia {keys.get('pk_strategy', 'surrogate_identity')}.",
        f"- FK: patrón «{naming.get('fk_column', '{referenced_table_singular}_id')}»; "
        f"por defecto ON DELETE {keys.get('default_on_delete', 'restrict')}.",
        (
            "- Clave natural evidente: además de la PK subrogada, declárala UNIQUE."
            if keys.get("natural_key_as_unique")
            else "- No se declaran claves naturales como UNIQUE."
        ),
        f"- Columnas de auditoría disponibles: "
        f"{', '.join(c['name'] for c in audit.get('columns', []) or [])}. "
        "Se añaden SOLO si la arquitectura declaró auditoría como transversal.",
        f"- Baja lógica: {'sí' if audit.get('soft_delete') else 'no'} por defecto.",
        f"- Defaults si el EF no precisa: string({defaults.get('string_length')}), "
        f"decimal({decimal.get('precision')},{decimal.get('scale')}).",
        f"- TIPOS LÓGICOS ADMITIDOS (enum cerrado, NO escribas tipos SQL): "
        f"{logical_types}.",
        "- Si no puedes deducir el tipo de un campo, márcalo como ambiguo y "
        "pregunta al DBA. PROHIBIDO adivinar.",
    ]
    return "\n".join(lines)
