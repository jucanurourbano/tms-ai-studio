"""Runner genérico de pipelines de agentes sobre ``BackgroundTasks``.

Factoriza ``run_ef_pipeline``: marca el job RUNNING, ejecuta el grafo con el
checkpointer Redis (``thread_id=job_id`` -> los reintentos NO re-facturan fases),
persiste artefacto + métricas reales y, ante fallo, marca FAILED.

**Qué queda cuando una corrida muere a mitad** (el escenario más probable de
todos: el freno de gasto cruzándose en la llamada 40 de 110). El reparto es
estructural y no depende de que nadie se acuerde:

* **En el libro mayor** quedan las filas de las llamadas que SÍ ocurrieron. Se
  escriben una a una, antes del fallo, así que el gasto está completo aunque la
  corrida no lo esté. Ése era el encargo: 6 de los 7 jobs ``FAILED`` del
  historial reportaban 0 USD habiendo gastado.
* **NO queda artefacto.** ``save_artifact`` se llama únicamente desde ``persist``,
  y ``persist`` lo invoca únicamente el nodo ``PERSIST``, que es el último del
  grafo. Un fallo en el nodo 5 de 12 no llega ahí. No hay artefacto parcial
  porque no hay ninguna escritura de artefacto intermedia que pudiera dejarlo.
* **El job queda ``FAILED``** con el motivo en ``error`` y —desde GAS1— con
  ``metrics`` escritas: la duración real y el bloque ``real`` del libro mayor.
  El job fallido dice cuánto costó fallar.
* **El semáforo del siguiente agente NO puede leer mal nada.** Su gate consulta
  el artefacto del job de entrada; un job ``FAILED`` no tiene fila en
  ``agent_artifacts``, así que la pregunta "¿está listo?" no encuentra un
  artefacto incompleto que interpretar: no encuentra artefacto. La garantía es
  ausencia de dato, no una comprobación que pueda olvidarse.

Se eligió ``FAILED`` y no un estado nuevo: el job no produjo nada utilizable, que
es exactamente lo que ``FAILED`` significa en el historial y en los cuatro grupos
del filtro. Un estado propio para "se frenó por presupuesto" obligaría a migrar
el enum de Postgres y a repartir el caso por los grupos del frontend, para
distinguir algo que el mensaje de ``error`` ya distingue.

Ruta de runtime real (Redis + LLM real). En tests se reemplaza por mocks
(REGLA DE PRESUPUESTO: nunca API real sin autorización).
"""

import time
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

    inicio = time.monotonic()
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
            repo = AgentJobRepository(session)
            # El orden importa: primero las métricas, después el estado. Si
            # escribir las métricas fallara, el job se queda RUNNING y se ve como
            # colgado —que es un problema visible—; al revés quedaría FAILED
            # diciendo que costó cero, que es el agujero que este bloque cierra.
            # `update_job_metrics` funde solo el bloque `real` desde el libro
            # mayor (GAS-D9): un job que murió antes de ASSEMBLE no tiene
            # estimación que conservar, y por eso aquí solo va la duración.
            await repo.update_job_metrics(
                job_id,
                {
                    "duration": round(time.monotonic() - inicio, 3),
                    "failed": True,
                },
            )
            await repo.update_job_status(job_id, JobStatus.FAILED, error=str(exc)[:500])
        raise PipelineError(str(exc)) from exc
