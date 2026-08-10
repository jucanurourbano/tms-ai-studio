"""Renderizado determinista del DDL desde el modelo físico.

Mismo modelo + mismo motor ⇒ **mismo SQL, carácter a carácter**. Eso es lo que
permite testear el DDL sin ejecutarlo y regenerarlo para otro motor sin volver a
llamar al LLM (decisión DB2: el tipo lógico es neutro y aquí se traduce).

Dos decisiones de forma que evitan clases enteras de error:

1. **Las claves foráneas van en un script aparte** (``ALTER TABLE ADD CONSTRAINT``),
   no dentro del ``CREATE TABLE``. Así el orden de creación deja de importar y un
   ciclo de referencias entre tablas no puede impedir que el esquema se cree. Las
   tablas se siguen emitiendo en orden topológico porque se lee mejor, pero la
   corrección ya no depende de ello.
2. **Los identificadores se entrecomillan solo si hace falta** (palabra reservada).
   Un esquema lleno de comillas es correcto pero incómodo de leer y de teclear;
   uno sin comillas donde hacían falta, no arranca.
"""

from typing import Any, Optional

from ai.knowledge import default_schema, engine_type_map, identity_clause

from ..naming import is_reserved
from ..schemas.enums import DdlScriptKind, LogicalType

#: Cómo se cita un identificador que colisiona con una palabra reservada.
_QUOTES = {
    "postgresql": ('"', '"'),
    "oracle": ('"', '"'),
    "sqlserver": ("[", "]"),
    "mysql": ("`", "`"),
}

#: Literal booleano por motor (no todos tienen tipo BOOLEAN nativo).
_BOOL_LITERALS = {
    "postgresql": {"true": "TRUE", "false": "FALSE"},
    "oracle": {"true": "1", "false": "0"},
    "sqlserver": {"true": "1", "false": "0"},
    "mysql": {"true": "1", "false": "0"},
}

#: Acciones referenciales → cláusula SQL. ``no_action`` se omite (es el default).
_ACTIONS = {
    "cascade": "CASCADE",
    "restrict": "RESTRICT",
    "set_null": "SET NULL",
    "no_action": "NO ACTION",
}


def quote(identifier: str, engine: str) -> str:
    """Entrecomilla el identificador solo si es palabra reservada."""
    if not is_reserved(identifier):
        return identifier
    left, right = _QUOTES.get(engine, ('"', '"'))
    return f"{left}{identifier}{right}"


def qualified(table: dict, engine: str) -> str:
    """Nombre de tabla con su esquema, si el motor lo usa."""
    schema = table.get("schema_name") or default_schema(engine)
    name = quote(table["name"], engine)
    return f"{quote(schema, engine)}.{name}" if schema else name


def render_type(column: dict, engine: str) -> str:
    """Traduce el ``logical_type`` de una columna al tipo físico del motor.

    Es el corazón de DB2: el modelo eligió un tipo lógico de un enum cerrado y aquí
    —y solo aquí— se convierte en sintaxis de un motor concreto.
    """
    logical = column["logical_type"]
    plantilla = engine_type_map(engine).get(logical)
    if plantilla is None:  # pragma: no cover - lo impide el test de invariante
        raise KeyError(f"El motor {engine} no tiene tipo para «{logical}»")
    return plantilla.format(
        length=column.get("length") or 100,
        precision=column.get("precision") or 12,
        scale=column.get("scale") if column.get("scale") is not None else 2,
    )


def render_default(column: dict, engine: str) -> Optional[str]:
    """Cláusula ``DEFAULT`` de la columna, normalizada al motor.

    Los booleanos son el caso incómodo: ``TRUE`` solo existe en PostgreSQL, así que
    un default ``true`` se traduce a ``1`` donde el tipo se representa numérico.
    """
    default = column.get("default")
    if default is None or str(default).strip() == "":
        return None
    literal = str(default).strip()
    if column["logical_type"] == LogicalType.BOOLEAN.value:
        clave = literal.lower()
        if clave in ("true", "false"):
            return _BOOL_LITERALS.get(engine, _BOOL_LITERALS["postgresql"])[clave]
    return literal


