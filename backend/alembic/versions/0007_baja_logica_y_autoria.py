"""Baja lógica de usuarios + autoría de jobs y validaciones.

Dos cosas que van juntas porque la primera depende de la segunda:

1. ``users.deleted_at`` — **baja lógica** (soft delete). Se descarta el borrado
   físico y también la anonimización: los jobs y las validaciones pasan a
   referenciar al usuario que los creó, y anonimizar dejaría el historial sin
   respuesta a "¿quién hizo esto?". Conservar la fila mantiene la integridad
   referencial y además la baja es reversible.
2. ``agent_jobs.created_by`` y ``agent_validations.answered_by`` — **autoría**.
   Sin esto no existía ninguna forma de saber si un usuario tiene actividad
   registrada, que es la condición para recomendar desactivar en vez de eliminar.
   Ambas nullable: los registros anteriores a esta migración no tienen autor
   conocido y no se les inventa uno. ``ON DELETE SET NULL`` para que un borrado
   físico (que la app no hace) nunca arrastre el historial.

Revision ID: 0007_baja_logica_y_autoria
Revises: 0006_roles_por_fase
Create Date: 2026-07-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_baja_logica_y_autoria"
down_revision = "0006_roles_por_fase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "agent_jobs", sa.Column("created_by", sa.String(length=26), nullable=True)
    )
    op.create_foreign_key(
        "fk_agent_jobs_created_by",
        "agent_jobs",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_agent_jobs_created_by", "agent_jobs", ["created_by"])

    op.add_column(
        "agent_validations",
        sa.Column("answered_by", sa.String(length=26), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_validations_answered_by",
        "agent_validations",
        "users",
        ["answered_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_validations_answered_by", "agent_validations", ["answered_by"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_validations_answered_by", table_name="agent_validations")
    op.drop_constraint(
        "fk_agent_validations_answered_by", "agent_validations", type_="foreignkey"
    )
    op.drop_column("agent_validations", "answered_by")

    op.drop_index("ix_agent_jobs_created_by", table_name="agent_jobs")
    op.drop_constraint("fk_agent_jobs_created_by", "agent_jobs", type_="foreignkey")
    op.drop_column("agent_jobs", "created_by")

    op.drop_column("users", "deleted_at")
