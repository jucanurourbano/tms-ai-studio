"""Servicio del Inventario de Sistemas (capa services).

Orquesta el repositorio, valida las reglas de negocio del inventario y traduce
los fallos a los errores de aplicación que el middleware convierte en respuestas
del envelope (``ConflictError`` 409, ``NotFoundError`` 404).

Regla central: **una recarga nunca pisa lo anterior**. Volver a subir el esquema
de un sistema crea la versión siguiente y conserva la previa, porque el inventario
es la memoria de lo que existe y perder el estado anterior impediría explicar por
qué un diseño anterior decidió lo que decidió.
"""

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai.inventory.promote import (
    PROMOTABLE_STATUSES,
    api_surface_from_artifact,
    db_schema_from_artifact,
    merge_api_surface,
    merge_db_schema,
)
from app.errors import ConflictError, NotFoundError
from app.models.inventory import (
    InventoryAsset,
    InventoryAssetOrigin,
    InventoryAssetType,
    InventorySystem,
    InventorySystemKind,
    InventorySystemStatus,
    InventoryValidationStatus,
)
from app.repositories.inventory_repository import InventoryRepository
from app.schemas.inventario import validate_asset_content


def system_to_dict(system: InventorySystem) -> dict[str, Any]:
    """Serializa un sistema para la API."""
    return {
        "id": system.id,
        "name": system.name,
        "description": system.description,
        "kind": system.kind.value,
        "status": system.status.value,
        "stack": system.stack or [],
        "created_at": system.created_at.isoformat() if system.created_at else None,
        "updated_at": system.updated_at.isoformat() if system.updated_at else None,
    }


def asset_to_dict(
    asset: InventoryAsset, *, include_content: bool = True
) -> dict[str, Any]:
    """Serializa un activo. ``include_content=False`` para los listados.

    Un listado de activos con el JSONB completo de cada esquema de BD serían
    cientos de kilobytes que la lista no pinta: el contenido se pide al abrir el
    activo.
    """
    data: dict[str, Any] = {
        "id": asset.id,
        "system_id": asset.system_id,
        "asset_type": asset.asset_type.value,
        "name": asset.name,
        "description": asset.description,
        "origin": asset.origin.value,
        "origin_ref": asset.origin_ref,
        "version": asset.version,
        "validation_status": asset.validation_status.value,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
    }
    if include_content:
        data["content"] = asset.content
    else:
        data["summary"] = summarize_content(asset)
    return data


def summarize_content(asset: InventoryAsset) -> dict[str, Any]:
    """Resumen barato del contenido, para que el listado diga algo útil.

    Un activo que en la lista solo muestra su nombre obliga a abrirlo para saber
    si tiene 3 tablas o 300.
    """
    content = asset.content or {}
    if asset.asset_type is InventoryAssetType.DB_SCHEMA:
        tablas = content.get("tables") or []
        return {
            "tables": len(tablas),
            "columns": sum(len(t.get("columns") or []) for t in tablas),
        }
    if asset.asset_type is InventoryAssetType.API:
        return {"endpoints": len(content.get("endpoints") or [])}
    if asset.asset_type is InventoryAssetType.MODULE:
        return {
            "functionalities": len(content.get("functionalities") or []),
            "entities": len(content.get("entities") or []),
        }
    return {"keys": len(content)}


