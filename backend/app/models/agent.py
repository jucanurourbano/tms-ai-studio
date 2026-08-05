"""Modelos ORM multi-agente (plataforma ISDF).

Generalización de las antiguas tablas ``ef_*`` a tablas compartidas por todos los
agentes del ISDF, discriminadas por ``agent_type`` (D1 del diseño). No hay tablas
propias por agente: el ``data`` del artefacto ya es JSONB agnóstico.

Tablas:
    ef_source_docs    — fuentes analizadas (archivo/texto). Solo la familia EF.
    agent_jobs        — trabajos de cualquier agente y su estado.
                        ``input_job_id`` enlaza cross-agente (Scrum → job EF).
    agent_artifacts   — artefacto persistido (JSONB) por job.
    agent_validations — validaciones del ciclo de afinamiento (NO mutan el artefacto).
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, IdMixin, JSONVariant, TimestampMixin


def pg_enum(enum_cls, name: str) -> SAEnum:
    """Construye un ``Enum`` que persiste los VALORES del enum (no los nombres).

    SQLAlchemy, por defecto, guarda el *nombre* del miembro (``TEXT``); las
    migraciones definen los tipos enum de Postgres a partir de los *valores*
    (``text``). ``values_callable`` alinea ambos: se persiste siempre el valor,
    coincidiendo con lo que crean las migraciones y con las claves de la API.
    """
    return SAEnum(
        enum_cls, name=name, values_callable=lambda e: [member.value for member in e]
    )


class AgentType(str, Enum):
    """Agente del ISDF que produce el job (discriminador multi-agente)."""

    EF = "ef"
    SCRUM = "scrum"
    ARQUITECTURA = "arquitectura"
    BD = "bd"
    API = "api"
    BACKEND = "backend"
    FRONTEND = "frontend"
    QA = "qa"
    DEVOPS = "devops"


class JobStatus(str, Enum):
    """Estado del trabajo de un agente."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    NEEDS_INPUT = "NEEDS_INPUT"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class JobStatusGroup(str, Enum):
    """Agrupación de estados para el filtro del historial.

    Los seis estados de :class:`JobStatus` son demasiados para una fila de tabs y
    algunos son transitorios. Se agrupan por **lo que el usuario quiere hacer**:
    abrir un resultado utilizable, revisar avisos, esperar algo en curso o
    diagnosticar un fallo.

    Vive junto a ``JobStatus`` (y no en la API o el frontend) para que el mapeo
    sea único: la clave del grupo es la misma en el query param, en la respuesta
    y en la URL del historial.
    """

    COMPLETADOS = "completados"
    AVISOS = "avisos"
    EN_PROCESO = "en_proceso"
    FALLIDOS = "fallidos"
    TODOS = "todos"


#: Estados que componen cada grupo. ``TODOS`` no filtra (ausente a propósito).
JOB_STATUS_GROUPS: dict[JobStatusGroup, tuple[JobStatus, ...]] = {
    JobStatusGroup.COMPLETADOS: (JobStatus.COMPLETED,),
    JobStatusGroup.AVISOS: (JobStatus.COMPLETED_WITH_WARNINGS,),
    # ``NEEDS_INPUT`` cuenta como "en proceso": el trabajo no terminó, está
    # esperando algo del usuario.
    JobStatusGroup.EN_PROCESO: (
        JobStatus.PENDING,
        JobStatus.RUNNING,
        JobStatus.NEEDS_INPUT,
    ),
    JobStatusGroup.FALLIDOS: (JobStatus.FAILED,),
}


#: Estados en los que un job **ya produjo un artefacto utilizable**. Es lo que
#: pueden consumir los agentes siguientes: un job fallido o en curso no tiene nada
#: que ofrecer, y ofrecerlo en un selector de origen solo genera errores del gate.
#: Los avisos SÍ cuentan: una cuarentena no invalida el artefacto.
USABLE_JOB_STATUSES: tuple[JobStatus, ...] = (
    JobStatus.COMPLETED,
    JobStatus.COMPLETED_WITH_WARNINGS,
)


