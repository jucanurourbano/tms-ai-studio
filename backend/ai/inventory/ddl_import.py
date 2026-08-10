"""Dump DDL (.sql) → contenido estructurado de un activo ``db_schema``.

**Sin LLM.** Es el gemelo inverso del renderizador del Agente BD: allí Python
escribe SQL a partir de un modelo; aquí Python lee SQL hacia un modelo. Pedirle a
un modelo de lenguaje que "interprete" un esquema de producción sería inventar un
riesgo donde hay un parser exacto.

La trampa de sqlglot (y por qué este módulo existe)
---------------------------------------------------
``sqlglot`` **no lanza excepción** ante una sentencia DDL que no entiende: la
degrada a un nodo ``Command`` con el texto crudo y sigue adelante, incluso con
``error_level=RAISE``. Un importador ingenuo la daría por buena y el inventario se
quedaría con un esquema al que le faltan tablas **sin que nadie se entere** — el
peor fallo posible aquí, porque RECONCILE concluiría "esa tabla no existe, créala"
sobre una tabla que sí existe.

Por eso toda sentencia que caiga en ``Command`` se reporta como error con su
**número de línea**, y nada entra al inventario en silencio: lo que no se pudo
leer se dice, y lo que se ignoró a propósito (GRANT, SET, CREATE SEQUENCE…) se
cuenta aparte.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError
from sqlglot.tokens import TokenType

#: Tipo físico (normalizado) -> ``logical_type`` del Agente BD. Permite que
#: RECONCILE compare una columna existente con una propuesta sin traducir dos
#: veces. Lo que no aparezca aquí deja ``logical_type=None``: NO se adivina.
_LOGICAL_BY_TYPE: dict[str, str] = {
    "VARCHAR": "string",
    "NVARCHAR": "string",
    "CHAR": "string",
    "NCHAR": "string",
    "TEXT": "text",
    "MEDIUMTEXT": "text",
    "LONGTEXT": "text",
    "CLOB": "text",
    "INT": "integer",
    "INTEGER": "integer",
    "SMALLINT": "integer",
    "TINYINT": "integer",
    "MEDIUMINT": "integer",
    "SERIAL": "integer",
    "BIGINT": "bigint",
    "BIGSERIAL": "bigint",
    "DECIMAL": "decimal",
    "NUMERIC": "decimal",
    "MONEY": "decimal",
    "DOUBLE": "decimal",
    "FLOAT": "decimal",
    "REAL": "decimal",
    "BOOLEAN": "boolean",
    "BIT": "boolean",
    "DATE": "date",
    "TIME": "time",
    "DATETIME": "timestamp",
    "TIMESTAMP": "timestamp",
    "TIMESTAMPTZ": "timestamptz",
    "TIMESTAMPLTZ": "timestamptz",
    "UUID": "uuid",
    "JSON": "json",
    "JSONB": "json",
    "BINARY": "binary",
    "VARBINARY": "binary",
    "BLOB": "binary",
    "BYTEA": "binary",
}

#: Sentencias que se ignoran a propósito: no describen la forma del esquema. Se
#: CUENTAN y se informan, nunca se descartan en silencio.
_IGNORABLES = (
    exp.Grant,
    exp.Set,
    exp.Use,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Insert,
    exp.Delete,
    exp.Update,
    exp.Drop,
)


@dataclass
class DdlImportIssue:
    """Un problema encontrado al leer el dump, con su línea."""

    code: str
    message: str
    line: Optional[int] = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "line": self.line}


@dataclass
class DdlImportResult:
    """Resultado de leer un dump: contenido, avisos y qué se ignoró."""

    content: dict[str, Any]
    errors: list[DdlImportIssue] = field(default_factory=list)
    warnings: list[DdlImportIssue] = field(default_factory=list)
    #: Sentencias reconocidas pero irrelevantes para la forma (GRANT, SET…).
    ignored_statements: int = 0
    parsed_statements: int = 0

    @property
    def tables(self) -> list[dict]:
        return self.content.get("tables", [])

    def as_report(self) -> dict[str, Any]:
        """Resumen para la API: qué se leyó y qué no."""
        return {
            "tables": len(self.tables),
            "columns": sum(len(t.get("columns") or []) for t in self.tables),
            "parsed_statements": self.parsed_statements,
            "ignored_statements": self.ignored_statements,
            "errors": [e.as_dict() for e in self.errors],
            "warnings": [w.as_dict() for w in self.warnings],
        }


class DdlImportError(Exception):
    """El dump no se pudo leer en absoluto (tokenizado imposible)."""

    def __init__(self, message: str, *, line: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


def _split_statements(sql: str, dialect: str) -> list[tuple[int, str]]:
    """Parte el dump en ``(línea_de_inicio, texto)`` por sentencia.

    Se hace con el tokenizador, y no dejando que ``sqlglot.parse`` trocee el
    archivo entero, por dos razones que son el núcleo de este módulo:

    1. ``sqlglot`` **no expone la línea** de un nodo ``Command`` (lo que devuelve
       cuando no entiende algo), que es justo el caso que hay que reportar.
    2. ``parse`` sobre el archivo completo lanza ``ParseError`` en cuanto UNA
       sentencia es inválida y se pierde el dump entero. Troceando primero, una
       sentencia propietaria se reporta con su línea y las demás se leen igual.
    """
    sentencias: list[tuple[int, str]] = []
    inicio: Optional[int] = None
    linea = 0
    fin = 0
    for token in sqlglot.tokenize(sql, read=dialect):
        if token.token_type == TokenType.SEMICOLON:
            if inicio is not None:
                sentencias.append((linea, sql[inicio : token.start]))
                inicio = None
            continue
        if inicio is None:
            inicio = token.start
            linea = token.line
        fin = token.end + 1
    if inicio is not None:
        sentencias.append((linea, sql[inicio:fin]))
    return [(ln, texto.strip()) for ln, texto in sentencias if texto.strip()]


def _logical_type(datatype: Optional[exp.DataType]) -> Optional[str]:
    """``logical_type`` del Agente BD para un tipo físico, o ``None``.

    Devolver ``None`` es una respuesta legítima: un tipo exótico o propio del
    motor no tiene equivalente y adivinarlo produciría comparaciones falsas en
    RECONCILE.
    """
    if datatype is None:
        return None
    return _LOGICAL_BY_TYPE.get(datatype.this.name.upper())


def _column_type_sql(column_def: exp.ColumnDef) -> str:
    """Tipo verbatim de la columna, tal como lo declara el dump."""
    datatype = column_def.args.get("kind")
    return datatype.sql(dialect="postgres") if datatype else ""


def _name_of(node: Any) -> str:
    """Nombre de un identificador de sqlglot, sin comillas."""
    if node is None:
        return ""
    if isinstance(node, exp.Identifier):
        return node.name
    if isinstance(node, exp.Column):
        return node.name
    if isinstance(node, str):
        return node
    return getattr(node, "name", "") or ""


def _columns_of_constraint(node: Any) -> list[str]:
    """Columnas citadas por una constraint (PK/UNIQUE/FK/índice)."""
    if node is None:
        return []
    nombres: list[str] = []
    for ident in node.find_all(exp.Identifier):
        nombre = ident.name
        if nombre and nombre not in nombres:
            nombres.append(nombre)
    return nombres


class _SchemaBuilder:
    """Acumula tablas conforme se leen las sentencias del dump."""

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, Any]] = {}
        self.warnings: list[DdlImportIssue] = []

    def table(self, name: str) -> Optional[dict[str, Any]]:
        return self.tables.get(name.lower())

    def ensure_table(self, name: str, schema_name: Optional[str]) -> dict[str, Any]:
        clave = name.lower()
        if clave not in self.tables:
            self.tables[clave] = {
                "name": name,
                "schema_name": schema_name,
                "comment": None,
                "columns": [],
                "primary_key": [],
                "foreign_keys": [],
                "constraints": [],
                "indexes": [],
            }
        return self.tables[clave]

    def as_content(self, engine: str) -> dict[str, Any]:
        return {"engine": engine, "tables": list(self.tables.values())}


def _read_create_table(create: exp.Create, builder: _SchemaBuilder, line: int) -> None:
    """Lee un ``CREATE TABLE`` completo: columnas y constraints de tabla."""
    tabla_exp = create.this
    if isinstance(tabla_exp, exp.Schema):
        objetivo = tabla_exp.this
        definiciones = tabla_exp.expressions
    else:
        objetivo = tabla_exp
        definiciones = []

    nombre = _name_of(objetivo.this if isinstance(objetivo, exp.Table) else objetivo)
    schema_name = None
    if isinstance(objetivo, exp.Table) and objetivo.args.get("db"):
        schema_name = _name_of(objetivo.args["db"])

    tabla = builder.ensure_table(nombre, schema_name)

    for definicion in definiciones:
        if isinstance(definicion, exp.ColumnDef):
            _read_column_def(definicion, tabla)
        elif isinstance(definicion, exp.PrimaryKey):
            tabla["primary_key"] = _columns_of_constraint(definicion)
        elif isinstance(definicion, exp.ForeignKey):
            _read_foreign_key(definicion, tabla, nombre_constraint=None)
        elif isinstance(definicion, exp.UniqueColumnConstraint):
            tabla["constraints"].append(
                {
                    "kind": "unique",
                    "name": None,
                    "columns": _columns_of_constraint(definicion),
                    "expression": None,
                }
            )
        elif isinstance(definicion, exp.Constraint):
            _read_named_constraint(definicion, tabla)
        elif isinstance(definicion, exp.CheckColumnConstraint):
            tabla["constraints"].append(
                {
                    "kind": "check",
                    "name": None,
                    "columns": [],
                    "expression": definicion.this.sql(dialect="postgres"),
                }
            )
        else:
            builder.warnings.append(
                DdlImportIssue(
                    "unsupported_table_definition",
                    (
                        f"En «{nombre}» se ignoró una definición que el lector no "
                        f"reconoce ({type(definicion).__name__})."
                    ),
                    line,
                )
            )

    # La PK declarada inline en una columna también cuenta.
    inline_pk = [c["name"] for c in tabla["columns"] if c.get("primary_key")]
    if inline_pk and not tabla["primary_key"]:
        tabla["primary_key"] = inline_pk
    # Y al revés: una PK de tabla marca sus columnas.
    for columna in tabla["columns"]:
        if columna["name"] in tabla["primary_key"]:
            columna["primary_key"] = True


def _read_column_def(definicion: exp.ColumnDef, tabla: dict[str, Any]) -> None:
    """Lee una columna con sus restricciones inline."""
    nombre = _name_of(definicion.this)
    tipo_sql = _column_type_sql(definicion)
    columna: dict[str, Any] = {
        "name": nombre,
        "type": tipo_sql,
        "logical_type": _logical_type(definicion.args.get("kind")),
        # En SQL una columna admite nulos salvo que se diga lo contrario.
        "nullable": True,
        "default": None,
        "primary_key": False,
        "comment": None,
    }

    for restriccion in definicion.args.get("constraints") or []:
        tipo = restriccion.kind if hasattr(restriccion, "kind") else None
        if isinstance(tipo, exp.NotNullColumnConstraint):
            # `NOT NULL` y `NULL` comparten nodo: `allow_null` distingue.
            columna["nullable"] = bool(tipo.args.get("allow_null"))
        elif isinstance(tipo, exp.PrimaryKeyColumnConstraint):
            columna["primary_key"] = True
            columna["nullable"] = False
        elif isinstance(tipo, exp.DefaultColumnConstraint):
            columna["default"] = tipo.this.sql(dialect="postgres")
        elif isinstance(tipo, exp.UniqueColumnConstraint):
            tabla["constraints"].append(
                {
                    "kind": "unique",
                    "name": None,
                    "columns": [nombre],
                    "expression": None,
                }
            )
        elif isinstance(tipo, exp.CheckColumnConstraint):
            tabla["constraints"].append(
                {
                    "kind": "check",
                    "name": None,
                    "columns": [nombre],
                    "expression": tipo.this.sql(dialect="postgres"),
                }
            )
        elif isinstance(tipo, exp.Reference):
            _read_inline_reference(tipo, tabla, nombre)
        elif isinstance(tipo, exp.CommentColumnConstraint):
            columna["comment"] = tipo.this.name

    # Los tipos autoincrementales implican NOT NULL aunque no se declare.
    if (tipo_sql or "").upper() in ("SERIAL", "BIGSERIAL", "SMALLSERIAL"):
        columna["nullable"] = False

    tabla["columns"].append(columna)


def _read_inline_reference(
    referencia: exp.Reference, tabla: dict[str, Any], columna: str
) -> None:
    """``... REFERENCES otra_tabla(col)`` declarado en la propia columna."""
    destino = referencia.this
    if isinstance(destino, exp.Schema):
        tabla_destino = _name_of(destino.this.this)
        columnas_destino = [_name_of(i) for i in destino.expressions]
    else:
        tabla_destino = _name_of(
            destino.this if isinstance(destino, exp.Table) else destino
        )
        columnas_destino = []
    _append_foreign_key(
        tabla,
        {
            "name": None,
            "columns": [columna],
            "referenced_table": tabla_destino,
            "referenced_columns": columnas_destino,
            "on_delete": _on_delete(referencia),
        },
    )


def _on_delete(node: Any) -> Optional[str]:
    """Acción ``ON DELETE`` declarada, en minúsculas (``cascade``, ``set null``…)."""
    opciones = node.args.get("options") or []
    for opcion in opciones:
        texto = str(opcion).upper()
        if texto.startswith("ON DELETE"):
            return texto.replace("ON DELETE", "").strip().lower()
    return None


def _read_foreign_key(
    fk: exp.ForeignKey, tabla: dict[str, Any], nombre_constraint: Optional[str]
) -> None:
    """``FOREIGN KEY (…) REFERENCES otra (…)`` a nivel de tabla."""
    columnas = [_name_of(c) for c in fk.args.get("expressions") or []]
    referencia = fk.args.get("reference")
    tabla_destino = ""
    columnas_destino: list[str] = []
    # `ON DELETE` cuelga del nodo `Reference`, no del `ForeignKey`: mirar solo el
    # segundo devolvía siempre `None` y el inventario perdía la acción referencial.
    accion = _on_delete(referencia) if referencia is not None else None
    if referencia is not None:
        destino = referencia.this
        if isinstance(destino, exp.Schema):
            tabla_destino = _name_of(destino.this.this)
            columnas_destino = [_name_of(i) for i in destino.expressions]
        elif isinstance(destino, exp.Table):
            tabla_destino = _name_of(destino.this)
    _append_foreign_key(
        tabla,
        {
            "name": nombre_constraint,
            "columns": columnas,
            "referenced_table": tabla_destino,
            "referenced_columns": columnas_destino,
            "on_delete": accion or _on_delete(fk),
        },
    )


def _append_foreign_key(tabla: dict[str, Any], fk: dict[str, Any]) -> None:
    """Añade una FK evitando duplicar la MISMA relación declarada dos veces.

    Un esquema puede traer la relación inline (``REFERENCES``) y repetirla luego
    como ``ALTER TABLE ADD CONSTRAINT`` con nombre. Son la misma clave foránea:
    contarla dos veces haría creer a RECONCILE que la tabla tiene el doble de
    relaciones. Gana la declaración **con nombre**, que es la que existe en el
    catálogo del motor.
    """
    for existente in tabla["foreign_keys"]:
        misma = existente["columns"] == fk["columns"] and (
            existente["referenced_table"].lower() == fk["referenced_table"].lower()
        )
        if not misma:
            continue
        if existente.get("name") is None and fk.get("name") is not None:
            existente.update(fk)
        return
    tabla["foreign_keys"].append(fk)


def _read_named_constraint(constraint: exp.Constraint, tabla: dict[str, Any]) -> None:
    """``CONSTRAINT nombre PRIMARY KEY|UNIQUE|CHECK|FOREIGN KEY (…)``."""
    nombre = _name_of(constraint.this)
    for parte in constraint.expressions:
        if isinstance(parte, exp.PrimaryKey):
            tabla["primary_key"] = _columns_of_constraint(parte)
        elif isinstance(parte, exp.ForeignKey):
            _read_foreign_key(parte, tabla, nombre_constraint=nombre)
        elif isinstance(parte, exp.UniqueColumnConstraint):
            tabla["constraints"].append(
                {
                    "kind": "unique",
                    "name": nombre,
                    "columns": _columns_of_constraint(parte),
                    "expression": None,
                }
            )
        elif isinstance(parte, exp.CheckColumnConstraint):
            tabla["constraints"].append(
                {
                    "kind": "check",
                    "name": nombre,
                    "columns": [],
                    "expression": parte.this.sql(dialect="postgres"),
                }
            )


def _read_alter(alter: exp.Alter, builder: _SchemaBuilder, line: int) -> None:
    """``ALTER TABLE … ADD CONSTRAINT …`` (y ``ADD COLUMN``)."""
    objetivo = alter.this
    nombre = _name_of(objetivo.this if isinstance(objetivo, exp.Table) else objetivo)
    tabla = builder.table(nombre)
    if tabla is None:
        builder.warnings.append(
            DdlImportIssue(
                "alter_on_unknown_table",
                (
                    f"ALTER sobre «{nombre}», que no se creó en este dump: la "
                    "restricción no se pudo aplicar."
                ),
                line,
            )
        )
        return

    for accion in alter.args.get("actions") or []:
        # `ADD CONSTRAINT` llega envuelto en `AddConstraint`, que agrupa una o
        # varias `Constraint`. Es la forma en que pg_dump emite TODAS las claves
        # foráneas, así que sin esta rama un dump real perdería sus relaciones.
        if isinstance(accion, exp.AddConstraint):
            for parte in accion.expressions:
                if isinstance(parte, exp.Constraint):
                    _read_named_constraint(parte, tabla)
                elif isinstance(parte, exp.PrimaryKey):
                    tabla["primary_key"] = _columns_of_constraint(parte)
                elif isinstance(parte, exp.ForeignKey):
                    _read_foreign_key(parte, tabla, nombre_constraint=None)
        elif isinstance(accion, exp.Constraint):
            _read_named_constraint(accion, tabla)
        elif isinstance(accion, exp.PrimaryKey):
            tabla["primary_key"] = _columns_of_constraint(accion)
            for columna in tabla["columns"]:
                if columna["name"] in tabla["primary_key"]:
                    columna["primary_key"] = True
        elif isinstance(accion, exp.ForeignKey):
            _read_foreign_key(accion, tabla, nombre_constraint=None)
        elif isinstance(accion, exp.ColumnDef):
            _read_column_def(accion, tabla)


def _read_index(create: exp.Create, builder: _SchemaBuilder, line: int) -> None:
    """``CREATE [UNIQUE] INDEX … ON tabla (columnas)``."""
    indice = create.this
    nombre = _name_of(indice.this) if indice is not None else None
    tabla_exp = indice.args.get("table") if indice is not None else None
    nombre_tabla = _name_of(
        tabla_exp.this if isinstance(tabla_exp, exp.Table) else tabla_exp
    )
    tabla = builder.table(nombre_tabla)
    if tabla is None:
        builder.warnings.append(
            DdlImportIssue(
                "index_on_unknown_table",
                (
                    f"Índice «{nombre}» sobre «{nombre_tabla}», que no se creó en "
                    "este dump."
                ),
                line,
            )
        )
        return
    # Las columnas del índice cuelgan de `params` (IndexParameters), que NO es
    # iterable: hay que entrar por su argumento `columns`.
    columnas: list[str] = []
    parametros = indice.args.get("params")
    if parametros is not None:
        for columna in parametros.args.get("columns") or []:
            columnas.extend(_columns_of_constraint(columna))
    if not columnas:
        columnas = _columns_of_constraint(indice.args.get("columns"))
    tabla["indexes"].append(
        {
            "name": nombre,
            "columns": columnas,
            "unique": bool(create.args.get("unique")),
        }
    )


def _read_comment(comment: exp.Comment, builder: _SchemaBuilder) -> None:
    """``COMMENT ON TABLE|COLUMN … IS '…'`` (documentación del esquema real)."""
    texto = comment.args.get("expression")
    valor = texto.name if texto is not None else None
    objetivo = comment.this
    tipo = (comment.args.get("kind") or "").upper()

    if tipo == "TABLE":
        nombre = _name_of(
            objetivo.this if isinstance(objetivo, exp.Table) else objetivo
        )
        tabla = builder.table(nombre)
        if tabla is not None:
            tabla["comment"] = valor
    elif tipo == "COLUMN" and isinstance(objetivo, exp.Column):
        nombre_tabla = _name_of(objetivo.args.get("table"))
        tabla = builder.table(nombre_tabla)
        if tabla is not None:
            for columna in tabla["columns"]:
                if columna["name"] == objetivo.name:
                    columna["comment"] = valor


def parse_ddl(sql: str, *, engine: str = "postgresql") -> DdlImportResult:
    """Lee un dump DDL y devuelve el contenido de un activo ``db_schema``.

    No lanza excepción ante una sentencia ilegible: la reporta en ``errors`` con
    su línea y sigue con el resto, porque un dump de producción de miles de
    líneas no debe perderse entero por una sentencia propietaria. Lo que **sí**
    interrumpe es un fallo de tokenizado (comilla sin cerrar), que deja el resto
    del archivo sin significado.
    """
    dialect = "postgres" if engine == "postgresql" else engine
    if not sql.strip():
        raise DdlImportError("El archivo está vacío: no hay DDL que leer.")

    # El tokenizado SÍ es fatal: una comilla sin cerrar deja el resto del archivo
    # sin significado, y trocear por `;` a partir de ahí daría basura.
    try:
        troceadas = _split_statements(sql, dialect)
    except TokenError as exc:
        raise DdlImportError(
            f"No se pudo leer el archivo SQL: {exc}. Suele ser una comilla o un "
            "comentario sin cerrar, que deja el resto del archivo sin sentido."
        ) from exc

    builder = _SchemaBuilder()
    errores: list[DdlImportIssue] = []
    ignoradas = 0
    leidas = 0

    for linea, texto in troceadas:
        # Las dos formas en que sqlglot rechaza una sentencia — excepción y
        # degradación muda a `Command` — desembocan en el MISMO informe. La
        # segunda es la peligrosa: sin detectarla, el dump parecería correcto y
        # al inventario le faltaría una tabla que sí existe en producción, con lo
        # que RECONCILE diría "no existe, créala".
        try:
            sentencia = sqlglot.parse_one(texto, read=dialect)
        except (ParseError, TokenError) as exc:
            errores.append(
                DdlImportIssue(
                    "unparsed_statement",
                    (
                        f"Línea {linea}: no se pudo interpretar esta sentencia "
                        f"({str(exc).splitlines()[0][:120]}). Revísala: si define "
                        "una tabla, esa tabla NO entró al inventario."
                    ),
                    linea,
                )
            )
            continue

        if sentencia is None:
            continue

        if isinstance(sentencia, exp.Command):
            errores.append(
                DdlImportIssue(
                    "unparsed_statement",
                    (
                        f"Línea {linea}: no se pudo interpretar esta sentencia "
                        f"«{texto[:80].strip()}…». Revísala: si define una tabla, "
                        "esa tabla NO entró al inventario."
                    ),
                    linea,
                )
            )
            continue

        leidas += 1
        if isinstance(sentencia, exp.Create):
            tipo = (sentencia.args.get("kind") or "").upper()
            if tipo == "TABLE":
                _read_create_table(sentencia, builder, linea or 0)
            elif tipo == "INDEX":
                _read_index(sentencia, builder, linea or 0)
            else:
                ignoradas += 1
                leidas -= 1
        elif isinstance(sentencia, exp.Alter):
            _read_alter(sentencia, builder, linea or 0)
        elif isinstance(sentencia, exp.Comment):
            _read_comment(sentencia, builder)
        elif isinstance(sentencia, _IGNORABLES):
            ignoradas += 1
            leidas -= 1
        else:
            ignoradas += 1
            leidas -= 1

    resultado = DdlImportResult(
        content=builder.as_content(engine),
        errors=errores,
        warnings=builder.warnings,
        ignored_statements=ignoradas,
        parsed_statements=leidas,
    )

    if not resultado.tables:
        resultado.errors.append(
            DdlImportIssue(
                "no_tables_found",
                (
                    "El archivo no contiene ningún CREATE TABLE legible. Si es un "
                    "dump completo, comprueba que incluya el esquema y no solo los "
                    "datos."
                ),
            )
        )
    return resultado
