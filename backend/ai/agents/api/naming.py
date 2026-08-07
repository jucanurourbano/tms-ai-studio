"""Nomenclatura determinista de la API (rutas, operaciones y esquemas).

Todo nombre público —segmento de ruta, ``operationId``, nombre de esquema— sale de
aquí y **no** del LLM, por la misma razón que en el Agente BD: el resultado es
reproducible (mismo modelo de datos ⇒ mismas rutas, lo que hace testeable el
documento) y ningún identificador puede salir con una forma que rompa a un
generador de clientes.

**Se reutiliza la pluralización castellana del Agente BD** (``snake``,
``pluralize``, ``singularize``): es el mismo problema ya resuelto y probado, y
duplicarlo aquí garantizaría que las dos copias se separen a la primera excepción
que alguien corrija en una sola.

La regla de idioma acordada (API6) se aplica aquí de forma literal: **el dominio va
en español y el protocolo en inglés**. Los segmentos de recurso son el nombre de la
tabla —que ya está en español— y los parámetros de paginación y orden viven en
``api_conventions.yaml``, en inglés.
"""

from ai.agents.bd.naming import singularize, snake
from ai.knowledge import load_api_conventions

#: Verbo de la operación → clave del patrón en ``api_conventions.yaml``.
_OPERATION_PATTERNS = ("list", "read_item", "create", "update", "delete", "action")


def kebab(text: str) -> str:
    """Convierte a ``kebab-case`` sin acentos (``siniestro_estados`` → ``…-estados``).

    Se apoya en ``snake`` del Agente BD (que ya quita tildes, separa *camelCase* y
    limpia caracteres especiales) y solo cambia el separador: así una tabla y su
    ruta no pueden divergir en cómo tratan un nombre raro.
    """
    return snake(text).replace("_", "-")


def resource_path_segment(table_name: str) -> str:
    """Segmento de ruta de un recurso, desde el nombre de su tabla.

    Las tablas del Agente BD ya nacen en plural y ``snake_case`` (``siniestros``,
    ``siniestro_estados``), así que aquí no se vuelve a pluralizar: hacerlo sería
    arriesgarse a un ``siniestroses`` por una tabla que el DBA nombró a mano.
    """
    return kebab(table_name)


def resource_singular(table_name: str) -> str:
    """Nombre en singular del recurso (``siniestro-estados`` → ``siniestro-estado``)."""
    return kebab(singularize(snake(table_name)))


def pascal(text: str) -> str:
    """``siniestro_estados`` → ``SiniestroEstados`` (para operaciones y esquemas)."""
    return "".join(part.capitalize() for part in snake(text).split("_") if part)


def path_parameter_name(pk_column: str) -> str:
    """Nombre del parámetro de ruta: **la columna PK tal cual**.

    No se traduce a ``id``: que el parámetro se llame ``siniestro_id`` hace que la
    ruta, el esquema y la columna del modelo de datos usen la misma palabra, que es
    justo lo que hace verificable la trazabilidad a simple vista.
    """
    return snake(pk_column)


def collection_path(base_path: str, segment: str) -> str:
    """Ruta de la colección: ``/api/v1`` + ``/siniestros``."""
    return f"{base_path.rstrip('/')}/{segment.strip('/')}"


def item_path(base_path: str, segment: str, pk_column: str) -> str:
    """Ruta del detalle: ``/api/v1/siniestros/{siniestro_id}``."""
    return f"{collection_path(base_path, segment)}/{{{path_parameter_name(pk_column)}}}"


def nested_path(base_path: str, parent: str, pk_column: str, child: str) -> str:
    """Ruta anidada de profundidad 1: ``/api/v1/guias/{guia_id}/siniestros``."""
    return f"{item_path(base_path, parent, pk_column)}/{kebab(child)}"


def action_path(base_path: str, segment: str, pk_column: str, accion: str) -> str:
    """Ruta de una acción de negocio: ``/api/v1/siniestros/{siniestro_id}/cerrar``."""
    return f"{item_path(base_path, segment, pk_column)}/{kebab(accion)}"


def operation_id(kind: str, resource_plural: str, *, accion: str = "") -> str:
    """``operationId`` desde el patrón de las convenciones.

    Es el nombre que los generadores de cliente convierten en método, así que tiene
    que ser único y estable: se compone de forma determinista y nunca lo redacta el
    modelo.
    """
    patrones = load_api_conventions().get("operation_id", {}) or {}
    plantilla = patrones.get(kind)
    if not plantilla:
        # Un tipo sin patrón no se inventa a medias: se compone de forma evidente
        # para que el fallo se vea en la revisión en vez de pasar por bueno.
        return f"{kind}{pascal(resource_plural)}"
    return plantilla.format(
        Resource=pascal(resource_plural),
        ResourceSingular=pascal(singularize(snake(resource_plural))),
        Child=pascal(resource_plural),
        ChildSingular=pascal(singularize(snake(resource_plural))),
        accion=snake(accion).replace("_", "") if accion else "",
    )


def schema_name(kind: str, resource_plural: str, *, accion: str = "") -> str:
    """Nombre del esquema en ``components.schemas`` (``SiniestroCreate``)."""
    patrones = load_api_conventions().get("schema_name", {}) or {}
    plantilla = patrones.get(kind, "{ResourceSingular}")
    return plantilla.format(
        ResourceSingular=pascal(singularize(snake(resource_plural))),
        Accion=pascal(accion) if accion else "",
    )


def is_reserved_segment(segment: str) -> bool:
    """¿El segmento choca con una ruta de infraestructura del propio servicio?

    Un recurso llamado ``health`` o ``docs`` colisionaría con lo que el framework
    publica por su cuenta, y el conflicto solo se vería al desplegar.
    """
    reservados = (load_api_conventions().get("paths", {}) or {}).get(
        "reserved_segments", []
    ) or []
    return kebab(segment) in {kebab(r) for r in reservados}
