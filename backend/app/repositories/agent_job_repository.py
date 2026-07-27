"""Repositorio genérico multi-agente (capa repositories).

Reemplaza al antiguo ``EFRepository`` por uno agnóstico del agente, discriminado
por ``agent_type`` (D1 del diseño). Recibe/devuelve ``dict`` para el artefacto y
las métricas, respetando el flujo api -> services -> repositories.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import (
    JOB_STATUS_GROUPS,
    AgentArtifactRow,
    AgentExternalLink,
    AgentJob,
    AgentType,
    AgentValidation,
    EFSourceDoc,
    EFSourceDocType,
    JobStatus,
    JobStatusGroup,
    ValidationStatus,
    ValidationTargetType,
    group_of_status,
)

_COMPLETED = (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS)
# Estados terminales: al alcanzarlos se sella ``completed_at`` (fecha de finalización).
_TERMINAL = (
    JobStatus.COMPLETED,
    JobStatus.COMPLETED_WITH_WARNINGS,
    JobStatus.FAILED,
)


class AgentJobRepository:
    """Operaciones de persistencia comunes a todos los agentes del ISDF."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Fuentes (familia EF) -----------------------------------------------

    async def get_or_create_source_doc(
        self,
        content_hash: str,
        doc_type: EFSourceDocType,
        filename: Optional[str] = None,
        doc_metadata: Optional[dict] = None,
    ) -> EFSourceDoc:
        """Devuelve la fuente con ese hash o la crea (idempotencia por hash)."""
        existing = await self.session.scalar(
            select(EFSourceDoc).where(EFSourceDoc.content_hash == content_hash)
        )
        if existing is not None:
            return existing
        doc = EFSourceDoc(
            content_hash=content_hash,
            type=doc_type,
            filename=filename,
            doc_metadata=doc_metadata,
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    # --- Jobs ---------------------------------------------------------------

    async def create_job(
        self,
        agent_type: AgentType,
        *,
        source_doc_id: Optional[str] = None,
        parent_job_id: Optional[str] = None,
        input_job_id: Optional[str] = None,
        title: Optional[str] = None,
        source_type: Optional[str] = None,
        version: int = 1,
        created_by: Optional[str] = None,
    ) -> AgentJob:
        """Crea un job en estado PENDING para el agente indicado.

        ``title``/``source_type`` se desnormalizan aquí (historial) y ``version``
        numera la cadena de afinamiento (v1 original, v2+ refinado).
        ``created_by`` atribuye el job a quien lo lanzó (nullable: los jobs
        anteriores a la migración 0007 no tienen autor conocido).
        """
        job = AgentJob(
            agent_type=agent_type,
            source_doc_id=source_doc_id,
            parent_job_id=parent_job_id,
            input_job_id=input_job_id,
            title=title,
            source_type=source_type,
            version=version,
            status=JobStatus.PENDING,
            created_by=created_by,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_job(self, job_id: str) -> Optional[AgentJob]:
        """Recupera un job por id."""
        return await self.session.get(AgentJob, job_id)

    async def find_completed_job_by_hash(
        self, content_hash: str, agent_type: AgentType = AgentType.EF
    ) -> Optional[AgentJob]:
        """Último job COMPLETED[_WITH_WARNINGS] de ese agente para el hash dado."""
        stmt = (
            select(AgentJob)
            .join(EFSourceDoc, AgentJob.source_doc_id == EFSourceDoc.id)
            .where(
                EFSourceDoc.content_hash == content_hash,
                AgentJob.agent_type == agent_type,
                AgentJob.status.in_(_COMPLETED),
                AgentJob.parent_job_id.is_(None),
            )
            .order_by(AgentJob.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def update_job_status(
        self, job_id: str, status: JobStatus, error: Optional[str] = None
    ) -> AgentJob:
        """Actualiza el estado (y opcionalmente el error) de un job."""
        job = await self.session.get(AgentJob, job_id)
        if job is None:
            raise ValueError(f"Job no encontrado: {job_id}")
        job.status = status
        if error is not None:
            job.error = error
        # Sella la fecha de finalización la primera vez que se alcanza un estado
        # terminal (idempotente ante reintentos con checkpointing).
        if status in _TERMINAL and job.completed_at is None:
            job.completed_at = datetime.now(timezone.utc)
        await self.session.flush()
        return job

    async def update_job_metrics(self, job_id: str, metrics: dict) -> AgentJob:
        """Persiste las métricas reales de la corrida."""
        job = await self.session.get(AgentJob, job_id)
        if job is None:
            raise ValueError(f"Job no encontrado: {job_id}")
        job.metrics = metrics
        await self.session.flush()
        return job

    async def list_jobs(
        self,
        *,
        agent_type: Optional[AgentType] = None,
        limit: int = 20,
        offset: int = 0,
        status_group: JobStatusGroup = JobStatusGroup.TODOS,
    ) -> tuple[list[AgentJob], int]:
        """Listado paginado de jobs (más recientes primero) + total del filtro.

        Si se pasa ``agent_type`` filtra por ese agente; si no, devuelve todos.
        ``status_group`` filtra por grupo de estado (ver ``JOB_STATUS_GROUPS``).

        El filtro se aplica **en la consulta**, no sobre la página ya traída: si
        no, la paginación de cada pestaña mentiría (una página de 20 podría
        quedarse en 3 filas tras filtrar en el cliente).
        """
        base = select(AgentJob)
        count_stmt = select(func.count()).select_from(AgentJob)
        if agent_type is not None:
            base = base.where(AgentJob.agent_type == agent_type)
            count_stmt = count_stmt.where(AgentJob.agent_type == agent_type)

        estados = JOB_STATUS_GROUPS.get(status_group)
        if estados:
            base = base.where(AgentJob.status.in_(estados))
            count_stmt = count_stmt.where(AgentJob.status.in_(estados))

        total = await self.session.scalar(count_stmt) or 0
        # ``id`` (ULID, ordenable por tiempo) desempata cuando dos jobs comparten
        # ``created_at`` (resolución baja del reloj), garantizando orden estable.
        rows = await self.session.scalars(
            base.order_by(AgentJob.created_at.desc(), AgentJob.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total)

    # --- Artefactos ---------------------------------------------------------

    async def save_artifact(
        self, job_id: str, data: dict, schema_version: str
    ) -> AgentArtifactRow:
        """Guarda (o reemplaza) el artefacto de un job."""
        existing = await self.session.scalar(
            select(AgentArtifactRow).where(AgentArtifactRow.job_id == job_id)
        )
        if existing is not None:
            existing.data = data
            existing.schema_version = schema_version
            await self.session.flush()
            return existing
        row = AgentArtifactRow(job_id=job_id, data=data, schema_version=schema_version)
        self.session.add(row)
        await self.session.flush()
        return row

    async def count_jobs_by_group(
        self, *, agent_type: Optional[AgentType] = None
    ) -> dict[str, int]:
        """Contadores por grupo de estado, en **una sola consulta** agregada.

        Cuenta sobre TODOS los jobs del agente (no sobre la página actual), que es
        lo que necesitan los tabs del historial para no mentir. Devuelve siempre
        las cinco claves, con 0 cuando no hay nada, para que el cliente no tenga
        que rellenar huecos.
        """
        stmt = select(AgentJob.status, func.count()).group_by(AgentJob.status)
        if agent_type is not None:
            stmt = stmt.where(AgentJob.agent_type == agent_type)

        counts: dict[str, int] = {g.value: 0 for g in JobStatusGroup}
        for status, cantidad in (await self.session.execute(stmt)).all():
            counts[group_of_status(status).value] += cantidad
            counts[JobStatusGroup.TODOS.value] += cantidad
        return counts

    async def get_artifact(self, job_id: str) -> Optional[AgentArtifactRow]:
        """Recupera el artefacto de un job."""
        return await self.session.scalar(
            select(AgentArtifactRow).where(AgentArtifactRow.job_id == job_id)
        )

    # --- Validaciones (ciclo de afinamiento) --------------------------------

    async def upsert_validation(
        self,
        job_id: str,
        target_type: ValidationTargetType,
        target_id: str,
        status: ValidationStatus,
        respuesta: Optional[str] = None,
        answered_by: Optional[str] = None,
    ) -> AgentValidation:
        """Registra/actualiza una validación (única por job+target).

        ``answered_by`` atribuye la respuesta a quien la registró.
        """
        existing = await self.session.scalar(
            select(AgentValidation).where(
                AgentValidation.job_id == job_id,
                AgentValidation.target_type == target_type,
                AgentValidation.target_id == target_id,
            )
        )
        if existing is not None:
            existing.status = status
            existing.respuesta = respuesta
            if answered_by is not None:
                existing.answered_by = answered_by
            await self.session.flush()
            return existing
        val = AgentValidation(
            job_id=job_id,
            target_type=target_type,
            target_id=target_id,
            status=status,
            respuesta=respuesta,
            answered_by=answered_by,
        )
        self.session.add(val)
        await self.session.flush()
        return val

    async def list_validations(self, job_id: str) -> list[AgentValidation]:
        """Todas las validaciones de un job."""
        rows = await self.session.scalars(
            select(AgentValidation)
            .where(AgentValidation.job_id == job_id)
            .order_by(AgentValidation.created_at.asc())
        )
        return list(rows)

    # --- Auditoría de publicaciones externas (ClickUp, fase b) --------------

    async def record_external_link(
        self,
        job_id: str,
        external_key: str,
        action: str,
        *,
        provider: str = "clickup",
        story_id: Optional[str] = None,
        external_id: Optional[str] = None,
        list_id: Optional[str] = None,
    ) -> AgentExternalLink:
        """Registra (idempotente por job+provider+external_key) una publicación."""
        existing = await self.session.scalar(
            select(AgentExternalLink).where(
                AgentExternalLink.job_id == job_id,
                AgentExternalLink.provider == provider,
                AgentExternalLink.external_key == external_key,
            )
        )
        if existing is not None:
            existing.action = action
            existing.story_id = story_id
            existing.external_id = external_id
            existing.list_id = list_id
            await self.session.flush()
            return existing
        link = AgentExternalLink(
            job_id=job_id,
            provider=provider,
            external_key=external_key,
            action=action,
            story_id=story_id,
            external_id=external_id,
            list_id=list_id,
        )
        self.session.add(link)
        await self.session.flush()
        return link

    async def list_external_links(self, job_id: str) -> list[AgentExternalLink]:
        """Todas las publicaciones externas registradas para un job."""
        rows = await self.session.scalars(
            select(AgentExternalLink)
            .where(AgentExternalLink.job_id == job_id)
            .order_by(AgentExternalLink.created_at.asc())
        )
        return list(rows)

    async def validation_summary(self, job_id: str) -> dict:
        """Resumen de validaciones: conteos por estado y por tipo."""
        validations = await self.list_validations(job_id)
        by_status: dict[str, int] = {}
        by_target: dict[str, int] = {}
        for v in validations:
            by_status[v.status.value] = by_status.get(v.status.value, 0) + 1
            by_target[v.target_type.value] = by_target.get(v.target_type.value, 0) + 1
        return {
            "total": len(validations),
            "by_status": by_status,
            "by_target_type": by_target,
            "validations": [
                {
                    "target_type": v.target_type.value,
                    "target_id": v.target_id,
                    "status": v.status.value,
                    "respuesta": v.respuesta,
                }
                for v in validations
            ],
        }