def render_column(column: dict, engine: str) -> str:
    """Una línea de definición de columna dentro del ``CREATE TABLE``."""
    partes = [quote(column["name"], engine), render_type(column, engine)]
    if column.get("is_primary_key") and column.get("is_generated"):
        clausula = identity_clause(engine)
        if clausula:
            partes.append(clausula)
    if not column.get("nullable", True):
        partes.append("NOT NULL")
    default = render_default(column, engine)
    if default is not None:
        partes.append(f"DEFAULT {default}")
    return " ".join(partes)


def _fk_clause(fk: dict, tables_by_name: dict, engine: str) -> str:
    """Cuerpo de una FK, común al ``ALTER TABLE`` y a la versión en línea."""
    destino = tables_by_name.get(fk["references_table"])
    destino_sql = (
        qualified(destino, engine)
        if destino is not None
        else quote(fk["references_table"], engine)
    )
    columnas = ", ".join(quote(c, engine) for c in fk["columns"])
    referencias = ", ".join(quote(c, engine) for c in fk["references_columns"])
    sql = (
        f"CONSTRAINT {quote(fk['name'], engine)} "
        f"FOREIGN KEY ({columnas}) REFERENCES {destino_sql} ({referencias})"
    )
    on_delete = _ACTIONS.get(fk.get("on_delete", "no_action"), "NO ACTION")
    if on_delete != "NO ACTION":
        sql += f" ON DELETE {on_delete}"
    on_update = _ACTIONS.get(fk.get("on_update", "no_action"), "NO ACTION")
    if on_update != "NO ACTION":
        sql += f" ON UPDATE {on_update}"
    return sql


def render_create_table(
    table: dict,
    engine: str,
    tables_by_name: Optional[dict] = None,
    inline_foreign_keys: bool = False,
) -> str:
    """``CREATE TABLE`` con columnas, PK, UNIQUE y CHECK.

    Las claves foráneas van **fuera** por defecto (script propio de ``ALTER TABLE``),
    para que el orden de creación no importe. ``inline_foreign_keys`` las mete en la
    definición: lo necesita la prueba de humo contra SQLite, que no soporta
    ``ALTER TABLE ADD CONSTRAINT``.
    """
    lineas = [f"  {render_column(c, engine)}" for c in table.get("columns", [])]

    pk = table.get("primary_key")
    if pk and pk.get("columns"):
        columnas = ", ".join(quote(c, engine) for c in pk["columns"])
        lineas.append(
            f"  CONSTRAINT {quote(pk['name'], engine)} PRIMARY KEY ({columnas})"
        )
    for uq in table.get("unique_constraints", []):
        columnas = ", ".join(quote(c, engine) for c in uq["columns"])
        lineas.append(f"  CONSTRAINT {quote(uq['name'], engine)} UNIQUE ({columnas})")
    for ck in table.get("check_constraints", []):
        lineas.append(
            f"  CONSTRAINT {quote(ck['name'], engine)} CHECK ({ck['expression']})"
        )
    if inline_foreign_keys:
        for fk in table.get("foreign_keys", []):
            lineas.append(f"  {_fk_clause(fk, tables_by_name or {}, engine)}")

    cuerpo = ",\n".join(lineas)
    return f"CREATE TABLE {qualified(table, engine)} (\n{cuerpo}\n)"


def render_foreign_key(table: dict, fk: dict, tables_by_name: dict, engine: str) -> str:
    """``ALTER TABLE … ADD CONSTRAINT … FOREIGN KEY``."""
    return (
        f"ALTER TABLE {qualified(table, engine)} "
        f"ADD {_fk_clause(fk, tables_by_name, engine)}"
    )


