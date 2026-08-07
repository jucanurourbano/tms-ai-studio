"""Nodo RESOURCE_MAP (determinista): el andamio de la API.

Es la pieza **anti-invención** del agente, equivalente exacto de ``MODEL_MAP`` en
el Agente BD. Aquí, en Python y sin LLM, queda fijado:

- **Qué recursos existen**: uno por tabla del modelo de datos, ni uno más. Los
  nodos LLM que vienen después reciben este conjunto ya cerrado y solo pueden
  describir lo que hay.
- **Qué operaciones existen**: las que autoriza la **matriz CRUD del EF** y las que
  el EF ya declaraba en ``apis[]``. Nada más. La consecuencia incómoda de esta
  regla es deliberada: si el EF no dice quién opera sobre una entidad, **no se
  generan endpoints para ella** y se emite una pregunta. Un endpoint que nadie
  puede llamar es código muerto, e inventarle un dueño para rellenar el hueco es
  exactamente lo que este cortafuegos existe para impedir.
- **Qué columnas son candidatas** a viajar por la API, con lo que ya se sabe de
  ellas (tipo, obligatoriedad, si es de solo lectura, si es dato personal).
- **Qué se puede filtrar y ordenar**: solo columnas con índice, PK o FK. Un filtro
  sin índice es un recorrido de tabla completo en producción.
- **Cómo se llama todo**: vía ``naming``, de forma reproducible.

Lo que RESOURCE_MAP **no** decide (y por eso llega marcado a los nodos siguientes):
qué columnas se ocultan, qué recursos se embeben en otros, las descripciones, las
acciones de negocio y las condiciones de alcance de la autorización.
"""

from typing import Any, Optional

from ai.knowledge import exposure_for, load_api_conventions

from .naming import collection_path as _collection_path
from .naming import (
    is_reserved_segment,
    item_path,
    nested_path,
    operation_id,
    path_parameter_name,
    resource_path_segment,
    resource_singular,
)

#: Naturalezas de tabla del Agente BD.
KIND_ENTITY = "entity"
KIND_CATALOG = "catalog"
KIND_JUNCTION = "junction"
KIND_AUDIT = "audit"

#: Exposiciones que publican el recurso en primer nivel.
_TOP_LEVEL = ("crud", "read_only")

#: Nombres de columna que nunca las escribe el cliente (auditoría del modelo).
_AUDIT_COLUMNS = ("created_at", "created_by", "updated_at", "updated_by", "deleted_at")


def _observation(description: str, reason: str) -> dict:
    """Hallazgo del andamio. Acabará como ``Observation``: nunca se calla nada."""
    return {"description": description, "reason": reason}


# --- Recursos ----------------------------------------------------------------


def _component_for(entity_ref: Optional[str], components: list[dict]) -> Optional[str]:
    """Componente de Arquitectura que reclama la entidad (agrupa por módulo)."""
    if not entity_ref:
        return None
    for component in components:
        refs = component.get("source_refs") or {}
        if entity_ref in (refs.get("entity_refs") or []):
            return component.get("id")
    return None


def _primary_key(table: dict) -> tuple[Optional[str], bool]:
    """Columna PK direccionable y si la tabla lo es.

    Una PK compuesta —la de las tablas puente— no da una ruta de detalle: no hay un
    identificador único que poner en la URL. Se declara y se sigue; el recurso vive
    anidado bajo su padre.
    """
    pk = table.get("primary_key") or {}
    columns = pk.get("columns") or []
    if len(columns) == 1:
        return columns[0], True
    return (columns[0] if columns else None), False


