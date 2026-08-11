"""RECONCILE dentro del pipeline del Agente BD (INV4).

Lo que aquí se prueba es la consecuencia REAL del veredicto, que es lo que hace
que el módulo sirva para algo: una tabla ``reuse`` no genera ``CREATE`` (ni un
``DROP`` en el rollback), y una ``extend`` sale como ``ALTER TABLE ADD COLUMN``.

Sin esto, la reconciliación sería una etiqueta bonita en un informe.
"""

import pytest

from ai.agents.bd.ddl.render import (
    build_ddl_scripts,
    render_alter_add_columns,
    split_by_reconciliation,
)
from ai.inventory.nodes import reconcile_tables


def columna(nombre: str, tipo: str = "string", **extra) -> dict:
    return {
        "id": f"COL-{nombre}",
        "name": nombre,
        "ordinal": 1,
        "logical_type": tipo,
        "type": "VARCHAR(120)",
        "nullable": extra.get("nullable", True),
        "default": extra.get("default"),
        "is_primary_key": extra.get("pk", False),
        "source_refs": [],
    }


def tabla(id_: str, nombre: str, *columnas: dict, reconciliation=None) -> dict:
    datos = {
        "id": id_,
        "name": nombre,
        "kind": "entity",
        "columns": list(columnas),
        "primary_key": {"name": f"pk_{nombre}", "columns": [columnas[0]["name"]]},
        "foreign_keys": [],
        "unique_constraints": [],
        "check_constraints": [],
        "indexes": [],
        "source_refs": [],
    }
    if reconciliation is not None:
        datos["reconciliation"] = reconciliation
    return datos


# --- reparto según veredicto -------------------------------------------------


def test_sin_reconciliacion_todo_se_crea_como_antes():
    """RETROCOMPATIBILIDAD: sin la fase, el DDL es exactamente el de siempre."""
    tablas = [tabla("T1", "envios", columna("envio_id", "bigint", pk=True))]
    a_crear, a_extender, reutilizadas = split_by_reconciliation(tablas)
    assert len(a_crear) == 1
    assert a_extender == [] and reutilizadas == []


def test_un_conflicto_se_trata_como_nuevo():
    """El conflicto ya bloqueó el semáforo; el DDL sigue siendo el del diseño.

    Asumir reutilización sobre algo NO confirmado sería justo el error que el
    conflicto está señalando.
    """
    tablas = [
        tabla(
            "T1",
            "movimientos",
            columna("movimiento_id", "bigint", pk=True),
            reconciliation={"status": "conflict", "reason": "x", "blocking": True},
        )
    ]
    a_crear, _, reutilizadas = split_by_reconciliation(tablas)
    assert len(a_crear) == 1
    assert reutilizadas == []


# --- las consecuencias en el DDL ---------------------------------------------


def test_una_tabla_reutilizada_no_genera_create_ni_drop():
    """Dropear en el rollback una tabla que solo se reutilizaba sería catastrófico."""
    tablas = [
        tabla(
            "T1",
            "usuarios",
            columna("usuario_id", "bigint", pk=True),
            reconciliation={"status": "reuse", "reason": "ya existe"},
        ),
        tabla("T2", "envios", columna("envio_id", "bigint", pk=True)),
    ]
    scripts, _ = build_ddl_scripts(tablas, [], "postgresql")
    sql = "\n".join(s["sql"] for s in scripts)

    assert "CREATE TABLE" in sql and "envios" in sql
    assert "CREATE TABLE usuarios" not in sql
    rollback = next(s for s in scripts if s["kind"] == "rollback")
    assert "usuarios" not in rollback["sql"]
    assert "envios" in rollback["sql"]


def test_una_tabla_extendida_sale_como_alter_no_como_create():
    """EL efecto que justifica el bloque: ALTER en vez de CREATE."""
    tablas = [
        tabla(
            "T1",
            "usuarios",
            columna("usuario_id", "bigint", pk=True),
            columna("nombre"),
            columna("codigo_planilla"),
            reconciliation={
                "status": "extend",
                "reason": "faltan columnas",
                "missing": ["codigo_planilla"],
            },
        )
    ]
    scripts, _ = build_ddl_scripts(tablas, [], "postgresql")
    sql = "\n".join(s["sql"] for s in scripts)

    assert "CREATE TABLE usuarios" not in sql
    alter = next(s for s in scripts if s["kind"] == "alters")
    # La tabla va cualificada con su esquema, igual que en el resto del DDL.
    assert "ALTER TABLE public.usuarios ADD COLUMN" in alter["sql"]
    assert "codigo_planilla" in alter["sql"]
    # Solo lo que falta: `nombre` ya existe en el destino.
    assert "ADD COLUMN nombre" not in alter["sql"]


def test_una_columna_obligatoria_anadida_se_relaja_a_nullable():
    """Un ADD COLUMN NOT NULL sin DEFAULT falla contra una tabla con datos.

    Generar ese ALTER sería entregar un script que revienta al ejecutarlo. Se
    relaja y se deja dicho en el propio script.
    """
    sentencias = render_alter_add_columns(
        {"name": "usuarios"},
        [columna("dni", nullable=False)],
        "postgresql",
    )
    assert "NOT NULL" not in sentencias[0]
    assert "ya tiene datos" in sentencias[0]


