"""Carga del inventario del sistema destino para la fase RECONCILE (INV4).

Puente entre los agentes (``ai/``) y la persistencia (``app/``). Se mantiene aparte
del clasificador a propósito: :mod:`ai.inventory.reconcile` no toca la base de
datos y por eso se puede probar entero sin sesión, con listas en memoria.
"""

from typing import Any, Optional

from app.dependencies.database import session_scope
from app.models.inventory import InventoryAssetType, InventorySystemKind
from app.repositories.inventory_repository import InventoryRepository


async def load_target_inventory(
    system_id: Optional[str] = None,
    *,
    asset_types: tuple[InventoryAssetType, ...] = (InventoryAssetType.DB_SCHEMA,),
) -> dict[str, Any]:
    """Activos VIGENTES del sistema destino, listos para reconciliar.

    Si no se indica ``system_id`` se resuelve el sistema marcado como ``destino``.
    Cuando hay más de uno —o ninguno— NO se elige por el usuario: se devuelve
    ``performed=False`` y la fase se salta declarándolo. Adivinar contra qué
    sistema reconciliar sería peor que no reconciliar: produciría veredictos
    ``reuse`` apuntando al sistema equivocado.
    """
    try:
        return await _load(system_id, asset_types)
    except Exception as exc:  # inventario inalcanzable (BD caída, sin migrar…)
        # Un diseño NO se cae porque el inventario no esté disponible: se produce
        # como greenfield y se DECLARA por qué. Caerse aquí convertiría una
        # indisponibilidad de una función auxiliar en la pérdida de un job entero.
        return {
            "performed": False,
            "reason": (
                "No se pudo consultar el inventario "
                f"({type(exc).__name__}): el diseño se produce como si fuera nuevo."
            ),
            "assets": [],
        }


async def _load(
    system_id: Optional[str],
    asset_types: tuple[InventoryAssetType, ...],
) -> dict[str, Any]:
    """Consulta real al inventario (ver :func:`load_target_inventory`)."""
    async with session_scope() as session:
        repo = InventoryRepository(session)

        system = None
        if system_id:
            system = await repo.get_system(system_id)
        else:
            destinos = await repo.list_systems(kind=InventorySystemKind.DESTINO)
            if len(destinos) == 1:
                system = destinos[0]
            elif len(destinos) > 1:
                return {
                    "performed": False,
                    "reason": (
                        f"Hay {len(destinos)} sistemas marcados como destino en el "
                        "inventario: indica cuál es el objetivo de este diseño."
                    ),
                    "assets": [],
                }

        if system is None:
            return {
                "performed": False,
                "reason": (
                    "No hay ningún sistema destino en el inventario contra el que "
                    "reconciliar: el diseño se produce como si fuera nuevo."
                ),
                "assets": [],
            }

        activos: list[dict[str, Any]] = []
        for asset_type in asset_types:
            for asset in await repo.list_current_assets(
                system.id, asset_type=asset_type
            ):
                activos.append(
                    {
                        "id": asset.id,
                        "name": asset.name,
                        "asset_type": asset.asset_type.value,
                        "content": asset.content,
                        "system_id": system.id,
                        "system_name": system.name,
                        "validation_status": asset.validation_status.value,
                        "version": asset.version,
                    }
                )

        return {
            "performed": True,
            "system_id": system.id,
            "system_name": system.name,
            "assets": activos,
        }
