"""Siembra la cadena completa EF → Scrum → Arquitectura → BD → API → QA (CIERRE del Agente QA).

Permite recorrer el Agente QA en el navegador **sin gastar un token** de la API
de Anthropic. Siembra dos cosas distintas y las dos hacen falta:

1. **La cadena hasta el contrato de API**, con el plan Scrum *a escala*
   (``example_rich_artifact``: tres épicas, siete historias, once criterios, las
   cuatro prioridades MoSCoW). Es lo que hace verificable la pantalla de
   creación: el selector muestra un plan en verde y la lista de contratos
   compatibles tiene algo que ofrecer.
2. **Un plan de pruebas ya generado**, producido por el pipeline REAL de doce
   nodos con un LLM falso. No es un artefacto escrito a mano: sale de los mismos
   nodos que en producción, así que la matriz, el esfuerzo y las preguntas son
   los que el agente produce de verdad.

⚠️  Pulsar «Generar plan de pruebas» en la interfaz SÍ llama al modelo real y
consume tokens. Este seed existe justamente para no tener que hacerlo: el plan
sembrado ya está completo y se puede explorar entero.

Uso (desde backend/, con el venv y Postgres arriba + migraciones aplicadas)::

    .venv/bin/python scripts/seed_qa_demo.py
"""

import asyncio
import os
import sys

# Permite ejecutar el archivo directamente (agrega backend/ al path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.agents.api.schemas.examples import example_artifact as api_example  # noqa: E402
from ai.agents.arquitectura.schemas.examples import (  # noqa: E402
    example_artifact as arch_example,
)
from ai.agents.bd.schemas.examples import example_artifact as bd_example  # noqa: E402
from ai.agents.ef.schemas.examples import example_artifact as ef_example  # noqa: E402
from ai.agents.scrum.schemas.examples import example_rich_artifact  # noqa: E402
from ai.orchestrator import build_qa_graph  # noqa: E402
from ai.orchestrator.checkpointer import build_memory_checkpointer  # noqa: E402
from app.dependencies.database import session_scope  # noqa: E402
from app.models.agent import AgentType, JobStatus  # noqa: E402
from app.models.ef import EFSourceDocType  # noqa: E402
from app.repositories.agent_job_repository import AgentJobRepository  # noqa: E402
from app.repositories.ef_repository import EFRepository  # noqa: E402

# El doble del LLM es el MISMO que usa la suite (`tests/agents/qa/test_cierre.py`).
# Importarlo aquí en vez de copiarlo evita que el plan de demostración y el que
# los tests verifican acaben divergiendo: si el doble cambia, cambian los dos.
from tests.mocks import QaRichLLM  # noqa: E402

TITULO = "Siniestros (demo QA)"
HOY = "2026-08-14"


