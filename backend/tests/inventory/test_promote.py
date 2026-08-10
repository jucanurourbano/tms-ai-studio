"""Promoción de artefactos del ISDF al inventario (INV6).

El riesgo del bloque no es convertir mal un artefacto: es **perder lo que ya
estaba**. Un diseño toca unas pocas tablas y el esquema del sistema tiene decenas;
si la promoción reemplazara el activo, el siguiente diseño reconciliaría contra
una foto incompleta y concluiría "no existe, créala" sobre tablas que sí están.
"""

from ai.inventory.promote import (
    api_surface_from_artifact,
    db_schema_from_artifact,
    merge_api_surface,
    merge_db_schema,
)


def artefacto_bd() -> dict:
    return {
        "target": {"engine": "postgresql"},
        "tables": [
            {
                "name": "envios",
                "description": "Envíos de la red",
                "columns": [
                    {
                        "name": "envio_id",
                        "logical_type": "bigint",
                        "type": "BIGINT",
                        "nullable": False,
                        "is_primary_key": True,
                        "description": "Identificador",
                    },
                    {
                        "name": "guia",
                        "logical_type": "string",
                        "type": "VARCHAR(40)",
                        "nullable": False,
                    },
                ],
                "primary_key": {"name": "pk_envios", "columns": ["envio_id"]},
                "foreign_keys": [
                    {
                        "name": "fk_envios_cliente",
                        "columns": ["cliente_id"],
                        "references_table": "clientes",
                        "references_columns": ["cliente_id"],
                        "on_delete": "restrict",
                    }
                ],
                "unique_constraints": [{"name": "ux_guia", "columns": ["guia"]}],
                "check_constraints": [{"name": "ck_peso", "expression": "peso > 0"}],
                "indexes": [
                    {"name": "ix_envios_guia", "columns": ["guia"], "unique": True}
                ],
            }
        ],
    }


# --- conversión --------------------------------------------------------------


def test_el_artefacto_de_bd_se_convierte_en_esquema_inventariable():
    contenido = db_schema_from_artifact(artefacto_bd())
    assert contenido["engine"] == "postgresql"
    tabla = contenido["tables"][0]
    assert tabla["name"] == "envios"
    assert tabla["primary_key"] == ["envio_id"]
    assert tabla["comment"] == "Envíos de la red"

    columna = tabla["columns"][0]
    # Se guarda el tipo FÍSICO (lo que existirá en el motor) y se conserva el
    # lógico, que es lo que compara RECONCILE.
    assert columna["type"] == "BIGINT"
    assert columna["logical_type"] == "bigint"
    assert columna["primary_key"] is True
    assert columna["nullable"] is False

    assert tabla["foreign_keys"][0]["referenced_table"] == "clientes"
    tipos = {c["kind"] for c in tabla["constraints"]}
    assert tipos == {"unique", "check"}
    assert tabla["indexes"][0]["unique"] is True


def test_lo_convertido_valida_contra_el_contrato_del_activo():
    from app.models.inventory import InventoryAssetType
    from app.schemas.inventario import validate_asset_content

    contenido = db_schema_from_artifact(artefacto_bd())
    assert validate_asset_content(InventoryAssetType.DB_SCHEMA, contenido)["tables"]


def test_el_artefacto_de_api_guarda_la_superficie_no_el_yaml():
    """Un YAML de mil líneas dentro de un activo no lo hace más comparable."""
    artefacto = {
        "target": {"base_path": "/api/v1"},
        "openapi": {"yaml": "openapi: 3.1.0\n..." * 100},
        "endpoints": [
            {
                "method": "get",
                "path": "/api/v1/envios",
                "operation_id": "listarEnvios",
                "kind": "list",
                "purpose": "Listar envíos",
            }
        ],
    }
    contenido = api_surface_from_artifact(artefacto)
    assert contenido["base_path"] == "/api/v1"
    assert contenido["endpoints"][0]["method"] == "GET"
    assert "openapi" not in contenido


def test_una_tabla_reutilizada_tambien_se_promueve():
    """El activo es una FOTO del esquema, no una lista de cambios."""
    artefacto = artefacto_bd()
    artefacto["tables"][0]["reconciliation"] = {"status": "reuse", "reason": "x"}
    contenido = db_schema_from_artifact(artefacto)
    assert len(contenido["tables"]) == 1


# --- EL riesgo: no perder lo que ya estaba -----------------------------------


def test_promover_MEZCLA_y_no_borra_lo_que_el_diseno_no_toca():
    """EL test del bloque.

    Reemplazar dejaría el inventario con una sola tabla y el siguiente diseño
    propondría crear de cero todo lo demás.
    """
    actual = {
        "engine": "postgresql",
        "tables": [
            {"name": "usuarios", "columns": [{"name": "usuario_id"}]},
            {"name": "clientes", "columns": [{"name": "cliente_id"}]},
            {"name": "envios", "columns": [{"name": "viejo"}]},
        ],
    }
    contenido, cambios = merge_db_schema(
        actual, db_schema_from_artifact(artefacto_bd())
    )

    nombres = {t["name"] for t in contenido["tables"]}
    assert nombres == {"usuarios", "clientes", "envios"}
    assert cambios["updated"] == ["envios"]
    assert cambios["added"] == []
    assert set(cambios["kept"]) == {"usuarios", "clientes"}

    # Y la tabla que el diseño SÍ define queda con su versión nueva.
    envios = next(t for t in contenido["tables"] if t["name"] == "envios")
    assert {c["name"] for c in envios["columns"]} == {"envio_id", "guia"}


def test_promover_sobre_un_inventario_vacio_anade_todo():
    contenido, cambios = merge_db_schema({}, db_schema_from_artifact(artefacto_bd()))
    assert cambios["added"] == ["envios"]
    assert cambios["updated"] == [] and cambios["kept"] == []
    assert len(contenido["tables"]) == 1


def test_la_mezcla_no_distingue_mayusculas_en_el_nombre():
    """`Envios` y `envios` son la misma tabla: duplicarla rompería RECONCILE."""
    actual = {"tables": [{"name": "Envios", "columns": []}]}
    contenido, cambios = merge_db_schema(actual, {"tables": [{"name": "envios"}]})
    assert len(contenido["tables"]) == 1
    assert cambios["updated"] == ["envios"]


def test_la_superficie_de_api_se_mezcla_por_metodo_y_ruta():
    actual = {
        "base_path": "/api/v1",
        "endpoints": [
            {"method": "GET", "path": "/api/v1/clientes"},
            {"method": "GET", "path": "/api/v1/envios"},
        ],
    }
    entrante = {
        "base_path": "/api/v1",
        "endpoints": [
            {"method": "GET", "path": "/api/v1/envios", "purpose": "nuevo"},
            {"method": "POST", "path": "/api/v1/envios"},
        ],
    }
    contenido, cambios = merge_api_surface(actual, entrante)
    claves = {f"{e['method']} {e['path']}" for e in contenido["endpoints"]}
    assert claves == {
        "GET /api/v1/clientes",
        "GET /api/v1/envios",
        "POST /api/v1/envios",
    }
    assert cambios["added"] == ["POST /api/v1/envios"]
    assert cambios["updated"] == ["GET /api/v1/envios"]
    assert cambios["kept"] == ["GET /api/v1/clientes"]
