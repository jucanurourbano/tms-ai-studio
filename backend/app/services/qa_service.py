"""Servicio del Agente QA (capa services).

Verifica el gate de entrada (**plan Scrum listo**) antes de crear el job, ejecuta el
grafo en segundo plano, computa el semáforo y gestiona el ciclo de afinamiento con el
QA lead.

Entrada: el job se enlaza al Scrum por ``input_job_id`` y el EF se resuelve subiendo
la cadena con ``resolve_lineage``. El **contrato de API es una excepción
estructural** (QA-D1): no está en la cadena hacia atrás sino hacia delante, así que
no se descubre — se indica en la petición, y se **valida que pertenezca a esta misma
cadena** antes de usarlo. Sin esa comprobación, un plan de pruebas podría diseñar sus
casos de autorización contra el contrato de otro proyecto, y el resultado tendría
todo el aspecto de estar bien.
"""

import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai.agents.base.lineage import resolve_lineage
from ai.agents.base.refine import build_authoritative_context
from ai.errors import GateError, IngestError
from ai.tools.ingest import compute_hash
from app.config.settings import settings
from app.models.agent import (
    USABLE_JOB_STATUSES,
    AgentJob,
    AgentType,
    JobStatusGroup,
    ValidationStatus,
    ValidationTargetType,
)
from app.repositories.agent_job_repository import AgentJobRepository
from app.services.api_service import ApiSpecService
from app.services.ef_service import EFAnalysisService
from app.services.scrum_service import ScrumPlanningService


async def run_qa_pipeline(
    job_id: str,
    scrum_job_id: str,
    scrum_artifact: dict,
    scrum_artifact_hash: str,
    ef_job_id: str,
    ef_artifact: dict,
    ef_artifact_hash: str,
    scrum_ready: bool,
    api_job_id: Optional[str] = None,
    api_artifact: Optional[dict] = None,
    api_artifact_hash: Optional[str] = None,
    target_overrides: Optional[dict] = None,
    authoritative_context: Optional[str] = None,
) -> None:  # pragma: no cover - ruta runtime con Redis/Postgres reales
    """Ejecuta el grafo del Agente QA en segundo plano y persiste resultados."""
    from ai.agents.base.pipeline import run_agent_pipeline
    from ai.agents.base.structured import ClaudeLLMClient
    from ai.orchestrator import build_qa_graph

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
    if api_job_id:
        state |= {
            "api_job_id": api_job_id,
            "api_artifact": api_artifact or {},
            "api_artifact_hash": api_artifact_hash,
        }
    if target_overrides:
        state["target_overrides"] = target_overrides
    if authoritative_context:
        state["authoritative_context"] = authoritative_context

    await run_agent_pipeline(
        job_id=job_id,
        build_graph=build_qa_graph,
        llm=ClaudeLLMClient(),
        initial_state=state,
    )


def artifact_hash(artifact: dict) -> str:
    """Hash reproducible del contenido de un artefacto consumido."""
    return compute_hash(
        json.dumps(artifact, sort_keys=True, ensure_ascii=False).encode()
    )


