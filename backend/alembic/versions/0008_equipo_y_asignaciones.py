"""Perfil de equipo del usuario + asignación de historias del plan Scrum.

1. ``users``: correo **institucional** (puede coincidir con el de acceso o
   diferir; es el que se exporta a ClickUp como responsable), ``position``
   (cargo/especialidad) y ``available_for_assignment``.
2. ``story_assignments``: quién ejecuta cada historia de un plan Scrum. Vive
   **fuera del artefacto**, igual que las validaciones — el ``ScrumArtifact`` es
   la salida del agente y no se muta; la asignación es una decisión del equipo,
   posterior e independiente, revisable sin regenerar el plan.
   Única por ``(job_id, story_id)``: una historia tiene como máximo un
   responsable, y reasignar actualiza la fila.

Revision ID: 0008_equipo_y_asignaciones
Revises: 0007_baja_logica_y_autoria
Create Date: 2026-07-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_equipo_y_asignaciones"
down_revision = "0007_baja_logica_y_autoria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 1. perfil de equipo -------------------------------------------------
    op.add_column(
        "users",
        sa.Column("institutional_email", sa.String(length=320), nullable=True),
    )
    op.add_column("users", sa.Column("position", sa.String(length=120), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "available_for_assignment",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # --- 2. asignación de historias ------------------------------------------
    op.create_table(
        "story_assignments",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("story_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by", sa.String(length=26), nullable=True),
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
        sa.ForeignKeyConstraint(["job_id"], ["agent_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_story_assignment_job_story",
        "story_assignments",
        ["job_id", "story_id"],
        unique=True,
    )
    op.create_index("ix_story_assignments_user_id", "story_assignments", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_story_assignments_user_id", table_name="story_assignments")
    op.drop_index("ux_story_assignment_job_story", table_name="story_assignments")
    op.drop_table("story_assignments")

    op.drop_column("users", "available_for_assignment")
    op.drop_column("users", "position")
    op.drop_column("users", "institutional_email")