class InventoryService:
    """Casos de uso del inventario."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = InventoryRepository(session)

    # --- sistemas -----------------------------------------------------------

    async def list_systems(
        self, *, kind: Optional[InventorySystemKind] = None
    ) -> list[dict[str, Any]]:
        """Sistemas del inventario con el conteo de sus activos vigentes."""
        systems = await self.repo.list_systems(kind=kind)
        salida = []
        for system in systems:
            data = system_to_dict(system)
            data["asset_counts"] = await self.repo.count_assets_by_type(system.id)
            salida.append(data)
        return salida

    async def get_system_or_404(self, system_id: str) -> InventorySystem:
        """Sistema por id, o ``NotFoundError``."""
        system = await self.repo.get_system(system_id)
        if system is None:
            raise NotFoundError(f"No existe el sistema «{system_id}» en el inventario.")
        return system

    async def get_system_detail(self, system_id: str) -> dict[str, Any]:
        """Ficha del sistema con sus activos vigentes (sin contenidos)."""
        system = await self.get_system_or_404(system_id)
        assets = await self.repo.list_current_assets(system_id)
        data = system_to_dict(system)
        data["assets"] = [asset_to_dict(a, include_content=False) for a in assets]
        data["asset_counts"] = await self.repo.count_assets_by_type(system_id)
        return data

    async def create_system(
        self,
        *,
        name: str,
        kind: InventorySystemKind,
        description: Optional[str],
        status: InventorySystemStatus,
        stack: Optional[list],
        actor_id: Optional[str],
    ) -> dict[str, Any]:
        """Da de alta un sistema. El nombre es único en el inventario."""
        if await self.repo.get_system_by_name(name) is not None:
            raise ConflictError(f"Ya existe un sistema llamado «{name}».")
        system = await self.repo.create_system(
            name=name,
            kind=kind,
            description=description,
            status=status,
            stack=stack,
            created_by=actor_id,
        )
        await self.session.commit()
        return system_to_dict(system)

    async def update_system(
        self, system_id: str, cambios: dict[str, Any]
    ) -> dict[str, Any]:
        """Edita el sistema aplicando **solo lo informado**."""
        system = await self.get_system_or_404(system_id)
        nombre = cambios.get("name")
        if nombre is not None and nombre != system.name:
            existente = await self.repo.get_system_by_name(nombre)
            if existente is not None and existente.id != system.id:
                raise ConflictError(f"Ya existe un sistema llamado «{nombre}».")
            system.name = nombre
        for campo in ("description", "kind", "status", "stack"):
            if cambios.get(campo) is not None:
                setattr(system, campo, cambios[campo])
        await self.session.commit()
        # `updated_at` lleva `onupdate=func.now()`: tras un UPDATE, SQLAlchemy no
        # conoce el valor que calculó el servidor y expira el atributo. Serializar
        # sin refrescar dispararía la carga FUERA del contexto async (MissingGreenlet).
        await self.session.refresh(system)
        return system_to_dict(system)

    async def delete_system(self, system_id: str) -> None:
        """Elimina el sistema con todos sus activos y su historial de versiones."""
        system = await self.get_system_or_404(system_id)
        await self.repo.delete_system(system)
        await self.session.commit()

    # --- activos ------------------------------------------------------------

    async def add_asset(
        self,
        system_id: str,
        *,
        asset_type: InventoryAssetType,
        name: str,
        content: dict[str, Any],
        origin: InventoryAssetOrigin,
        origin_ref: Optional[str] = None,
        description: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Registra un activo, o una versión nueva si ya existía ese nombre.

        El contenido se valida contra la forma de su tipo ANTES de persistir: un
        ``db_schema`` con tablas duplicadas o sin nombre entraría al inventario y
        rompería el matching de RECONCILE mucho más tarde, lejos de la causa.
        """
        await self.get_system_or_404(system_id)
        try:
            validado = validate_asset_content(asset_type, content)
        except ValueError as exc:
            raise ConflictError(
                f"El contenido del activo «{name}» no tiene la forma esperada "
                f"para un activo de tipo «{asset_type.value}»: {exc}"
            ) from exc

        asset = await self.repo.add_asset_version(
            system_id=system_id,
            asset_type=asset_type,
            name=name,
            content=validado,
            origin=origin,
            origin_ref=origin_ref,
            description=description,
            created_by=actor_id,
        )
        await self.session.commit()
        return asset_to_dict(asset)

    async def get_asset_or_404(self, asset_id: str) -> InventoryAsset:
        """Activo por id, o ``NotFoundError``."""
        asset = await self.repo.get_asset(asset_id)
        if asset is None:
            raise NotFoundError(f"No existe el activo «{asset_id}» en el inventario.")
        return asset

    async def get_asset(self, asset_id: str) -> dict[str, Any]:
        """Activo completo, con su contenido."""
        return asset_to_dict(await self.get_asset_or_404(asset_id))

    async def list_assets(
        self,
        system_id: str,
        *,
        asset_type: Optional[InventoryAssetType] = None,
    ) -> list[dict[str, Any]]:
        """Activos vigentes del sistema (sin contenidos)."""
        await self.get_system_or_404(system_id)
        assets = await self.repo.list_current_assets(system_id, asset_type=asset_type)
        return [asset_to_dict(a, include_content=False) for a in assets]

    async def list_versions(self, asset_id: str) -> list[dict[str, Any]]:
        """Historial de versiones del activo al que pertenece ``asset_id``."""
        asset = await self.get_asset_or_404(asset_id)
        versiones = await self.repo.list_asset_versions(
            asset.system_id, asset.asset_type, asset.name
        )
        return [asset_to_dict(v, include_content=False) for v in versiones]

    async def set_validation_status(
        self, asset_id: str, status: InventoryValidationStatus
    ) -> dict[str, Any]:
        """Marca el activo como revisado por una persona (o lo revierte)."""
        asset = await self.get_asset_or_404(asset_id)
        await self.repo.set_validation_status(asset, status)
        await self.session.commit()
        # Ver la nota de `update_system`: `updated_at` queda expirado tras el UPDATE.
        await self.session.refresh(asset)
        return asset_to_dict(asset, include_content=False)

    async def delete_asset(self, asset_id: str) -> None:
        """Elimina UNA versión del activo."""
        asset = await self.get_asset_or_404(asset_id)
        await self.repo.delete_asset(asset)
        await self.session.commit()

    async def promote_job(
        self,
        system_id: str,
        job_id: str,
        *,
        asset_name: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Promueve el artefacto de un job de BD o API al inventario (INV6).

        Cierra el ciclo: los agentes leen el inventario para reconciliar y ahora
        también lo alimentan, así que cada proyecto entregado engorda la memoria de
        la organización sin que nadie la mantenga a mano.

        **Se mezcla, no se reemplaza.** Un diseño toca unas pocas tablas; el
        esquema del sistema tiene decenas. Reemplazar borraría del inventario todo
        lo que este diseño no menciona, y el siguiente reconciliaría contra una
        foto incompleta concluyendo "no existe, créala" sobre tablas que sí están.
        """
        from app.models.agent import AgentType
        from app.repositories.agent_job_repository import AgentJobRepository

        system = await self.get_system_or_404(system_id)
        jobs = AgentJobRepository(self.session)

        job = await jobs.get_job(job_id)
        if job is None:
            raise NotFoundError(f"No existe el job «{job_id}».")
        if job.status.value not in PROMOTABLE_STATUSES:
            raise ConflictError(
                f"El job está en estado «{job.status.value}»: solo se promueve un "
                "trabajo terminado, porque un artefacto a medias metería en el "
                "inventario un diseño que nadie completó."
            )
        if job.agent_type not in (AgentType.BD, AgentType.API):
            raise ConflictError(
                f"Un job de «{job.agent_type.value}» no produce activos "
                "inventariables. Solo se promueven modelos de datos (BD) y "
                "contratos de API."
            )

        fila = await jobs.get_artifact(job_id)
        if fila is None:
            raise ConflictError(f"El job «{job_id}» no tiene artefacto guardado.")
        artifact = fila.data or {}

        if job.agent_type is AgentType.BD:
            asset_type = InventoryAssetType.DB_SCHEMA
            nombre = asset_name or "core"
            entrante = db_schema_from_artifact(artifact)
            fusionar = merge_db_schema
        else:
            asset_type = InventoryAssetType.API
            nombre = asset_name or "api"
            entrante = api_surface_from_artifact(artifact)
            fusionar = merge_api_surface

        vigente = await self.repo.get_current_asset(system_id, asset_type, nombre)
        contenido, cambios = fusionar(
            (vigente.content if vigente is not None else {}) or {}, entrante
        )

        asset = await self.repo.add_asset_version(
            system_id=system_id,
            asset_type=asset_type,
            name=nombre,
            content=validate_asset_content(asset_type, contenido),
            origin=InventoryAssetOrigin.ISDF,
            origin_ref=f"generado por ISDF · agente {job.agent_type.value} · job {job_id}",
            description=(
                f"Promovido desde el job {job_id} del agente "
                f"{job.agent_type.value}."
            ),
            created_by=actor_id,
        )
        await self.session.commit()

        data = asset_to_dict(asset, include_content=False)
        data["changes"] = cambios
        data["system_name"] = system.name
        return data

    async def add_assets_bulk(
        self,
        system_id: str,
        activos: list[dict[str, Any]],
        *,
        origin: InventoryAssetOrigin,
        origin_ref: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Registra varios activos en UNA transacción (carga de documento, INV3).

        O entran todos o no entra ninguno: un documento que dejara a medias sus
        módulos produciría un inventario que dice tener menos de lo que el
        documento describe, y eso es indistinguible de un sistema que realmente
        tiene menos.
        """
        await self.get_system_or_404(system_id)
        creados: list[dict[str, Any]] = []
        for activo in activos:
            asset_type = InventoryAssetType(activo["asset_type"])
            try:
                contenido = validate_asset_content(asset_type, activo["content"])
            except ValueError as exc:
                raise ConflictError(
                    f"El activo «{activo['name']}» no tiene la forma esperada: {exc}"
                ) from exc
            asset = await self.repo.add_asset_version(
                system_id=system_id,
                asset_type=asset_type,
                name=activo["name"],
                content=contenido,
                origin=origin,
                origin_ref=origin_ref,
                description=activo.get("description"),
                created_by=actor_id,
            )
            creados.append(asset_to_dict(asset, include_content=False))
        await self.session.commit()
        return creados
