"""Validación de expresiones ``CHECK`` con un vocabulario SQL restringido.

Una constraint ``CHECK`` es el único punto del artefacto donde el LLM escribe algo
parecido a SQL, y por tanto el único que necesita un portero. Se valida con
**sqlglot** (parseo real, sin base de datos) contra una lista blanca de nodos del
AST, no con expresiones regulares: así se rechazan de forma fiable los tres casos
que importan.

1. **Subconsultas y sentencias** (``SELECT``, ``DROP``, varias sentencias
   separadas por ``;``). Ningún motor admite una subconsulta en un CHECK, y una
   segunda sentencia colada en el texto acabaría en el script DDL.
2. **Funciones no deterministas** (``CURRENT_DATE``, ``NOW()``, ``GETDATE()``).
   Este es el caso realista del dominio: «la fecha del siniestro no puede ser
   futura» parece un CHECK y no lo es — PostgreSQL y SQL Server rechazan la
   constraint, y Oracle la acepta evaluándola solo al insertar. La regla es
   correcta, pero pertenece a la capa de aplicación, así que se clasifica como
   ``application`` en vez de generar un DDL que falla.
3. **Columnas inexistentes**: un CHECK que cite una columna que no está en la
   tabla es un error que solo aparecería al ejecutar el DDL.

Las funciones deterministas (``UPPER``, ``LENGTH``) también se rechazan, aunque
serían legales: su comportamiento varía entre motores (colación, tratamiento de
NULL) y el valor de tener un CHECK así no compensa el riesgo de portabilidad. Si
hace falta, se pide como regla de aplicación.
"""

from typing import Optional

import sqlglot
from sqlglot import exp

#: Nodos permitidos en una expresión CHECK. Todo lo que no esté aquí se rechaza
#: (fail-closed): es más seguro pedir una regla de aplicación que emitir un DDL
#: que el motor no acepta.
_ALLOWED_NODES: tuple[type, ...] = (
    exp.Column,
    exp.Identifier,
    exp.Literal,
    exp.Boolean,
    exp.Null,
    exp.Paren,
    exp.And,
    exp.Or,
    exp.Not,
    exp.EQ,
    exp.NEQ,
    exp.LT,
    exp.LTE,
    exp.GT,
    exp.GTE,
    exp.In,
    exp.Between,
    exp.Is,
    exp.Like,
    exp.Tuple,
    exp.Neg,
)

#: Motivos de rechazo, estables para poder testearlos y mostrarlos en la UI.
REASON_UNPARSEABLE = "no_parseable"
REASON_MULTIPLE_STATEMENTS = "varias_sentencias"
REASON_SUBQUERY = "subconsulta"
REASON_NON_DETERMINISTIC = "funcion_no_determinista"
REASON_FUNCTION = "funcion_no_permitida"
REASON_UNKNOWN_COLUMN = "columna_inexistente"
REASON_NO_COLUMN = "sin_columnas"

#: Funciones de fecha/hora del momento actual: delatan una regla temporal que NO
#: puede vivir en un CHECK.
_NON_DETERMINISTIC = (
    exp.CurrentDate,
    exp.CurrentTime,
    exp.CurrentTimestamp,
    exp.CurrentUser,
)


class ExpressionVerdict:
    """Resultado de validar una expresión CHECK."""

    __slots__ = ("ok", "reason", "detail", "columns")

    def __init__(
        self,
        ok: bool,
        reason: Optional[str] = None,
        detail: Optional[str] = None,
        columns: Optional[set[str]] = None,
    ) -> None:
        self.ok = ok
        self.reason = reason
        self.detail = detail
        self.columns = columns or set()

    def __bool__(self) -> bool:  # pragma: no cover - azúcar de lectura
        return self.ok


def validate_check_expression(
    expression: str, table_columns: set[str], engine: str = "postgresql"
) -> ExpressionVerdict:
    """Valida una expresión CHECK contra el vocabulario permitido.

    ``table_columns`` son los nombres de columna de **esa** tabla; una expresión
    que cite otra cosa se rechaza. Devuelve un veredicto con el motivo, para que
    quien llame decida qué hacer (reclasificar la regla, observar, preguntar).
    """
    text = (expression or "").strip().rstrip(";").strip()
    if not text:
        return ExpressionVerdict(False, REASON_UNPARSEABLE, "expresión vacía")

    dialect = _sqlglot_dialect(engine)
    try:
        parsed = sqlglot.parse(text, read=dialect)
    except Exception as exc:  # sqlglot.ParseError y derivados
        return ExpressionVerdict(False, REASON_UNPARSEABLE, str(exc)[:150])

    statements = [s for s in parsed if s is not None]
    if len(statements) != 1:
        return ExpressionVerdict(
            False,
            REASON_MULTIPLE_STATEMENTS,
            f"se esperaba una sola expresión y hay {len(statements)}",
        )

    tree = statements[0]
    for node in tree.walk():
        if isinstance(node, (exp.Select, exp.Subquery)):
            return ExpressionVerdict(False, REASON_SUBQUERY, type(node).__name__)
        if isinstance(node, _NON_DETERMINISTIC):
            return ExpressionVerdict(
                False, REASON_NON_DETERMINISTIC, type(node).__name__
            )
        # La lista blanca se consulta ANTES de rechazar funciones: en sqlglot los
        # conectores lógicos (`And`, `Or`, `Not`) son subclases de ``exp.Func``, así
        # que comprobar `Func` primero rechazaría `monto > 0 AND monto < 100`.
        if isinstance(node, _ALLOWED_NODES):
            continue
        return ExpressionVerdict(
            False,
            REASON_SUBQUERY if isinstance(node, exp.DDL) else REASON_FUNCTION,
            type(node).__name__,
        )

    columns = {c.name.lower() for c in tree.find_all(exp.Column)}
    if not columns:
        return ExpressionVerdict(
            False, REASON_NO_COLUMN, "la expresión no referencia ninguna columna"
        )

    conocidas = {c.lower() for c in table_columns}
    desconocidas = sorted(columns - conocidas)
    if desconocidas:
        return ExpressionVerdict(
            False, REASON_UNKNOWN_COLUMN, ", ".join(desconocidas), columns
        )

    return ExpressionVerdict(True, None, None, columns)


def _sqlglot_dialect(engine: str) -> str:
    """Traduce la clave del motor al nombre del dialecto de sqlglot."""
    return {
        "postgresql": "postgres",
        "sqlserver": "tsql",
        "oracle": "oracle",
        "mysql": "mysql",
    }.get(engine, "postgres")