def group_of_status(status: JobStatus) -> JobStatusGroup:
    """Grupo al que pertenece un estado (para agregar contadores)."""
    for grupo, estados in JOB_STATUS_GROUPS.items():
        if status in estados:
            return grupo
    return JobStatusGroup.TODOS


class EFSourceDocType(str, Enum):
    """Tipo de fuente (familia EF)."""

    DOCUMENT = "document"
    TEXT = "text"


class ValidationTargetType(str, Enum):
    """A qué apunta una validación del ciclo de afinamiento (enum extensible).

    - ``question``: pregunta al analista (EF) o al Product Owner (Scrum).
    - ``assumption``: supuesto de interpretación (EF).
    - ``estimate``: corrección de estimación (Scrum v1.1).
    """

    QUESTION = "question"
    ASSUMPTION = "assumption"
    ESTIMATE = "estimate"


class ValidationStatus(str, Enum):
    """Estado de una validación."""

    PENDIENTE = "pendiente"
    CONFIRMADO = "confirmado"
    CORREGIDO = "corregido"


class EFSourceDoc(Base, IdMixin, TimestampMixin):
    """Fuente analizada (familia EF). ``content_hash`` es único (idempotencia)."""

    __tablename__ = "ef_source_docs"

    filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    type: Mapped[EFSourceDocType] = mapped_column(
        pg_enum(EFSourceDocType, "ef_source_doc_type"), nullable=False
    )
    doc_metadata: Mapped[Optional[dict]] = mapped_column(JSONVariant, nullable=True)

    jobs: Mapped[list["AgentJob"]] = relationship(back_populates="source_doc")


class AgentJob(Base, IdMixin, TimestampMixin):
    """Trabajo de un agente del ISDF.

    ``parent_job_id`` enlaza un refine del MISMO agente; ``input_job_id`` enlaza la
    entrada CROSS-agente (p. ej. un job Scrum apunta al job EF de origen).
    ``source_doc_id`` solo lo usa la familia EF (nullable para los demás agentes).
    """

    __tablename__ = "agent_jobs"

    agent_type: Mapped[AgentType] = mapped_column(
        pg_enum(AgentType, "agent_type"), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "agent_job_status"),
        nullable=False,
        default=JobStatus.PENDING,
    )
    parent_job_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_jobs.id"), nullable=True
    )
    input_job_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_jobs.id"), nullable=True
    )
    source_doc_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ef_source_docs.id"), nullable=True
    )
    # Metadatos de historial (usabilidad del listado). ``title`` y ``source_type``
    # se desnormalizan al crear el job para evitar joins/N+1 en el listado y
    # generalizar a todos los agentes; se rellenan por la migración 0004.
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSONVariant, nullable=True)
    # Autor del job. Nullable: los jobs anteriores a la migración 0007 no tienen
    # autor conocido y no se inventa uno. ``ON DELETE SET NULL`` para que borrar
    # físicamente un usuario (algo que la app NO hace: usa baja lógica) jamás
    # arrastre el historial de trabajos.
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    source_doc: Mapped[Optional["EFSourceDoc"]] = relationship(back_populates="jobs")
    artifact: Mapped[Optional["AgentArtifactRow"]] = relationship(
        back_populates="job", uselist=False
    )
    validations: Mapped[list["AgentValidation"]] = relationship(back_populates="job")

    __table_args__ = (
        Index("ix_agent_jobs_agent_type", "agent_type"),
        Index("ix_agent_jobs_source_doc_id", "source_doc_id"),
        Index("ix_agent_jobs_input_job_id", "input_job_id"),
    )


class AgentArtifactRow(Base, IdMixin, TimestampMixin):
    """Artefacto persistido (JSONB) asociado a un job. Agnóstico del agente."""

    __tablename__ = "agent_artifacts"

    job_id: Mapped[str] = mapped_column(
        ForeignKey("agent_jobs.id"), nullable=False, unique=True
    )
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    data: Mapped[dict] = mapped_column(JSONVariant, nullable=False)

    job: Mapped["AgentJob"] = relationship(back_populates="artifact")


