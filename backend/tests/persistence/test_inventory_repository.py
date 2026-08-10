"""Persistencia del Inventario de Sistemas (INV1).

El foco está en el **versionado**, que es donde vive el riesgo: recargar un activo
no puede pisar lo anterior, y la versión vigente tiene que resolverse sola sin
banderas que puedan desincronizarse.
"""

import pytest

from app.errors import ConflictError, NotFoundError
from app.models.inventory import (
    InventoryAssetOrigin,
    InventoryAssetType,
    InventorySystemKind,
    InventorySystemStatus,
    InventoryValidationStatus,
)
from app.repositories.inventory_repository import InventoryRepository
from app.services.inventory_service import InventoryService


def esquema(*tablas: str) -> dict:
    """Contenido mínimo válido de un activo ``db_schema``."""
    return {
        "engine": "postgresql",
        "tables": [
            {
                "name": t,
                "columns": [
                    {"name": f"{t}_id", "type": "bigint", "primary_key": True},
                    {"name": "nombre", "type": "character varying(120)"},
                ],
                "primary_key": [f"{t}_id"],
            }
            for t in tablas
        ],
    }


@pytest.fixture
def repo(session):
    return InventoryRepository(session)


@pytest.fixture
def service(session):
    return InventoryService(session)


async def _sistema(repo, name="TMS Moderno", kind=InventorySystemKind.DESTINO):
    return await repo.create_system(name=name, kind=kind)


# --- sistemas ---------------------------------------------------------------


async def test_alta_y_listado_de_sistemas(repo):
    await _sistema(repo, "TMS Legado", InventorySystemKind.LEGADO)
    await _sistema(repo, "TMS Moderno", InventorySystemKind.DESTINO)

    todos = await repo.list_systems()
    assert [s.name for s in todos] == ["TMS Legado", "TMS Moderno"]  # orden estable

    solo_destino = await repo.list_systems(kind=InventorySystemKind.DESTINO)
    assert [s.name for s in solo_destino] == ["TMS Moderno"]


async def test_el_sistema_nace_activo_y_sin_activos(repo):
    system = await _sistema(repo)
    assert system.status is InventorySystemStatus.ACTIVO
    assert await repo.list_current_assets(system.id) == []
    assert await repo.count_assets_by_type(system.id) == {}


# --- versionado (el corazón del bloque) -------------------------------------


async def test_recargar_un_activo_crea_version_nueva_y_conserva_la_anterior(repo):
    """La regla que define el inventario: recargar NO pisa.

    Perder el esquema anterior haría imposible explicar por qué un diseño pasado
    decidió lo que decidió.
    """
    system = await _sistema(repo)

    v1 = await repo.add_asset_version(
        system_id=system.id,
        asset_type=InventoryAssetType.DB_SCHEMA,
        name="core",
        content=esquema("usuarios"),
        origin=InventoryAssetOrigin.DDL_DUMP,
        origin_ref="dump-enero.sql",
    )
    v2 = await repo.add_asset_version(
        system_id=system.id,
        asset_type=InventoryAssetType.DB_SCHEMA,
        name="core",
        content=esquema("usuarios", "envios"),
        origin=InventoryAssetOrigin.DDL_DUMP,
        origin_ref="dump-agosto.sql",
    )

    assert v1.version == 1
    assert v2.version == 2
    # La versión 1 sigue ahí, con su contenido intacto.
    anterior = await repo.get_asset(v1.id)
    assert anterior is not None
    assert len(anterior.content["tables"]) == 1
    assert anterior.origin_ref == "dump-enero.sql"


async def test_la_version_vigente_es_la_mayor_sin_bandera_que_mantener(repo):
    """`list_current_assets` devuelve una sola fila por activo: la última."""
    system = await _sistema(repo)
    for i in range(3):
        await repo.add_asset_version(
            system_id=system.id,
            asset_type=InventoryAssetType.DB_SCHEMA,
            name="core",
            content=esquema(*[f"t{j}" for j in range(i + 1)]),
            origin=InventoryAssetOrigin.DDL_DUMP,
        )

    vigentes = await repo.list_current_assets(system.id)
    assert len(vigentes) == 1
    assert vigentes[0].version == 3
    assert len(vigentes[0].content["tables"]) == 3

    # Y el historial completo sigue disponible, del más reciente al primero.
    historial = await repo.list_asset_versions(
        system.id, InventoryAssetType.DB_SCHEMA, "core"
    )
    assert [v.version for v in historial] == [3, 2, 1]


async def test_activos_distintos_versionan_por_separado(repo):
    """El contador es por ``(sistema, tipo, nombre)``, no global.

    Si fuera global, cargar el esquema haría que el siguiente módulo naciera en
    la versión 2 sin haber tenido nunca una versión 1.
    """
    system = await _sistema(repo)
    await repo.add_asset_version(
        system_id=system.id,
        asset_type=InventoryAssetType.DB_SCHEMA,
        name="core",
        content=esquema("usuarios"),
        origin=InventoryAssetOrigin.DDL_DUMP,
    )
    modulo = await repo.add_asset_version(
        system_id=system.id,
        asset_type=InventoryAssetType.MODULE,
        name="Reparto",
        content={"functionalities": ["asignar ruta"]},
        origin=InventoryAssetOrigin.MANUAL,
    )
    assert modulo.version == 1

    vigentes = await repo.list_current_assets(system.id)
    assert {a.name for a in vigentes} == {"core", "Reparto"}
    assert await repo.count_assets_by_type(system.id) == {"db_schema": 1, "module": 1}


