"""Endpoints del Inventario de Sistemas (API v1). Toda respuesta usa ApiResponse.

Lectura para todos los roles (el inventario es conocimiento transversal) y
escritura para ``admin``/``arquitecto``, que son quienes lo curan. Ver la
justificación de la excepción a la regla de forma en ``app/core/permissions.py``.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import AccessLevel, Module
from app.dependencies.database import get_session
from app.dependencies.permissions import require_module
from app.models.inventory import InventoryAssetType, InventorySystemKind
from app.models.user import User
from app.schemas.inventario import (
    CreateAssetRequest,
    CreateSystemRequest,
    UpdateAssetStatusRequest,
    UpdateSystemRequest,
)
from app.services.inventory_service import InventoryService
from shared.responses.api_response import ApiResponse

_READ = Depends(require_module(Module.INVENTARIO, AccessLevel.READ))
_WRITE = Depends(require_module(Module.INVENTARIO, AccessLevel.FULL))

router = APIRouter(
    prefix="/inventario",
    tags=["Inventario de Sistemas"],
    dependencies=[_READ],
)


def _service(session: AsyncSession) -> InventoryService:
    return InventoryService(session)


# --- sistemas ---------------------------------------------------------------


@router.get("/systems", summary="Sistemas inventariados")
async def list_systems(
    session: AsyncSession = Depends(get_session),
    kind: Optional[InventorySystemKind] = Query(
        None, description="Filtra por papel del sistema (destino/legado/externo)"
    ),
) -> ApiResponse:
    """Lista los sistemas con el conteo de sus activos vigentes por tipo."""
    items = await _service(session).list_systems(kind=kind)
    return ApiResponse.ok(data={"items": items})


@router.post("/systems", summary="Registrar un sistema en el inventario")
async def create_system(
    body: CreateSystemRequest,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Da de alta un sistema. El nombre es único (409 si ya existe)."""
    data = await _service(session).create_system(
        name=body.name,
        kind=body.kind,
        description=body.description,
        status=body.status,
        stack=[s.model_dump(mode="json") for s in body.stack] if body.stack else None,
        actor_id=actor.id,
    )
    return ApiResponse.ok(data=data, message="Sistema registrado en el inventario")


@router.get("/systems/{system_id}", summary="Ficha de un sistema y sus activos")
async def get_system(
    system_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve el sistema con sus activos vigentes (sin los contenidos)."""
    return ApiResponse.ok(data=await _service(session).get_system_detail(system_id))


@router.patch("/systems/{system_id}", summary="Editar un sistema")
async def update_system(
    system_id: str,
    body: UpdateSystemRequest,
    _actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Aplica **solo lo informado**; los campos ausentes no se tocan."""
    cambios = body.model_dump(exclude_unset=True)
    if body.stack is not None:
        cambios["stack"] = [s.model_dump(mode="json") for s in body.stack]
    data = await _service(session).update_system(system_id, cambios)
    return ApiResponse.ok(data=data, message="Sistema actualizado")


@router.delete("/systems/{system_id}", summary="Eliminar un sistema del inventario")
async def delete_system(
    system_id: str,
    _actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Elimina el sistema **con todos sus activos y versiones** (en cascada)."""
    await _service(session).delete_system(system_id)
    return ApiResponse.ok(
        data={"system_id": system_id}, message="Sistema eliminado del inventario"
    )


# --- activos ----------------------------------------------------------------


@router.get("/systems/{system_id}/assets", summary="Activos vigentes de un sistema")
async def list_assets(
    system_id: str,
    session: AsyncSession = Depends(get_session),
    asset_type: Optional[InventoryAssetType] = Query(
        None, description="Filtra por tipo (db_schema/module/api/document)"
    ),
) -> ApiResponse:
    """Lista los activos en su versión vigente, con un resumen de su contenido."""
    items = await _service(session).list_assets(system_id, asset_type=asset_type)
    return ApiResponse.ok(data={"items": items})


@router.post("/systems/{system_id}/assets", summary="Registrar un activo (o versión)")
async def create_asset(
    system_id: str,
    body: CreateAssetRequest,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Registra un activo. Si ya existe ese nombre, crea la **versión siguiente**.

    La versión anterior se conserva: el inventario no pierde memoria.
    """
    data = await _service(session).add_asset(
        system_id,
        asset_type=body.asset_type,
        name=body.name,
        content=body.content,
        origin=body.origin,
        origin_ref=body.origin_ref,
        description=body.description,
        actor_id=actor.id,
    )
    return ApiResponse.ok(
        data=data, message=f"Activo registrado (versión {data['version']})"
    )


@router.get("/assets/{asset_id}", summary="Contenido completo de un activo")
async def get_asset(
    asset_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve el activo con su ``content`` estructurado."""
    return ApiResponse.ok(data=await _service(session).get_asset(asset_id))


@router.get("/assets/{asset_id}/versions", summary="Historial de versiones del activo")
async def list_versions(
    asset_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Todas las versiones del activo, de la más reciente a la primera."""
    items = await _service(session).list_versions(asset_id)
    return ApiResponse.ok(data={"items": items})


@router.patch("/assets/{asset_id}/status", summary="Marcar un activo como validado")
async def set_asset_status(
    asset_id: str,
    body: UpdateAssetStatusRequest,
    _actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Pasa el activo de ``importado`` a ``validado`` (o lo revierte)."""
    data = await _service(session).set_validation_status(
        asset_id, body.validation_status
    )
    return ApiResponse.ok(data=data, message="Estado de validación actualizado")


@router.delete("/assets/{asset_id}", summary="Eliminar una versión de un activo")
async def delete_asset(
    asset_id: str,
    _actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Elimina **esa** versión; el resto del historial permanece."""
    await _service(session).delete_asset(asset_id)
    return ApiResponse.ok(data={"asset_id": asset_id}, message="Versión eliminada")
