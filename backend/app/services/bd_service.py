"""Servicio del Agente BD (capa services).

Verifica el gate de entrada (**diseño de arquitectura listo**) antes de crear el
job, ejecuta el grafo en segundo plano, computa el semáforo compuesto y gestiona el
ciclo de afinamiento con el DBA.

Entrada triple transitiva: el job se enlaza a Arquitectura por ``input_job_id``, y
Scrum y EF se resuelven subiendo la cadena con ``resolve_lineage`` (dos saltos, sin
columna nueva).
"""

import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai.agents.base.lineage import resolve_lineage
from ai.agents.base.refine import build_authoritative_context
from ai.agents.bd.ddl.render import build_ddl_scripts
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
from app.services.ef_service import EFAnalysisService
from app.services.scrum_service import ScrumPlanningService
from app.services.spend_sink import preflight_mensual


async def run_bd_pipeline(
    job_id: str,
    architecture_job_id: str,
    architecture_artifact: dict,
    architecture_artifact_hash: str,
    scrum_job_id: Optional[str],
    scrum_artifact: Optional[dict],
    scrum_artifact_hash: Optional[str],
    ef_job_id: str,
    ef_artifact: dict,
    ef_artifact_hash: str,
    architecture_ready: bool,
    engine_override: Optional[str] = None,
    authoritative_context: Optional[str] = None,
) -> None:  # pragma: no cover - ruta runtime con Redis/Postgres reales
    """Ejecuta el grafo del Agente BD en segundo plano y persiste resultados."""
    from ai.agents.base.pipeline import run_agent_pipeline
    from ai.llm import get_llm
    from ai.orchestrator import build_bd_graph

    state = {
        "job_id": job_id,
        "architecture_job_id": architecture_job_id,
        "architecture_artifact": architecture_artifact,
        "architecture_artifact_hash": architecture_artifact_hash,
        "architecture_ready": architecture_ready,
        "scrum_job_id": scrum_job_id,
        "scrum_artifact": scrum_artifact or {},
        "scrum_artifact_hash": scrum_artifact_hash,
        "ef_job_id": ef_job_id,
        "ef_artifact": ef_artifact,
        "ef_artifact_hash": ef_artifact_hash,
    }
    if engine_override:
        state["engine_override"] = engine_override
    if authoritative_context:
        state["authoritative_context"] = authoritative_context

    await run_agent_pipeline(
        job_id=job_id,
        build_graph=build_bd_graph,
        # `data_class` es keyword-only y sin default (ver ai/llm/factory.py).
        # Mientras la clasificación de fuentes no exista (LLM2) se declara
        # `real`: el valor conservador, el que NO autoriza a un proveedor de
        # pruebas a ver este contenido.
        llm=get_llm("bd", data_class="real", job_id=job_id),
        initial_state=state,
    )


def artifact_hash(artifact: dict) -> str:
    """Hash reproducible del contenido de un artefacto consumido."""
    return compute_hash(
        json.dumps(artifact, sort_keys=True, ensure_ascii=False).encode()
    )


