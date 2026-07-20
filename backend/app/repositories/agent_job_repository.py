"""Repositorio genérico multi-agente (capa repositories).

Reemplaza al antiguo ``EFRepository`` por uno agnóstico del agente, discriminado
por ``agent_type`` (D1 del diseño). Recibe/devuelve ``dict`` para el artefacto y
las métricas, respetando el flujo api -> services -> repositories.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import (
    AgentArtifactRow,
    AgentJob,
    AgentType,
    AgentValidation,
    EFSourceDoc,
    EFSourceDocType,
    JobStatus,
    ValidationStatus,
    ValidationTargetType,
)

_COMPLETED = (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS)


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
    ) -> AgentJob:
        """Crea un job en estado PENDING para el agente indicado."""
        job = AgentJob(
            agent_type=agent_type,
            source_doc_id=source_doc_id,
            parent_job_id=parent_job_id,
            input_job_id=input_job_id,
            status=JobStatus.PENDING,
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
    ) -> tuple[list[AgentJob], int]:
        """Listado paginado de jobs (más recientes primero) + total.

        Si se pasa ``agent_type`` filtra por ese agente; si no, devuelve todos.
        """
        base = select(AgentJob)
        count_stmt = select(func.count()).select_from(AgentJob)
        if agent_type is not None:
            base = base.where(AgentJob.agent_type == agent_type)
            count_stmt = count_stmt.where(AgentJob.agent_type == agent_type)

        total = await self.session.scalar(count_stmt) or 0
        rows = await self.session.scalars(
            base.order_by(AgentJob.created_at.desc()).limit(limit).offset(offset)
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
    ) -> AgentValidation:
        """Registra/actualiza una validación (única por job+target)."""
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
            await self.session.flush()
            return existing
        val = AgentValidation(
            job_id=job_id,
            target_type=target_type,
            target_id=target_id,
            status=status,
            respuesta=respuesta,
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