def render_index(table: dict, index: dict, engine: str) -> str:
    """``CREATE [UNIQUE] INDEX``."""
    columnas = ", ".join(quote(c, engine) for c in index["columns"])
    unico = "UNIQUE " if index.get("unique") else ""
    return (
        f"CREATE {unico}INDEX {quote(index['name'], engine)} "
        f"ON {qualified(table, engine)} ({columnas})"
    )


def _literal(value: Any, column: dict, engine: str) -> str:
    """Literal SQL de un valor de semilla, según el tipo lógico de su columna."""
    if value is None:
        return "NULL"
    logical = column["logical_type"]
    if logical == LogicalType.BOOLEAN.value:
        clave = "true" if str(value).lower() in ("true", "1", "sí", "si") else "false"
        return _BOOL_LITERALS.get(engine, _BOOL_LITERALS["postgresql"])[clave]
    if logical in (
        LogicalType.INTEGER.value,
        LogicalType.BIGINT.value,
        LogicalType.DECIMAL.value,
    ):
        return str(value)
    # Todo lo demás va entrecomillado, escapando la comilla simple.
    texto = str(value).replace("'", "''")
    return f"'{texto}'"


def render_seed_rows(seed: dict, table: dict, engine: str) -> list[str]:
    """``INSERT`` por fila de semilla (uno por fila: legible y depurable)."""
    columnas_tabla = {c["name"]: c for c in table.get("columns", [])}
    columnas = [c for c in seed.get("columns", []) if c in columnas_tabla]
    if not columnas:
        return []

    sentencias: list[str] = []
    lista = ", ".join(quote(c, engine) for c in columnas)
    for row in seed.get("rows", []):
        valores = ", ".join(
            _literal(row.get(c), columnas_tabla[c], engine) for c in columnas
        )
        sentencias.append(
            f"INSERT INTO {qualified(table, engine)} ({lista}) VALUES ({valores})"
        )
    return sentencias


def topological_order(tables: list[dict]) -> tuple[list[dict], list[str]]:
    """Ordena las tablas por dependencias de FK (padres primero).

    Devuelve ``(tablas_ordenadas, ciclos)``. Un ciclo **no impide** generar el DDL
    —las FK van en un script aparte— pero se reporta: un ciclo de claves foráneas
    obligatorias hace imposible insertar la primera fila, y eso es un problema del
    modelo aunque el esquema se cree sin errores.
    """
    por_nombre = {t["name"]: t for t in tables}
    dependencias = {
        t["name"]: {
            fk["references_table"]
            for fk in t.get("foreign_keys", [])
            if fk["references_table"] in por_nombre
            and fk["references_table"] != t["name"]
        }
        for t in tables
    }

    ordenadas: list[dict] = []
    pendientes = {t["name"] for t in tables}
    while pendientes:
        libres = sorted(n for n in pendientes if not (dependencias[n] & pendientes))
        if not libres:
            # Ciclo: se emite el resto en orden estable para no perder tablas.
            ciclo = sorted(pendientes)
            ordenadas.extend(por_nombre[n] for n in ciclo)
            return ordenadas, ciclo
        for nombre in libres:
            ordenadas.append(por_nombre[nombre])
            pendientes.discard(nombre)
    return ordenadas, []


def _script(
    id_: str,
    order: int,
    name: str,
    kind: DdlScriptKind,
    engine: str,
    statements: list[str],
    header: str,
    source_refs: list[str],
) -> dict:
    """Empaqueta un conjunto de sentencias como script del artefacto."""
    cuerpo = "\n\n".join(f"{s};" for s in statements)
    return {
        "id": id_,
        "order": order,
        "name": name,
        "kind": kind.value,
        "engine": engine,
        "statements": statements,
        "sql": f"-- {header}\n\n{cuerpo}\n",
        "source_refs": source_refs,
    }