class BdModelingService:
    """Casos de uso del Agente BD."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AgentJobRepository(session)
        self.ef = EFAnalysisService(session)
        self.scrum = ScrumPlanningService(session)
        self.arquitectura = ArquitecturaService(session)

    # --- Generación (con gate de entrada) -----------------------------------

    async def create_model(
        self,
        architecture_job_id: str,
        *,
        engine_override: Optional[str] = None,
        background_tasks=None,
        actor_id: Optional[str] = None,
    ) -> AgentJob:
        """Crea un modelo de datos desde un diseño de arquitectura **listo**."""
        # Preflight del techo del mes (cortesía, no la garantía): sin esto el
        # usuario ve un job que arranca, corre y muere. Va ANTES de crear el
        # job para no dejar una fila PENDING que nunca va a correr. Quien
        # GARANTIZA es el freno de MeteredLLMClient, que corre antes de cada
        # llamada; un freno en el servicio es un freno que un nodo se salta.
        await preflight_mensual()
        chain = await self._load_chain(architecture_job_id)

        summary = await self.arquitectura.validation_summary(architecture_job_id)
        if not summary.get("ready_for_next_stage"):
            pending = summary.get("blocking_pending", [])
            raise GateError(
                f"El diseño de arquitectura {architecture_job_id} no está listo "
                f"para modelar la base de datos: quedan {len(pending)} preguntas "
                "bloqueantes al Arquitecto sin responder o falta contenido mínimo. "
                "Complétalas o genera un diseño afinado "
                f"(POST /arquitectura/jobs/{architecture_job_id}/refine)."
            )

        job = await self.repo.create_job(
            AgentType.BD,
            input_job_id=architecture_job_id,
            title=chain["architecture_job"].title,
            source_type=chain["architecture_job"].source_type,
            created_by=actor_id,
        )
        await self.session.commit()

        if background_tasks is not None:
            background_tasks.add_task(
                run_bd_pipeline,
                job.id,
                architecture_job_id,
                chain["architecture_artifact"],
                artifact_hash(chain["architecture_artifact"]),
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
                engine_override,
            )
        return job

    async def _load_chain(self, architecture_job_id: str) -> dict:
        """Carga el job de Arquitectura y sus antecesores (Scrum y EF).

        El EF es la materia prima y su ausencia es un error de dominio; el Scrum
        solo aporta trazabilidad, así que si faltara **no** se bloquea el modelado.
        """
        architecture_job = await self.repo.get_job(architecture_job_id)
        if (
            architecture_job is None
            or architecture_job.agent_type != AgentType.ARQUITECTURA
        ):
            raise IngestError(
                f"No existe un job de Arquitectura con id {architecture_job_id}."
            )

        architecture_artifact = await self.arquitectura.get_artifact(
            architecture_job_id
        )
        if architecture_artifact is None:
            raise GateError(
                f"El diseño de arquitectura {architecture_job_id} aún no tiene "
                "artefacto disponible."
            )

        chain = await resolve_lineage(self.repo, architecture_job)
        scrum_job = chain.get(AgentType.SCRUM)
        ef_job = chain.get(AgentType.EF)
        if ef_job is None:
            raise GateError(
                "No se pudo recuperar el EFArtifact de origen (transitivo) del "
                f"diseño de arquitectura {architecture_job_id}."
            )

        ef_artifact = await self.ef.get_artifact(ef_job.id)
        if ef_artifact is None:
            raise GateError(
                f"El job EF {ef_job.id} de origen no tiene artefacto disponible."
            )
        scrum_artifact = (
            await self.scrum.get_artifact(scrum_job.id) if scrum_job else None
        )

        return {
            "architecture_job": architecture_job,
            "architecture_artifact": architecture_artifact,
            "scrum_job_id": scrum_job.id if scrum_job else None,
            "scrum_artifact": scrum_artifact,
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
            agent_type=AgentType.BD,
            limit=limit,
            offset=offset,
            status_group=status_group,
        )

    async def count_jobs_by_group(self) -> dict[str, int]:
        return await self.repo.count_jobs_by_group(agent_type=AgentType.BD)

    async def list_ready_architecture_jobs(self, limit: int, offset: int) -> list[dict]:
        """Lista los jobs de Arquitectura que un selector de origen puede ofrecer.

        Solo estados **utilizables** (completados y con avisos): un job fallido o
        en curso no tiene artefacto que consumir, y ofrecerlo solo produce un
        rechazo del gate. Los que no están listos SÍ se devuelven, marcados: el
        selector los muestra como "casi listos" para que se vea qué falta.
        """
        jobs, _ = await self.repo.list_jobs(
            agent_type=AgentType.ARQUITECTURA,
            limit=limit,
            offset=offset,
            statuses=USABLE_JOB_STATUSES,
        )
        out: list[dict] = []
        for job in jobs:
            summary = await self.arquitectura.validation_summary(job.id)
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

    # --- Export del DDL -----------------------------------------------------

    async def render_ddl(
        self, job_id: str, *, engine: Optional[str] = None
    ) -> Optional[dict]:
        """Devuelve el DDL del job, opcionalmente **re-renderizado a otro motor**.

        Cambiar de motor aquí no cuesta una sola llamada al modelo: el artefacto
        guarda el tipo *lógico* de cada columna y el renderizador lo traduce
        (decisión DB2). Tampoco muta el artefacto: el motor que decidió la
        arquitectura sigue siendo el suyo, y esto es una vista alternativa.
        """
        artifact = await self.get_artifact(job_id)
        if artifact is None:
            return None

        target_engine = engine or artifact["target"]["engine"]
        if engine and engine != artifact["target"]["engine"]:
            # El esquema es propio de cada motor (`public` en PostgreSQL, `dbo` en
            # SQL Server, ninguno en Oracle/MySQL): al cambiar de dialecto se
            # descarta el que traía el artefacto para que aplique el del destino.
            # Sin esto, un re-render a Oracle emitía `CREATE TABLE public.guias`.
            tables = [
                {**table, "schema_name": None} for table in artifact.get("tables", [])
            ]
            scripts, _ = build_ddl_scripts(
                tables, artifact.get("seed_data", []), target_engine
            )
        else:
            scripts = artifact.get("ddl_scripts", [])

        return {
            "engine": target_engine,
            "engine_of_record": artifact["target"]["engine"],
            "regenerated": bool(engine and engine != artifact["target"]["engine"]),
            "scripts": scripts,
            "sql": "\n".join(
                s["sql"] for s in sorted(scripts, key=lambda x: x["order"])
            ),
        }

    # --- Validaciones del DBA + semáforo compuesto --------------------------

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
        """Resumen + ``ready_for_next_stage`` (habilita al Agente API)."""
        summary = await self.repo.validation_summary(job_id)
        artifact = await self.get_artifact(job_id)

        blocking_ids: list[str] = []
        if artifact:
            blocking_ids = [
                q["id"]
                for q in artifact.get("questions_for_dba", [])
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
        """Contenido mínimo del semáforo (BD3 del diseño).

        Además de no tener bloqueantes: al menos una tabla, **todas con clave
        primaria**, cobertura de entidades por encima del umbral y **DDL válido**.
        Un modelo sin PK o con un DDL que no se puede ejecutar no habilita al
        Agente API por mucho que nadie haya dejado preguntas sin responder.
        """
        if not artifact:
            return {
                "no_blocking_questions": len(pending) == 0,
                "has_tables": False,
                "all_tables_have_pk": False,
                "coverage_met": False,
                "ddl_valid": False,
            }

        tables = artifact.get("tables", [])
        coverage = artifact.get("analysis", {}).get("coverage", {}) or {}
        total = coverage.get("entities_total", 0)
        ratio = 1.0 if not total else coverage.get("entities_mapped", 0) / total
        validation = artifact.get("validation", {}) or {}

        return {
            "no_blocking_questions": len(pending) == 0,
            "has_tables": len(tables) >= 1,
            "all_tables_have_pk": bool(tables)
            and all(t.get("primary_key") for t in tables),
            "coverage_met": ratio >= settings.BD_COVERAGE_THRESHOLD,
            "ddl_valid": bool(
                validation.get("syntax_ok") and not validation.get("errors")
            ),
        }

    # --- Refine (DBA) -------------------------------------------------------

    async def create_refine(
        self,
        parent_job_id: str,
        *,
        background_tasks=None,
        actor_id: Optional[str] = None,
    ) -> AgentJob:
        """Crea un job hijo reinyectando las respuestas del DBA como contexto."""
        # Preflight del techo del mes (cortesía, no la garantía): sin esto el
        # usuario ve un job que arranca, corre y muere. Va ANTES de crear el
        # job para no dejar una fila PENDING que nunca va a correr. Quien
        # GARANTIZA es el freno de MeteredLLMClient, que corre antes de cada
        # llamada; un freno en el servicio es un freno que un nodo se salta.
        await preflight_mensual()
        parent = await self.repo.get_job(parent_job_id)
        if parent is None or parent.agent_type != AgentType.BD:
            raise IngestError(f"No existe un job de BD con id {parent_job_id}.")

        summary = await self.repo.validation_summary(parent_job_id)
        authoritative_context = build_authoritative_context(summary)
        if authoritative_context is None:
            raise IngestError(
                "No hay validaciones respondidas para reinyectar en el refine."
            )

        architecture_job_id = parent.input_job_id
        if not architecture_job_id:
            raise GateError(
                "No se pudo recuperar el diseño de arquitectura de origen del refine."
            )
        chain = await self._load_chain(architecture_job_id)

        # El motor del job original se conserva: un refine afina el modelo, no
        # cambia la plataforma sobre la que se construye.
        artifact = await self.get_artifact(parent_job_id)
        engine_override = (artifact or {}).get("target", {}).get("engine")

        child = await self.repo.create_job(
            AgentType.BD,
            parent_job_id=parent_job_id,
            input_job_id=architecture_job_id,
            title=parent.title,
            source_type=parent.source_type,
            version=parent.version + 1,
            created_by=actor_id,
        )
        await self.session.commit()

        if background_tasks is not None:
            background_tasks.add_task(
                run_bd_pipeline,
                child.id,
                architecture_job_id,
                chain["architecture_artifact"],
                artifact_hash(chain["architecture_artifact"]),
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
                engine_override,
                authoritative_context,
            )
        return child