async def test_el_mismo_nombre_en_sistemas_distintos_no_colisiona(repo):
    """Dos sistemas pueden tener ambos un esquema llamado `core`."""
    legado = await _sistema(repo, "TMS Legado", InventorySystemKind.LEGADO)
    moderno = await _sistema(repo, "TMS Moderno", InventorySystemKind.DESTINO)
    for system in (legado, moderno):
        asset = await repo.add_asset_version(
            system_id=system.id,
            asset_type=InventoryAssetType.DB_SCHEMA,
            name="core",
            content=esquema("usuarios"),
            origin=InventoryAssetOrigin.DDL_DUMP,
        )
        assert asset.version == 1


async def test_un_activo_nace_importado_no_validado(repo):
    """Cargar no es revisar: RECONCILE decide contra esto y debe saberlo."""
    system = await _sistema(repo)
    asset = await repo.add_asset_version(
        system_id=system.id,
        asset_type=InventoryAssetType.DB_SCHEMA,
        name="core",
        content=esquema("usuarios"),
        origin=InventoryAssetOrigin.INTROSPECTION,
    )
    assert asset.validation_status is InventoryValidationStatus.IMPORTADO

    await repo.set_validation_status(asset, InventoryValidationStatus.VALIDADO)
    assert asset.validation_status is InventoryValidationStatus.VALIDADO


async def test_borrar_una_version_deja_vigente_la_anterior(repo):
    """Eliminar la última carga debe devolver el activo a su estado previo."""
    system = await _sistema(repo)
    v1 = await repo.add_asset_version(
        system_id=system.id,
        asset_type=InventoryAssetType.DB_SCHEMA,
        name="core",
        content=esquema("usuarios"),
        origin=InventoryAssetOrigin.DDL_DUMP,
    )
    v2 = await repo.add_asset_version(
        system_id=system.id,
        asset_type=InventoryAssetType.DB_SCHEMA,
        name="core",
        content=esquema("usuarios", "envios"),
        origin=InventoryAssetOrigin.DDL_DUMP,
    )
    await repo.delete_asset(v2)

    vigentes = await repo.list_current_assets(system.id)
    assert len(vigentes) == 1
    assert vigentes[0].id == v1.id


async def test_borrar_el_sistema_arrastra_activos_y_versiones(repo, session):
    """Cascada: no puede quedar un activo huérfano apuntando a nada."""
    system = await _sistema(repo)
    for _ in range(2):
        await repo.add_asset_version(
            system_id=system.id,
            asset_type=InventoryAssetType.DB_SCHEMA,
            name="core",
            content=esquema("usuarios"),
            origin=InventoryAssetOrigin.DDL_DUMP,
        )
    await repo.delete_system(system)
    assert await repo.get_system(system.id) is None


# --- servicio: validación del contenido y conflictos ------------------------


async def test_el_servicio_rechaza_un_esquema_con_tablas_duplicadas(service, repo):
    """Se valida ANTES de persistir: un duplicado rompería el matching de INV4.

    Dejar entrar el activo y fallar al reconciliar pondría el error a kilómetros
    de su causa.
    """
    system = await _sistema(repo)
    await service.session.commit()

    contenido = esquema("usuarios")
    contenido["tables"].append(contenido["tables"][0])

    with pytest.raises(ConflictError, match="duplicada"):
        await service.add_asset(
            system.id,
            asset_type=InventoryAssetType.DB_SCHEMA,
            name="core",
            content=contenido,
            origin=InventoryAssetOrigin.DDL_DUMP,
        )


async def test_el_servicio_rechaza_contenido_vacio(service, repo):
    system = await _sistema(repo)
    await service.session.commit()
    with pytest.raises(ConflictError, match="vac"):
        await service.add_asset(
            system.id,
            asset_type=InventoryAssetType.MODULE,
            name="Reparto",
            content={},
            origin=InventoryAssetOrigin.MANUAL,
        )


async def test_el_servicio_rechaza_un_sistema_con_nombre_repetido(service):
    await service.create_system(
        name="TMS Moderno",
        kind=InventorySystemKind.DESTINO,
        description=None,
        status=InventorySystemStatus.ACTIVO,
        stack=None,
        actor_id=None,
    )
    with pytest.raises(ConflictError, match="Ya existe"):
        await service.create_system(
            name="TMS Moderno",
            kind=InventorySystemKind.LEGADO,
            description=None,
            status=InventorySystemStatus.ACTIVO,
            stack=None,
            actor_id=None,
        )


async def test_activo_sobre_sistema_inexistente_es_404(service):
    with pytest.raises(NotFoundError):
        await service.add_asset(
            "01JZZZZZZZZZZZZZZZZZZZZZZZ",
            asset_type=InventoryAssetType.MODULE,
            name="Reparto",
            content={"functionalities": []},
            origin=InventoryAssetOrigin.MANUAL,
        )


async def test_el_listado_no_arrastra_los_contenidos(service, repo):
    """Un listado con el JSONB de cada esquema serían cientos de KB inútiles."""
    system = await _sistema(repo)
    await service.session.commit()
    await service.add_asset(
        system.id,
        asset_type=InventoryAssetType.DB_SCHEMA,
        name="core",
        content=esquema("usuarios", "envios"),
        origin=InventoryAssetOrigin.DDL_DUMP,
    )
    items = await service.list_assets(system.id)
    assert "content" not in items[0]
    # Pero el resumen dice lo justo para no tener que abrirlo.
    assert items[0]["summary"] == {"tables": 2, "columns": 4}
