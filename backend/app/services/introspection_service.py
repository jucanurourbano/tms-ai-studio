"""Introspección **read-only** de un PostgreSQL externo → activo ``db_schema``.

Esto se conecta a bases de datos de PRODUCCIÓN de la organización. Es, con
diferencia, la capacidad más peligrosa del módulo, así que está construida
fail-closed en cuatro capas independientes:

1. **El cliente NUNCA envía una cadena de conexión.** Envía un *alias* que debe
   existir en ``INVENTORY_INTROSPECTION_DSNS`` (settings/``.env``). Si el alias
   viniera del cliente como DSN, cualquiera con permiso de escritura podría
   apuntar el servidor a un host arbitrario — un SSRF de manual. Con alias, el
   conjunto de destinos posibles lo fija quien despliega, no quien llama.
2. **Allowlist de hosts.** El host resuelto del alias debe estar en
   ``INVENTORY_INTROSPECTION_ALLOWED_HOSTS``. Sin allowlist configurada NO se
   conecta a nada: la lista vacía significa "nada autorizado", no "todo".
3. **Solo lectura, impuesto en el servidor.** La sesión se abre con
   ``default_transaction_read_only=on`` y dentro de una transacción ``READ ONLY``.
   No se depende de que las consultas "sean SELECT": el propio Postgres rechaza
   cualquier escritura, incluida la que pudiera colarse por un error futuro.
4. **La credencial nunca sale.** Ni en la respuesta de la API, ni en el
   ``origin_ref`` del activo, ni en un log: todo lo que se expone pasa por
   :func:`redact_dsn`.

La cadena se guarda en la configuración del despliegue, jamás en la base de datos
de la plataforma ni en el artefacto.
"""

import re
from typing import Any, Optional
from urllib.parse import urlparse

from app.config.settings import settings
from app.errors import ConflictError, ForbiddenError, NotFoundError

#: Esquemas de sistema que nunca describen el negocio.
_SCHEMAS_DE_SISTEMA = ("pg_catalog", "information_schema", "pg_toast")

#: Tipo físico de Postgres -> ``logical_type`` del Agente BD. Mismo criterio que
#: en el lector de DDL: lo que no esté aquí queda en ``None``, no se adivina.
_LOGICAL_BY_PG_TYPE: dict[str, str] = {
    "character varying": "string",
    "character": "string",
    "varchar": "string",
    "bpchar": "string",
    "text": "text",
    "smallint": "integer",
    "integer": "integer",
    "bigint": "bigint",
    "numeric": "decimal",
    "money": "decimal",
    "real": "decimal",
    "double precision": "decimal",
    "boolean": "boolean",
    "date": "date",
    "time without time zone": "time",
    "time with time zone": "time",
    "timestamp without time zone": "timestamp",
    "timestamp with time zone": "timestamptz",
    "uuid": "uuid",
    "json": "json",
    "jsonb": "json",
    "bytea": "binary",
}


def redact_dsn(dsn: str) -> str:
    """Devuelve el DSN sin credenciales, apto para logs y respuestas."""
    return re.sub(r"//[^/@]*@", "//***@", dsn or "")


def _host_of(dsn: str) -> str:
    """Host del DSN (sin puerto). Cadena vacía si no se puede determinar."""
    try:
        return (urlparse(dsn).hostname or "").lower()
    except ValueError:
        return ""


def available_sources() -> list[dict[str, str]]:
    """Orígenes configurados que además superan la allowlist.

    Solo alias y host redactado: la API nunca devuelve una cadena de conexión.
    Un alias configurado pero NO autorizado no se lista, para que el panel no
    ofrezca un botón que siempre va a fallar.
    """
    if not settings.INVENTORY_INTROSPECTION_ENABLED:
        return []
    permitidos = {h.lower() for h in settings.INVENTORY_INTROSPECTION_ALLOWED_HOSTS}
    return [
        {"alias": alias, "host": _host_of(dsn)}
        for alias, dsn in settings.INVENTORY_INTROSPECTION_DSNS.items()
        if _host_of(dsn) in permitidos
    ]


