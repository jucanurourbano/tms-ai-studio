"""Repositorio del Inventario de Sistemas (capa repositories).

Persistencia pura: no decide permisos ni valida contenidos (eso es del servicio).

La pieza no obvia es el **versionado**. Un activo recargado no se sobrescribe:
se inserta una fila nueva con ``version = anterior + 1``. La versión vigente es la
de mayor ``version`` dentro de ``(system_id, asset_type, name)`` y se calcula al
leer, con un ``GROUP BY`` que solo toca la clave — nunca se cargan los JSONB de
las versiones antiguas para descartarlos después.
"""

from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import (
    InventoryAsset,
    InventoryAssetOrigin,
    InventoryAssetType,
    InventorySystem,
    InventorySystemKind,
    InventorySystemStatus,
    InventoryValidationStatus,
)


class InventoryRepository:
    """Operaciones de persistencia del inventario."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- sistemas -----------------------------------------------------------

    async def list_systems(
        self, *, kind: Optional[InventorySystemKind] = None
    ) -> list[InventorySystem]:
        """Sistemas del inventario, en orden estable por nombre."""
        query = select(InventorySystem).order_by(InventorySystem.name.asc())
        if kind is not None:
            query = query.where(InventorySystem.kind == kind)
        return list(await self.session.scalars(query))

    async def get_system(self, system_id: str) -> Optional[InventorySystem]:
        """Un sistema por id (``None`` si no existe)."""
        return await self.session.get(InventorySystem, system_id)

    async def get_system_by_name(self, name: str) -> Optional[InventorySystem]:
        """Un sistema por nombre exacto (el nombre es único)."""
        return await self.session.scalar(
            select(InventorySystem).where(InventorySystem.name == name)
        )

    async def create_system(
        self,
        *,
        name: str,
        kind: InventorySystemKind,
        description: Optional[str] = None,
        status: InventorySystemStatus = InventorySystemStatus.ACTIVO,
        stack: Optional[list] = None,
        created_by: Optional[str] = None,
    ) -> InventorySystem:
        """Da de alta un sistema."""
        system = InventorySystem(
            name=name,
            kind=kind,
            description=description,
            status=status,
            stack=stack,
            created_by=created_by,
        )
        self.session.add(system)
        await self.session.flush()
        return system

    async def delete_system(self, system: InventorySystem) -> None:
        """Elimina el sistema y, en cascada, todos sus activos y versiones."""
        await self.session.delete(system)
        await self.session.flush()

    # --- activos ------------------------------------------------------------

    async def get_asset(self, asset_id: str) -> Optional[InventoryAsset]:
        """Un activo por id, en la versión concreta que se guardó."""
        return await self.session.get(InventoryAsset, asset_id)

    async def latest_version(
        self, system_id: str, asset_type: InventoryAssetType, name: str
    ) -> int:
        """Número de la última versión de un activo (``0`` si aún no existe)."""
        version = await self.session.scalar(
            select(func.max(InventoryAsset.version)).where(
                InventoryAsset.system_id == system_id,
                InventoryAsset.asset_type == asset_type,
                InventoryAsset.name == name,
            )
        )
        return int(version or 0)

    async def add_asset_version(
        self,
        *,
        system_id: str,
        asset_type: InventoryAssetType,
        name: str,
        content: dict,
        origin: InventoryAssetOrigin,
        origin_ref: Optional[str] = None,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> InventoryAsset:
        """Inserta una versión nueva del activo, conservando las anteriores.

        Toda carga pasa por aquí: la primera crea la versión 1 y las siguientes
        incrementan. Nace siempre como ``importado`` — que alguien lo cargue no
        significa que alguien lo haya revisado.
        """
        asset = InventoryAsset(
            system_id=system_id,
            asset_type=asset_type,
            name=name,
            content=content,
            origin=origin,
            origin_ref=origin_ref,
            description=description,
            created_by=created_by,
            version=await self.latest_version(system_id, asset_type, name) + 1,
            validation_status=InventoryValidationStatus.IMPORTADO,
        )
        self.session.add(asset)
        await self.session.flush()
        return asset

    async def list_current_assets(
        self,
        system_id: str,
        *,
        asset_type: Optional[InventoryAssetType] = None,
    ) -> list[InventoryAsset]:
        """Activos de un sistema en su **versión vigente** (la mayor de cada uno).

        El ``GROUP BY`` de la subconsulta solo agrega la clave y el número de
        versión: los ``content`` de las versiones antiguas nunca se leen.
        """
        ultimas = (
            select(
                InventoryAsset.asset_type.label("asset_type"),
                InventoryAsset.name.label("name"),
                func.max(InventoryAsset.version).label("version"),
            )
            .where(InventoryAsset.system_id == system_id)
            .group_by(InventoryAsset.asset_type, InventoryAsset.name)
            .subquery()
        )
        query = (
            select(InventoryAsset)
            .join(
                ultimas,
                and_(
                    InventoryAsset.asset_type == ultimas.c.asset_type,
                    InventoryAsset.name == ultimas.c.name,
                    InventoryAsset.version == ultimas.c.version,
                ),
            )
            .where(InventoryAsset.system_id == system_id)
            .order_by(InventoryAsset.asset_type.asc(), InventoryAsset.name.asc())
        )
        if asset_type is not None:
            query = query.where(InventoryAsset.asset_type == asset_type)
        return list(await self.session.scalars(query))

    async def get_current_asset(
        self, system_id: str, asset_type: InventoryAssetType, name: str
    ) -> Optional[InventoryAsset]:
        """Versión vigente de un activo concreto."""
        return await self.session.scalar(
            select(InventoryAsset)
            .where(
                InventoryAsset.system_id == system_id,
                InventoryAsset.asset_type == asset_type,
                InventoryAsset.name == name,
            )
            .order_by(InventoryAsset.version.desc())
            .limit(1)
        )

    async def list_asset_versions(
        self, system_id: str, asset_type: InventoryAssetType, name: str
    ) -> list[InventoryAsset]:
        """Historial completo de un activo, de la versión más reciente a la primera."""
        return list(
            await self.session.scalars(
                select(InventoryAsset)
                .where(
                    InventoryAsset.system_id == system_id,
                    InventoryAsset.asset_type == asset_type,
                    InventoryAsset.name == name,
                )
                .order_by(InventoryAsset.version.desc())
            )
        )

    async def set_validation_status(
        self, asset: InventoryAsset, status: InventoryValidationStatus
    ) -> InventoryAsset:
        """Marca una versión concreta como revisada (o la devuelve a importada)."""
        asset.validation_status = status
        await self.session.flush()
        return asset

    async def delete_asset(self, asset: InventoryAsset) -> None:
        """Elimina UNA versión del activo (las demás siguen ahí)."""
        await self.session.delete(asset)
        await self.session.flush()

    async def count_assets_by_type(self, system_id: str) -> dict[str, int]:
        """Conteo de activos VIGENTES por tipo (para las tarjetas del panel)."""
        assets = await self.list_current_assets(system_id)
        conteo: dict[str, int] = {}
        for asset in assets:
            conteo[asset.asset_type.value] = conteo.get(asset.asset_type.value, 0) + 1
        return conteo
