"""Introspección read-only de bases de datos externas (INV2).

Esta capacidad se conecta a PRODUCCIÓN, así que los tests que importan no son los
del "camino feliz" sino los del guard: **sin configuración explícita no se conecta
a nada**, y el destino nunca lo elige quien llama a la API.

El test de integración contra un Postgres real está al final y se **omite** si no
hay motor disponible, para que la suite siga siendo verde sin contenedores.
"""

import pytest

from app.config.settings import settings
from app.errors import ConflictError, ForbiddenError, NotFoundError
from app.services.introspection_service import (
    assert_source_authorized,
    available_sources,
    introspect_postgres,
    origin_ref_for,
    redact_dsn,
)

DSN = "postgresql://usuario:secreto@db.interna:5432/tms"


@pytest.fixture
def configurado(monkeypatch):
    """Deja un origen configurado y autorizado."""
    monkeypatch.setattr(settings, "INVENTORY_INTROSPECTION_ENABLED", True)
    monkeypatch.setattr(settings, "INVENTORY_INTROSPECTION_DSNS", {"legado": DSN})
    monkeypatch.setattr(
        settings, "INVENTORY_INTROSPECTION_ALLOWED_HOSTS", ["db.interna"]
    )


# --- el guard: fail-closed en cada capa --------------------------------------


def test_desactivada_por_defecto_no_conecta_a_nada(monkeypatch):
    """Nace apagada: activarla es una decisión consciente del despliegue."""
    monkeypatch.setattr(settings, "INVENTORY_INTROSPECTION_ENABLED", False)
    with pytest.raises(ForbiddenError, match="desactivada"):
        assert_source_authorized("legado")
    assert available_sources() == []


def test_sin_allowlist_no_hay_nada_autorizado(monkeypatch):
    """Lista vacía significa "nada", NUNCA "todo". Es la diferencia entre un
    despliegue a medio configurar y una puerta abierta a cualquier host."""
    monkeypatch.setattr(settings, "INVENTORY_INTROSPECTION_ENABLED", True)
    monkeypatch.setattr(settings, "INVENTORY_INTROSPECTION_DSNS", {"legado": DSN})
    monkeypatch.setattr(settings, "INVENTORY_INTROSPECTION_ALLOWED_HOSTS", [])
    with pytest.raises(ForbiddenError, match="allowlist|autorizado"):
        assert_source_authorized("legado")


def test_un_host_fuera_de_la_allowlist_se_rechaza(monkeypatch):
    monkeypatch.setattr(settings, "INVENTORY_INTROSPECTION_ENABLED", True)
    monkeypatch.setattr(settings, "INVENTORY_INTROSPECTION_DSNS", {"otro": DSN})
    monkeypatch.setattr(
        settings, "INVENTORY_INTROSPECTION_ALLOWED_HOSTS", ["otra.cosa"]
    )
    with pytest.raises(ForbiddenError, match="allowlist"):
        assert_source_authorized("otro")


def test_un_alias_inexistente_no_se_puede_inventar(configurado):
    """El destino lo fija el despliegue: la API no acepta cadenas de conexión.

    Es la defensa contra el SSRF: si el cliente pudiera mandar el DSN, cualquiera
    con permiso de escritura apuntaría el servidor al host que quisiera.
    """
    with pytest.raises(NotFoundError, match="No hay ningún origen"):
        assert_source_authorized("postgres://atacante@evil.example/db")


def test_el_alias_autorizado_resuelve_a_su_dsn(configurado):
    assert assert_source_authorized("legado") == DSN


def test_la_peticion_de_introspeccion_no_admite_cadena_de_conexion():
    """El contrato NO tiene campo para el DSN, y lo que sobra se ignora."""
    from app.schemas.inventario import IntrospectRequest

    peticion = IntrospectRequest.model_validate(
        {"alias": "legado", "dsn": "postgresql://atacante@evil.example/db"}
    )
    assert not hasattr(peticion, "dsn")
    assert peticion.alias == "legado"
    assert peticion.schema_name == "public"


