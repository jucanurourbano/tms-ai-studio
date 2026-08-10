"""Nodos RECONCILE de los agentes de diseño (INV4).

Un nodo por agente porque cada uno reconcilia una cosa distinta —tablas,
componentes, endpoints— pero los tres comparten clasificador, contrato y
semántica. La lógica de decisión vive en :mod:`ai.inventory.reconcile`, que no
toca la base de datos; aquí solo se conecta el estado del grafo con ella.

**El nodo nunca tumba el pipeline.** Si no hay inventario, o el sistema destino es
ambiguo, la fase se declara no ejecutada (``performed=False``) y el diseño sigue
como *greenfield*. Un inventario ausente es una circunstancia normal —el primer
proyecto de una organización no tiene con qué reconciliar—, no un error.
"""

from typing import Any, Optional

from app.models.inventory import InventoryAssetType

from .loader import load_target_inventory
from .reconcile import (
    ReconciliationStatus,
    classify,
    flatten_db_schema,
    flatten_endpoints,
    flatten_modules,
    summarize,
)


def _empty(inventario: dict[str, Any]) -> dict[str, Any]:
    """Resumen de una fase que no se ejecutó, con el motivo escrito."""
    return {
        "performed": False,
        "system_id": None,
        "system_name": None,
        "counts": {estado.value: 0 for estado in ReconciliationStatus},
        "blocking": 0,
        "reconciled": 0,
        "total": 0,
        "reason": inventario.get("reason", ""),
    }


async def _reconcile(
    *,
    system_id: Optional[str],
    asset_types: tuple[InventoryAssetType, ...],
    flatten,
    elementos: list[dict[str, Any]],
    nombre_de,
    columnas_de=None,
) -> tuple[dict[str, dict], dict[str, Any]]:
    """Motor común: clasifica ``elementos`` contra el inventario del destino.

    Devuelve ``(veredictos_por_id, resumen)``.
    """
    inventario = await load_target_inventory(system_id, asset_types=asset_types)
    if not inventario.get("performed"):
        return {}, _empty(inventario)

    plano = flatten(inventario["assets"])
    veredictos: dict[str, dict] = {}
    crudos = []
    for elemento in elementos:
        columnas = columnas_de(elemento) if columnas_de is not None else None
        veredicto = classify(nombre_de(elemento), plano, columnas_propuestas=columnas)
        crudos.append(veredicto)
        veredictos[elemento["id"]] = veredicto.as_dict()

    resumen = summarize(crudos)
    resumen.update(
        {
            "performed": True,
            "system_id": inventario["system_id"],
            "system_name": inventario["system_name"],
        }
    )
    return veredictos, resumen


async def reconcile_tables(
    tables: list[dict], *, system_id: Optional[str] = None
) -> tuple[dict[str, dict], dict[str, Any]]:
    """Agente BD: cada tabla propuesta contra el esquema real del destino.

    Es la reconciliación con más consecuencias: un veredicto ``extend`` cambia el
    DDL de ``CREATE TABLE`` a ``ALTER TABLE ADD COLUMN``, y un ``reuse`` hace que
    no se genere DDL alguno para esa tabla.
    """
    return await _reconcile(
        system_id=system_id,
        asset_types=(InventoryAssetType.DB_SCHEMA,),
        flatten=flatten_db_schema,
        elementos=tables,
        nombre_de=lambda t: t.get("name", ""),
        columnas_de=lambda t: [c.get("name", "") for c in t.get("columns") or []],
    )


async def reconcile_components(
    components: list[dict], *, system_id: Optional[str] = None
) -> tuple[dict[str, dict], dict[str, Any]]:
    """Agente Arquitectura: cada componente contra los módulos ya inventariados."""
    return await _reconcile(
        system_id=system_id,
        asset_types=(InventoryAssetType.MODULE,),
        flatten=flatten_modules,
        elementos=components,
        nombre_de=lambda c: c.get("name", ""),
    )


async def reconcile_endpoints(
    endpoints: list[dict], *, system_id: Optional[str] = None
) -> tuple[dict[str, dict], dict[str, Any]]:
    """Agente API: cada endpoint contra la superficie de API ya existente."""
    return await _reconcile(
        system_id=system_id,
        asset_types=(InventoryAssetType.API,),
        flatten=flatten_endpoints,
        elementos=endpoints,
        nombre_de=lambda e: f"{(e.get('method') or '').upper()} {e.get('path') or ''}",
    )


def conflict_questions(
    veredictos: dict[str, dict],
    elementos: list[dict],
    *,
    audience: str,
    prefijo: str,
    desde: int = 1,
) -> list[dict]:
    """Convierte los ``conflict`` en preguntas BLOQUEANTES.

    Un conflicto es lo único que la reconciliación no puede resolver sola: hay algo
    parecido pero no se sabe si es lo mismo. Los demás errores se corrigen en
    revisión; éste no, porque un ``reuse`` equivocado apunta el diseño nuevo contra
    una tabla viva de producción.

    Se agrupan por elemento y no por candidato: una tabla con tres coincidencias
    dudosas es UNA decisión, no tres.
    """
    por_id = {e["id"]: e for e in elementos}
    preguntas: list[dict] = []
    numero = desde
    for element_id, veredicto in veredictos.items():
        if veredicto.get("status") != ReconciliationStatus.CONFLICT.value:
            continue
        elemento = por_id.get(element_id, {})
        emparejado = veredicto.get("matched") or {}
        preguntas.append(
            {
                "id": f"{prefijo}-{numero:03d}",
                "text": (
                    f"¿«{elemento.get('name', element_id)}» es lo mismo que "
                    f"«{emparejado.get('name', '?')}», que ya existe en "
                    f"«{emparejado.get('system_name', 'el inventario')}»? "
                    "Si lo es, se reutilizará o se extenderá; si no, se creará "
                    "aparte y habrá que distinguir los nombres."
                ),
                "audience": audience,
                "reason": veredicto.get("reason", ""),
                "blocking": True,
                "linked_to_ref": element_id,
            }
        )
        numero += 1
    return preguntas