def _column_candidates(table: dict) -> list[dict]:
    """Columnas candidatas a viajar por la API, con lo que ya se sabe de ellas."""
    pk_columns = set((table.get("primary_key") or {}).get("columns") or [])
    fk_columns = {
        column
        for fk in table.get("foreign_keys") or []
        for column in (fk.get("columns") or [])
    }
    enum_por_columna = _enum_values(table)

    columnas: list[dict] = []
    for column in table.get("columns") or []:
        nombre = column.get("name") or ""
        generada = bool(column.get("is_generated"))
        es_pk = bool(column.get("is_primary_key")) or nombre in pk_columns
        # De solo lectura lo que el cliente no escribe nunca: la clave que genera
        # el motor y las columnas de auditoría que rellena la aplicación.
        read_only = generada or es_pk or nombre in _AUDIT_COLUMNS
        columnas.append(
            {
                "name": nombre,
                "column_ref": column.get("id"),
                "logical_type": column.get("logical_type"),
                "nullable": bool(column.get("nullable", True)),
                # Obligatorio al crear: no admite nulo, no tiene default y no lo
                # genera el motor.
                "required": not column.get("nullable", True)
                and column.get("default") in (None, "")
                and not read_only,
                "read_only": read_only,
                "is_primary_key": es_pk,
                "is_foreign_key": nombre in fk_columns,
                "max_length": column.get("length"),
                "enum": enum_por_columna.get(nombre),
                "example": column.get("example"),
                "description": column.get("description"),
                "pii": bool(column.get("pii")),
                "field_ref": column.get("field_ref"),
                "source_refs": list(column.get("source_refs") or []),
            }
        )
    return columnas


def _enum_values(table: dict) -> dict[str, list[str]]:
    """Valores admitidos por columna, si un CHECK del modelo los enumera.

    Solo se leen los ``IN (...)`` simples: el objetivo no es interpretar SQL, es
    aprovechar lo que el modelo ya dejó explícito. Un CHECK más complejo no se
    adivina; queda sin enum y el campo viaja como su tipo base.
    """
    valores: dict[str, list[str]] = {}
    for check in table.get("check_constraints") or []:
        expresion = (check.get("expression") or "").strip()
        if " in (" not in expresion.lower():
            continue
        columna, _, resto = expresion.partition(" ")
        izquierda = columna.strip().strip("()")
        _, _, lista = resto.partition("(")
        lista = lista.rstrip(") ")
        items = [item.strip().strip("'\"") for item in lista.split(",") if item.strip()]
        if izquierda and items:
            valores[izquierda] = items
    return valores


def build_resource_candidates(sources: dict[str, Any]) -> list[dict]:
    """Un recurso candidato por tabla del modelo de datos, en orden reproducible.

    **Incluye las tablas que no se exponen.** Un recurso con ``exposure="none"`` y
    su motivo escrito es más útil que una tabla ausente: al leer el artefacto se
    distingue lo que se decidió no publicar de lo que se olvidó.
    """
    tables = sorted(
        (
            t
            for t in (sources.get("bd", {}) or {}).get("tables", []) or []
            if t.get("id")
        ),
        key=lambda t: t["id"],
    )
    components = (sources.get("architecture", {}) or {}).get("components", []) or []

    candidatos: list[dict] = []
    for posicion, table in enumerate(tables, start=1):
        nombre = table.get("name") or ""
        kind = table.get("kind") or KIND_ENTITY
        exposicion, motivo = exposure_for(kind)
        pk_column, direccionable = _primary_key(table)
        segmento = resource_path_segment(nombre)
        candidatos.append(
            {
                "id": f"RES-{posicion:03d}",
                "name": nombre,
                "segment": segmento,
                "singular": resource_singular(nombre),
                "table_ref": table.get("id"),
                "table_kind": kind,
                "entity_ref": table.get("entity_ref"),
                "component_ref": _component_for(table.get("entity_ref"), components),
                "description": table.get("description"),
                "exposure": exposicion,
                "exposure_reason": motivo or None,
                "pk_column": pk_column,
                "addressable": direccionable,
                "columns": _column_candidates(table),
                "filterable": _filterable_columns(table),
                "sortable": _filterable_columns(table),
                "parent_resource_ref": None,  # lo resuelve _link_junctions
                "reserved_segment": is_reserved_segment(segmento),
                "source_refs": [
                    ref for ref in (table.get("entity_ref"), table.get("id")) if ref
                ],
            }
        )
    _link_junctions(candidatos, tables)
    return candidatos