def test_la_nota_del_alter_no_se_come_el_punto_y_coma():
    """REGRESIÓN: el comentario iba al FINAL y se tragaba el separador.

    El empaquetador añade `;` a cada sentencia. Con la nota al final, el `;`
    quedaba DENTRO del comentario: la sentencia no terminaba y la siguiente se
    fundía con ella, perdiendo columnas en silencio. Lo destapó ejecutar el
    render de verdad contra el inventario sembrado.
    """
    tablas = [
        tabla(
            "T1",
            "usuarios",
            columna("usuario_id", "bigint", pk=True),
            columna("dni", nullable=False),
            columna("codigo", nullable=False),
            reconciliation={
                "status": "extend",
                "reason": "x",
                "missing": ["dni", "codigo"],
            },
        )
    ]
    scripts, _ = build_ddl_scripts(tablas, [], "postgresql")
    alter = next(s for s in scripts if s["kind"] == "alters")

    # Las DOS columnas llegan como sentencias completas y terminadas.
    assert alter["sql"].count("ADD COLUMN") == 2
    for linea in alter["sql"].splitlines():
        if linea.strip().startswith("--"):
            assert not linea.rstrip().endswith(
                ";"
            ), f"el «;» quedó dentro de un comentario: {linea}"
    for sentencia in alter["statements"]:
        # Cada sentencia acaba en la ALTER, nunca en un comentario.
        assert sentencia.strip().splitlines()[-1].startswith("ALTER TABLE")


def test_una_columna_obligatoria_con_default_se_respeta():
    sentencias = render_alter_add_columns(
        {"name": "usuarios"},
        [columna("activo", nullable=False, default="true")],
        "postgresql",
    )
    assert "NOT NULL" in sentencias[0]


def test_no_se_siembra_un_catalogo_que_se_reutiliza():
    """Sembrarlo duplicaría datos que ya están en producción."""
    tablas = [
        tabla(
            "T1",
            "estados_envio",
            columna("estado_envio_id", "bigint", pk=True),
            columna("nombre"),
            reconciliation={"status": "reuse", "reason": "ya existe"},
        )
    ]
    semilla = [
        {
            "id": "SEED-001",
            "table": "estados_envio",
            "columns": ["nombre"],
            "rows": [{"nombre": "EN TRANSITO"}],
        }
    ]
    scripts, _ = build_ddl_scripts(tablas, semilla, "postgresql")
    assert not any(s["kind"] == "seed" for s in scripts)


def test_los_indices_de_una_tabla_extendida_si_se_crean():
    """Una columna nueva sobre una tabla existente puede necesitar su índice."""
    tablas = [
        tabla(
            "T1",
            "usuarios",
            columna("usuario_id", "bigint", pk=True),
            columna("codigo_planilla"),
            reconciliation={
                "status": "extend",
                "reason": "x",
                "missing": ["codigo_planilla"],
            },
        )
    ]
    tablas[0]["indexes"] = [
        {
            "id": "IDX-1",
            "name": "ix_usuarios_planilla",
            "columns": ["codigo_planilla"],
            "unique": False,
            "rationale": "búsqueda por planilla",
        }
    ]
    scripts, _ = build_ddl_scripts(tablas, [], "postgresql")
    indices = next(s for s in scripts if s["kind"] == "indexes")
    assert "ix_usuarios_planilla" in indices["sql"]


# --- el nodo ----------------------------------------------------------------


async def test_el_nodo_no_tumba_el_pipeline_sin_inventario():
    """Un inventario ausente es una circunstancia normal, no un error.

    El cortafuegos autouse de conftest deja la fase como no ejecutada, que es lo
    que ocurre en un despliegue sin inventario cargado.
    """
    tablas = [tabla("T1", "envios", columna("envio_id", "bigint", pk=True))]
    veredictos, resumen = await reconcile_tables(tablas)
    assert veredictos == {}
    assert resumen["performed"] is False
    assert resumen["reason"], "una fase saltada sin motivo no es auditable"


async def test_el_resumen_encaja_en_el_contrato_aunque_no_se_ejecute():
    from ai.inventory.contract import ReconciliationSummary

    _, resumen = await reconcile_tables([])
    modelo = ReconciliationSummary.model_validate(resumen)
    assert modelo.performed is False
    assert modelo.total == 0


@pytest.mark.parametrize("estado", ["reuse", "extend", "new", "conflict"])
def test_todo_veredicto_es_representable_en_el_ddl(estado: str):
    """Ningún estado puede dejar al renderizador sin saber qué hacer."""
    tablas = [
        tabla(
            "T1",
            "usuarios",
            columna("usuario_id", "bigint", pk=True),
            columna("extra"),
            reconciliation={
                "status": estado,
                "reason": "x",
                "missing": ["extra"],
            },
        )
    ]
    scripts, _ = build_ddl_scripts(tablas, [], "postgresql")
    assert isinstance(scripts, list)
