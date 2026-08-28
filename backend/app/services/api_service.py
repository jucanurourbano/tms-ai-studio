"""Servicio del Agente API (capa services).

Verifica el gate de entrada (**modelo de datos listo**) antes de crear el job,
ejecuta el grafo en segundo plano, computa el semáforo compuesto y gestiona el
ciclo de afinamiento con el líder técnico.

Entrada cuádruple transitiva: el job se enlaza a BD por ``input_job_id``, y
Arquitectura, Scrum y EF se resuelven subiendo la cadena con ``resolve_lineage``
(tres saltos, sin columna nueva).
"""

import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai.agents.api.openapi.render import to_yaml
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
from app.services.arquitectura_service import ArquitecturaService
from app.services.bd_service import BdModelingService
from app.services.ef_service import EFAnalysisService
from app.services.scrum_service import ScrumPlanningService
from app.services.spend_sink import preflight_mensual


async def run_api_pipeline(
    job_id: str,
    bd_job_id: str,
    bd_artifact: dict,
    bd_artifact_hash: str,
    architecture_job_id: Optional[str],
    architecture_artifact: Optional[dict],
    architecture_artifact_hash: Optional[str],
    scrum_job_id: Optional[str],
    scrum_artifact: Optional[dict],
    scrum_artifact_hash: Optional[str],
    ef_job_id: str,
    ef_artifact: dict,
    ef_artifact_hash: str,
    bd_ready: bool,
    style_override: Optional[str] = None,
    authoritative_context: Optional[str] = None,
) -> None:  # pragma: no cover - ruta runtime con Redis/Postgres reales
    """Ejecuta el grafo del Agente API en segundo plano y persiste resultados."""
    from ai.agents.base.pipeline import run_agent_pipeline
    from ai.llm import get_llm
    from ai.orchestrator import build_api_graph

    state = {
        "job_id": job_id,
        "bd_job_id": bd_job_id,
        "bd_artifact": bd_artifact,
        "bd_artifact_hash": bd_artifact_hash,
        "bd_ready": bd_ready,
        "architecture_job_id": architecture_job_id,
        "architecture_artifact": architecture_artifact or {},
        "architecture_artifact_hash": architecture_artifact_hash,
        "scrum_job_id": scrum_job_id,
        "scrum_artifact": scrum_artifact or {},
        "scrum_artifact_hash": scrum_artifact_hash,
        "ef_job_id": ef_job_id,
        "ef_artifact": ef_artifact,
        "ef_artifact_hash": ef_artifact_hash,
    }
    if style_override:
        state["style_override"] = style_override
    if authoritative_context:
        state["authoritative_context"] = authoritative_context

    await run_agent_pipeline(
        job_id=job_id,
        build_graph=build_api_graph,
        # `data_class` es keyword-only y sin default (ver ai/llm/factory.py).
        # Mientras la clasificación de fuentes no exista (LLM2) se declara
        # `real`: el valor conservador, el que NO autoriza a un proveedor de
        # pruebas a ver este contenido.
        llm=get_llm("api", data_class="real", job_id=job_id),
        initial_state=state,
    )


def artifact_hash(artifact: dict) -> str:
    """Hash reproducible del contenido de un artefacto consumido."""
    return compute_hash(
        json.dumps(artifact, sort_keys=True, ensure_ascii=False).encode()
    )