def _filterable_columns(table: dict) -> list[str]:
    """Columnas por las que se puede filtrar u ordenar: **solo las indexadas**.

    Regla dura, no preferencia. El modelo de datos ya decidió qué está indexado; si
    hace falta filtrar por otra columna, lo correcto es pedir el índice al Agente
    BD, no publicar un filtro que en producción recorrerá la tabla entera.
    """
    columnas: list[str] = []
    for nombre in (table.get("primary_key") or {}).get("columns") or []:
        columnas.append(nombre)
    for fk in table.get("foreign_keys") or []:
        columnas.extend(fk.get("columns") or [])
    for index in table.get("indexes") or []:
        columnas.extend(index.get("columns") or [])
    for unique in table.get("unique_constraints") or []:
        columnas.extend(unique.get("columns") or [])
    vistas: list[str] = []
    for nombre in columnas:
        if nombre and nombre not in vistas:
            vistas.append(nombre)
    return vistas


def _link_junctions(candidatos: list[dict], tables: list[dict]) -> None:
    """Cuelga cada tabla puente de su recurso padre (la primera FK, en orden).

    Una tabla puente no es un recurso de primer nivel: su identificador no
    significa nada para el negocio. Se gestiona desde uno de los dos extremos de la
    relación, y se elige el primero de forma determinista para que la ruta sea
    reproducible.
    """
    por_tabla = {c["table_ref"]: c for c in candidatos}
    por_nombre = {c["name"]: c for c in candidatos}
    for table in tables:
        candidato = por_tabla.get(table.get("id"))
        if candidato is None or candidato["table_kind"] != KIND_JUNCTION:
            continue
        for fk in table.get("foreign_keys") or []:
            padre = por_nombre.get(fk.get("references_table") or "")
            if padre is not None:
                candidato["parent_resource_ref"] = padre["id"]
                break


# --- Operaciones --------------------------------------------------------------


def _update_method() -> str:
    """Verbo de actualización acordado (API11: ``PATCH``)."""
    return (load_api_conventions().get("paths", {}) or {}).get("update_verb", "PATCH")


def _crud_by_entity(crud: list[dict]) -> dict[str, list[dict]]:
    """Celdas de la matriz CRUD agrupadas por entidad, en orden estable."""
    agrupadas: dict[str, list[dict]] = {}
    for cell in crud:
        ref = cell.get("entity_ref")
        if ref:
            agrupadas.setdefault(ref, []).append(cell)
    for celdas in agrupadas.values():
        celdas.sort(key=lambda c: c.get("id") or "")
    return agrupadas


def _actors_for(cells: list[dict], permiso: str) -> tuple[list[str], list[str]]:
    """Actores que tienen ese permiso y las celdas CRUD que lo respaldan."""
    actores: list[str] = []
    refs: list[str] = []
    for cell in cells:
        if not cell.get(permiso):
            continue
        actor = cell.get("actor_ref")
        if actor and actor not in actores:
            actores.append(actor)
        if cell.get("id"):
            refs.append(cell["id"])
    return actores, refs


def _operation(
    kind: str,
    method: str,
    path: str,
    resource: dict,
    *,
    actor_refs: list[str],
    basis: str,
    crud_refs: Optional[list[str]] = None,
    source_refs: Optional[list[str]] = None,
    paginated: bool = False,
    idempotent: bool = False,
) -> dict:
    return {
        "kind": kind,
        "method": method,
        "path": path,
        "operation_id": operation_id(kind, resource["name"]),
        "resource_ref": resource["id"],
        "actor_refs": actor_refs,
        "basis": basis,
        "crud_refs": crud_refs or [],
        "ef_api_ref": None,
        "source_refs": source_refs or list(resource["source_refs"]),
        "paginated": paginated,
        "idempotent": idempotent,
    }


