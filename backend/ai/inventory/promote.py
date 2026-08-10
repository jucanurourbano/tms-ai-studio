"""Promoción de un artefacto del ISDF al inventario (INV6).

Cierra el ciclo que abrió INV1: los agentes leen el inventario para reconciliar
(INV4) y ahora también lo **alimentan**. Cada proyecto entregado engorda la memoria
de la organización, así que el siguiente diseño reconcilia contra un inventario más
completo sin que nadie lo mantenga a mano.

La decisión no obvia: se MEZCLA, no se reemplaza
------------------------------------------------
Un diseño toca un puñado de tablas; el esquema del sistema tiene decenas. Si la
promoción sustituyera el activo por lo que trae el artefacto, promover un proyecto
pequeño **borraría del inventario el resto del esquema** — y el siguiente diseño
reconciliaría contra una foto incompleta, concluyendo "no existe, créala" sobre
tablas que sí están. Por eso se parte de la versión vigente y se superponen las
tablas del artefacto: lo que el diseño define gana, lo que no menciona se conserva.
"""

from typing import Any

# Estados de job cuyo artefacto es utilizable (los mismos que consumen los agentes
# siguientes). Un job fallido o a medias no tiene nada que promover.
PROMOTABLE_STATUSES = ("COMPLETED", "COMPLETED_WITH_WARNINGS")


def _column_from_artifact(columna: dict[str, Any]) -> dict[str, Any]:
    """Columna del ``DatabaseArtifact`` → columna del inventario.

    El inventario guarda el tipo FÍSICO renderizado (lo que existirá en el motor)
    y conserva además el ``logical_type``, que es lo que compara RECONCILE.
    """
    return {
        "name": columna.get("name", ""),
        "type": columna.get("type") or columna.get("logical_type") or "",
        "logical_type": columna.get("logical_type"),
        "nullable": bool(columna.get("nullable", True)),
        "default": columna.get("default"),
        "primary_key": bool(columna.get("is_primary_key")),
        "comment": columna.get("description"),
    }


def db_schema_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """``DatabaseArtifact`` → contenido de un activo ``db_schema``.

    Las tablas marcadas ``reuse`` se incluyen igualmente: el activo es una **foto
    del esquema**, no una lista de cambios, y omitirlas dejaría huecos en la foto.
    """
    tablas = []
    for tabla in artifact.get("tables") or []:
        pk = tabla.get("primary_key") or {}
        tablas.append(
            {
                "name": tabla.get("name", ""),
                "schema_name": tabla.get("schema_name"),
                "comment": tabla.get("description"),
                "columns": [
                    _column_from_artifact(c) for c in tabla.get("columns") or []
                ],
                "primary_key": list(pk.get("columns") or []),
                "foreign_keys": [
                    {
                        "name": fk.get("name"),
                        "columns": list(fk.get("columns") or []),
                        "referenced_table": fk.get("references_table", ""),
                        "referenced_columns": list(fk.get("references_columns") or []),
                        "on_delete": fk.get("on_delete"),
                    }
                    for fk in tabla.get("foreign_keys") or []
                ],
                "constraints": [
                    {
                        "kind": "unique",
                        "name": uq.get("name"),
                        "columns": list(uq.get("columns") or []),
                        "expression": None,
                    }
                    for uq in tabla.get("unique_constraints") or []
                ]
                + [
                    {
                        "kind": "check",
                        "name": ck.get("name"),
                        "columns": [],
                        "expression": ck.get("expression"),
                    }
                    for ck in tabla.get("check_constraints") or []
                ],
                "indexes": [
                    {
                        "name": idx.get("name"),
                        "columns": list(idx.get("columns") or []),
                        "unique": bool(idx.get("unique")),
                    }
                    for idx in tabla.get("indexes") or []
                ],
            }
        )
    return {
        "engine": (artifact.get("target") or {}).get("engine") or "postgresql",
        "tables": tablas,
    }


def api_surface_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """``ApiArtifact`` → contenido de un activo ``api``.

    Se guarda la superficie (método, ruta, propósito y recurso), no el documento
    OpenAPI completo: lo que RECONCILE compara es qué operaciones existen, y un
    YAML de mil líneas dentro de un activo no lo hace más comparable.
    """
    endpoints = []
    for endpoint in artifact.get("endpoints") or []:
        endpoints.append(
            {
                "method": (endpoint.get("method") or "").upper(),
                "path": endpoint.get("path", ""),
                "operation_id": endpoint.get("operation_id"),
                "kind": endpoint.get("kind"),
                "purpose": endpoint.get("purpose"),
                "resource_ref": endpoint.get("resource_ref"),
                "deprecated": bool(endpoint.get("deprecated")),
            }
        )
    return {
        "base_path": (artifact.get("target") or {}).get("base_path"),
        "endpoints": endpoints,
    }


def merge_db_schema(
    actual: dict[str, Any], entrante: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Superpone las tablas de ``entrante`` sobre la foto ``actual``.

    Devuelve ``(contenido, {"added": [...], "updated": [...], "kept": [...]})`` para
    que la respuesta pueda decir exactamente qué cambió. Reemplazar en vez de
    mezclar borraría del inventario las tablas que este diseño no toca.
    """
    por_nombre: dict[str, dict] = {
        t["name"].lower(): t for t in (actual.get("tables") or [])
    }
    previas = set(por_nombre)

    anadidas: list[str] = []
    actualizadas: list[str] = []
    for tabla in entrante.get("tables") or []:
        clave = tabla["name"].lower()
        if clave in por_nombre:
            actualizadas.append(tabla["name"])
        else:
            anadidas.append(tabla["name"])
        por_nombre[clave] = tabla

    conservadas = sorted(
        por_nombre[c]["name"]
        for c in previas
        if c not in {t.lower() for t in actualizadas}
    )
    contenido = {
        "engine": entrante.get("engine") or actual.get("engine") or "postgresql",
        "tables": [por_nombre[c] for c in sorted(por_nombre)],
    }
    return contenido, {
        "added": sorted(anadidas),
        "updated": sorted(actualizadas),
        "kept": conservadas,
    }


def merge_api_surface(
    actual: dict[str, Any], entrante: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Superpone endpoints sobre la superficie actual. Clave: ``MÉTODO ruta``."""

    def clave(endpoint: dict) -> str:
        return f"{(endpoint.get('method') or '').upper()} {endpoint.get('path') or ''}"

    por_clave: dict[str, dict] = {clave(e): e for e in (actual.get("endpoints") or [])}
    previas = set(por_clave)

    anadidos: list[str] = []
    actualizados: list[str] = []
    for endpoint in entrante.get("endpoints") or []:
        k = clave(endpoint)
        (actualizados if k in por_clave else anadidos).append(k)
        por_clave[k] = endpoint

    contenido = {
        "base_path": entrante.get("base_path") or actual.get("base_path"),
        "endpoints": [por_clave[k] for k in sorted(por_clave)],
    }
    return contenido, {
        "added": sorted(anadidos),
        "updated": sorted(actualizados),
        "kept": sorted(previas - set(actualizados)),
    }