class ApiSpecService:
    """Casos de uso del Agente API."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AgentJobRepository(session)
        self.ef = EFAnalysisService(session)
        self.scrum = ScrumPlanningService(session)
        self.arquitectura = ArquitecturaService(session)
        self.bd = BdModelingService(session)

    # --- Generación (con gate de entrada) -----------------------------------

    async def create_spec(
        self,
        bd_job_id: str,
        *,
        style_override: Optional[str] = None,
        background_tasks=None,
        actor_id: Optional[str] = None,
    ) -> AgentJob:
        """Crea una especificación de API desde un modelo de datos **listo**."""
        # Preflight del techo del mes (cortesía, no la garantía): sin esto el
        # usuario ve un job que arranca, corre y muere. Va ANTES de crear el
        # job para no dejar una fila PENDING que nunca va a correr. Quien
        # GARANTIZA es el freno de MeteredLLMClient, que corre antes de cada
        # llamada; un freno en el servicio es un freno que un nodo se salta.
        await preflight_mensual()
        chain = await self._load_chain(bd_job_id)

        summary = await self.bd.validation_summary(bd_job_id)
        if not summary.get("ready_for_next_stage"):
            pending = summary.get("blocking_pending", [])
            raise GateError(
                f"El modelo de datos {bd_job_id} no está listo para especificar la "
                f"API: quedan {len(pending)} preguntas bloqueantes al DBA sin "
                "responder o falta contenido mínimo. Complétalas o genera un modelo "
                f"afinado (POST /bd/jobs/{bd_job_id}/refine)."
            )

        job = await self.repo.create_job(
            AgentType.API,
            input_job_id=bd_job_id,
            title=chain["bd_job"].title,
            source_type=chain["bd_job"].source_type,
            created_by=actor_id,
        )
        await self.session.commit()

        if background_tasks is not None:
            background_tasks.add_task(
                run_api_pipeline,
                job.id,
                bd_job_id,
                chain["bd_artifact"],
                artifact_hash(chain["bd_artifact"]),
                chain["architecture_job_id"],
                chain["architecture_artifact"],
                (
                    artifact_hash(chain["architecture_artifact"])
                    if chain["architecture_artifact"]
                    else None
                ),
                chain["scrum_job_id"],
                chain["scrum_artifact"],
                (
                    artifact_hash(chain["scrum_artifact"])
                    if chain["scrum_artifact"]
                    else None
                ),
                chain["ef_job_id"],
                chain["ef_artifact"],
                artifact_hash(chain["ef_artifact"]),
                True,
                style_override,
            )
        return job

    async def _load_chain(self, bd_job_id: str) -> dict:
        """Carga el job de BD y sus antecesores (Arquitectura, Scrum y EF).

        El EF es materia prima —de él salen actores, matriz CRUD y reglas— y su
        ausencia es un error de dominio. Arquitectura y Scrum aportan agrupación y
        trazabilidad: si faltaran, el contrato se degrada pero no se bloquea.
        """
        bd_job = await self.repo.get_job(bd_job_id)
        if bd_job is None or bd_job.agent_type != AgentType.BD:
            raise IngestError(f"No existe un job de BD con id {bd_job_id}.")

        bd_artifact = await self.bd.get_artifact(bd_job_id)
        if bd_artifact is None:
            raise GateError(
                f"El modelo de datos {bd_job_id} aún no tiene artefacto disponible."
            )

        chain = await resolve_lineage(self.repo, bd_job)
        architecture_job = chain.get(AgentType.ARQUITECTURA)
        scrum_job = chain.get(AgentType.SCRUM)
        ef_job = chain.get(AgentType.EF)
        if ef_job is None:
            raise GateError(
                "No se pudo recuperar el EFArtifact de origen (transitivo) del "
                f"modelo de datos {bd_job_id}."
            )

        ef_artifact = await self.ef.get_artifact(ef_job.id)
        if ef_artifact is None:
            raise GateError(
                f"El job EF {ef_job.id} de origen no tiene artefacto disponible."
            )

        return {
            "bd_job": bd_job,
            "bd_artifact": bd_artifact,
            "architecture_job_id": architecture_job.id if architecture_job else None,
            "architecture_artifact": (
                await self.arquitectura.get_artifact(architecture_job.id)
                if architecture_job
                else None
            ),
            "scrum_job_id": scrum_job.id if scrum_job else None,
            "scrum_artifact": (
                await self.scrum.get_artifact(scrum_job.id) if scrum_job else None
            ),
            "ef_job_id": ef_job.id,
            "ef_artifact": ef_artifact,
        }

    # --- Lectura ------------------------------------------------------------

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
            agent_type=AgentType.API,
            limit=limit,
            offset=offset,
            status_group=status_group,
        )

    async def count_jobs_by_group(self) -> dict[str, int]:
        return await self.repo.count_jobs_by_group(agent_type=AgentType.API)

    async def list_ready_bd_jobs(self, limit: int, offset: int) -> list[dict]:
        """Modelos de datos que un selector de origen puede ofrecer.

        Los que no están listos SÍ se devuelven, marcados: el selector los muestra
        como "casi listos" para que se vea qué falta, en vez de esconderlos y dejar
        al usuario preguntándose dónde está su modelo.
        """
        jobs, _ = await self.repo.list_jobs(
            agent_type=AgentType.BD,
            limit=limit,
            offset=offset,
            statuses=USABLE_JOB_STATUSES,
        )
        out: list[dict] = []
        for job in jobs:
            summary = await self.bd.validation_summary(job.id)
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

    # --- Export del documento ------------------------------------------------

    async def render_openapi(
        self, job_id: str, *, formato: str = "yaml"
    ) -> Optional[dict]:
        """Devuelve el documento OpenAPI, en YAML canónico o en JSON.

        El YAML es el que se validó y el que guarda el artefacto. El JSON se
        **re-serializa** desde él: es la misma especificación en otra codificación,
        y no cuesta una sola llamada al modelo (mismo dividendo que el DDL por
        motor del Agente BD).
        """
        import yaml as _yaml

        artifact = await self.get_artifact(job_id)
        if artifact is None:
            return None

        bloque = artifact.get("openapi") or {}
        contenido = bloque.get("content") or ""
        if formato == "json":
            documento = _yaml.safe_load(contenido) or {}
            texto = json.dumps(documento, ensure_ascii=False, indent=2)
        else:
            texto = contenido

        return {
            "format": formato,
            "spec_version": bloque.get("spec_version"),
            "operations_total": bloque.get("operations_total", 0),
            "checksum": bloque.get("checksum"),
            "valid": bool((artifact.get("validation") or {}).get("spec_valid")),
            "content": texto,
        }

    # --- Validaciones del líder técnico + semáforo compuesto ----------------

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
        """Resumen + ``ready_for_next_stage`` (habilita a Backend y Frontend)."""
        summary = await self.repo.validation_summary(job_id)
        artifact = await self.get_artifact(job_id)

        blocking_ids: list[str] = []
        if artifact:
            blocking_ids = [
                q["id"]
                for q in artifact.get("questions_for_tech_lead", [])
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
        """Contenido mínimo del semáforo.

        Además de no tener bloqueantes: al menos un endpoint, **todos con una
        decisión de acceso**, cobertura por encima del umbral y especificación
        válida. Un contrato con un endpoint que nadie puede llamar no habilita a
        los Agentes Backend y Frontend por mucho que el documento parsee.
        """
        if not artifact:
            return {
                "no_blocking_questions": len(pending) == 0,
                "has_endpoints": False,
                "all_endpoints_authorized": False,
                "coverage_met": False,
                "spec_valid": False,
            }

        endpoints = artifact.get("endpoints", [])
        metrics = artifact.get("metrics", {}) or {}
        validation = artifact.get("validation", {}) or {}

        return {
            "no_blocking_questions": len(pending) == 0,
            "has_endpoints": len(endpoints) >= 1,
            "all_endpoints_authorized": metrics.get("endpoints_unauthorized", 0) == 0,
            "coverage_met": metrics.get("coverage", 0.0)
            >= settings.API_COVERAGE_THRESHOLD,
            "spec_valid": bool(
                validation.get("spec_valid") and not validation.get("errors")
            ),
        }

    # --- Refine (líder técnico) ---------------------------------------------

    async def create_refine(
        self,
        parent_job_id: str,
        *,
        background_tasks=None,
        actor_id: Optional[str] = None,
    ) -> AgentJob:
        """Crea un job hijo reinyectando las respuestas como contexto autoritativo."""
        # Preflight del techo del mes (cortesía, no la garantía): sin esto el
        # usuario ve un job que arranca, corre y muere. Va ANTES de crear el
        # job para no dejar una fila PENDING que nunca va a correr. Quien
        # GARANTIZA es el freno de MeteredLLMClient, que corre antes de cada
        # llamada; un freno en el servicio es un freno que un nodo se salta.
        await preflight_mensual()
        parent = await self.repo.get_job(parent_job_id)
        if parent is None or parent.agent_type != AgentType.API:
            raise IngestError(f"No existe un job de API con id {parent_job_id}.")

        summary = await self.repo.validation_summary(parent_job_id)
        authoritative_context = build_authoritative_context(summary)
        if authoritative_context is None:
            raise IngestError(
                "No hay validaciones respondidas para reinyectar en el refine."
            )

        bd_job_id = parent.input_job_id
        if not bd_job_id:
            raise GateError(
                "No se pudo recuperar el modelo de datos de origen del refine."
            )
        chain = await self._load_chain(bd_job_id)

        # El estilo del job original se conserva: afinar el contrato no cambia la
        # clase de API que se está diseñando.
        artifact = await self.get_artifact(parent_job_id)
        style_override = (artifact or {}).get("target", {}).get("api_style")

        child = await self.repo.create_job(
            AgentType.API,
            parent_job_id=parent_job_id,
            input_job_id=bd_job_id,
            title=parent.title,
            source_type=parent.source_type,
            version=parent.version + 1,
            created_by=actor_id,
        )
        await self.session.commit()

        if background_tasks is not None:
            background_tasks.add_task(
                run_api_pipeline,
                child.id,
                bd_job_id,
                chain["bd_artifact"],
                artifact_hash(chain["bd_artifact"]),
                chain["architecture_job_id"],
                chain["architecture_artifact"],
                (
                    artifact_hash(chain["architecture_artifact"])
                    if chain["architecture_artifact"]
                    else None
                ),
                chain["scrum_job_id"],
                chain["scrum_artifact"],
                (
                    artifact_hash(chain["scrum_artifact"])
                    if chain["scrum_artifact"]
                    else None
                ),
                chain["ef_job_id"],
                chain["ef_artifact"],
                artifact_hash(chain["ef_artifact"]),
                True,
                style_override,
                authoritative_context,
            )
        return child