def assert_source_authorized(alias: str) -> str:
    """Resuelve el alias a su DSN comprobando TODAS las guardas. Fail-closed.

    Devuelve el DSN; lanza ``ForbiddenError``/``NotFoundError`` si algo no cuadra.
    Nunca incluye la credencial en el mensaje de error.
    """
    if not settings.INVENTORY_INTROSPECTION_ENABLED:
        raise ForbiddenError(
            "La introspección de bases de datos externas está desactivada. "
            "Actívala con INVENTORY_INTROSPECTION_ENABLED en la configuración del "
            "despliegue."
        )

    permitidos = {h.lower() for h in settings.INVENTORY_INTROSPECTION_ALLOWED_HOSTS}
    if not permitidos:
        raise ForbiddenError(
            "No hay ningún host autorizado para introspección "
            "(INVENTORY_INTROSPECTION_ALLOWED_HOSTS está vacía). Sin allowlist no "
            "se conecta a ninguna base de datos."
        )

    dsn = settings.INVENTORY_INTROSPECTION_DSNS.get(alias)
    if not dsn:
        raise NotFoundError(
            f"No hay ningún origen de introspección llamado «{alias}». Los orígenes "
            "se declaran en la configuración del despliegue, no desde la API."
        )

    host = _host_of(dsn)
    if host not in permitidos:
        raise ForbiddenError(
            f"El host «{host}» del origen «{alias}» no está en la allowlist de "
            "introspección. Añádelo explícitamente si debe consultarse."
        )
    return dsn


# --- Consultas al catálogo (todas de solo lectura) ---------------------------

_SQL_COLUMNS = """
SELECT c.table_name, c.column_name, c.data_type, c.is_nullable,
       c.column_default, c.character_maximum_length,
       c.numeric_precision, c.numeric_scale, c.ordinal_position
  FROM information_schema.columns c
  JOIN information_schema.tables t
    ON t.table_schema = c.table_schema AND t.table_name = c.table_name
 WHERE c.table_schema = $1 AND t.table_type = 'BASE TABLE'
 ORDER BY c.table_name, c.ordinal_position
"""

_SQL_CONSTRAINTS = """
SELECT tc.constraint_name, tc.table_name, tc.constraint_type,
       kcu.column_name, kcu.ordinal_position,
       ccu.table_name  AS referenced_table,
       ccu.column_name AS referenced_column,
       rc.delete_rule
  FROM information_schema.table_constraints tc
  LEFT JOIN information_schema.key_column_usage kcu
         ON kcu.constraint_name = tc.constraint_name
        AND kcu.table_schema = tc.table_schema
  LEFT JOIN information_schema.referential_constraints rc
         ON rc.constraint_name = tc.constraint_name
        AND rc.constraint_schema = tc.table_schema
  LEFT JOIN information_schema.constraint_column_usage ccu
         ON ccu.constraint_name = tc.constraint_name
        AND ccu.table_schema = tc.table_schema
       AND tc.constraint_type = 'FOREIGN KEY'
 WHERE tc.table_schema = $1
   AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')
 ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position
"""

_SQL_CHECKS = """
SELECT tc.table_name, tc.constraint_name, cc.check_clause
  FROM information_schema.table_constraints tc
  JOIN information_schema.check_constraints cc
    ON cc.constraint_name = tc.constraint_name
   AND cc.constraint_schema = tc.table_schema
 WHERE tc.table_schema = $1 AND tc.constraint_type = 'CHECK'
   AND cc.check_clause NOT LIKE '%IS NOT NULL'
 ORDER BY tc.table_name, tc.constraint_name
"""

_SQL_INDEXES = """
SELECT tablename, indexname, indexdef
  FROM pg_indexes
 WHERE schemaname = $1
 ORDER BY tablename, indexname
"""

_SQL_COMMENTS = """
SELECT c.relname AS table_name, a.attname AS column_name,
       obj_description(c.oid) AS table_comment,
       col_description(c.oid, a.attnum) AS column_comment
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0
 WHERE n.nspname = $1 AND c.relkind = 'r'
"""


def _physical_type(row: Any) -> str:
    """Reconstruye el tipo con su longitud/precisión, como se declaró."""
    base = row["data_type"]
    if row["character_maximum_length"]:
        return f"{base}({row['character_maximum_length']})"
    if base == "numeric" and row["numeric_precision"]:
        escala = row["numeric_scale"] or 0
        return f"numeric({row['numeric_precision']},{escala})"
    return base


