"""Metadatos de historial en agent_jobs: title, source_type, version, completed_at.

Mejora de usabilidad del listado de jobs (EF y Scrum): expone por cada job un
título legible, el tipo de fuente (document|text), la versión (v1 original, v2+
refinado) y la fecha de finalización. Los tres primeros se **desnormalizan** en
``agent_jobs`` para que el listado sea una consulta de una sola tabla (sin joins
ni N+1) y para generalizar a todos los agentes del ISDF.

La migración **rellena los jobs existentes** cuando es posible:
- ``title``/``source_type`` desde la fuente (``ef_source_docs``) de los jobs EF, y
  luego se heredan cross-agente (Scrum → EF por ``input_job_id``) y en la cadena
  de afinamiento (por ``parent_job_id``).
- ``completed_at`` = ``updated_at`` para los jobs en estado terminal.
- ``version`` = profundidad en la cadena de refine (CTE recursivo).

Revision ID: 0004_job_history_metadata
Revises: 0003_agent_external_links
Create Date: 2026-07-20
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_job_history_metadata"
down_revision = "0003_agent_external_links"
branch_labels = None
depends_on = None

_TERMINAL = ("COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED")


def upgrade() -> None:
    op.add_column(
        "agent_jobs", sa.Column("title", sa.String(length=512), nullable=True)
    )
    op.add_column(
        "agent_jobs", sa.Column("source_type", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "agent_jobs",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "agent_jobs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 1) title/source_type desde la fuente (jobs EF con source_doc_id).
    op.execute("""
        UPDATE agent_jobs AS j
        SET title = COALESCE(j.title, d.filename),
            source_type = COALESCE(j.source_type, d.type::text)
        FROM ef_source_docs AS d
        WHERE j.source_doc_id = d.id
        """)
    # Para texto libre el filename es '<título>.txt'; se recupera el título.
    op.execute("""
        UPDATE agent_jobs
        SET title = left(title, length(title) - 4)
        WHERE source_type = 'text' AND title LIKE '%.txt'
        """)
    # 2) Herencia cross-agente: Scrum toma el título del EF de origen (input_job_id).
    op.execute("""
        UPDATE agent_jobs AS c
        SET title = p.title, source_type = p.source_type
        FROM agent_jobs AS p
        WHERE c.input_job_id = p.id AND c.title IS NULL
        """)
    # 3) Herencia en la cadena de afinamiento (parent_job_id).
    op.execute("""
        UPDATE agent_jobs AS c
        SET title = p.title, source_type = p.source_type
        FROM agent_jobs AS p
        WHERE c.parent_job_id = p.id AND c.title IS NULL
        """)
    # 4) completed_at para los jobs ya terminales (mejor esfuerzo = updated_at).
    op.execute("""
        UPDATE agent_jobs
        SET completed_at = updated_at
        WHERE status IN ('COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED')
          AND completed_at IS NULL
        """)
    # 5) version = profundidad en la cadena de refine (raíz = 1).
    op.execute("""
        WITH RECURSIVE chain AS (
            SELECT id, 1 AS v
            FROM agent_jobs
            WHERE parent_job_id IS NULL
            UNION ALL
            SELECT j.id, c.v + 1
            FROM agent_jobs AS j
            JOIN chain AS c ON j.parent_job_id = c.id
        )
        UPDATE agent_jobs AS a
        SET version = chain.v
        FROM chain
        WHERE a.id = chain.id
        """)

    # Deja de forzar el server_default: las nuevas filas reciben la versión del ORM.
    op.alter_column("agent_jobs", "version", server_default=None)


def downgrade() -> None:
    op.drop_column("agent_jobs", "completed_at")
    op.drop_column("agent_jobs", "version")
    op.drop_column("agent_jobs", "source_type")
    op.drop_column("agent_jobs", "title")
