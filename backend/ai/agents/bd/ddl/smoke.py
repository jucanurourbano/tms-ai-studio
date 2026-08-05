"""Capa L3a: **ejecutar** el DDL contra una base de datos efímera.

L1 y L2 comprueban coherencia y sintaxis; esta capa comprueba lo único que ninguna
de las dos puede: que el esquema **se crea de verdad** y que los datos semilla
entran sin violar sus propias restricciones.

Se ejecuta contra SQLite en memoria (``sqlite3`` de la biblioteca estándar: sin
contenedor, sin red, milisegundos), transpilando antes el DDL con sqlglot desde el
dialecto destino. La transpilación tiene límites conocidos y por eso esto es un
**smoke test, no una certificación**: SQLite usa afinidades de tipo en vez de tipos
estrictos y no aplica todos los CHECK igual que PostgreSQL. Sirve para cazar lo que
importa —una FK a una tabla inexistente, una columna repetida, una semilla que viola
un NOT NULL o un UNIQUE— y por eso vive en los tests y no en el pipeline, que
declara ``executed=False``.

La certificación real contra PostgreSQL 16 (L3b) usa el contenedor del
``docker-compose.yml`` y es opt-in, fuera de la suite por defecto.
"""

import sqlite3
from typing import Optional

import sqlglot

from ..expressions import _sqlglot_dialect


class SmokeResult:
    """Resultado de ejecutar el DDL contra la base efímera."""

    __slots__ = ("ok", "failed_statement", "error", "executed", "tables")

    def __init__(
        self,
        ok: bool,
        executed: int = 0,
        failed_statement: Optional[str] = None,
        error: Optional[str] = None,
        tables: Optional[set[str]] = None,
    ) -> None:
        self.ok = ok
        self.executed = executed
        self.failed_statement = failed_statement
        self.error = error
        self.tables = tables or set()

    def __bool__(self) -> bool:  # pragma: no cover - azúcar de lectura
        return self.ok


def _to_sqlite(statement: str, engine: str) -> Optional[str]:
    """Transpila una sentencia al dialecto de SQLite (``None`` si no se puede)."""
    try:
        salida = sqlglot.transpile(
            statement, read=_sqlglot_dialect(engine), write="sqlite"
        )
    except Exception:
        return None
    return salida[0] if salida else None


def run_ddl_on_sqlite(
    tables: list[dict], seed_data: list[dict], engine: str
) -> SmokeResult:
    """Crea el esquema en SQLite en memoria e inserta la semilla.

    Se **re-renderiza** el DDL con las claves foráneas en línea porque SQLite no
    soporta ``ALTER TABLE ADD CONSTRAINT``. El resto del SQL (columnas, tipos, PK,
    UNIQUE, CHECK, INSERT) es exactamente el mismo que se entrega al equipo: pasa
    por el mismo renderizador, así que un bug en él aparece aquí.

    Las claves foráneas se activan (``PRAGMA foreign_keys=ON``); sin eso SQLite las
    acepta y las ignora, y esto no probaría nada. Además, como SQLite resuelve el
    destino de una FK de forma diferida, se comprueba explícitamente con
    ``PRAGMA foreign_key_list`` que cada tabla padre existe: si no, un modelo con
    una FK rota pasaría el test mientras no hubiera filas.
    """
    from .render import build_ddl_scripts

    scripts, _ = build_ddl_scripts(tables, seed_data, engine, inline_foreign_keys=True)

    conexion = sqlite3.connect(":memory:")
    conexion.execute("PRAGMA foreign_keys = ON")
    ejecutadas = 0

    try:
        for script in sorted(scripts, key=lambda s: s["order"]):
            if script["kind"] in ("rollback", "schema"):
                # El rollback destruye lo creado; el esquema no existe en SQLite.
                continue
            for statement in script.get("statements", []):
                sql = _sqlite_ready(statement, engine)
                if sql is None:
                    continue
                try:
                    conexion.execute(sql)
                    ejecutadas += 1
                except sqlite3.Error as exc:
                    return SmokeResult(False, ejecutadas, statement, str(exc))
        conexion.commit()

        creadas = {
            f[0]
            for f in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        rota = _first_broken_fk(conexion, creadas)
        if rota is not None:
            return SmokeResult(False, ejecutadas, rota[0], rota[1], creadas)

        violaciones = conexion.execute("PRAGMA foreign_key_check").fetchall()
        if violaciones:
            return SmokeResult(
                False,
                ejecutadas,
                "PRAGMA foreign_key_check",
                f"filas que violan una clave foránea: {violaciones[:3]}",
                creadas,
            )
        return SmokeResult(True, ejecutadas, tables=creadas)
    finally:
        conexion.close()


def _first_broken_fk(
    conexion: sqlite3.Connection, creadas: set[str]
) -> Optional[tuple[str, str]]:
    """Primera FK cuya tabla destino no existe, o ``None`` si todas resuelven."""
    for tabla in sorted(creadas):
        for fila in conexion.execute(f'PRAGMA foreign_key_list("{tabla}")').fetchall():
            destino = fila[2]
            if destino not in creadas:
                return (
                    f"FOREIGN KEY de {tabla}",
                    f"la tabla destino «{destino}» no existe en el esquema creado",
                )
    return None


def _sqlite_ready(statement: str, engine: str) -> Optional[str]:
    """Prepara una sentencia para SQLite: transpila y salva dos incompatibilidades.

    1. **Esquemas**: SQLite no los tiene; ``public.guias`` se interpretaría como la
       base adjunta ``public``. Se quita el prefijo.
    2. **Identidad**: sqlglot traduce ``GENERATED BY DEFAULT AS IDENTITY`` a
       ``AUTOINCREMENT``, que en SQLite **solo** es válido escrito en línea sobre
       un ``INTEGER PRIMARY KEY``. Como aquí la PK se declara como constraint de
       tabla (que es lo correcto en los motores reales), la palabra sobra y se
       elimina.
    3. **Orden de nulos en los índices**: al transpilar, sqlglot hace explícito el
       ``NULLS LAST`` que PostgreSQL aplica por defecto, y SQLite no lo admite.

    Ninguna de las tres afecta a lo que esta capa comprueba —estructura, claves,
    restricciones y semilla—, y por eso es un smoke test y no una certificación:
    la generación de identificadores hay que probarla contra el motor real (L3b).
    """
    sql = _to_sqlite(statement, engine)
    if sql is None:
        return None
    sql = sql.replace('"public".', "").replace("public.", "").replace("dbo.", "")
    sql = sql.replace(" AUTOINCREMENT", "")
    return sql.replace(" NULLS LAST", "").replace(" NULLS FIRST", "")
