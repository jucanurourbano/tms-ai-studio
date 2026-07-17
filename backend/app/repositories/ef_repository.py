"""Repositorio del Agente EF (acceso a datos, capa repositories).

Independiente de los esquemas Pydantic de ``ai``: recibe/devuelve ``dict`` para
el artefacto y las métricas, respetando el flujo api -> services -> repositories.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ef import (
    EFArtifactRow,
    EFJob,
    EFSourceDoc,
    EFSourceDocType,
    EFValidation,
    JobStatus,
    ValidationStatus,
    ValidationTargetType,
)


class EFRepository:
    """Operaciones de persistencia del Agente EF."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Fuentes ------------------------------------------------------------

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
        self, source_doc_id: str, parent_job_id: Optional[str] = None
    ) -> EFJob:
        """Crea un job en estado PENDING."""
        job = EFJob(
            source_doc_id=source_doc_id,
            parent_job_id=parent_job_id,
            status=JobStatus.PENDING,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_job(self, job_id: str) -> Optional[EFJob]:
        """Recupera un job por id."""
        return await self.session.get(EFJob, job_id)

    async def find_completed_job_by_hash(self, content_hash: str) -> Optional[EFJob]:
        """Último job COMPLETED/COMPLETED_WITH_WARNINGS para ese hash (idempotencia)."""
        stmt = (
            select(EFJob)
            .join(EFSourceDoc, EFJob.source_doc_id == EFSourceDoc.id)
            .where(
                EFSourceDoc.content_hash == content_hash,
                EFJob.status.in_(
                    [JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS]
                ),
                EFJob.parent_job_id.is_(None),
            )
            .order_by(EFJob.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def update_job_status(
        self, job_id: str, status: JobStatus, error: Optional[str] = None
    ) -> EFJob:
        """Actualiza el estado (y opcionalmente el error) de un job."""
        job = await self.session.get(EFJob, job_id)
        if job is None:
            raise ValueError(f"Job no encontrado: {job_id}")
        job.status = status
        if error is not None:
            job.error = error
        await self.session.flush()
        return job

    async def update_job_metrics(self, job_id: str, metrics: dict) -> EFJob:
        """Persiste las métricas reales de la corrida."""
        job = await self.session.get(EFJob, job_id)
        if job is None:
            raise ValueError(f"Job no encontrado: {job_id}")
        job.metrics = metrics
        await self.session.flush()
        return job

    async def list_jobs(
        self, limit: int = 20, offset: int = 0
    ) -> tuple[list[EFJob], int]:
        """Listado paginado de jobs (más recientes primero) + total."""
        total = await self.session.scalar(select(func.count()).select_from(EFJob)) or 0
        rows = await self.session.scalars(
            select(EFJob).order_by(EFJob.created_at.desc()).limit(limit).offset(offset)
        )
        return list(rows), int(total)

    # --- Artefactos ---------------------------------------------------------

    async def save_artifact(
        self, job_id: str, data: dict, schema_version: str
    ) -> EFArtifactRow:
        """Guarda (o reemplaza) el EFArtifact de un job."""
        existing = await self.session.scalar(
            select(EFArtifactRow).where(EFArtifactRow.job_id == job_id)
        )
        if existing is not None:
            existing.data = data
            existing.schema_version = schema_version
            await self.session.flush()
            return existing
        row = EFArtifactRow(job_id=job_id, data=data, schema_version=schema_version)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_artifact(self, job_id: str) -> Optional[EFArtifactRow]:
        """Recupera el artefacto de un job."""
        return await self.session.scalar(
            select(EFArtifactRow).where(EFArtifactRow.job_id == job_id)
        )

    # --- Validaciones (ciclo de afinamiento) --------------------------------

    async def upsert_validation(
        self,
        job_id: str,
        target_type: ValidationTargetType,
        target_id: str,
        status: ValidationStatus,
        respuesta: Optional[str] = None,
    ) -> EFValidation:
        """Registra/actualiza una validación (única por job+target)."""
        existing = await self.session.scalar(
            select(EFValidation).where(
                EFValidation.job_id == job_id,
                EFValidation.target_type == target_type,
                EFValidation.target_id == target_id,
            )
        )
        if existing is not None:
            existing.status = status
            existing.respuesta = respuesta
            await self.session.flush()
            return existing
        val = EFValidation(
            job_id=job_id,
            target_type=target_type,
            target_id=target_id,
            status=status,
            respuesta=respuesta,
        )
        self.session.add(val)
        await self.session.flush()
        return val

    async def list_validations(self, job_id: str) -> list[EFValidation]:
        """Todas las validaciones de un job."""
        rows = await self.session.scalars(
            select(EFValidation)
            .where(EFValidation.job_id == job_id)
            .order_by(EFValidation.created_at.asc())
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