async def main() -> None:
    async with session_scope() as session:
        # --- EF: la raíz de la cadena --------------------------------------
        ef_repo = EFRepository(session)
        doc = await ef_repo.get_or_create_source_doc(
            content_hash="seed-qa-demo-siniestros-0001",
            doc_type=EFSourceDocType.TEXT,
            filename="demo_siniestros_qa.txt",
            doc_metadata={"seed": True, "source_type": "text"},
        )
        ef_job = await ef_repo.create_job(
            source_doc_id=doc.id, title=TITULO, source_type="text"
        )
        ef_art = ef_example().model_dump(mode="json")
        await ef_repo.save_artifact(ef_job.id, ef_art, ef_art["schema_version"])
        await ef_repo.update_job_metrics(ef_job.id, ef_art["metrics"])
        await ef_repo.update_job_status(ef_job.id, JobStatus.COMPLETED)

        repo = AgentJobRepository(session)

        async def eslabon(agent_type: AgentType, entrada: str, artefacto: dict):
            """Crea un job COMPLETED enlazado al anterior por `input_job_id`."""
            job = await repo.create_job(
                agent_type, input_job_id=entrada, title=TITULO, source_type="text"
            )
            await repo.save_artifact(job.id, artefacto, artefacto["schema_version"])
            await repo.update_job_metrics(job.id, artefacto.get("metrics", {}))
            await repo.update_job_status(job.id, JobStatus.COMPLETED)
            return job

        # --- Scrum: el plan A ESCALA, sin preguntas bloqueantes -------------
        scrum_art = example_rich_artifact().model_dump(mode="json")
        for pregunta in scrum_art["questions_for_po"]:
            # El gate del QA exige el plan en verde. Dejar una bloqueante haría
            # que el selector lo mostrara "casi listo" y el seed no serviría para
            # lo que existe: recorrer el flujo entero.
            pregunta["blocking"] = False
        scrum_job = await eslabon(AgentType.SCRUM, ef_job.id, scrum_art)

        # --- Arquitectura → BD → API: la cadena hasta el contrato -----------
        arch_job = await eslabon(
            AgentType.ARQUITECTURA,
            scrum_job.id,
            arch_example().model_dump(mode="json"),
        )
        bd_job = await eslabon(
            AgentType.BD, arch_job.id, bd_example().model_dump(mode="json")
        )
        api_art = api_example().model_dump(mode="json")
        api_job = await eslabon(AgentType.API, bd_job.id, api_art)

        # --- QA: el plan de pruebas, por el pipeline real y LLM falso -------
        qa_job = await repo.create_job(
            AgentType.QA, input_job_id=scrum_job.id, title=TITULO, source_type="text"
        )

        async def persist(job_id: str, artifact: dict, status: str, metrics: dict):
            await repo.save_artifact(job_id, artifact, artifact["schema_version"])
            await repo.update_job_metrics(job_id, metrics)
            await repo.update_job_status(job_id, JobStatus[status])

        graph = build_qa_graph(build_memory_checkpointer())
        await graph.ainvoke(
            {
                "job_id": qa_job.id,
                "scrum_job_id": scrum_job.id,
                "scrum_artifact": scrum_art,
                "scrum_artifact_hash": "seed-scrum-hash",
                "scrum_ready": True,
                "ef_job_id": ef_job.id,
                "ef_artifact": ef_art,
                "ef_artifact_hash": "seed-ef-hash",
                "api_job_id": api_job.id,
                "api_artifact": api_art,
                "api_artifact_hash": "seed-api-hash",
                "started_at": 0.0,
            },
            config={
                "configurable": {
                    "thread_id": qa_job.id,
                    "llm": QaRichLLM(),
                    "today": HOY,
                    "persist": persist,
                }
            },
        )

        artefacto = await repo.get_artifact(qa_job.id)
        casos = len(artefacto.data["test_cases"]) if artefacto else 0
        criterios = len(artefacto.data["trace_matrix"]["rows"]) if artefacto else 0
        preguntas = len(artefacto.data["questions_for_qa_lead"]) if artefacto else 0

        ids = {
            "ef": ef_job.id,
            "scrum": scrum_job.id,
            "arquitectura": arch_job.id,
            "bd": bd_job.id,
            "api": api_job.id,
            "qa": qa_job.id,
        }

    print("=" * 70)
    print("Cadena sembrada (todos COMPLETED):")
    for nombre, jid in ids.items():
        print(f"  {nombre:13} {jid}")
    print("-" * 70)
    print(
        f"Plan de pruebas: {casos} casos · {criterios} criterios · {preguntas} preguntas"
    )
    print("-" * 70)
    print("Abrir en el navegador:")
    print(f"  Plan de pruebas   http://localhost:3000/agents/qa/jobs/{ids['qa']}")
    print(f"  Plan Scrum        http://localhost:3000/agents/scrum/jobs/{ids['scrum']}")
    print(f"  Contrato de API   http://localhost:3000/agents/api/jobs/{ids['api']}")
    print("  Crear otro plan   http://localhost:3000/agents/qa/new")
    print()
    print("⚠️  «Generar plan de pruebas» en /agents/qa/new llama al modelo REAL")
    print("    y consume tokens. El plan de arriba ya está completo.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
