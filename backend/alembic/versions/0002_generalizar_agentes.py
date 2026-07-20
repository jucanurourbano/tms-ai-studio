"""Generalización multi-agente: ef_* -> agent_* (D1 del diseño).

Renombra las tablas ``ef_jobs`` / ``ef_artifacts`` / ``ef_validations`` a
``agent_jobs`` / ``agent_artifacts`` / ``agent_validations``, agrega el
discriminador ``agent_type`` y el enlace cross-agente ``input_job_id``, y hace
``source_doc_id`` nullable (solo la familia EF lo usa). ``ef_source_docs`` no
cambia. No hay datos de producción; los jobs existentes se marcan como ``ef``.

Revision ID: 0002_generalizar_agentes
Revises: 0001_initial
Create Date: 2026-07-20
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_generalizar_agentes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_AGENT_TYPES = (
    "ef",
    "scrum",
    "arquitectura",
    "bd",
    "api",
    "backend",
    "frontend",
    "qa",
    "devops",
)


def upgrade() -> None:
    # 1) Renombrar los tipos enum que conservan sus valores.
    op.execute("ALTER TYPE ef_job_status RENAME TO agent_job_status")
    op.execute(
        "ALTER TYPE ef_validation_target_type RENAME TO agent_validation_target_type"
    )
    op.execute("ALTER TYPE ef_validation_status RENAME TO agent_validation_status")

    # Nuevo valor extensible para validaciones (Scrum v1.1: corrección de estimación).
    op.execute(
        "ALTER TYPE agent_validation_target_type ADD VALUE IF NOT EXISTS 'estimate'"
    )

    # 2) Nuevo enum discriminador de agente.
    agent_type = sa.Enum(*_AGENT_TYPES, name="agent_type")
    agent_type.create(op.get_bind(), checkfirst=True)

    # 3) Renombrar las tablas.
    op.rename_table("ef_jobs", "agent_jobs")
    op.rename_table("ef_artifacts", "agent_artifacts")
    op.rename_table("ef_validations", "agent_validations")

    # 4) agent_jobs: agent_type (default 'ef' para las filas existentes) + input_job_id.
    op.add_column(
        "agent_jobs",
        sa.Column("agent_type", agent_type, nullable=False, server_default="ef"),
    )
    op.alter_column("agent_jobs", "agent_type", server_default=None)
    op.add_column(
        "agent_jobs", sa.Column("input_job_id", sa.String(length=26), nullable=True)
    )
    op.alter_column("agent_jobs", "source_doc_id", nullable=True)
    op.create_foreign_key(
        "fk_agent_jobs_input_job_id",
        "agent_jobs",
        "agent_jobs",
        ["input_job_id"],
        ["id"],
    )

    # 5) Reindexado con nombres del nuevo esquema.
    op.execute(
        "ALTER INDEX ix_ef_jobs_source_doc_id RENAME TO ix_agent_jobs_source_doc_id"
    )
    op.execute(
        "ALTER INDEX ux_ef_validation_job_target RENAME TO ux_agent_validation_job_target"
    )
    op.create_index("ix_agent_jobs_agent_type", "agent_jobs", ["agent_type"])
    op.create_index("ix_agent_jobs_input_job_id", "agent_jobs", ["input_job_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_jobs_input_job_id", table_name="agent_jobs")
    op.drop_index("ix_agent_jobs_agent_type", table_name="agent_jobs")
    op.execute(
        "ALTER INDEX ux_agent_validation_job_target RENAME TO ux_ef_validation_job_target"
    )
    op.execute(
        "ALTER INDEX ix_agent_jobs_source_doc_id RENAME TO ix_ef_jobs_source_doc_id"
    )

    op.drop_constraint("fk_agent_jobs_input_job_id", "agent_jobs", type_="foreignkey")
    op.alter_column("agent_jobs", "source_doc_id", nullable=False)
    op.drop_column("agent_jobs", "input_job_id")
    op.drop_column("agent_jobs", "agent_type")

    op.rename_table("agent_validations", "ef_validations")
    op.rename_table("agent_artifacts", "ef_artifacts")
    op.rename_table("agent_jobs", "ef_jobs")

    sa.Enum(name="agent_type").drop(op.get_bind(), checkfirst=True)

    # Nota: el valor 'estimate' del enum de validaciones no se elimina (Postgres no
    # soporta quitar valores de un enum); es inocuo. Se renombran los tipos de vuelta.
    op.execute("ALTER TYPE agent_validation_status RENAME TO ef_validation_status")
    op.execute(
        "ALTER TYPE agent_validation_target_type RENAME TO ef_validation_target_type"
    )
    op.execute("ALTER TYPE agent_job_status RENAME TO ef_job_status")