def plan_operations(
    resource: dict, cells: list[dict], base: str
) -> tuple[list[dict], list[dict]]:
    """Operaciones candidatas de un recurso, según la matriz CRUD del EF.

    Devuelve ``(operaciones, observaciones)``. El catálogo es la única excepción a
    "sin celda no hay operación": se le concede el listado aunque nadie lo declare,
    porque sin poder leer los estados no se puede ni pintar el formulario que los
    usa. La excepción queda **registrada** como observación, no escondida.
    """
    operaciones: list[dict] = []
    observaciones: list[dict] = []
    if resource["exposure"] not in _TOP_LEVEL:
        return operaciones, observaciones

    coleccion = _collection_path(base, resource["segment"])
    detalle = (
        item_path(base, resource["segment"], resource["pk_column"])
        if resource["addressable"] and resource["pk_column"]
        else None
    )

    lectores, refs_lectura = _actors_for(cells, "read")
    if lectores:
        operaciones.append(
            _operation(
                "list",
                "GET",
                coleccion,
                resource,
                actor_refs=lectores,
                basis="crud_matrix",
                crud_refs=refs_lectura,
                paginated=True,
                idempotent=True,
            )
        )
        if detalle:
            operaciones.append(
                _operation(
                    "read_item",
                    "GET",
                    detalle,
                    resource,
                    actor_refs=lectores,
                    basis="crud_matrix",
                    crud_refs=refs_lectura,
                    idempotent=True,
                )
            )
    elif resource["exposure"] == "read_only":
        operaciones.append(
            _operation(
                "list",
                "GET",
                coleccion,
                resource,
                actor_refs=[],
                basis="inferred",
                paginated=True,
                idempotent=True,
            )
        )
        observaciones.append(
            _observation(
                f"El catálogo «{resource['name']}» se publica en lectura sin celda "
                "de la matriz CRUD que lo respalde.",
                "Sin poder consultarlo no se puede usar el recurso que lo referencia; "
                "la autorización queda por confirmar.",
            )
        )

    if resource["exposure"] != "crud":
        return operaciones, observaciones

    creadores, refs_creacion = _actors_for(cells, "create")
    if creadores:
        operaciones.append(
            _operation(
                "create",
                "POST",
                coleccion,
                resource,
                actor_refs=creadores,
                basis="crud_matrix",
                crud_refs=refs_creacion,
            )
        )
    editores, refs_edicion = _actors_for(cells, "update")
    if editores and detalle:
        operaciones.append(
            _operation(
                "update",
                _update_method(),
                detalle,
                resource,
                actor_refs=editores,
                basis="crud_matrix",
                crud_refs=refs_edicion,
            )
        )
    borradores, refs_borrado = _actors_for(cells, "delete")
    if borradores and detalle:
        operaciones.append(
            _operation(
                "delete",
                "DELETE",
                detalle,
                resource,
                actor_refs=borradores,
                basis="crud_matrix",
                crud_refs=refs_borrado,
                idempotent=True,
            )
        )
    return operaciones, observaciones


def _child_key(resource: dict, padre: dict) -> Optional[str]:
    """Columna que identifica al **otro** extremo de la relación N:M.

    En ``/guias/{guia_id}/siniestros/{siniestro_id}``, el padre ya está en la ruta:
    lo que falta para desenlazar es la clave del otro lado. Se busca en la PK
    compuesta de la tabla puente la columna que **no** es la del padre; si la PK no
    tiene esa forma, no se inventa una ruta y no se genera el desenlace.
    """
    columnas = [
        c["name"] for c in resource.get("columns") or [] if c.get("is_primary_key")
    ]
    ajenas = [c for c in columnas if c != padre.get("pk_column")]
    return ajenas[0] if len(ajenas) == 1 else None


