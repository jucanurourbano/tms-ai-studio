"""Esquema inicial del Agente EF.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ef_source_docs",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "type",
            sa.Enum("document", "text", name="ef_source_doc_type"),
            nullable=False,
        ),
        sa.Column("doc_metadata", postgresql.JSONB(), nullable=True),
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
        sa.UniqueConstraint("content_hash"),
    )

    op.create_table(
        "ef_jobs",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("source_doc_id", sa.String(length=26), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "NEEDS_INPUT",
                "COMPLETED",
                "COMPLETED_WITH_WARNINGS",
                "FAILED",
                name="ef_job_status",
            ),
            nullable=False,
        ),
        sa.Column("parent_job_id", sa.String(length=26), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
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
        sa.ForeignKeyConstraint(["source_doc_id"], ["ef_source_docs.id"]),
        sa.ForeignKeyConstraint(["parent_job_id"], ["ef_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ef_jobs_source_doc_id", "ef_jobs", ["source_doc_id"])

    op.create_table(
        "ef_artifacts",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
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
        sa.ForeignKeyConstraint(["job_id"], ["ef_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )

    op.create_table(
        "ef_validations",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column(
            "target_type",
            sa.Enum("question", "assumption", name="ef_validation_target_type"),
            nullable=False,
        ),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pendiente",
                "confirmado",
                "corregido",
                name="ef_validation_status",
            ),
            nullable=False,
        ),
        sa.Column("respuesta", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["job_id"], ["ef_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_ef_validation_job_target",
        "ef_validations",
        ["job_id", "target_type", "target_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_ef_validation_job_target", table_name="ef_validations")
    op.drop_table("ef_validations")
    op.drop_table("ef_artifacts")
    op.drop_index("ix_ef_jobs_source_doc_id", table_name="ef_jobs")
    op.drop_table("ef_jobs")
    op.drop_table("ef_source_docs")
    for enum_name in (
        "ef_validation_status",
        "ef_validation_target_type",
        "ef_job_status",
        "ef_source_doc_type",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