def render_alter_add_columns(
    table: dict, columnas: list[dict], engine: str
) -> list[str]:
    """``ALTER TABLE … ADD COLUMN`` para una tabla que YA EXISTE (INV4).

    Las columnas añadidas a una tabla con datos **no pueden ser NOT NULL sin
    DEFAULT**: el motor no sabría qué poner en las filas existentes y la sentencia
    falla. Se relaja a nullable y se deja dicho en el script, en vez de generar un
    ALTER que reventaría contra la base real.
    """
    sentencias: list[str] = []
    for columna in columnas:
        copia = dict(columna)
        if not copia.get("nullable", True) and copia.get("default") is None:
            copia["nullable"] = True
            comentario = (
                f" -- se declara NULL: la tabla ya tiene datos y la columna no "
                "trae DEFAULT"
            )
        else:
            comentario = ""
        sentencias.append(
            f"ALTER TABLE {qualified(table, engine)} "
            f"ADD COLUMN {render_column(copia, engine)}{comentario}"
        )
    return sentencias


def split_by_reconciliation(
    tables: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Separa las tablas según su veredicto de RECONCILE (INV4).

    Devuelve ``(a_crear, a_extender, reutilizadas)``. Sin reconciliación —o con la
    fase no ejecutada— **todo va a crear**: el comportamiento previo al módulo se
    conserva intacto, que es lo que hace el cambio retrocompatible.

    Un ``conflict`` va a **crear**: el conflicto ya generó una pregunta bloqueante
    y el semáforo está en rojo, así que el DDL propuesto debe seguir siendo el del
    diseño nuevo. Asumir reutilización sobre algo no confirmado sería justo el
    error que el conflicto señala.
    """
    a_crear, a_extender, reutilizadas = [], [], []
    for table in tables:
        estado = (table.get("reconciliation") or {}).get("status")
        if estado == "reuse":
            reutilizadas.append(table)
        elif estado == "extend":
            a_extender.append(table)
        else:
            a_crear.append(table)
    return a_crear, a_extender, reutilizadas


def build_ddl_scripts(
    tables: list[dict],
    seed_data: list[dict],
    engine: str,
    *,
    inline_foreign_keys: bool = False,
) -> tuple[list[dict], list[str]]:
    """Genera los scripts DDL completos. Devuelve ``(scripts, ciclos_detectados)``.

    Los scripts se numeran por orden de ejecución: esquema → tablas → ALTERs →
    claves foráneas → índices → semilla, y un ``rollback`` final en orden inverso.

    Si la fase RECONCILE (INV4) marcó tablas como ``reuse`` o ``extend``, el DDL lo
    respeta: lo reutilizado NO se crea (ni se dropea en el rollback: destruir una
    tabla de producción que solo se estaba reutilizando sería catastrófico) y lo
    extendido sale como ``ALTER TABLE ADD COLUMN`` en un script propio.

    ``inline_foreign_keys`` mete las FK dentro del ``CREATE TABLE`` y suprime el
    script de claves foráneas. Es lo que necesita la prueba de humo contra SQLite
    (§ ``smoke.py``); el DDL que se entrega al equipo usa siempre la forma normal.
    """
    a_crear, a_extender, reutilizadas = split_by_reconciliation(tables)
    # El orden topológico solo aplica a lo que se crea: lo que ya existe en el
    # destino no participa en las dependencias de creación.
    ordenadas, ciclos = topological_order(a_crear)
    por_nombre = {t["name"]: t for t in tables}
    scripts: list[dict] = []
    orden = 0

    schema = default_schema(engine)
    if schema:
        orden += 1
        scripts.append(
            _script(
                f"DDL-{orden:03d}",
                orden,
                "01_esquema.sql",
                DdlScriptKind.SCHEMA,
                engine,
                [f"CREATE SCHEMA IF NOT EXISTS {quote(schema, engine)}"],
                f"Esquema {schema}",
                [],
            )
        )

    if ordenadas:
        orden += 1
        scripts.append(
            _script(
                f"DDL-{orden:03d}",
                orden,
                f"{orden:02d}_tablas.sql",
                DdlScriptKind.TABLES,
                engine,
                [
                    render_create_table(t, engine, por_nombre, inline_foreign_keys)
                    for t in ordenadas
                ],
                "Tablas (columnas, claves primarias, unicidad y CHECK)",
                [t["id"] for t in ordenadas],
            )
        )

    # ALTERs de lo que ya existe y hay que extender (INV4). Van antes que las
    # constraints porque éstas pueden referirse a las columnas recién añadidas.
    sentencias_alter: list[str] = []
    refs_alter: list[str] = []
    for table in a_extender:
        faltantes = set((table.get("reconciliation") or {}).get("missing") or [])
        columnas = [c for c in table.get("columns", []) if c["name"] in faltantes]
        if not columnas:
            continue
        sentencias_alter.extend(render_alter_add_columns(table, columnas, engine))
        refs_alter.append(table["id"])
    if sentencias_alter:
        orden += 1
        scripts.append(
            _script(
                f"DDL-{orden:03d}",
                orden,
                f"{orden:02d}_alteraciones.sql",
                DdlScriptKind.ALTERS,
                engine,
                sentencias_alter,
                (
                    "Cambios sobre tablas que YA EXISTEN en el sistema destino "
                    "(reconciliación): se añaden columnas, no se recrean tablas"
                ),
                refs_alter,
            )
        )

    fks = (
        []
        if inline_foreign_keys
        else [(t, fk) for t in ordenadas for fk in t.get("foreign_keys", [])]
    )
    if fks:
        orden += 1
        scripts.append(
            _script(
                f"DDL-{orden:03d}",
                orden,
                f"{orden:02d}_claves_foraneas.sql",
                DdlScriptKind.CONSTRAINTS,
                engine,
                [render_foreign_key(t, fk, por_nombre, engine) for t, fk in fks],
                "Claves foráneas (aparte, para que el orden de creación no importe)",
                [fk["id"] for _, fk in fks],
            )
        )

    # Los índices sí aplican a las tablas extendidas: una columna nueva sobre una
    # tabla existente puede necesitar el suyo. Las reutilizadas se quedan fuera:
    # no se toca una tabla que solo se está consumiendo.
    indices = [(t, idx) for t in ordenadas + a_extender for idx in t.get("indexes", [])]
    if indices:
        orden += 1
        scripts.append(
            _script(
                f"DDL-{orden:03d}",
                orden,
                f"{orden:02d}_indices.sql",
                DdlScriptKind.INDEXES,
                engine,
                [render_index(t, idx, engine) for t, idx in indices],
                "Índices",
                [idx["id"] for _, idx in indices],
            )
        )

    sentencias_semilla: list[str] = []
    refs_semilla: list[str] = []
    reutilizadas_por_nombre = {t["name"] for t in reutilizadas}
    for seed in seed_data:
        table = por_nombre.get(seed.get("table"))
        if table is None:
            continue
        # Sembrar un catálogo que se está REUTILIZANDO duplicaría datos que ya
        # están en producción. Se omite; el veredicto ya dice que existe.
        if table["name"] in reutilizadas_por_nombre:
            continue
        filas = render_seed_rows(seed, table, engine)
        if filas:
            sentencias_semilla.extend(filas)
            refs_semilla.append(seed["id"])
    if sentencias_semilla:
        orden += 1
        scripts.append(
            _script(
                f"DDL-{orden:03d}",
                orden,
                f"{orden:02d}_semilla.sql",
                DdlScriptKind.SEED,
                engine,
                sentencias_semilla,
                "Datos semilla de catálogos (valores citados en el EF)",
                refs_semilla,
            )
        )

    if ordenadas:
        orden += 1
        scripts.append(
            _script(
                f"DDL-{orden:03d}",
                orden,
                "99_rollback.sql",
                DdlScriptKind.ROLLBACK,
                engine,
                [
                    f"DROP TABLE IF EXISTS {qualified(t, engine)}"
                    for t in reversed(ordenadas)
                ],
                (
                    "ROLLBACK — DESTRUCTIVO: elimina las tablas y sus datos. "
                    "Revisar antes de ejecutar"
                ),
                [t["id"] for t in ordenadas],
            )
        )

    return scripts, ciclos