def plan_nested_operations(
    resource: dict, padre: dict, cells_padre: list[dict], base: str
) -> list[dict]:
    """Operaciones de una tabla puente, colgadas de su recurso padre.

    Los permisos se heredan del padre: quien puede leer una guía puede ver con qué
    está relacionada, y quien puede modificarla puede enlazar y desenlazar. No se
    inventa un actor propio para la tabla puente, porque el EF nunca habla de ella.
    """
    if not padre.get("addressable") or not padre.get("pk_column"):
        return []
    ruta = nested_path(base, padre["segment"], padre["pk_column"], resource["segment"])
    lectores, refs_lectura = _actors_for(cells_padre, "read")
    editores, refs_edicion = _actors_for(cells_padre, "update")

    operaciones: list[dict] = []
    if lectores:
        operaciones.append(
            _operation(
                "nested_list",
                "GET",
                ruta,
                resource,
                actor_refs=lectores,
                basis="crud_matrix",
                crud_refs=refs_lectura,
                paginated=True,
                idempotent=True,
            )
        )
    if editores:
        operaciones.append(
            _operation(
                "nested_create",
                "POST",
                ruta,
                resource,
                actor_refs=editores,
                basis="crud_matrix",
                crud_refs=refs_edicion,
            )
        )
        hijo_pk = _child_key(resource, padre)
        if hijo_pk:
            operaciones.append(
                _operation(
                    "nested_delete",
                    "DELETE",
                    f"{ruta}/{{{path_parameter_name(hijo_pk)}}}",
                    resource,
                    actor_refs=editores,
                    basis="crud_matrix",
                    crud_refs=refs_edicion,
                    idempotent=True,
                )
            )
    return operaciones


# --- APIs que el EF ya declaraba ----------------------------------------------


def _kind_from_ef_api(api: dict) -> str:
    """Deduce el tipo de operación de un ``API-`` del EF por su forma."""
    method = (api.get("method") or "GET").upper()
    tiene_parametro = "{" in (api.get("path") or "")
    if method == "POST":
        return "create"
    if method in ("PATCH", "PUT"):
        return "update"
    if method == "DELETE":
        return "delete"
    return "read_item" if tiene_parametro else "list"


