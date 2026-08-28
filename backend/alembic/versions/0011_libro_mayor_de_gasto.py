"""Libro mayor de gasto en LLM: una fila por llamada al modelo.

El ``0011`` estaba nominalmente apartado para QC2, que quedó **aplazado**
(``docs/diseno-qa-modo-c.md`` §0.bis); si QC2 se reanuda, toma el ``0012``.

``cost_usd`` es ``NUMERIC(12,6)`` y no ``float``: es dinero que se suma miles de
veces contra un umbral, y el error de coma flotante acumulado no tiene por qué
aparecer en la decisión de bloquear.

``job_id`` es nullable con ``ON DELETE SET NULL``, mismo criterio que
``agent_jobs.created_by``: el total del mes no puede cambiar porque alguien borró
un job, y la fila conserva su ``agent_role``.

Revision ID: 0011_libro_mayor_de_gasto
Revises: 0010_inventario_de_sistemas
Create Date: 2026-08-28
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_libro_mayor_de_gasto"
down_revision = "0010_inventario_de_sistemas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_spend",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=True),
        sa.Column("agent_role", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("usage_source", sa.String(length=16), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "cache_read_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "cache_write_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["agent_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_spend_created_at", "llm_spend", ["created_at"])
    op.create_index("ix_llm_spend_job_id", "llm_spend", ["job_id"])
    op.create_index("ix_llm_spend_agent_stage", "llm_spend", ["agent_role", "stage"])


def downgrade() -> None:
    op.drop_index("ix_llm_spend_agent_stage", table_name="llm_spend")
    op.drop_index("ix_llm_spend_job_id", table_name="llm_spend")
    op.drop_index("ix_llm_spend_created_at", table_name="llm_spend")
    op.drop_table("llm_spend")
