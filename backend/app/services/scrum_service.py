"""Servicio de planificación del Agente Scrum (capa services).

Verifica el gate de entrada (EF listo) **antes** de crear el job, ejecuta el grafo
Scrum en segundo plano (métricas reales), computa el semáforo compuesto (D5) y
gestiona el ciclo de afinamiento con el PO (validaciones + refine con job hijo).
"""

import json
from datetime import datetime, timezone
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
from app.models.user import User
from app.repositories.agent_job_repository import AgentJobRepository
from app.repositories.story_assignment_repository import StoryAssignmentRepository
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
        actor_id: Optional[str] = None,
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
            created_by=actor_id,
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

    # --- Equipo y asignación de historias -----------------------------------

    def _assignments(self) -> StoryAssignmentRepository:
        return StoryAssignmentRepository(self.session)

    @staticmethod
    def _member_out(user: User) -> dict:
        """Vista pública mínima de un colaborador (nunca expone credenciales)."""
        return {
            "id": user.id,
            "full_name": user.full_name,
            # El correo institucional es el que se exporta a ClickUp; si no está
            # informado se cae al de acceso para no dejar la tarea sin destinatario.
            "institutional_email": user.institutional_email or user.email,
            "specialty": user.specialty.value if user.specialty else None,
            "role": user.role.value,
            "is_active": user.is_active,
        }

    async def list_team(self) -> list[dict]:
        """Colaboradores asignables (activos, vigentes y disponibles)."""
        users = await self._assignments().assignable_users()
        return [self._member_out(u) for u in users]

    @staticmethod
    def _sprint_of_story(artifact: dict) -> dict[str, str]:
        """``story_id`` -> ``sprint_id`` según el artefacto."""
        mapa: dict[str, str] = {}
        for sprint in artifact.get("sprints", []):
            for sid in sprint.get("story_ids", []):
                mapa[sid] = sprint.get("id")
        return mapa

    async def list_assignments(self, job_id: str) -> dict:
        """Asignaciones EFECTIVAS del plan, con la cascada del sprint resuelta.

        Regla: **la asignación por historia prevalece sobre la del sprint**. La
        cascada no se materializa en ``story_assignments`` (ver
        ``SprintAssignment``), se resuelve aquí al leer, y cada historia informa
        de dónde viene su responsable con ``source``:
          - ``story``  → asignada explícitamente.
          - ``sprint`` → heredada del responsable del sprint.

        Devuelve ``{"items": [...historias...], "sprints": [...]}``.
        """
        repo = self._assignments()
        story_rows = await repo.list_for_job(job_id)
        sprint_rows = await repo.list_sprints_for_job(job_id)

        users = await repo.users_by_ids(
            [r.user_id for r in story_rows] + [r.user_id for r in sprint_rows]
        )

        items: list[dict] = []
        explicitas: set[str] = set()
        for row in story_rows:
            user = users.get(row.user_id)
            explicitas.add(row.story_id)
            items.append(
                {
                    "story_id": row.story_id,
                    "user_id": row.user_id,
                    "source": "story",
                    "assigned_at": (
                        row.assigned_at.isoformat() if row.assigned_at else None
                    ),
                    "assigned_by": row.assigned_by,
                    # ``user`` solo faltaría con un borrado físico (la app usa baja
                    # lógica), pero el listado no debe romperse por eso.
                    "user": self._member_out(user) if user is not None else None,
                }
            )

        sprints: list[dict] = []
        if sprint_rows:
            artifact = await self.get_artifact(job_id) or {}
            por_sprint: dict[str, list[str]] = {}
            for sprint in artifact.get("sprints", []):
                por_sprint[sprint.get("id")] = list(sprint.get("story_ids", []))

            for row in sprint_rows:
                user = users.get(row.user_id)
                miembro = self._member_out(user) if user is not None else None
                sprints.append(
                    {
                        "sprint_id": row.sprint_id,
                        "user_id": row.user_id,
                        "assigned_at": (
                            row.assigned_at.isoformat() if row.assigned_at else None
                        ),
                        "assigned_by": row.assigned_by,
                        "user": miembro,
                    }
                )
                # Cascada: las historias del sprint SIN asignación propia.
                for sid in por_sprint.get(row.sprint_id, []):
                    if sid in explicitas:
                        continue
                    items.append(
                        {
                            "story_id": sid,
                            "user_id": row.user_id,
                            "source": "sprint",
                            "assigned_at": (
                                row.assigned_at.isoformat() if row.assigned_at else None
                            ),
                            "assigned_by": row.assigned_by,
                            "user": miembro,
                        }
                    )

        items.sort(key=lambda x: x["story_id"])
        return {"items": items, "sprints": sprints}

    async def assign_sprint(
        self,
        *,
        job_id: str,
        sprint_id: str,
        user_id: Optional[str],
        actor_id: Optional[str] = None,
    ) -> dict:
        """Asigna o desasigna un **sprint completo** (``user_id=None`` desasigna).

        Sus historias sin responsable propio pasan a mostrarse a nombre de esa
        persona (cascada derivada); las que ya tienen asignación individual la
        conservan.
        """
        artifact = await self._require_artifact(job_id)
        conocidos = {s.get("id") for s in artifact.get("sprints", [])}
        if sprint_id not in conocidos:
            raise IngestError(f"El sprint {sprint_id} no pertenece al plan {job_id}.")

        repo = self._assignments()
        if user_id is None:
            await repo.unassign_sprint(job_id=job_id, sprint_id=sprint_id)
            await self.session.commit()
            return {"sprint_id": sprint_id, "user_id": None}

        await self._require_assignable(user_id)
        await repo.assign_sprint(
            job_id=job_id,
            sprint_id=sprint_id,
            user_id=user_id,
            assigned_by=actor_id,
            when=datetime.now(timezone.utc),
        )
        await self.session.commit()
        return {"sprint_id": sprint_id, "user_id": user_id}

    async def _require_artifact(self, job_id: str) -> dict:
        """Valida que el job sea un plan Scrum con artefacto y lo devuelve."""
        job = await self.repo.get_job(job_id)
        if job is None or job.agent_type != AgentType.SCRUM:
            raise IngestError(f"No existe un job Scrum con id {job_id}.")
        artifact = await self.get_artifact(job_id)
        if artifact is None:
            raise IngestError(f"El job Scrum {job_id} no tiene artefacto disponible.")
        return artifact

    async def _require_assignable(self, user_id: str) -> None:
        """Valida que el destinatario pueda recibir trabajo."""
        assignable = {u.id for u in await self._assignments().assignable_users()}
        if user_id not in assignable:
            raise IngestError(
                "El usuario indicado no está disponible para asignación "
                "(inactivo, dado de baja o marcado como no asignable)."
            )

    async def assign_story(
        self,
        *,
        job_id: str,
        story_id: str,
        user_id: Optional[str],
        actor_id: Optional[str] = None,
    ) -> dict:
        """Asigna o desasigna una historia (``user_id=None`` desasigna).

        Valida que el plan exista, que la historia pertenezca a su artefacto y
        que el destinatario sea asignable: sin esto se podrían crear asignaciones
        a historias inventadas que nunca aparecerían en la UI.
        """
        artifact = await self._require_artifact(job_id)
        known = {s.get("id") for s in artifact.get("stories", [])}
        if story_id not in known:
            raise IngestError(f"La historia {story_id} no pertenece al plan {job_id}.")

        repo = self._assignments()
        if user_id is None:
            await repo.unassign(job_id=job_id, story_id=story_id)
            await self.session.commit()
            return {"story_id": story_id, "user_id": None}

        await self._require_assignable(user_id)
        await repo.assign(
            job_id=job_id,
            story_id=story_id,
            user_id=user_id,
            assigned_by=actor_id,
            when=datetime.now(timezone.utc),
        )
        await self.session.commit()
        return {"story_id": story_id, "user_id": user_id}

    async def _assignee_emails(self, job_id: str) -> dict[str, str]:
        """``story_id`` -> correo institucional del responsable EFECTIVO.

        Usa las asignaciones ya resueltas (``list_assignments``), así que una
        historia que hereda el responsable de su sprint también sale asignada en
        el export: es lo que el equipo ve en pantalla.
        """
        resueltas = await self.list_assignments(job_id)
        emails: dict[str, str] = {}
        for item in resueltas["items"]:
            user = item.get("user")
            if user:
                emails[item["story_id"]] = user["institutional_email"]
        return emails

    # --- Export ClickUp (fase a: sin API, sin riesgo) -----------------------

    async def export_clickup(self, job_id: str, fmt: str = "csv") -> dict:
        """Genera el export compatible con ClickUp (CSV o JSON) del artefacto."""
        from ai.integrations.clickup import to_clickup_csv, to_clickup_rows

        artifact = await self.get_artifact(job_id)
        if artifact is None:
            raise IngestError(f"El job Scrum {job_id} no tiene artefacto disponible.")

        # Las asignaciones NO están en el artefacto: se resuelven aparte y se
        # inyectan en el mapeo como `assignee_email` (lo que ClickUp espera para
        # asignar la tarea al importar).
        assignees = await self._assignee_emails(job_id)

        if fmt == "json":
            return {
                "format": "json",
                "filename": f"scrum_{job_id}_clickup.json",
                "content": to_clickup_rows(artifact, assignees=assignees),
            }
        return {
            "format": "csv",
            "filename": f"scrum_{job_id}_clickup.csv",
            "content": to_clickup_csv(artifact, assignees=assignees),
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
        actor_id: Optional[str] = None,
    ):
        val = await self.repo.upsert_validation(
            job_id=job_id,
            target_type=ValidationTargetType(target_type),
            target_id=target_id,
            status=ValidationStatus(status),
            respuesta=respuesta,
            answered_by=actor_id,
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
        self,
        parent_job_id: str,
        *,
        background_tasks=None,
        actor_id: Optional[str] = None,
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
            created_by=actor_id,
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
