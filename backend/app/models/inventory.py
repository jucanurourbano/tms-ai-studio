"""Modelos ORM del **Inventario de Sistemas** (evolución brownfield del ISDF).

Hasta aquí el ISDF era *greenfield*: cada agente diseñaba desde el EF como si no
existiera nada. Pero Urbano no parte de cero — tiene sistemas en producción, un
esquema de datos vivo y un programa de modernización en curso. El inventario es
la memoria de **lo que ya existe**, y es lo que permite a la fase RECONCILE
(INV4) decir "esto ya está, reutilízalo" en vez de proponer una tabla `usuarios`
que lleva diez años creada.

Tablas:
    inventory_systems — un sistema de la organización (destino/legado/externo).
    inventory_assets  — un activo de ese sistema (esquema de BD, módulo, API,
                        documento), con su contenido estructurado y su versión.

Versionado
----------
Un activo NO se sobrescribe: cada carga crea una **fila nueva** con
``version = anterior + 1`` y la anterior se conserva. La versión vigente es la de
mayor ``version`` dentro de ``(system_id, asset_type, name)`` y se resuelve **al
leer** — no hay bandera ``is_current`` que mantener. Es la misma decisión que la
cascada sprint→historia del Scrum: un dato derivado no puede desincronizarse,
una bandera materializada sí.
"""

from enum import Enum
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .agent import pg_enum
from .base import Base, IdMixin, JSONVariant, TimestampMixin


class InventorySystemKind(str, Enum):
    """Papel del sistema dentro del programa de modernización."""

    #: Sistema al que se migra (el TMS moderno). Es contra este que reconcilian
    #: los agentes de diseño: lo que proponen acaba aquí.
    DESTINO = "destino"
    #: Sistema en producción que será reemplazado o absorbido.
    LEGADO = "legado"
    #: Sistema de un tercero con el que hay que integrarse (no se modifica).
    EXTERNO = "externo"


class InventorySystemStatus(str, Enum):
    """Momento del ciclo de vida en que está el sistema."""

    EN_CONSTRUCCION = "en_construccion"
    ACTIVO = "activo"
    EN_MIGRACION = "en_migracion"
    RETIRADO = "retirado"


class InventoryAssetType(str, Enum):
    """Naturaleza del activo inventariado (decide la forma de ``content``)."""

    #: Esquema de base de datos: tablas, columnas, PKs, FKs, constraints.
    DB_SCHEMA = "db_schema"
    #: Módulo funcional del sistema (agrupa funcionalidades y entidades).
    MODULE = "module"
    #: Superficie de API expuesta por el sistema.
    API = "api"
    #: Conocimiento extraído de un documento (diseño, manual, acta).
    DOCUMENT = "document"


class InventoryAssetOrigin(str, Enum):
    """De dónde salió el activo. Es trazabilidad, no metadato decorativo.

    Un activo cargado desde un dump de producción y otro deducido por un LLM a
    partir de un documento NO merecen la misma confianza al reconciliar, y quien
    revisa el inventario tiene derecho a distinguirlos de un vistazo.
    """

    #: Dump DDL (.sql) parseado con sqlglot.
    DDL_DUMP = "ddl_dump"
    #: Introspección read-only de un motor real (``information_schema``).
    INTROSPECTION = "introspection"
    #: Extracción de conocimiento desde un documento (docx/pdf) vía LLM.
    DOCUMENT = "document"
    #: Alta o edición manual desde el panel.
    MANUAL = "manual"
    #: Promovido desde un artefacto generado por el propio ISDF (INV6).
    ISDF = "isdf"


class InventoryValidationStatus(str, Enum):
    """Cuánto se ha revisado el activo.

    ``importado`` es el estado de nacimiento de todo lo que entra por una vía
    automática: está cargado, pero **nadie lo ha mirado**. ``validado`` significa
    que una persona lo confirmó. La distinción importa porque RECONCILE decide
    contra este contenido: reutilizar una tabla que un parser dedujo mal es
    peor que no tener el dato.
    """

    IMPORTADO = "importado"
    VALIDADO = "validado"


class InventorySystem(Base, IdMixin, TimestampMixin):
    """Un sistema de la organización, con su stack y su estado."""

    __tablename__ = "inventory_systems"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kind: Mapped[InventorySystemKind] = mapped_column(
        pg_enum(InventorySystemKind, "inventory_system_kind"), nullable=False
    )
    status: Mapped[InventorySystemStatus] = mapped_column(
        pg_enum(InventorySystemStatus, "inventory_system_status"),
        nullable=False,
        default=InventorySystemStatus.ACTIVO,
    )
    #: Stack del sistema como lista de ``{layer, technology, version}``. Espeja la
    #: forma de ``stack[]`` del ArchitectureArtifact y las capas de
    #: ``tech_stack.yaml``, para poder compararlos sin traducir nada.
    stack: Mapped[Optional[list]] = mapped_column(JSONVariant, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    assets: Mapped[list["InventoryAsset"]] = relationship(
        back_populates="system", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_inventory_systems_kind", "kind"),)


class InventoryAsset(Base, IdMixin, TimestampMixin):
    """Un activo de un sistema, en una versión concreta.

    ``content`` es JSONB y su forma depende de ``asset_type`` (ver
    ``app/schemas/inventario.py``). Para ``db_schema`` estructura tablas, columnas,
    tipos, PKs, FKs y constraints: es lo que RECONCILE compara columna a columna.

    Único por ``(system_id, asset_type, name, version)``: dos cargas del mismo
    activo producen versiones distintas, nunca una colisión silenciosa.
    """

    __tablename__ = "inventory_assets"

    system_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_systems.id", ondelete="CASCADE"), nullable=False
    )
    asset_type: Mapped[InventoryAssetType] = mapped_column(
        pg_enum(InventoryAssetType, "inventory_asset_type"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    origin: Mapped[InventoryAssetOrigin] = mapped_column(
        pg_enum(InventoryAssetOrigin, "inventory_asset_origin"), nullable=False
    )
    #: Referencia legible al origen concreto: nombre del archivo, host de la
    #: introspección, id del job del ISDF que lo promovió. Sin esto, `origin` dice
    #: "vino de un dump" pero no de cuál.
    origin_ref: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    validation_status: Mapped[InventoryValidationStatus] = mapped_column(
        pg_enum(InventoryValidationStatus, "inventory_validation_status"),
        nullable=False,
        default=InventoryValidationStatus.IMPORTADO,
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    system: Mapped["InventorySystem"] = relationship(back_populates="assets")

    __table_args__ = (
        Index(
            "ux_inventory_asset_version",
            "system_id",
            "asset_type",
            "name",
            "version",
            unique=True,
        ),
        Index("ix_inventory_assets_system_type", "system_id", "asset_type"),
    )
