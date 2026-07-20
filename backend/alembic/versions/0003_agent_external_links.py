"""Auditoría de publicaciones externas (ClickUp): tabla agent_external_links.

Revision ID: 0003_agent_external_links
Revises: 0002_generalizar_agentes
Create Date: 2026-07-20
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_agent_external_links"
down_revision = "0002_generalizar_agentes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_external_links",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("story_id", sa.String(length=64), nullable=True),
        sa.Column("external_key", sa.String(length=128), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=True),
        sa.Column("list_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
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
        sa.ForeignKeyConstraint(["job_id"], ["agent_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_agent_external_link_key",
        "agent_external_links",
        ["job_id", "provider", "external_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_agent_external_link_key", table_name="agent_external_links")
    op.drop_table("agent_external_links")
