"""Servicio de planificación del Agente Scrum (capa services).

Verifica el gate de entrada (EF listo) **antes** de crear el job, ejecuta el grafo
Scrum en segundo plano (métricas reales), computa el semáforo compuesto (D5) y
gestiona el ciclo de afinamiento con el PO (validaciones + refine con job hijo).
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


async def run_scrum_pipeline(
    job_id: str,
    ef_job_id: str,
    ef_artifact: dict,
    ef_artifact_hash: str,
    ef_ready: bool,
    capacity_points: int,
    authoritative_context: Optional[str] = None,
) -> None:  # pragma: no cover - ruta runtime con Redis/Postgres reales
    """Ejecuta el grafo Scrum en segundo plano y persiste artefacto + métricas."""
    from ai.agents.base.pipeline import run_agent_pipeline
    from ai.agents.base.structured import ClaudeLLMClient
    from ai.orchestrator import build_scrum_graph

    state = {
        "job_id": job_id,
        "ef_job_id": ef_job_id,
        "ef_artifact": ef_artifact,
        "ef_artifact_hash": ef_artifact_hash,
        "ef_ready": ef_ready,
        "capacity_points": capacity_points,
        "coverage_threshold": settings.SCRUM_COVERAGE_THRESHOLD,
    }
    if authoritative_context:
        state["authoritative_context"] = authoritative_context

    await run_agent_pipeline(
        job_id=job_id,
        build_graph=build_scrum_graph,
        llm=ClaudeLLMClient(),
        initial_state=state,
        extra_config={"critique_llm": ClaudeLLMClient()},
    )


def artifact_hash(ef_artifact: dict) -> str:
    """Hash reproducible del contenido del EFArtifact consumido."""
    return compute_hash(
        json.dumps(ef_artifact, sort_keys=True, ensure_ascii=False).encode()
    )


class ScrumPlanningService:
    """Casos de uso del Agente Scrum."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AgentJobRepository(session)
        self.ef = EFAnalysisService(session)

    # --- Generación (con gate de entrada) -----------------------------------

    async def create_plan(
        self,
        ef_job_id: str,
        capacity_points: Optional[int] = None,
        *,
        background_tasks=None,
    ) -> AgentJob:
        """Crea un plan Scrum a partir de un job EF **listo**. Falla rápido si no."""
        ef_job = await self.repo.get_job(ef_job_id)
        if ef_job is None or ef_job.agent_type != AgentType.EF:
            raise IngestError(f"No existe un job EF con id {ef_job_id}.")

        ef_artifact = await self.ef.get_artifact(ef_job_id)
        if ef_artifact is None:
            raise GateError(f"El job EF {ef_job_id} aún no tiene artefacto disponible.")

        summary = await self.ef.validation_summary(ef_job_id)
        if not summary.get("ready_for_next_stage"):
            pending = summary.get("blocking_pending", [])
            raise GateError(
                f"El artefacto EF {ef_job_id} no está listo para planificación: "
                f"quedan {len(pending)} preguntas bloqueantes sin responder. "
                "Complétalas o genera una versión afinada "
                f"(POST /ef/jobs/{ef_job_id}/refine)."
            )

        capacity = capacity_points or settings.SCRUM_SPRINT_CAPACITY
        # El título/fuente del plan Scrum se heredan del EF de origen (historial).
        job = await self.repo.create_job(
            AgentType.SCRUM,
            input_job_id=ef_job_id,
            title=ef_job.title,
            source_type=ef_job.source_type,
        )
        await self.session.commit()

        if background_tasks is not None:
            background_tasks.add_task(
                run_scrum_pipeline,
                job.id,
                ef_job_id,
                ef_artifact,
                artifact_hash(ef_artifact),
                True,
                capacity,
            )
        return job

    async def get_job(self, job_id: str) -> Optional[AgentJob]:
        return await self.repo.get_job(job_id)

    async def get_artifact(self, job_id: str) -> Optional[dict]:
        row = await self.repo.get_artifact(job_id)
        return row.data if row is not None else None

    async def list_jobs(self, limit: int, offset: int) -> tuple[list[AgentJob], int]:
        return await self.repo.list_jobs(
            agent_type=AgentType.SCRUM, limit=limit, offset=offset
        )

    # --- Export ClickUp (fase a: sin API, sin riesgo) -----------------------

    async def export_clickup(self, job_id: str, fmt: str = "csv") -> dict:
        """Genera el export compatible con ClickUp (CSV o JSON) del artefacto."""
        from ai.integrations.clickup import to_clickup_csv, to_clickup_rows

        artifact = await self.get_artifact(job_id)
        if artifact is None:
            raise IngestError(f"El job Scrum {job_id} no tiene artefacto disponible.")

        if fmt == "json":
            return {
                "format": "json",
                "filename": f"scrum_{job_id}_clickup.json",
                "content": to_clickup_rows(artifact),
            }
        return {
            "format": "csv",
            "filename": f"scrum_{job_id}_clickup.csv",
            "content": to_clickup_csv(artifact),
        }

    async def list_ready_ef_jobs(self, limit: int, offset: int) -> list[dict]:
        """Lista jobs EF completados marcando si están listos para planificación."""
        jobs, _ = await self.repo.list_jobs(
            agent_type=AgentType.EF, limit=limit, offset=offset
        )
        out: list[dict] = []
        for job in jobs:
            summary = await self.ef.validation_summary(job.id)
            out.append(
                {
                    "job_id": job.id,
                    "status": job.status.value,
                    "ready_for_next_stage": summary.get("ready_for_next_stage", False),
                    "blocking_pending": summary.get("blocking_pending", []),
                }
            )
        return out

    # --- Validaciones del PO + semáforo compuesto (D5) ----------------------

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
        """Resumen + ``ready_for_next_stage`` compuesto del Scrum (D5)."""
        summary = await self.repo.validation_summary(job_id)
        artifact = await self.get_artifact(job_id)

        blocking_ids: list[str] = []
        if artifact:
            blocking_ids = [
                q["id"]
                for q in artifact.get("questions_for_po", [])
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
        """Condiciones del semáforo compuesto (D5). Sin artefacto: todo falso."""
        if not artifact:
            return {
                "no_blocking_questions": len(pending) == 0,
                "must_should_estimated": False,
                "coverage_met": False,
                "no_must_unassigned": False,
            }
        stories = artifact.get("stories", [])
        unassigned = set(artifact.get("unassigned_story_ids", []))
        must_should_estimated = all(
            s.get("story_points") is not None
            for s in stories
            if s.get("priority") in ("must", "should")
        )
        coverage = (artifact.get("analysis", {}).get("coverage") or {}).get(
            "coverage_ratio", 0.0
        )
        no_must_unassigned = not any(
            s.get("id") in unassigned and s.get("priority") == "must" for s in stories
        )
        return {
            "no_blocking_questions": len(pending) == 0,
            "must_should_estimated": must_should_estimated,
            "coverage_met": coverage >= settings.SCRUM_COVERAGE_THRESHOLD,
            "no_must_unassigned": no_must_unassigned,
        }

    # --- Refine (PO) --------------------------------------------------------

    async def create_refine(
        self, parent_job_id: str, *, background_tasks=None
    ) -> AgentJob:
        """Crea un job hijo Scrum reinyectando las respuestas del PO como contexto."""
        parent = await self.repo.get_job(parent_job_id)
        if parent is None or parent.agent_type != AgentType.SCRUM:
            raise IngestError(f"No existe un job Scrum con id {parent_job_id}.")

        summary = await self.repo.validation_summary(parent_job_id)
        authoritative_context = build_authoritative_context(summary)
        if authoritative_context is None:
            raise IngestError(
                "No hay validaciones respondidas para reinyectar en el refine."
            )

        ef_job_id = parent.input_job_id
        ef_artifact = await self.ef.get_artifact(ef_job_id) if ef_job_id else None
        if ef_artifact is None:
            raise GateError("No se pudo recuperar el EFArtifact de origen del refine.")

        child = await self.repo.create_job(
            AgentType.SCRUM,
            parent_job_id=parent_job_id,
            input_job_id=ef_job_id,
            title=parent.title,
            source_type=parent.source_type,
            version=parent.version + 1,
        )
        await self.session.commit()

        if background_tasks is not None:
            background_tasks.add_task(
                run_scrum_pipeline,
                child.id,
                ef_job_id,
                ef_artifact,
                artifact_hash(ef_artifact),
                True,
                settings.SCRUM_SPRINT_CAPACITY,
                authoritative_context,
            )
        return child
