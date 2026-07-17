"""Modelos ORM del Agente EF.

Tablas:
    ef_source_docs  — fuentes analizadas (archivo/texto), con hash de contenido.
    ef_jobs         — trabajos de análisis y su estado.
    ef_artifacts    — EFArtifact persistido (JSONB) por job.
    ef_validations  — validaciones del ciclo de afinamiento (NO mutan el artefacto).
"""

from enum import Enum
from typing import Optional

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, IdMixin, JSONVariant, TimestampMixin


class JobStatus(str, Enum):
    """Estado del trabajo de análisis."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    NEEDS_INPUT = "NEEDS_INPUT"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class EFSourceDocType(str, Enum):
    """Tipo de fuente."""

    DOCUMENT = "document"
    TEXT = "text"


class ValidationTargetType(str, Enum):
    """A qué apunta una validación del ciclo de afinamiento."""

    QUESTION = "question"
    ASSUMPTION = "assumption"


class ValidationStatus(str, Enum):
    """Estado de una validación."""

    PENDIENTE = "pendiente"
    CONFIRMADO = "confirmado"
    CORREGIDO = "corregido"


class EFSourceDoc(Base, IdMixin, TimestampMixin):
    """Fuente analizada. ``content_hash`` es único (idempotencia)."""

    __tablename__ = "ef_source_docs"

    filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    type: Mapped[EFSourceDocType] = mapped_column(
        SAEnum(EFSourceDocType, name="ef_source_doc_type"), nullable=False
    )
    doc_metadata: Mapped[Optional[dict]] = mapped_column(JSONVariant, nullable=True)

    jobs: Mapped[list["EFJob"]] = relationship(back_populates="source_doc")


class EFJob(Base, IdMixin, TimestampMixin):
    """Trabajo de análisis del Agente EF."""

    __tablename__ = "ef_jobs"

    source_doc_id: Mapped[str] = mapped_column(
        ForeignKey("ef_source_docs.id"), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="ef_job_status"),
        nullable=False,
        default=JobStatus.PENDING,
    )
    parent_job_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ef_jobs.id"), nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSONVariant, nullable=True)

    source_doc: Mapped["EFSourceDoc"] = relationship(back_populates="jobs")
    artifact: Mapped[Optional["EFArtifactRow"]] = relationship(
        back_populates="job", uselist=False
    )
    validations: Mapped[list["EFValidation"]] = relationship(back_populates="job")

    __table_args__ = (Index("ix_ef_jobs_source_doc_id", "source_doc_id"),)


class EFArtifactRow(Base, IdMixin, TimestampMixin):
    """EFArtifact persistido (JSONB) asociado a un job."""

    __tablename__ = "ef_artifacts"

    job_id: Mapped[str] = mapped_column(
        ForeignKey("ef_jobs.id"), nullable=False, unique=True
    )
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    data: Mapped[dict] = mapped_column(JSONVariant, nullable=False)

    job: Mapped["EFJob"] = relationship(back_populates="artifact")


class EFValidation(Base, IdMixin, TimestampMixin):
    """Validación del ciclo de afinamiento. Persiste aparte, sin mutar el artefacto."""

    __tablename__ = "ef_validations"

    job_id: Mapped[str] = mapped_column(ForeignKey("ef_jobs.id"), nullable=False)
    target_type: Mapped[ValidationTargetType] = mapped_column(
        SAEnum(ValidationTargetType, name="ef_validation_target_type"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ValidationStatus] = mapped_column(
        SAEnum(ValidationStatus, name="ef_validation_status"),
        nullable=False,
        default=ValidationStatus.PENDIENTE,
    )
    respuesta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job: Mapped["EFJob"] = relationship(back_populates="validations")

    __table_args__ = (
        Index(
            "ux_ef_validation_job_target",
            "job_id",
            "target_type",
            "target_id",
            unique=True,
        ),
    )
