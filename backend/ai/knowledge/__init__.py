"""Conocimiento inyectable en los prompts.

- **Glosario logístico** (dominio): términos → definiciones (EF, Scrum, etc.).
- **Stack de la casa** (`tech_stack.yaml`): allow-list por capa que consume el
  nodo STACK del Agente Arquitectura para no proponer exotismos.
- **Convenciones de BD** (`db_conventions.yaml`): naming, claves, auditoría y el
  **mapa de tipos por motor** que consume el Agente BD. Doble uso: los bloques
  de naming/claves se inyectan en los prompts, mientras que `types`/`identity`
  son contrato del renderizador de DDL en Python (el LLM nunca escribe SQL).
- **Convenciones de API** (`api_conventions.yaml`): rutas, propiedades, envelope,
  errores y paginación que consume el Agente API. Mismo doble uso y misma regla
  rectora: `paths`/`properties`/`exposure` se inyectan en los prompts, mientras
  que `types`/`errors`/`envelope`/`security` son contrato del renderizador de
  OpenAPI (el LLM nunca escribe YAML ni JSON Schema).
"""

from functools import lru_cache
from pathlib import Path

import yaml

_KNOWLEDGE_DIR = Path(__file__).resolve().parent
_GLOSSARY_PATH = _KNOWLEDGE_DIR / "glossary.yaml"
_TECH_STACK_PATH = _KNOWLEDGE_DIR / "tech_stack.yaml"
_DB_CONVENTIONS_PATH = _KNOWLEDGE_DIR / "db_conventions.yaml"
_API_CONVENTIONS_PATH = _KNOWLEDGE_DIR / "api_conventions.yaml"


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


@lru_cache
def tech_stack_sources() -> dict[str, dict]:
    """Documentos que respaldan las capas validadas (clave → ficha)."""
    return dict(load_tech_stack().get("sources", {}) or {})


@lru_cache
def house_architecture_style() -> dict:
    """Estilo arquitectónico de la casa (**sesga** el default, no lo sustituye).

    Vive fuera de ``layers`` a propósito: el Agente Arquitectura ya decide el
    estilo como ciudadano de primera clase (``architecture_style`` respaldado por
    ADR-001 y por el perfil de alcance determinista). Esto es conocimiento de la
    casa que inclina ese default hacia el destino del programa de modernización;
    si el agente se aparta, debe justificarlo en su ADR.

    Devuelve ``{}`` si el archivo no declara el bloque, para que quien llame
    conserve su heurística previa en vez de romperse.
    """
    return dict(load_tech_stack().get("architecture", {}) or {})


