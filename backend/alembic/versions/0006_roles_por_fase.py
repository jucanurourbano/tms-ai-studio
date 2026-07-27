"""Roles funcionales por fase ISDF + asignaciones adicionales por usuario.

Sustituye el rol binario (``admin`` | ``member``) por seis roles funcionales
(``admin``, ``procesos``, ``analista``, ``arquitecto``, ``developer``, ``qa``) y
añade la tabla ``user_module_grants``, que concede accesos extra por usuario y
**suma** sobre el permiso del rol.

Notas de la conversión del enum
-------------------------------
Postgres no permite *quitar* valores de un enum existente, así que no basta con
``ALTER TYPE ... ADD VALUE``: se crea un tipo nuevo (``user_role_v2``), se
convierte la columna con un ``USING`` que mapea ``member`` -> ``analista``, se
elimina el tipo antiguo y se renombra el nuevo a ``user_role``. Al terminar, el
nombre del tipo es el mismo que espera el modelo ORM.

**Las sesiones vigentes NO se rompen:** el ``sub`` del JWT es el id del usuario,
no su rol, y los ids no se tocan. Un usuario con sesión abierta sigue autenticado
y simplemente pasa a resolver sus permisos con el rol nuevo.

Revision ID: 0006_roles_por_fase
Revises: 0005_users
Create Date: 2026-07-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_roles_por_fase"
down_revision = "0005_users"
branch_labels = None
depends_on = None

ROLES = ("admin", "procesos", "analista", "arquitecto", "developer", "qa")
MODULES = (
    "ef",
    "scrum",
    "arquitectura",
    "bd",
    "api",
    "backend",
    "frontend",
    "qa",
    "devops",
    "config",
)
LEVELS = ("read", "full")


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # --- 1. rol: enum binario -> seis roles funcionales ----------------------
    if is_postgres:
        sa.Enum(*ROLES, name="user_role_v2").create(bind, checkfirst=False)
        # El default antiguo ('member') referencia el tipo viejo: fuera primero.
        op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
        op.execute("""
            ALTER TABLE users
            ALTER COLUMN role TYPE user_role_v2
            USING (
                CASE WHEN role::text = 'member' THEN 'analista' ELSE role::text END
            )::user_role_v2
            """)
        sa.Enum(name="user_role").drop(bind, checkfirst=True)
        op.execute("ALTER TYPE user_role_v2 RENAME TO user_role")
        op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'analista'")
    else:
        # SQLite (y otros sin tipos enum nativos): basta reescribir los datos.
        op.execute("UPDATE users SET role = 'analista' WHERE role = 'member'")

    # --- 2. asignaciones adicionales por usuario -----------------------------
    op.create_table(
        "user_module_grants",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("module", sa.Enum(*MODULES, name="access_module"), nullable=False),
        sa.Column("level", sa.Enum(*LEVELS, name="access_level"), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "module", name="uq_user_module_grant"),
    )
    op.create_index("ix_user_module_grants_user_id", "user_module_grants", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_index("ix_user_module_grants_user_id", table_name="user_module_grants")
    op.drop_table("user_module_grants")
    if is_postgres:
        sa.Enum(name="access_module").drop(bind, checkfirst=True)
        sa.Enum(name="access_level").drop(bind, checkfirst=True)

    # Vuelta al rol binario: todo lo que no sea admin cae a 'member' (la
    # granularidad por fase no tiene equivalente en el modelo anterior).
    if is_postgres:
        sa.Enum("admin", "member", name="user_role_old").create(bind, checkfirst=False)
        op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
        op.execute("""
            ALTER TABLE users
            ALTER COLUMN role TYPE user_role_old
            USING (
                CASE WHEN role::text = 'admin' THEN 'admin' ELSE 'member' END
            )::user_role_old
            """)
        sa.Enum(name="user_role").drop(bind, checkfirst=True)
        op.execute("ALTER TYPE user_role_old RENAME TO user_role")
        op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'member'")
    else:
        op.execute("UPDATE users SET role = 'member' WHERE role <> 'admin'")
