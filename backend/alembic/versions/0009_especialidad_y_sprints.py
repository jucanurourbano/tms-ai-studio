"""Especialidad como enum cerrado + asignación de sprints completos.

1. ``users.position`` (texto libre) -> ``users.specialty`` (enum
   ``backend|frontend|db|qa|fullstack|otro``). Con texto libre acabarían
   conviviendo "Backend", "backend" y "BackEnd" sin poder agrupar ni filtrar, y
   la especialidad se muestra en el selector "Asignar a" del plan. La conversión
   mapea los valores conocidos (sin distinguir mayúsculas ni acentos habituales)
   y manda el resto a ``otro`` — **nada se pierde en silencio**: lo que no
   encaja queda como ``otro`` y se puede reclasificar desde el panel.
2. ``sprint_assignments``: responsable de un sprint completo. La cascada a las
   historias es **derivada** (regla "historia > sprint" al leer), no
   materializada, así que esta tabla no duplica nada de ``story_assignments``.

Revision ID: 0009_especialidad_y_sprints
Revises: 0008_equipo_y_asignaciones
Create Date: 2026-07-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_especialidad_y_sprints"
down_revision = "0008_equipo_y_asignaciones"
branch_labels = None
depends_on = None

SPECIALTIES = ("backend", "frontend", "db", "qa", "fullstack", "otro")

# Texto libre -> enum. Se comparan en minúsculas y sin espacios sobrantes.
_MAPEO = {
    "backend": "backend",
    "back-end": "backend",
    "back end": "backend",
    "frontend": "frontend",
    "front-end": "frontend",
    "front end": "frontend",
    "db": "db",
    "bd": "db",
    "base de datos": "db",
    "database": "db",
    "qa": "qa",
    "quality assurance": "qa",
    "testing": "qa",
    "fullstack": "fullstack",
    "full-stack": "fullstack",
    "full stack": "fullstack",
}


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # --- 1. especialidad -----------------------------------------------------
    especialidad = sa.Enum(*SPECIALTIES, name="user_specialty")
    if is_postgres:
        especialidad.create(bind, checkfirst=True)
    op.add_column("users", sa.Column("specialty", especialidad, nullable=True))

    # Conversión de los valores conocidos; el resto de textos no vacíos -> otro.
    casos = " ".join(
        f"WHEN lower(trim(position)) = '{origen}' THEN '{destino}'"
        for origen, destino in _MAPEO.items()
    )
    cast = "::user_specialty" if is_postgres else ""
    op.execute(f"""
        UPDATE users
        SET specialty = (CASE {casos} ELSE 'otro' END){cast}
        WHERE position IS NOT NULL AND trim(position) <> ''
        """)
    op.drop_column("users", "position")

    # --- 2. asignación de sprints -------------------------------------------
    op.create_table(
        "sprint_assignments",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("sprint_id", sa.String(length=64), nullable=False),
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
        "ux_sprint_assignment_job_sprint",
        "sprint_assignments",
        ["job_id", "sprint_id"],
        unique=True,
    )
    op.create_index("ix_sprint_assignments_user_id", "sprint_assignments", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_index("ix_sprint_assignments_user_id", table_name="sprint_assignments")
    op.drop_index("ux_sprint_assignment_job_sprint", table_name="sprint_assignments")
    op.drop_table("sprint_assignments")

    # Vuelta a texto libre: se conserva el valor del enum como etiqueta.
    op.add_column("users", sa.Column("position", sa.String(length=120), nullable=True))
    op.execute(
        "UPDATE users SET position = specialty::text"
        if is_postgres
        else "UPDATE users SET position = specialty"
    )
    op.drop_column("users", "specialty")
    if is_postgres:
        sa.Enum(name="user_specialty").drop(bind, checkfirst=True)
