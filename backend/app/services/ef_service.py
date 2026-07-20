"""Servicio de análisis del Agente EF (capa services).

Orquesta ingesta idempotente, ejecución del grafo (BackgroundTasks capturando
métricas reales) y el ciclo de afinamiento (validaciones + refine con job hijo).
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai.agents.base.refine import build_authoritative_context
from ai.errors import IngestError
from ai.tools.ingest import LocalStorage, compute_hash, ingest
from app.config.settings import settings
from app.models.ef import (
    EFJob,
    EFSourceDoc,
    EFSourceDocType,
    ValidationStatus,
    ValidationTargetType,
)
from app.repositories.ef_repository import EFRepository

_MIN_TEXT = 100


def _derive_title(filename: Optional[str], source_type: str) -> Optional[str]:
    """Título legible para el historial.

    Para texto libre el filename es ``<título>.txt`` (ver la ruta ``/analyze``);
    se recupera el título quitando el sufijo. Para documentos se usa el filename tal
    cual (con su extensión).
    """
    if not filename:
        return None
    if source_type == "text" and filename.endswith(".txt"):
        return filename[: -len(".txt")] or filename
    return filename


async def run_ef_pipeline(
    job_id: str, source: dict, authoritative_context: Optional[str] = None
) -> None:  # pragma: no cover - ruta runtime con Redis/Postgres reales
    """Ejecuta el grafo EF en segundo plano y persiste artefacto + métricas reales.

    Delega en el runner genérico compartido (``run_agent_pipeline``). En tests se
    reemplaza por un mock (REGLA DE PRESUPUESTO: nunca API real sin autorización).
    """
    from ai.agents.base.pipeline import run_agent_pipeline
    from ai.agents.base.structured import ClaudeLLMClient
    from ai.orchestrator import build_ef_graph

    state = {
        "job_id": job_id,
        "filename": source.get("filename") or "fuente",
        "source": source,
    }
    if authoritative_context:
        state["authoritative_context"] = authoritative_context

    await run_agent_pipeline(
        job_id=job_id,
        build_graph=build_ef_graph,
        llm=ClaudeLLMClient(),
        initial_state=state,
    )


class EFAnalysisService:
    """Casos de uso del Agente EF."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = EFRepository(session)

    def _storage(self) -> LocalStorage:
        return LocalStorage(settings.STORAGE_DIR)

    async def create_analysis(
        self,
        filename: str,
        content: bytes,
        *,
        background_tasks=None,
    ) -> tuple[EFJob, bool]:
        """Crea (o reutiliza por hash) un análisis. Devuelve (job, cached)."""
        content_hash = compute_hash(content)

        # Idempotencia: si ya hay un job completado para este hash, se reutiliza.
        cached_job = await self.repo.find_completed_job_by_hash(content_hash)
        if cached_job is not None:
            return cached_job, True

        # Valida MIME/tamaño y almacena (lanza AgentError -> 4xx en el middleware).
        result = ingest(
            filename=filename,
            content=content,
            storage=self._storage(),
            max_upload_mb=settings.MAX_UPLOAD_MB,
        )

        doc = await self.repo.get_or_create_source_doc(
            content_hash=content_hash,
            doc_type=EFSourceDocType(result.source_type),
            filename=result.filename,
            doc_metadata=result.model_dump(),
        )
        job = await self.repo.create_job(
            source_doc_id=doc.id,
            title=_derive_title(result.filename, result.source_type),
            source_type=result.source_type,
        )
        await self.session.commit()

        if background_tasks is not None:
            background_tasks.add_task(run_ef_pipeline, job.id, result.model_dump())
        return job, False

    async def get_job(self, job_id: str) -> Optional[EFJob]:
        return await self.repo.get_job(job_id)

    async def get_artifact(self, job_id: str) -> Optional[dict]:
        row = await self.repo.get_artifact(job_id)
        return row.data if row is not None else None

    async def list_jobs(self, limit: int, offset: int) -> tuple[list[EFJob], int]:
        return await self.repo.list_jobs(limit=limit, offset=offset)

    async def register_validation(
        self,
        job_id: str,
        target_type: str,
        target_id: str,
        status: str,
        respuesta: Optional[str] = None,
    ):
        val = await self.repo.upsert_validation(
            job_id=job_id,
            target_type=ValidationTargetType(target_type),
            target_id=target_id,
            status=ValidationStatus(status),
            respuesta=respuesta,
        )
        await self.session.commit()
        return val

    async def validation_summary(self, job_id: str) -> dict:
        """Resumen + ready_for_next_stage (sin blocking pendientes)."""
        summary = await self.repo.validation_summary(job_id)

        artifact = await self.get_artifact(job_id)
        blocking_ids = []
        if artifact:
            blocking_ids = [
                q["id"]
                for q in artifact.get("questions_for_analyst", [])
                if q.get("blocking")
            ]
        resolved = {
            v["target_id"]
            for v in summary["validations"]
            if v["status"] in ("confirmado", "corregido")
        }
        pending = [qid for qid in blocking_ids if qid not in resolved]
        summary["blocking_total"] = len(blocking_ids)
        summary["blocking_pending"] = pending
        summary["ready_for_next_stage"] = len(pending) == 0
        return summary

    async def create_refine(
        self, parent_job_id: str, *, background_tasks=None
    ) -> EFJob:
        """Crea un job hijo reinyectando las respuestas como contexto autoritativo."""
        parent = await self.repo.get_job(parent_job_id)
        if parent is None:
            raise IngestError(f"Job padre no encontrado: {parent_job_id}")

        summary = await self.repo.validation_summary(parent_job_id)
        authoritative_context = build_authoritative_context(summary)
        if authoritative_context is None:
            raise IngestError(
                "No hay validaciones respondidas para reinyectar en el refine."
            )

        child = await self.repo.create_job(
            source_doc_id=parent.source_doc_id,
            parent_job_id=parent_job_id,
            title=parent.title,
            source_type=parent.source_type,
            version=parent.version + 1,
        )
        await self.session.commit()

        # Reconstruye el 'source' desde los metadatos del documento.
        doc = await self.session.get(EFSourceDoc, parent.source_doc_id)
        source = dict(doc.doc_metadata or {}) if doc else {}
        if background_tasks is not None:
            background_tasks.add_task(
                run_ef_pipeline, child.id, source, authoritative_context
            )
        return child
