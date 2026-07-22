"""Tabla de usuarios y autenticación (email + password_hash + rol).

Introduce la tabla ``users`` para la autenticación real de la plataforma:
identidad (email único, nombre), credenciales (hash bcrypt) y rol
(``admin`` | ``member``). El primer usuario del sistema se crea vía el endpoint
de bootstrap (``POST /auth/register`` sin auth cuando la tabla está vacía) y
nace ``admin``.

Revision ID: 0005_users
Revises: 0004_job_history_metadata
Create Date: 2026-07-22
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_users"
down_revision = "0004_job_history_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # El tipo enum ``user_role`` lo crea ``create_table`` de forma implícita (mismo
    # patrón que la migración inicial 0001); se elimina explícitamente en el
    # downgrade porque ``drop_table`` no lo hace.
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "member", name="user_role"),
            nullable=False,
            server_default="member",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
