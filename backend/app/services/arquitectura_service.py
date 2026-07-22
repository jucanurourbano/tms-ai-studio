"""Servicio de diseño del Agente Arquitectura (capa services).

Verifica el gate de entrada (**plan Scrum listo**) antes de crear el job, ejecuta
el grafo de Arquitectura en segundo plano (métricas reales), computa el semáforo
compuesto (sin bloqueantes + contenido mínimo) y gestiona el ciclo de afinamiento
con el Arquitecto (validaciones + refine con job hijo).

Entrada doble transitiva: el job se enlaza a Scrum por ``input_job_id`` y el EF se
resuelve por ``scrum_job.input_job_id`` (sin columna nueva).
"""

import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai.agents.base.refine import build_authoritative_context
from ai.errors import GateError, IngestError
from ai.tools.ingest import compute_hash
from app.config.settings import settings
from app.models.agent import (
    AgentJob,
    AgentType,
    ValidationStatus,
    ValidationTargetType,
)
from app.repositories.agent_job_repository import AgentJobRepository
from app.services.ef_service import EFAnalysisService
from app.services.scrum_service import ScrumPlanningService


async def run_arquitectura_pipeline(
    job_id: str,
    scrum_job_id: str,
    scrum_artifact: dict,
    scrum_artifact_hash: str,
    ef_job_id: str,
    ef_artifact: dict,
    ef_artifact_hash: str,
    scrum_ready: bool,
    authoritative_context: Optional[str] = None,
) -> None:  # pragma: no cover - ruta runtime con Redis/Postgres reales
    """Ejecuta el grafo de Arquitectura en segundo plano y persiste resultados."""
    from ai.agents.base.pipeline import run_agent_pipeline
    from ai.agents.base.structured import ClaudeLLMClient
    from ai.orchestrator import build_arquitectura_graph

    state = {
        "job_id": job_id,
        "scrum_job_id": scrum_job_id,
        "scrum_artifact": scrum_artifact,
        "scrum_artifact_hash": scrum_artifact_hash,
        "scrum_ready": scrum_ready,
        "ef_job_id": ef_job_id,
        "ef_artifact": ef_artifact,
        "ef_artifact_hash": ef_artifact_hash,
    }
    if authoritative_context:
        state["authoritative_context"] = authoritative_context

    await run_agent_pipeline(
        job_id=job_id,
        build_graph=build_arquitectura_graph,
        llm=ClaudeLLMClient(),
        initial_state=state,
    )


def artifact_hash(artifact: dict) -> str:
    """Hash reproducible del contenido de un artefacto consumido."""
    return compute_hash(
        json.dumps(artifact, sort_keys=True, ensure_ascii=False).encode()
    )


