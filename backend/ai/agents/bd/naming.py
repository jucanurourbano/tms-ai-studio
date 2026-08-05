"""Nomenclatura física determinista (identificadores del esquema).

Todo nombre del esquema —tablas, columnas, constraints, índices— sale de aquí y
**no** del LLM. Dos razones: el resultado es reproducible (mismo EF ⇒ mismos
nombres, lo que hace testeable el DDL) y ningún identificador puede exceder el
límite del motor ni traer caracteres que obliguen a comillas.

La pluralización/singularización es **castellana** porque las entidades del EF
vienen en español ("Guia" → "guias", "Siniestro" → "siniestros"). No se busca una
gramática completa: se cubren las reglas regulares y las excepciones se aceptan
como coste conocido (un nombre imperfecto es un detalle cosmético; un
identificador inválido rompe el DDL).
"""

import hashlib
import re
import unicodedata

from ai.knowledge import load_db_conventions, max_identifier_length

#: Vocales sin acento, para decidir la regla de plural.
_VOCALES = "aeiou"


def strip_accents(text: str) -> str:
    """Quita tildes y diacríticos (``guía`` → ``guia``)."""
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def snake(text: str) -> str:
    """Convierte a ``snake_case`` sin acentos ni caracteres especiales.

    Separa también los límites de *camelCase* (``NumeroGuia`` → ``numero_guia``),
    porque el EF mezcla estilos según cómo estuviera redactado el documento.
    """
    clean = strip_accents(text or "").strip()
    clean = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", clean)
    clean = re.sub(r"[^0-9A-Za-z]+", "_", clean)
    return re.sub(r"_+", "_", clean).strip("_").lower()


def pluralize(word: str) -> str:
    """Plural castellano regular de una palabra ya en ``snake_case``.

    Reglas aplicadas: ``-z`` → ``-ces``; vocal → ``+s``; consonante → ``+es``; y
    lo que ya acaba en ``s`` se deja igual (evita ``guiass``). Solo se pluraliza
    la **última** palabra del identificador compuesto.
    """
    if not word:
        return word
    head, _, last = word.rpartition("_")
    if not last:
        return word
    if last.endswith("s"):
        plural = last
    elif last.endswith("z"):
        plural = f"{last[:-1]}ces"
    elif last[-1] in _VOCALES:
        plural = f"{last}s"
    else:
        plural = f"{last}es"
    return f"{head}_{plural}" if head else plural


def singularize(word: str) -> str:
    """Singular castellano aproximado (inverso de :func:`pluralize`)."""
    if not word:
        return word
    head, _, last = word.rpartition("_")
    if not last:
        return word
    if last.endswith("ces"):
        singular = f"{last[:-3]}z"
    elif last.endswith("es") and len(last) > 3:
        singular = last[:-2]
    elif last.endswith("s") and len(last) > 2:
        singular = last[:-1]
    else:
        singular = last
    return f"{head}_{singular}" if head else singular


def truncate_identifier(name: str, engine: str) -> str:
    """Recorta al límite del motor **sin** perder unicidad por el recorte.

    Si el nombre excede el límite se conserva un prefijo legible y se le añade un
    sufijo derivado del nombre completo. Así dos constraints con el mismo prefijo
    largo no acaban colisionando tras el truncado, que es como se producen los
    errores de "duplicate constraint name" en Oracle.

    El sufijo sale de ``sha1`` y **no** de ``hash()``: el hash de Python está
    aleatorizado por proceso (``PYTHONHASHSEED``), así que el mismo EF habría
    generado nombres distintos en cada corrida y el DDL habría dejado de ser
    reproducible.
    """
    limit = max_identifier_length(engine)
    if len(name) <= limit:
        return name
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:4]
    keep = limit - len(digest) - 1
    return f"{name[:keep].rstrip('_')}_{digest}"


def _pattern(key: str, default: str) -> str:
    patterns = (load_db_conventions().get("naming", {}) or {}).get("patterns", {}) or {}
    return patterns.get(key, default)


def table_name(entity_name: str) -> str:
    """Nombre físico de la tabla de una entidad del EF (``Guia`` → ``guias``)."""
    conventions = load_db_conventions().get("naming", {}) or {}
    base = snake(entity_name)
    if conventions.get("tables", "plural") == "plural":
        return pluralize(base)
    return base


def pk_column_name(table_singular: str) -> str:
    """Columna de PK subrogada según el patrón de la casa."""
    conventions = load_db_conventions().get("naming", {}) or {}
    pattern = conventions.get("pk_column", "{table_singular}_id")
    return pattern.format(table_singular=table_singular, table=table_singular)


def fk_column_name(referenced_singular: str) -> str:
    """Columna de FK según el patrón de la casa (``guia`` → ``guia_id``)."""
    conventions = load_db_conventions().get("naming", {}) or {}
    pattern = conventions.get("fk_column", "{referenced_table_singular}_id")
    return pattern.format(
        referenced_table_singular=referenced_singular,
        referenced_table=referenced_singular,
    )


def junction_table_name(table_a: str, table_b: str) -> str:
    """Nombre de la tabla puente de una relación N:M.

    Ordena los dos nombres alfabéticamente **a propósito**: la misma pareja de
    entidades produce el mismo nombre aunque el EF declare la relación en el otro
    sentido, de modo que no se generen dos tablas puente para una sola relación.
    """
    first, second = sorted((table_a, table_b))
    return f"{first}_{second}"


def constraint_name(kind: str, table: str, engine: str, **parts: str) -> str:
    """Nombre de constraint/índice según el patrón de la casa, ya truncado.

    ``kind`` es la clave del patrón (``primary_key``, ``foreign_key``, ``unique``,
    ``check``, ``index``).
    """
    defaults = {
        "primary_key": "pk_{table}",
        "foreign_key": "fk_{table}_{referenced_table}",
        "unique": "uq_{table}_{columns}",
        "check": "ck_{table}_{suffix}",
        "index": "ix_{table}_{columns}",
    }
    pattern = _pattern(kind, defaults.get(kind, "{table}"))
    values = {
        "table": table,
        "referenced_table": parts.get("referenced_table", ""),
        "columns": parts.get("columns", ""),
        "suffix": parts.get("suffix", ""),
    }
    raw = pattern.format(**values)
    return truncate_identifier(snake(raw), engine)


def columns_suffix(columns: list[str]) -> str:
    """Une columnas para el nombre de un índice/unique (``estado_id_fecha``)."""
    return "_".join(snake(c) for c in columns if c)


def is_reserved(name: str) -> bool:
    """``True`` si el identificador es una palabra reservada habitual en SQL."""
    reserved = (load_db_conventions().get("naming", {}) or {}).get(
        "reserved_words", []
    ) or []
    return snake(name) in {snake(w) for w in reserved}