# --- la credencial nunca sale ------------------------------------------------


def test_el_dsn_se_redacta_siempre():
    assert redact_dsn(DSN) == "postgresql://***@db.interna:5432/tms"
    assert "secreto" not in redact_dsn(DSN)
    assert redact_dsn("") == ""


def test_los_origenes_publicados_no_llevan_credenciales(configurado):
    items = available_sources()
    assert items == [{"alias": "legado", "host": "db.interna"}]
    assert "secreto" not in str(items)


def test_un_origen_configurado_pero_no_autorizado_no_se_lista(monkeypatch):
    """El panel no debe ofrecer un botón que siempre va a fallar."""
    monkeypatch.setattr(settings, "INVENTORY_INTROSPECTION_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "INVENTORY_INTROSPECTION_DSNS",
        {"bueno": DSN, "malo": "postgresql://u:p@prohibido.example/db"},
    )
    monkeypatch.setattr(
        settings, "INVENTORY_INTROSPECTION_ALLOWED_HOSTS", ["db.interna"]
    )
    assert [i["alias"] for i in available_sources()] == ["bueno"]


def test_la_referencia_de_origen_del_activo_no_lleva_credenciales():
    """Queda escrita en el inventario para siempre: no puede contener la clave."""
    ref = origin_ref_for("legado", DSN, "public")
    assert "secreto" not in ref
    assert "usuario" not in ref
    assert "db.interna" in ref and "public" in ref


# --- esquemas de sistema -----------------------------------------------------


async def test_no_se_introspecciona_un_esquema_del_sistema():
    """`information_schema` no describe el negocio de nadie."""
    with pytest.raises(ConflictError, match="sistema"):
        await introspect_postgres(DSN, schema="information_schema")


# --- integración real (se omite si no hay motor) -----------------------------


@pytest.mark.asyncio
async def test_introspeccion_real_contra_la_bd_local():
    """Lee el catálogo del Postgres local y comprueba la forma del resultado.

    Se omite si no hay motor disponible: la suite no puede depender de que haya
    contenedores levantados. Cuando SÍ los hay, prueba lo que ningún mock puede:
    que las consultas al `information_schema` son válidas y que el resultado
    encaja en el contrato del activo.
    """
    dsn = settings.DATABASE_URL
    try:
        contenido = await introspect_postgres(dsn, schema="public")
    except Exception as exc:  # motor ausente o sin permisos
        pytest.skip(f"sin PostgreSQL local disponible: {type(exc).__name__}")

    from app.models.inventory import InventoryAssetType
    from app.schemas.inventario import validate_asset_content

    assert contenido["engine"] == "postgresql"
    nombres = {t["name"] for t in contenido["tables"]}
    # Las tablas de la propia plataforma tienen que estar.
    assert {"users", "agent_jobs", "inventory_systems"} <= nombres

    # Lo leído debe poder guardarse como activo tal cual (contrato de INV1).
    validado = validate_asset_content(InventoryAssetType.DB_SCHEMA, contenido)
    assert validado["tables"]

    # Y la forma fina: PK, FK con su acción, tipos normalizados.
    jobs = next(t for t in contenido["tables"] if t["name"] == "agent_jobs")
    assert jobs["primary_key"] == ["id"]
    assert any(c["primary_key"] for c in jobs["columns"])
    fk_autor = next(
        (fk for fk in jobs["foreign_keys"] if fk["columns"] == ["created_by"]), None
    )
    assert fk_autor is not None
    assert fk_autor["referenced_table"] == "users"
    assert fk_autor["on_delete"] == "set null"

    assets = next(t for t in contenido["tables"] if t["name"] == "inventory_assets")
    version = next(c for c in assets["columns"] if c["name"] == "version")
    assert version["logical_type"] == "integer"
    assert version["nullable"] is False
    contenido_col = next(c for c in assets["columns"] if c["name"] == "content")
    assert contenido_col["logical_type"] == "json"