def tech_stack_block() -> str:
    """Renderiza el stack de la casa para inyectar en el prompt de STACK.

    Presenta, por capa, la tecnología por defecto y la lista blanca permitida. El
    agente **solo** puede recomendar tecnologías de estas listas; ante una
    necesidad fuera de ellas, pregunta al Arquitecto (no inventa exotismos).

    Las capas ya confirmadas por el equipo se marcan como VALIDADA: el agente debe
    saber que apartarse de ellas no es una preferencia, es una excepción que hay
    que justificar. El servicio gestionado (``managed_service``), cuando existe,
    viaja junto al motor porque cambia las opciones de despliegue sin cambiar el
    dialecto.

    NO se incluye el estilo arquitectónico: no es una entrada del ``stack[]`` y
    mostrarlo aquí invitaría al modelo a rellenarlo como si lo fuera.
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
        linea = f"- {layer}: por defecto «{default}»; permitidas: [{allowed}]"
        if cfg.get("managed_service"):
            linea += f"; servicio gestionado: {cfg['managed_service']}"
        if cfg.get("validated"):
            linea += " (VALIDADA por el equipo)"
        lines.append(linea)
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


# --- Convenciones de API (Agente API) ----------------------------------------


@lru_cache
def load_api_conventions() -> dict:
    """Carga las convenciones de diseño de APIs REST desde YAML."""
    return yaml.safe_load(_API_CONVENTIONS_PATH.read_text(encoding="utf-8")) or {}


@lru_cache
def openapi_type(logical_type: str) -> dict[str, str]:
    """Tipo del esquema OpenAPI 3.1 para un ``logical_type`` del Agente BD.

    Es el contrato del renderizador, análogo a ``engine_type_map`` en BD: el tipo
    lo decidió el modelo de datos y aquí solo se traduce, sin volver a preguntarle
    al LLM. Un ``logical_type`` ausente es un error de programación (el enum del BD
    y este mapa deben ir a la par, y hay un test que lo verifica).

    Los decimales respetan ``properties.decimal_as_string``: viajan como cadena
    para no perder precisión con el número de coma flotante de JavaScript.
    """
    data = load_api_conventions()
    types: dict = data.get("types", {}) or {}
    if logical_type == "decimal" and not (data.get("properties", {}) or {}).get(
        "decimal_as_string", True
    ):
        return dict(types.get("decimal_numeric", {}) or {})
    return dict(types.get(logical_type, {}) or {})


@lru_cache
def api_error_catalog() -> tuple[dict, ...]:
    """Catálogo estándar de errores (contrato del renderizador)."""
    errors: dict = load_api_conventions().get("errors", {}) or {}
    return tuple(errors.get("catalog", []) or [])


@lru_cache
def api_error(error_id: str) -> dict:
    """Entrada del catálogo por id (``ERR-409``…); ``{}`` si no existe."""
    return next((e for e in api_error_catalog() if e.get("id") == error_id), {})


@lru_cache
def constraint_error_id(constraint_kind: str) -> str:
    """Error que corresponde a la violación de una constraint del modelo.

    Traduce ``unique``/``check``/``not_null``/``foreign_key`` al error del
    catálogo. Los códigos de estado **no los decide el LLM**: salen de aquí.
    """
    mapa: dict = (load_api_conventions().get("errors", {}) or {}).get(
        "constraint_status", {}
    ) or {}
    return mapa.get(constraint_kind, "ERR-422")


@lru_cache
def success_status(endpoint_kind: str) -> int:
    """Código de éxito del tipo de operación (semántica HTTP, no opinión)."""
    mapa: dict = load_api_conventions().get("success_status", {}) or {}
    return int(mapa.get(endpoint_kind, 200))


@lru_cache
def security_scheme_for(provider: str) -> str:
    """Esquema de seguridad que corresponde al proveedor de ``tech_stack.auth``.

    Un proveedor desconocido cae al esquema por defecto; quien llama decide si eso
    merece una pregunta (aquí no se inventa nada, solo se traduce lo conocido).
    """
    security: dict = load_api_conventions().get("security", {}) or {}
    mapa: dict = security.get("provider_scheme", {}) or {}
    return mapa.get(provider or "", security.get("default_scheme", "bearer_jwt"))


@lru_cache
def exposure_for(table_kind: str) -> tuple[str, str]:
    """Exposición por defecto de una tabla según su naturaleza, **con motivo**.

    Devuelve ``(exposure, reason)``. El motivo es obligatorio en todo lo que no sea
    ``crud``: una tabla que no se publica debe decir por qué, o la exclusión sería
    una omisión muda (API12).
    """
    exposure: dict = load_api_conventions().get("exposure", {}) or {}
    valor = exposure.get(table_kind, "crud")
    razon = (exposure.get("reasons", {}) or {}).get(table_kind, "")
    return valor, razon


def api_conventions_block() -> str:
    """Renderiza las convenciones de API para inyectar en los prompts del Agente API.

    Incluye SOLO lo que el LLM debe respetar al nombrar y decidir. **No** se
    inyectan el mapa de tipos, el envelope, el catálogo de errores ni los esquemas
    de seguridad: eso lo aplica el renderizador en Python. Es la misma salvaguarda
    que en BD, donde el bloque nunca muestra sintaxis SQL: si enseñara la forma del
    documento, el modelo podría intentar escribirlo.
    """
    data = load_api_conventions()
    paths = data.get("paths", {}) or {}
    props = data.get("properties", {}) or {}
    page = data.get("pagination", {}) or {}
    filtering = data.get("filtering", {}) or {}
    sorting = data.get("sorting", {}) or {}
    exposure = data.get("exposure", {}) or {}
    lines = [
        "CONVENCIONES DE API DE URBANO (son obligatorias; no improvises otro "
        f"estilo). Estado: {data.get('status', 'desconocido')}.",
        f"- Rutas: dominio en {'español' if paths.get('language') == 'es' else 'inglés'}, "
        f"{paths.get('case', 'kebab-case')}, recursos en "
        f"{paths.get('number', 'plural')}, bajo el prefijo "
        f"«{paths.get('prefix', '/api/v1')}». Los parámetros de protocolo "
        "(limit, offset, sort) van SIEMPRE en inglés.",
        "- Los nombres de recurso espejan las tablas del modelo de datos: no los "
        "traduzcas ni los renombres.",
        f"- Actualización parcial con {paths.get('update_verb', 'PATCH')}; "
        f"anidamiento máximo {paths.get('max_nesting', 1)} nivel "
        "(más profundo → recurso de primer nivel con filtro).",
        "- Acciones de negocio: verbo en infinitivo y en español al final de la "
        "ruta del recurso (por ejemplo «cerrar», «anular»). SOLO si un proceso o "
        "una regla del EF la respalda, citando la evidencia.",
        f"- Propiedades del cuerpo en {props.get('case', 'snake_case')}, con el "
        "MISMO nombre que la columna del modelo de datos.",
        f"- Listados paginados con «{page.get('limit_param', 'limit')}» "
        f"(por defecto {page.get('default_limit', 20)}, máximo "
        f"{page.get('max_limit', 100)}) y «{page.get('offset_param', 'offset')}».",
        f"- Orden con «{sorting.get('param', 'sort')}» y prefijo "
        f"«{sorting.get('descending_prefix', '-')}» para descendente.",
        "- FILTROS Y ORDEN: solo sobre columnas indexadas, PK, FK o de enumeración. "
        "Un filtro sin índice es una consulta lenta en producción; si hace falta "
        "otro, pídelo como índice al modelo de datos, no lo expongas.",
        "- Exposición por naturaleza de la tabla: "
        + "; ".join(
            f"{kind} → {value}" for kind, value in exposure.items() if kind != "reasons"
        )
        + ". Toda exclusión debe llevar su motivo escrito.",
        "- PROHIBIDO escribir YAML, JSON Schema u OpenAPI: eso lo genera Python. "
        "Tú decides la semántica.",
        "- PROHIBIDO inventar recursos, endpoints o campos: el conjunto te llega "
        "cerrado desde el modelo de datos y el EF. Si falta algo, PREGUNTA.",
    ]
    return "\n".join(lines)