class AgentExternalLink(Base, IdMixin, TimestampMixin):
    """Auditoría de artefactos publicados en sistemas externos (p. ej. ClickUp).

    Registra qué historia originó cada tarea creada, cuándo y en qué lista, y
    permite la creación **idempotente** por ``external_key`` en la fase (b).
    """

    __tablename__ = "agent_external_links"

    job_id: Mapped[str] = mapped_column(ForeignKey("agent_jobs.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="clickup")
    story_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    external_key: Mapped[str] = mapped_column(String(128), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    list_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        Index(
            "ux_agent_external_link_key",
            "job_id",
            "provider",
            "external_key",
            unique=True,
        ),
    )


class StoryAssignment(Base, IdMixin, TimestampMixin):
    """Asignación de una historia del plan Scrum a un colaborador.

    Vive **FUERA del artefacto**, igual que las validaciones: el ``ScrumArtifact``
    es la salida del agente y no se muta: quién ejecuta cada historia es una
    decisión del equipo, posterior e independiente de la generación del plan (y
    revisable sin regenerar nada).

    Una historia tiene **como máximo un** responsable por plan (única sobre
    ``job_id`` + ``story_id``); reasignar actualiza la fila y su ``assigned_at``.
    """

    __tablename__ = "story_assignments"

    job_id: Mapped[str] = mapped_column(
        ForeignKey("agent_jobs.id", ondelete="CASCADE"), nullable=False
    )
    #: Id de la historia dentro del artefacto (``stories[].id``), no una FK.
    story_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: Cuándo se hizo ESTA asignación (se refresca al reasignar, a diferencia de
    #: ``created_at``, que conserva la primera vez que se tocó la historia).
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    assigned_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ux_story_assignment_job_story", "job_id", "story_id", unique=True),
        Index("ix_story_assignments_user_id", "user_id"),
    )


class SprintAssignment(Base, IdMixin, TimestampMixin):
    """Asignación de un **sprint completo** a un colaborador.

    Complementa :class:`StoryAssignment`: asignar un sprint hace que TODAS sus
    historias sin responsable propio pasen a mostrarse a nombre de esa persona.

    La cascada es **derivada, no materializada**: no se crean filas de
    ``story_assignments`` al asignar el sprint. Se resuelve al leer con la regla
    "historia > sprint". Así:
      - retirar la asignación del sprint deshace la cascada sin dejar huérfanas;
      - una asignación por historia sigue siendo una EXCEPCIÓN explícita en vez de
        quedar sobreescrita por la del sprint;
      - reasignar el sprint no pisa las excepciones que el equipo ya decidió.

    Única por ``(job_id, sprint_id)``: un sprint tiene un responsable por plan.
    """

    __tablename__ = "sprint_assignments"

    job_id: Mapped[str] = mapped_column(
        ForeignKey("agent_jobs.id", ondelete="CASCADE"), nullable=False
    )
    #: Id del sprint dentro del artefacto (``sprints[].id``), no una FK.
    sprint_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    assigned_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ux_sprint_assignment_job_sprint", "job_id", "sprint_id", unique=True),
        Index("ix_sprint_assignments_user_id", "user_id"),
    )


class AgentValidation(Base, IdMixin, TimestampMixin):
    """Validación del ciclo de afinamiento. Persiste aparte, sin mutar el artefacto."""

    __tablename__ = "agent_validations"

    job_id: Mapped[str] = mapped_column(ForeignKey("agent_jobs.id"), nullable=False)
    target_type: Mapped[ValidationTargetType] = mapped_column(
        pg_enum(ValidationTargetType, "agent_validation_target_type"),
        nullable=False,
    )
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ValidationStatus] = mapped_column(
        pg_enum(ValidationStatus, "agent_validation_status"),
        nullable=False,
        default=ValidationStatus.PENDIENTE,
    )
    respuesta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Quién respondió la validación (mismo criterio que ``AgentJob.created_by``).
    answered_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    job: Mapped["AgentJob"] = relationship(back_populates="validations")

    __table_args__ = (
        Index(
            "ux_agent_validation_job_target",
            "job_id",
            "target_type",
            "target_id",
            unique=True,
        ),
    )