class QaTestDesignService:
    """Casos de uso del Agente QA."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AgentJobRepository(session)
        self.ef = EFAnalysisService(session)
        self.scrum = ScrumPlanningService(session)
        self.api = ApiSpecService(session)

    # --- Generación (con gate de entrada) -----------------------------------

    async def create_plan(
        self,
        scrum_job_id: str,
        *,
        api_job_id: Optional[str] = None,
        target_overrides: Optional[dict] = None,
        background_tasks=None,
        actor_id: Optional[str] = None,
    ) -> AgentJob:
        """Crea un plan de pruebas desde un plan Scrum **listo**."""
        chain = await self._load_chain(scrum_job_id)

        summary = await self.scrum.validation_summary(scrum_job_id)
        if not summary.get("ready_for_next_stage"):
            pending = summary.get("blocking_pending", [])
            raise GateError(
                f"El plan Scrum {scrum_job_id} no está listo para diseñar las "
                f"pruebas: quedan {len(pending)} preguntas bloqueantes al PO sin "
                "responder o falta contenido mínimo. Complétalas o genera un plan "
                f"afinado (POST /scrum/jobs/{scrum_job_id}/refine)."
            )

        contrato = await self._load_api_contract(api_job_id, scrum_job_id)

        job = await self.repo.create_job(
            AgentType.QA,
            input_job_id=scrum_job_id,
            title=chain["scrum_job"].title,
            source_type=chain["scrum_job"].source_type,
            created_by=actor_id,
        )
        await self.session.commit()

        if background_tasks is not None:
            background_tasks.add_task(
                run_qa_pipeline,
                job.id,
                scrum_job_id,
                chain["scrum_artifact"],
                artifact_hash(chain["scrum_artifact"]),
                chain["ef_job_id"],
                chain["ef_artifact"],
                artifact_hash(chain["ef_artifact"]),
                True,
                contrato["api_job_id"],
                contrato["api_artifact"],
                contrato["api_artifact_hash"],
                target_overrides,
            )
        return job

    async def _load_chain(self, scrum_job_id: str) -> dict:
        """Carga el job de Scrum y su EF de origen (transitivo)."""
        scrum_job = await self.repo.get_job(scrum_job_id)
        if scrum_job is None or scrum_job.agent_type != AgentType.SCRUM:
            raise IngestError(f"No existe un plan Scrum con id {scrum_job_id}.")

        scrum_artifact = await self.scrum.get_artifact(scrum_job_id)
        if scrum_artifact is None:
            raise GateError(
                f"El plan Scrum {scrum_job_id} aún no tiene artefacto disponible."
            )

        chain = await resolve_lineage(self.repo, scrum_job)
        ef_job = chain.get(AgentType.EF)
        if ef_job is None:
            raise GateError(
                "No se pudo recuperar el EFArtifact de origen (transitivo) del plan "
                f"Scrum {scrum_job_id}. De él salen las reglas y validaciones que "
                "dan los casos de borde."
            )

        ef_artifact = await self.ef.get_artifact(ef_job.id)
        if ef_artifact is None:
            raise GateError(
                f"El job EF {ef_job.id} de origen no tiene artefacto disponible."
            )

        return {
            "scrum_job": scrum_job,
            "scrum_artifact": scrum_artifact,
            "ef_job_id": ef_job.id,
            "ef_artifact": ef_artifact,
        }

    async def _load_api_contract(
        self, api_job_id: Optional[str], scrum_job_id: str
    ) -> dict:
        """Carga el contrato de API indicado, **validando que sea de esta cadena**.

        Un contrato de otro proyecto produciría casos de autorización perfectamente
        formados sobre endpoints que este sistema no tiene. El plan pasaría la
        revisión —los casos citan reglas reales, con su matriz y todo— y probaría
        otra cosa. Por eso el vínculo se verifica, no se supone.
        """
        if not api_job_id:
            return {"api_job_id": None, "api_artifact": None, "api_artifact_hash": None}

        api_job = await self.repo.get_job(api_job_id)
        if api_job is None or api_job.agent_type != AgentType.API:
            raise IngestError(f"No existe un contrato de API con id {api_job_id}.")

        cadena = await resolve_lineage(self.repo, api_job)
        scrum_de_la_api = cadena.get(AgentType.SCRUM)
        if scrum_de_la_api is None or scrum_de_la_api.id != scrum_job_id:
            raise GateError(
                f"El contrato de API {api_job_id} no pertenece a la cadena del plan "
                f"Scrum {scrum_job_id}: diseñar sus casos de autorización sobre él "
                "produciría pruebas de otro sistema."
            )

        artefacto = await self.api.get_artifact(api_job_id)
        if artefacto is None:
            raise GateError(
                f"El contrato de API {api_job_id} aún no tiene artefacto disponible."
            )

        return {
            "api_job_id": api_job_id,
            "api_artifact": artefacto,
            "api_artifact_hash": artifact_hash(artefacto),
        }

    # --- Lectura -------------------------------------------------------------

    async def get_job(self, job_id: str) -> Optional[AgentJob]:
        return await self.repo.get_job(job_id)

    async def get_artifact(self, job_id: str) -> Optional[dict]:
        row = await self.repo.get_artifact(job_id)
        return row.data if row is not None else None

    async def list_jobs(
        self,
        limit: int,
        offset: int,
        status_group: JobStatusGroup = JobStatusGroup.TODOS,
    ) -> tuple[list[AgentJob], int]:
        return await self.repo.list_jobs(
            agent_type=AgentType.QA,
            limit=limit,
            offset=offset,
            status_group=status_group,
        )

    async def count_jobs_by_group(self) -> dict[str, int]:
        return await self.repo.count_jobs_by_group(agent_type=AgentType.QA)

    async def list_ready_scrum_jobs(self, limit: int, offset: int) -> list[dict]:
        """Planes Scrum que un selector de origen puede ofrecer.

        Los que no están listos SÍ se devuelven, marcados: el selector los muestra
        como "casi listos" para que se vea qué falta, en vez de esconderlos y dejar
        al usuario preguntándose dónde está su plan.
        """
        jobs, _ = await self.repo.list_jobs(
            agent_type=AgentType.SCRUM,
            limit=limit,
            offset=offset,
            statuses=USABLE_JOB_STATUSES,
        )
        out: list[dict] = []
        for job in jobs:
            summary = await self.scrum.validation_summary(job.id)
            out.append(
                {
                    "job_id": job.id,
                    "title": job.title,
                    "status": job.status.value,
                    "ready_for_next_stage": summary.get("ready_for_next_stage", False),
                    "blocking_pending": summary.get("blocking_pending", []),
                }
            )
        return out

    async def list_compatible_api_jobs(self, scrum_job_id: str) -> list[dict]:
        """Contratos de API de **esta** cadena, para que el QA lead elija uno.

        El descubrimiento existe como ayuda al humano; la elección es suya (QA-D1).
        Ofrecer automáticamente "el más reciente" sería adivinar cuál contrato quiere
        probar, y con varias iteraciones del diseño esa suposición se equivoca.
        """
        jobs, _ = await self.repo.list_jobs(
            agent_type=AgentType.API,
            limit=100,
            offset=0,
            statuses=USABLE_JOB_STATUSES,
        )
        out: list[dict] = []
        for job in jobs:
            cadena = await resolve_lineage(self.repo, job)
            scrum = cadena.get(AgentType.SCRUM)
            if scrum is None or scrum.id != scrum_job_id:
                continue
            summary = await self.api.validation_summary(job.id)
            out.append(
                {
                    "job_id": job.id,
                    "title": job.title,
                    "status": job.status.value,
                    "version": job.version,
                    "ready_for_next_stage": summary.get("ready_for_next_stage", False),
                }
            )
        return out

    # --- Validaciones del QA lead + semáforo --------------------------------

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
        """Resumen + ``ready_for_next_stage`` ("el plan se puede ejecutar")."""
        summary = await self.repo.validation_summary(job_id)
        artifact = await self.get_artifact(job_id)

        blocking_ids: list[str] = []
        if artifact:
            blocking_ids = [
                q["id"]
                for q in artifact.get("questions_for_qa_lead", [])
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
        """Contenido mínimo del semáforo (QA-D5).

        El QA es hoy el último eslabón, así que su ``ready`` no habilita a otro
        agente: significa **"el plan se puede ejecutar"**. Además de no tener
        bloqueantes: al menos un caso, todos anclados a un criterio real, y la
        cobertura de los criterios de historias ``must``/``should`` completa. Los
        criterios de historias ``could``/``wont`` sin caso son advertencia, no
        bloqueo — así "criterio sin caso = advertencia" y el umbral del 100% no se
        contradicen.
        """
        if not artifact:
            return {
                "no_blocking_questions": len(pending) == 0,
                "has_test_cases": False,
                "all_cases_anchored": False,
                "blocking_coverage_met": False,
            }

        casos = artifact.get("test_cases", []) or []
        matriz = artifact.get("trace_matrix", {}) or {}
        cobertura = matriz.get("coverage", {}) or {}
        criterios = {f.get("criterion_ref") for f in matriz.get("rows", []) or []}

        total_bloqueante = cobertura.get("blocking_criteria_total", 0)
        cubierto_bloqueante = cobertura.get("blocking_criteria_covered", 0)
        ratio = (cubierto_bloqueante / total_bloqueante) if total_bloqueante else 1.0

        return {
            "no_blocking_questions": len(pending) == 0,
            "has_test_cases": len(casos) >= 1,
            # Un caso cuyo criterio no está en la matriz vendría de la nada. El
            # contrato ya lo impide ítem a ítem; esto lo comprueba sobre el conjunto.
            "all_cases_anchored": all(
                c.get("criterion_ref") in criterios for c in casos
            ),
            "blocking_coverage_met": ratio >= settings.QA_COVERAGE_THRESHOLD,
        }

    # --- Refine (QA lead) ----------------------------------------------------

    async def create_refine(
        self,
        parent_job_id: str,
        *,
        background_tasks=None,
        actor_id: Optional[str] = None,
    ) -> AgentJob:
        """Crea un job hijo reinyectando las respuestas como contexto autoritativo."""
        parent = await self.repo.get_job(parent_job_id)
        if parent is None or parent.agent_type != AgentType.QA:
            raise IngestError(f"No existe un plan de pruebas con id {parent_job_id}.")

        summary = await self.repo.validation_summary(parent_job_id)
        authoritative_context = build_authoritative_context(summary)
        if authoritative_context is None:
            raise IngestError(
                "No hay validaciones respondidas para reinyectar en el refine."
            )

        scrum_job_id = parent.input_job_id
        if not scrum_job_id:
            raise GateError("No se pudo recuperar el plan Scrum de origen del refine.")
        chain = await self._load_chain(scrum_job_id)

        # El contrato de API del job original se conserva: afinar el plan no cambia
        # contra qué contrato se probó. Recuperarlo del artefacto y no volver a
        # preguntarlo evita que un refine cambie de contrato sin que nadie lo pida.
        artifact = await self.get_artifact(parent_job_id)
        source = (artifact or {}).get("source", {}) or {}
        api_job_id = source.get("api_job_id") if source.get("api_available") else None
        try:
            contrato = await self._load_api_contract(api_job_id, scrum_job_id)
        except (IngestError, GateError) as exc:
            # El contrato con el que se generó el plan original ya no está
            # disponible. NO se degrada a un refine sin autorización: perder una
            # clase entera de casos entre dos versiones del mismo plan, y en
            # silencio, es peor que no poder afinar. Se explica de dónde viene.
            raise GateError(
                f"El plan {parent_job_id} se generó contra el contrato de API "
                f"{api_job_id}, que ya no está disponible ({exc}). Afinarlo sin él "
                "dejaría el plan sin casos de autorización sin que nadie lo pidiera: "
                "genera un plan nuevo indicando un contrato vigente."
            ) from exc

        # Y los umbrales también: un refine que cambiara el techo de casos o la
        # cobertura exigida haría incomparables la versión afinada y la original,
        # que es justo la comparación para la que existe el refine.
        target = (artifact or {}).get("target", {}) or {}
        overrides = {
            k: target[k]
            for k in (
                "coverage_threshold",
                "max_cases_per_criterion",
                "manual_capacity_minutes",
            )
            if target.get(k) is not None
        }

        child = await self.repo.create_job(
            AgentType.QA,
            parent_job_id=parent_job_id,
            input_job_id=scrum_job_id,
            title=parent.title,
            source_type=parent.source_type,
            version=parent.version + 1,
            created_by=actor_id,
        )
        await self.session.commit()

        if background_tasks is not None:
            background_tasks.add_task(
                run_qa_pipeline,
                child.id,
                scrum_job_id,
                chain["scrum_artifact"],
                artifact_hash(chain["scrum_artifact"]),
                chain["ef_job_id"],
                chain["ef_artifact"],
                artifact_hash(chain["ef_artifact"]),
                True,
                contrato["api_job_id"],
                contrato["api_artifact"],
                contrato["api_artifact_hash"],
                overrides,
                authoritative_context,
            )
        return child
