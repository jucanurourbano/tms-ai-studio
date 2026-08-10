"""Esquemas del Inventario de Sistemas: DTOs de la API y forma del ``content``.

Dos familias distintas conviven aquí a propósito:

1. **DTOs de petición** (``CreateSystemRequest``…): lo que acepta la API.
2. **Forma del ``content``** (``DbSchemaContent`` y sus piezas): el contrato del
   JSONB de cada tipo de activo. NO es decoración: es lo que INV2 (parseo de DDL
   e introspección) debe producir y lo que INV4 (RECONCILE) compara columna a
   columna. Si el contenido fuera un dict libre, cada vía de carga inventaría su
   propia forma y el comparador tendría que adivinar.

Solo ``db_schema`` está cerrado en este bloque, porque es el único cuyo productor
existe ya (INV2). ``module``/``api``/``document`` se validan como objeto no vacío
y se cierran en INV3, cuando el extractor que los produce esté escrito. Cerrar
ahora una forma sin productor sería inventarla.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.inventory import (
    InventoryAssetOrigin,
    InventoryAssetType,
    InventorySystemKind,
    InventorySystemStatus,
    InventoryValidationStatus,
)

# --- Forma del `content` de un activo `db_schema` ----------------------------


class InventoryColumn(BaseModel):
    """Una columna tal y como existe HOY en el sistema inventariado."""

    name: str
    #: Tipo tal cual viene del origen (``character varying(120)``, ``NUMBER(10)``).
    #: Se conserva verbatim: es la verdad del sistema real.
    type: str
    #: Tipo normalizado al enum del Agente BD, si se pudo deducir. ``None`` cuando
    #: el tipo de origen no tiene equivalente claro — y no se adivina.
    logical_type: Optional[str] = None
    nullable: bool = True
    default: Optional[str] = None
    primary_key: bool = False
    comment: Optional[str] = None


class InventoryForeignKey(BaseModel):
    """Clave foránea declarada en el sistema inventariado."""

    name: Optional[str] = None
    columns: list[str] = Field(default_factory=list)
    referenced_table: str
    referenced_columns: list[str] = Field(default_factory=list)
    on_delete: Optional[str] = None


class InventoryConstraint(BaseModel):
    """Restricción declarativa (``unique`` o ``check``)."""

    kind: Literal["unique", "check"]
    name: Optional[str] = None
    columns: list[str] = Field(default_factory=list)
    #: Expresión verbatim para los ``check``; ``None`` en los ``unique``.
    expression: Optional[str] = None


class InventoryIndex(BaseModel):
    """Índice declarado sobre la tabla."""

    name: Optional[str] = None
    columns: list[str] = Field(default_factory=list)
    unique: bool = False


class InventoryTable(BaseModel):
    """Una tabla del esquema inventariado, con todo lo que RECONCILE compara."""

    name: str
    schema_name: Optional[str] = None
    comment: Optional[str] = None
    columns: list[InventoryColumn] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[InventoryForeignKey] = Field(default_factory=list)
    constraints: list[InventoryConstraint] = Field(default_factory=list)
    indexes: list[InventoryIndex] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _nombre_no_vacio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("una tabla sin nombre no es inventariable")
        return v


class DbSchemaContent(BaseModel):
    """Contenido de un activo ``db_schema``: el conjunto de tablas del esquema."""

    tables: list[InventoryTable] = Field(default_factory=list)
    #: Motor del que salió el esquema, si se conoce (``postgresql``, ``oracle``…).
    engine: Optional[str] = None

    @field_validator("tables")
    @classmethod
    def _sin_tablas_duplicadas(cls, v: list[InventoryTable]) -> list[InventoryTable]:
        """Dos tablas con el mismo nombre harían ambiguo el matching de INV4."""
        vistos: set[tuple[str, str]] = set()
        for tabla in v:
            clave = (tabla.schema_name or "", tabla.name.lower())
            if clave in vistos:
                raise ValueError(f"tabla duplicada en el esquema: {tabla.name}")
            vistos.add(clave)
        return v


def validate_asset_content(
    asset_type: InventoryAssetType, content: dict[str, Any]
) -> dict[str, Any]:
    """Valida el ``content`` según el tipo de activo y lo devuelve normalizado.

    Para ``db_schema`` aplica el contrato completo (y por tanto rechaza un esquema
    con tablas duplicadas o sin nombre, que INV4 no sabría comparar). Para los
    demás tipos exige, por ahora, un objeto no vacío: su forma se cierra en INV3
    junto al extractor que los produce.
    """
    if not isinstance(content, dict) or not content:
        raise ValueError("El contenido del activo no puede estar vacío.")
    if asset_type is InventoryAssetType.DB_SCHEMA:
        return DbSchemaContent.model_validate(content).model_dump(mode="json")
    return content


# --- DTOs de la API ----------------------------------------------------------


class StackEntry(BaseModel):
    """Una capa del stack de un sistema inventariado."""

    layer: str
    technology: str
    version: Optional[str] = None


class CreateSystemRequest(BaseModel):
    """Alta de un sistema en el inventario."""

    name: str = Field(min_length=1, max_length=200)
    kind: InventorySystemKind
    description: Optional[str] = None
    status: InventorySystemStatus = InventorySystemStatus.ACTIVO
    stack: Optional[list[StackEntry]] = None


class UpdateSystemRequest(BaseModel):
    """Edición de un sistema. Aplica **solo lo informado** (``None`` = no tocar)."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    kind: Optional[InventorySystemKind] = None
    description: Optional[str] = None
    status: Optional[InventorySystemStatus] = None
    stack: Optional[list[StackEntry]] = None


class CreateAssetRequest(BaseModel):
    """Alta manual de un activo (o de una versión nueva del mismo activo)."""

    asset_type: InventoryAssetType
    name: str = Field(min_length=1, max_length=200)
    content: dict[str, Any]
    description: Optional[str] = None
    origin: InventoryAssetOrigin = InventoryAssetOrigin.MANUAL
    origin_ref: Optional[str] = None


class UpdateAssetStatusRequest(BaseModel):
    """Marca un activo como revisado (o lo devuelve a ``importado``)."""

    validation_status: InventoryValidationStatus


class PromoteJobRequest(BaseModel):
    """Promoción de un artefacto terminado del ISDF al inventario (INV6)."""

    job_id: str = Field(min_length=1)
    #: Activo destino. Por defecto ``core`` (esquema) o ``api`` (superficie).
    asset_name: Optional[str] = Field(default=None, max_length=200)


class IntrospectRequest(BaseModel):
    """Petición de introspección read-only de una base de datos externa.

    **Solo un alias.** Deliberadamente NO hay campo para la cadena de conexión: si
    lo hubiera, quien pudiera escribir en el inventario podría apuntar el servidor
    a un host arbitrario. Los destinos posibles los fija el despliegue en
    ``INVENTORY_INTROSPECTION_DSNS``.
    """

    alias: str = Field(min_length=1, description="Alias del origen configurado")
    #: ``schema`` colisiona con `BaseModel.schema` de Pydantic; se expone con su
    #: nombre real por alias para no filtrar el detalle a la API.
    schema_name: str = Field(default="public", alias="schema")
    name: str = Field(default="core", max_length=200)

    model_config = {"populate_by_name": True}