class ArquitecturaService:
    """Casos de uso del Agente Arquitectura."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AgentJobRepository(session)
        self.ef = EFAnalysisService(session)
        self.scrum = ScrumPlanningService(session)

    # --- Generación (con gate de entrada) -----------------------------------

    async def create_design(
        self, scrum_job_id: str, *, background_tasks=None
    ) -> AgentJob:
        """Crea un diseño desde un plan Scrum **listo**. Falla rápido si no lo está."""
        scrum_job = await self.repo.get_job(scrum_job_id)
        if scrum_job is None or scrum_job.agent_type != AgentType.SCRUM:
            raise IngestError(f"No existe un job Scrum con id {scrum_job_id}.")

        scrum_artifact = await self.scrum.get_artifact(scrum_job_id)
        if scrum_artifact is None:
            raise GateError(
                f"El job Scrum {scrum_job_id} aún no tiene artefacto disponible."
            )

        summary = await self.scrum.validation_summary(scrum_job_id)
        if not summary.get("ready_for_next_stage"):
            pending = summary.get("blocking_pending", [])
            raise GateError(
                f"El plan Scrum {scrum_job_id} no está listo para diseño de "
                f"arquitectura: quedan {len(pending)} preguntas bloqueantes al PO "
                "sin responder o falta cobertura. Complétalas o genera un plan "
                f"afinado (POST /scrum/jobs/{scrum_job_id}/refine)."
            )

        ef_job_id = scrum_job.input_job_id
        ef_artifact = await self.ef.get_artifact(ef_job_id) if ef_job_id else None
        if ef_artifact is None:
            raise GateError(
                "No se pudo recuperar el EFArtifact de origen (transitivo) del plan "
                f"Scrum {scrum_job_id}."
            )

        job = await self.repo.create_job(
            AgentType.ARQUITECTURA,
            input_job_id=scrum_job_id,
            title=scrum_job.title,
            source_type=scrum_job.source_type,
        )
        await self.session.commit()

        if background_tasks is not None:
            background_tasks.add_task(
                run_arquitectura_pipeline,
                job.id,
                scrum_job_id,
                scrum_artifact,
                artifact_hash(scrum_artifact),
                ef_job_id,
                ef_artifact,
                artifact_hash(ef_artifact),
                True,
            )
        return job

    async def get_job(self, job_id: str) -> Optional[AgentJob]:
        return await self.repo.get_job(job_id)

    async def get_artifact(self, job_id: str) -> Optional[dict]:
        row = await self.repo.get_artifact(job_id)
        return row.data if row is not None else None

    async def list_jobs(self, limit: int, offset: int) -> tuple[list[AgentJob], int]:
        return await self.repo.list_jobs(
            agent_type=AgentType.ARQUITECTURA, limit=limit, offset=offset
        )

    async def list_ready_scrum_jobs(self, limit: int, offset: int) -> list[dict]:
        """Lista jobs Scrum marcando si están listos para diseño de arquitectura."""
        jobs, _ = await self.repo.list_jobs(
            agent_type=AgentType.SCRUM, limit=limit, offset=offset
        )
        out: list[dict] = []
        for job in jobs:
            summary = await self.scrum.validation_summary(job.id)
            out.append(
                {
                    "job_id": job.id,
                    "status": job.status.value,
                    "ready_for_next_stage": summary.get("ready_for_next_stage", False),
                    "blocking_pending": summary.get("blocking_pending", []),
                }
            )
        return out

    # --- Validaciones del Arquitecto + semáforo compuesto -------------------

    async def register_validation(
        self,
        job_id: str,
        target_id: str,
        status: str,
        respuesta: Optional[str] = None,
        target_type: str = "question",
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
        """Resumen + ``ready_for_next_stage`` (sin bloqueantes + contenido mínimo)."""
        summary = await self.repo.validation_summary(job_id)
        artifact = await self.get_artifact(job_id)

        blocking_ids: list[str] = []
        if artifact:
            blocking_ids = [
                q["id"]
                for q in artifact.get("questions_for_architect", [])
                if q.get("blocking")
            ]
        resolved = {
            v["target_id"]
            for v in summary["validations"]
            if v["status"] in ("confirmado", "corregido")
        }
        pending = [qid for qid in blocking_ids if qid not in resolved]

        checks = self._compound_checks(artifact, pending)
        summary["blocking_total"] = len(blocking_ids)
        summary["blocking_pending"] = pending
        summary["checks"] = checks
        summary["ready_for_next_stage"] = all(checks.values())
        return summary

    @staticmethod
    def _compound_checks(artifact: Optional[dict], pending: list[str]) -> dict:
        """Contenido mínimo: estilo decidido + ≥1 componente + cobertura épicas/
        entidades. Los RNF/integraciones sin contrato ya entran como bloqueantes."""
        if not artifact:
            return {
                "no_blocking_questions": len(pending) == 0,
                "style_decided": False,
                "has_components": False,
                "coverage_met": False,
            }
        coverage = artifact.get("analysis", {}).get("coverage", {}) or {}
        threshold = settings.ARCH_COVERAGE_THRESHOLD

        def ratio(mapped_key: str, total_key: str) -> float:
            total = coverage.get(total_key, 0)
            return 1.0 if not total else coverage.get(mapped_key, 0) / total

        coverage_met = (
            ratio("epics_mapped", "epics_total") >= threshold
            and ratio("entities_mapped", "entities_total") >= threshold
        )
        return {
            "no_blocking_questions": len(pending) == 0,
            "style_decided": bool(artifact.get("architecture_style")),
            "has_components": len(artifact.get("components", [])) >= 1,
            "coverage_met": coverage_met,
        }

    # --- Refine (Arquitecto) ------------------------------------------------

    async def create_refine(
        self, parent_job_id: str, *, background_tasks=None
    ) -> AgentJob:
        """Crea un job hijo reinyectando las respuestas del Arquitecto como contexto."""
        parent = await self.repo.get_job(parent_job_id)
        if parent is None or parent.agent_type != AgentType.ARQUITECTURA:
            raise IngestError(f"No existe un job Arquitectura con id {parent_job_id}.")

        summary = await self.repo.validation_summary(parent_job_id)
        authoritative_context = build_authoritative_context(summary)
        if authoritative_context is None:
            raise IngestError(
                "No hay validaciones respondidas para reinyectar en el refine."
            )

        scrum_job_id = parent.input_job_id
        scrum_artifact = (
            await self.scrum.get_artifact(scrum_job_id) if scrum_job_id else None
        )
        scrum_job = await self.repo.get_job(scrum_job_id) if scrum_job_id else None
        if scrum_artifact is None or scrum_job is None:
            raise GateError("No se pudo recuperar el plan Scrum de origen del refine.")

        ef_job_id = scrum_job.input_job_id
        ef_artifact = await self.ef.get_artifact(ef_job_id) if ef_job_id else None
        if ef_artifact is None:
            raise GateError("No se pudo recuperar el EFArtifact de origen del refine.")

        child = await self.repo.create_job(
            AgentType.ARQUITECTURA,
            parent_job_id=parent_job_id,
            input_job_id=scrum_job_id,
            title=parent.title,
            source_type=parent.source_type,
            version=parent.version + 1,
        )
        await self.session.commit()

        if background_tasks is not None:
            background_tasks.add_task(
                run_arquitectura_pipeline,
                child.id,
                scrum_job_id,
                scrum_artifact,
                artifact_hash(scrum_artifact),
                ef_job_id,
                ef_artifact,
                artifact_hash(ef_artifact),
                True,
                authoritative_context,
            )
        return child