def merge_ef_apis(
    resources: list[dict],
    operaciones_por_recurso: dict[str, list[dict]],
    apis: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Cruza las APIs declaradas en el EF con las operaciones ya planificadas.

    Una API del EF que coincide con una operación existente **la marca como
    declarada** (``origin=stated`` en el artefacto): lo que el analista ya pidió no
    se presenta después como una idea del agente. Una que no coincide con ninguna
    se **añade**, porque el EF es una fuente legítima además de la matriz CRUD.

    Devuelve ``(observaciones, apis_huérfanas)``.
    """
    observaciones: list[dict] = []
    huerfanas: list[dict] = []
    por_entidad = {r["entity_ref"]: r for r in resources if r.get("entity_ref")}

    for api in sorted((a for a in apis if a.get("id")), key=lambda a: a["id"]):
        recurso = por_entidad.get(api.get("entity_ref") or "")
        if recurso is None:
            huerfanas.append(
                {
                    "api_ref": api["id"],
                    "path": api.get("path"),
                    "reason": (
                        "el endpoint del EF no cita ninguna entidad con tabla en el "
                        "modelo de datos"
                    ),
                }
            )
            continue

        kind = _kind_from_ef_api(api)
        existentes = operaciones_por_recurso.setdefault(recurso["id"], [])
        coincidencia = next(
            (op for op in existentes if op["kind"] == kind and not op["ef_api_ref"]),
            None,
        )
        if coincidencia is not None:
            coincidencia["ef_api_ref"] = api["id"]
            if api["id"] not in coincidencia["source_refs"]:
                coincidencia["source_refs"].insert(0, api["id"])
            continue

        # El EF lo pide y la matriz CRUD no lo respalda: se crea igualmente (el EF
        # es fuente legítima) pero sin actores, así que nacerá denegado y con
        # pregunta. Nunca se le asigna un actor por conveniencia.
        nueva = _operation(
            kind,
            (api.get("method") or "GET").upper(),
            api.get("path") or _collection_path("/api/v1", recurso["segment"]),
            recurso,
            actor_refs=[],
            basis="ef_api",
            source_refs=[api["id"], *recurso["source_refs"]],
            paginated=kind == "list",
            idempotent=kind in ("list", "read_item", "delete"),
        )
        nueva["ef_api_ref"] = api["id"]
        existentes.append(nueva)
        observaciones.append(
            _observation(
                f"El endpoint {api['id']} ({api.get('method')} {api.get('path')}) "
                "viene del EF pero ninguna celda de la matriz CRUD dice quién puede "
                "llamarlo.",
                "Se especifica porque el EF lo declara, y queda denegado hasta que "
                "se confirme el actor.",
            )
        )
    return observaciones, huerfanas


# --- Andamio completo ----------------------------------------------------------


def build_resource_map(sources: dict[str, Any], base: str = "/api/v1") -> dict:
    """Construye el andamio completo: recursos, operaciones y lo que falta.

    Todo lo que queda fuera se devuelve enumerado (``resources_without_operations``,
    ``orphan_crud``, ``orphan_ef_apis``, ``observations``) para que los nodos
    siguientes lo conviertan en preguntas y observaciones. Nada se descarta en
    silencio.
    """
    ef = sources.get("ef", {}) or {}
    recursos = build_resource_candidates(sources)
    celdas_por_entidad = _crud_by_entity(ef.get("crud", []) or [])
    por_recurso: dict[str, list[dict]] = {}
    observaciones: list[dict] = []

    for recurso in recursos:
        celdas = celdas_por_entidad.get(recurso.get("entity_ref") or "", [])
        operaciones, obs = plan_operations(recurso, celdas, base)
        por_recurso[recurso["id"]] = operaciones
        observaciones.extend(obs)
        if recurso["reserved_segment"]:
            observaciones.append(
                _observation(
                    f"El recurso «{recurso['name']}» usaría el segmento reservado "
                    f"«{recurso['segment']}».",
                    "Chocaría con una ruta de infraestructura del propio servicio.",
                )
            )

    # Las tablas puente, una vez que todos los padres tienen sus permisos resueltos.
    por_id = {r["id"]: r for r in recursos}
    for recurso in recursos:
        if recurso["exposure"] != "nested_only":
            continue
        padre = por_id.get(recurso.get("parent_resource_ref") or "")
        if padre is None:
            observaciones.append(
                _observation(
                    f"La tabla puente «{recurso['name']}» no tiene recurso padre.",
                    "Sus claves foráneas no apuntan a ninguna tabla con recurso, así "
                    "que la relación no se puede gestionar desde ningún extremo.",
                )
            )
            continue
        celdas_padre = celdas_por_entidad.get(padre.get("entity_ref") or "", [])
        por_recurso[recurso["id"]] = plan_nested_operations(
            recurso, padre, celdas_padre, base
        )

    obs_apis, huerfanas = merge_ef_apis(recursos, por_recurso, ef.get("apis", []) or [])
    observaciones.extend(obs_apis)

    # Recursos que deberían publicarse y se quedan sin una sola operación: es el
    # síntoma de una matriz CRUD incompleta, y se reporta como tal.
    sin_operaciones = [
        recurso["id"]
        for recurso in recursos
        if recurso["exposure"] in _TOP_LEVEL and not por_recurso.get(recurso["id"])
    ]

    entidades_con_tabla = {r["entity_ref"] for r in recursos if r.get("entity_ref")}
    crud_huerfano = [
        {
            "crud_ref": cell.get("id"),
            "entity_ref": cell.get("entity_ref"),
            "reason": "la celda CRUD cita una entidad sin tabla en el modelo de datos",
        }
        for cell in ef.get("crud", []) or []
        if cell.get("entity_ref") not in entidades_con_tabla
    ]

    for recurso in recursos:
        recurso["operations"] = por_recurso.get(recurso["id"], [])

    return {
        "base_path": base,
        "resources": recursos,
        "actors": list(ef.get("actors", []) or []),
        "resources_without_operations": sin_operaciones,
        "orphan_crud": crud_huerfano,
        "orphan_ef_apis": huerfanas,
        "observations": observaciones,
    }


def all_operations(resource_map: dict) -> list[dict]:
    """Todas las operaciones del andamio, en orden estable de recurso."""
    return [
        operacion
        for recurso in resource_map.get("resources", [])
        for operacion in recurso.get("operations", [])
    ]
