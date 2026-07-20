"""Runner genérico de pipelines de agentes sobre ``BackgroundTasks``.

Factoriza ``run_ef_pipeline``: marca el job RUNNING, ejecuta el grafo con el
checkpointer Redis (``thread_id=job_id`` -> los reintentos NO re-facturan fases),
persiste artefacto + métricas reales y, ante fallo, marca FAILED.

Ruta de runtime real (Redis + LLM real). En tests se reemplaza por mocks
(REGLA DE PRESUPUESTO: nunca API real sin autorización).
"""

from typing import Callable, Optional

from ai.errors import PipelineError


async def run_agent_pipeline(
    *,
    job_id: str,
    build_graph: Callable,
    llm,
    initial_state: dict,
    extra_config: Optional[dict] = None,
) -> None:  # pragma: no cover - ruta runtime con Redis/Postgres reales
    """Ejecuta un grafo de agente en segundo plano y persiste sus resultados."""
    from ai.orchestrator.checkpointer import build_redis_checkpointer
    from app.dependencies.database import session_scope
    from app.models.agent import JobStatus
    from app.repositories.agent_job_repository import AgentJobRepository

    async def persist(jid: str, artifact: dict, status: str, metrics: dict) -> None:
        async with session_scope() as session:
            repo = AgentJobRepository(session)
            await repo.save_artifact(jid, artifact, artifact["schema_version"])
            await repo.update_job_metrics(jid, metrics)
            await repo.update_job_status(jid, JobStatus[status])

    try:
        async with session_scope() as session:
            await AgentJobRepository(session).update_job_status(
                job_id, JobStatus.RUNNING
            )

        graph = build_graph(build_redis_checkpointer())
        config = {
            "configurable": {
                "thread_id": job_id,
                "llm": llm,
                "persist": persist,
                **(extra_config or {}),
            }
        }
        await graph.ainvoke(initial_state, config)
    except Exception as exc:
        async with session_scope() as session:
            await AgentJobRepository(session).update_job_status(
                job_id, JobStatus.FAILED, error=str(exc)[:500]
            )
        raise PipelineError(str(exc)) from exc
