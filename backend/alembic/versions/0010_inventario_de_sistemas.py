"""Inventario de Sistemas: memoria de lo que YA existe (INV1).

Dos tablas y cinco enums. El ISDF deja de ser greenfield: los agentes de diseño
podrán reconciliar lo que proponen contra lo que la organización ya tiene en
producción, en vez de proponer desde cero una tabla creada hace diez años.

Nota sobre el versionado: NO hay columna ``is_current``. La versión vigente de un
activo es la de mayor ``version`` dentro de ``(system_id, asset_type, name)`` y se
resuelve al leer. Una bandera materializada podría desincronizarse (dos filas
vigentes, o ninguna); un máximo derivado, no. La única sobre esas cuatro columnas
garantiza que dos cargas simultáneas no puedan compartir número de versión.

Revision ID: 0010_inventario_de_sistemas
Revises: 0009_especialidad_y_sprints
Create Date: 2026-08-10
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_inventario_de_sistemas"
down_revision = "0009_especialidad_y_sprints"
branch_labels = None
depends_on = None

SYSTEM_KINDS = ("destino", "legado", "externo")
SYSTEM_STATUSES = ("en_construccion", "activo", "en_migracion", "retirado")
ASSET_TYPES = ("db_schema", "module", "api", "document")
ASSET_ORIGINS = ("ddl_dump", "introspection", "document", "manual", "isdf")
VALIDATION_STATUSES = ("importado", "validado")


def upgrade() -> None:
    # Los tipos enum NO se crean a mano: `create_table` los emite al ver la
    # columna, igual que en la migración 0001. Crearlos antes con `checkfirst` y
    # dejar además que `create_table` los emita produce un `CREATE TYPE`
    # duplicado y la migración aborta.
    kind = sa.Enum(*SYSTEM_KINDS, name="inventory_system_kind")
    status = sa.Enum(*SYSTEM_STATUSES, name="inventory_system_status")
    asset_type = sa.Enum(*ASSET_TYPES, name="inventory_asset_type")
    origin = sa.Enum(*ASSET_ORIGINS, name="inventory_asset_origin")
    validation = sa.Enum(*VALIDATION_STATUSES, name="inventory_validation_status")

    # JSONB en Postgres, JSON en el resto (mismo criterio que `JSONVariant`).
    json_type = sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql")

    op.create_table(
        "inventory_systems",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", kind, nullable=False),
        sa.Column("status", status, nullable=False, server_default="activo"),
        sa.Column("stack", json_type, nullable=True),
        sa.Column("created_by", sa.String(length=26), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="ux_inventory_systems_name"),
    )
    op.create_index("ix_inventory_systems_kind", "inventory_systems", ["kind"])

    op.create_table(
        "inventory_assets",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("system_id", sa.String(length=26), nullable=False),
        sa.Column("asset_type", asset_type, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", json_type, nullable=False),
        sa.Column("origin", origin, nullable=False),
        sa.Column("origin_ref", sa.String(length=512), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "validation_status", validation, nullable=False, server_default="importado"
        ),
        sa.Column("created_by", sa.String(length=26), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["system_id"], ["inventory_systems.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_inventory_asset_version",
        "inventory_assets",
        ["system_id", "asset_type", "name", "version"],
        unique=True,
    )
    op.create_index(
        "ix_inventory_assets_system_type",
        "inventory_assets",
        ["system_id", "asset_type"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_index("ix_inventory_assets_system_type", table_name="inventory_assets")
    op.drop_index("ux_inventory_asset_version", table_name="inventory_assets")
    op.drop_table("inventory_assets")
    op.drop_index("ix_inventory_systems_kind", table_name="inventory_systems")
    op.drop_table("inventory_systems")

    if is_postgres:
        for name in (
            "inventory_validation_status",
            "inventory_asset_origin",
            "inventory_asset_type",
            "inventory_system_status",
            "inventory_system_kind",
        ):
            sa.Enum(name=name).drop(bind, checkfirst=True)