def _build_content(
    columnas: list, constraints: list, checks: list, indices: list, comentarios: list
) -> dict[str, Any]:
    """Compone el ``DbSchemaContent`` desde las filas del catálogo."""
    tablas: dict[str, dict[str, Any]] = {}

    for row in columnas:
        tabla = tablas.setdefault(
            row["table_name"],
            {
                "name": row["table_name"],
                "schema_name": None,
                "comment": None,
                "columns": [],
                "primary_key": [],
                "foreign_keys": [],
                "constraints": [],
                "indexes": [],
            },
        )
        tabla["columns"].append(
            {
                "name": row["column_name"],
                "type": _physical_type(row),
                "logical_type": _LOGICAL_BY_PG_TYPE.get(row["data_type"]),
                "nullable": row["is_nullable"] == "YES",
                "default": row["column_default"],
                "primary_key": False,
                "comment": None,
            }
        )

    # PK / FK / UNIQUE. Las filas vienen desnormalizadas (una por columna).
    agrupadas: dict[tuple, dict[str, Any]] = {}
    for row in constraints:
        tabla = tablas.get(row["table_name"])
        if tabla is None:
            continue
        clave = (row["table_name"], row["constraint_name"], row["constraint_type"])
        grupo = agrupadas.setdefault(
            clave,
            {
                "columns": [],
                "referenced_table": row["referenced_table"],
                "referenced_columns": [],
                "delete_rule": row["delete_rule"],
            },
        )
        if row["column_name"] and row["column_name"] not in grupo["columns"]:
            grupo["columns"].append(row["column_name"])
        if row["referenced_column"] and (
            row["referenced_column"] not in grupo["referenced_columns"]
        ):
            grupo["referenced_columns"].append(row["referenced_column"])

    for (nombre_tabla, nombre, tipo), grupo in agrupadas.items():
        tabla = tablas[nombre_tabla]
        if tipo == "PRIMARY KEY":
            tabla["primary_key"] = grupo["columns"]
            for columna in tabla["columns"]:
                if columna["name"] in grupo["columns"]:
                    columna["primary_key"] = True
        elif tipo == "FOREIGN KEY":
            tabla["foreign_keys"].append(
                {
                    "name": nombre,
                    "columns": grupo["columns"],
                    "referenced_table": grupo["referenced_table"] or "",
                    "referenced_columns": grupo["referenced_columns"],
                    "on_delete": (grupo["delete_rule"] or "").lower() or None,
                }
            )
        elif tipo == "UNIQUE":
            tabla["constraints"].append(
                {
                    "kind": "unique",
                    "name": nombre,
                    "columns": grupo["columns"],
                    "expression": None,
                }
            )

    for row in checks:
        tabla = tablas.get(row["table_name"])
        if tabla is not None:
            tabla["constraints"].append(
                {
                    "kind": "check",
                    "name": row["constraint_name"],
                    "columns": [],
                    "expression": row["check_clause"],
                }
            )

    for row in indices:
        tabla = tablas.get(row["tablename"])
        if tabla is None:
            continue
        definicion = row["indexdef"] or ""
        dentro = definicion[definicion.find("(") + 1 : definicion.rfind(")")]
        tabla["indexes"].append(
            {
                "name": row["indexname"],
                "columns": [
                    c.strip().strip('"') for c in dentro.split(",") if c.strip()
                ],
                "unique": "UNIQUE INDEX" in definicion.upper(),
            }
        )

    for row in comentarios:
        tabla = tablas.get(row["table_name"])
        if tabla is None:
            continue
        if row["table_comment"]:
            tabla["comment"] = row["table_comment"]
        if row["column_comment"] and row["column_name"]:
            for columna in tabla["columns"]:
                if columna["name"] == row["column_name"]:
                    columna["comment"] = row["column_comment"]

    return {"engine": "postgresql", "tables": list(tablas.values())}


async def introspect_postgres(dsn: str, *, schema: str = "public") -> dict[str, Any]:
    """Lee el catálogo de un PostgreSQL externo y devuelve el ``db_schema``.

    Abre la conexión en modo **solo lectura a nivel de servidor**: aunque alguien
    introdujera por error una sentencia de escritura en este módulo, Postgres la
    rechazaría. La garantía no depende de revisar el SQL de arriba.
    """
    if schema in _SCHEMAS_DE_SISTEMA:
        raise ConflictError(
            f"El esquema «{schema}» es del sistema y no describe el negocio."
        )

    import asyncpg

    # El DSN de la app viene con el driver de SQLAlchemy; asyncpg quiere el crudo.
    crudo = dsn.replace("postgresql+asyncpg://", "postgresql://")
    try:
        conexion = await asyncpg.connect(
            crudo,
            timeout=15,
            server_settings={"default_transaction_read_only": "on"},
        )
    except Exception as exc:
        raise ConflictError(
            f"No se pudo conectar al origen ({redact_dsn(crudo)}): "
            f"{type(exc).__name__}."
        ) from exc

    try:
        async with conexion.transaction(readonly=True):
            columnas = await conexion.fetch(_SQL_COLUMNS, schema)
            constraints = await conexion.fetch(_SQL_CONSTRAINTS, schema)
            checks = await conexion.fetch(_SQL_CHECKS, schema)
            indices = await conexion.fetch(_SQL_INDEXES, schema)
            comentarios = await conexion.fetch(_SQL_COMMENTS, schema)
    finally:
        await conexion.close()

    if not columnas:
        raise ConflictError(
            f"El esquema «{schema}» no tiene tablas (o el usuario no puede verlas)."
        )
    return _build_content(columnas, constraints, checks, indices, comentarios)


def origin_ref_for(alias: str, dsn: str, schema: str) -> Optional[str]:
    """Referencia de origen legible y **sin credenciales** para el activo."""
    return f"introspección {alias} ({_host_of(dsn)}/{schema})"
