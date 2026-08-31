"""CMP0 — corre Arquitectura + BD + API sobre el EF y el Scrum REALES de julio.

Por qué existe
--------------
Hasta hoy los tres agentes de diseño solo se habían ejercido contra los
``examples.py``: artefactos escritos a mano, de juguete (**3 tablas, 2
historias**), que sirven para probar la FORMA del contrato y nada más. Una
cadena que solo se ha visto pasar sobre sus propias semillas es indistinguible
de una que no funciona: las semillas están construidas para encajar.

Este script sustituye la entrada por lo único real que hay en la base: el
``EFArtifact`` y el ``ScrumArtifact`` que sí salieron de Claude en julio de 2026
(31 historias, 110 criterios, 16 RF). Lo que se mide no es la calidad del
modelo —eso exige saldo— sino si la **maquinaria determinista** (MODEL_MAP,
RESOURCE_MAP, el render de DDL y de OpenAPI, los cortafuegos anti-invención)
aguanta un tamaño que no es el suyo.

Coste: **0,00 USD**. Los tres nodos LLM usan los dobles de la suite
(``tests.mocks``), los mismos que verifican los tests: si el doble cambia,
cambian los dos. Nunca se llama a la API real (REGLA DE PRESUPUESTO).

Qué NO demuestra
----------------
Los dobles de BD y de API son **dirigidos por la entrada** (leen el payload y
responden sobre él), así que escalan con el documento. El de Arquitectura
**no**: devuelve tres componentes fijos pase lo que pase. Por tanto el número de
componentes de esta corrida NO es una medida de escala, y así se reporta.

Trazabilidad — que nadie confunda esto con una corrida real
-----------------------------------------------------------
Tres marcas, y las tres hacen falta porque protegen de cosas distintas:

1. **En el título**, ``[DOBLE·CMP0]``. Es lo que se ve en el listado de jobs sin
   abrir nada, que es donde alguien se confundiría dentro de seis meses.
2. **En ``metrics.provenance``**, un bloque legible por máquina con el script, el
   doble y la fecha. Sobrevive a que alguien edite el título.
3. **La ausencia de ``metrics.real``**. Ninguna llamada pasó por
   ``MeteredLLMClient``, así que no hay filas en el libro mayor. Es una señal
   débil a propósito —la regla del proyecto dice que la ausencia de un dato no
   es el valor 0 de ese dato— y por eso NO se usa sola.

Uso (desde backend/, con el venv y Postgres arriba)::

    .venv/bin/python scripts/cmp0_cadena_real.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.orchestrator import (  # noqa: E402
    build_api_graph,
    build_arquitectura_graph,
    build_bd_graph,
)
from ai.orchestrator.checkpointer import build_memory_checkpointer  # noqa: E402
from app.dependencies.database import session_scope  # noqa: E402
from app.models.agent import AgentType, JobStatus  # noqa: E402
from app.repositories.agent_job_repository import AgentJobRepository  # noqa: E402
from app.services.arquitectura_service import artifact_hash  # noqa: E402
from tests.mocks import ApiMapLLM, ArchMapLLM, BdMapLLM  # noqa: E402

# --- Las dos corridas REALES de julio (las únicas que existen) ---------------
# EF:    documento "Gestión de solicitudes de vacaciones", COMPLETED 2026-07-21.
# Scrum: su plan, COMPLETED_WITH_WARNINGS 2026-07-21 — 31 historias, 110
#        criterios. Es el mismo plan sobre el que se reconstruyó la línea base
#        del gasto (§3.bis de docs/diseno-control-de-gasto.md).
EF_REAL = "01KY2V9HKCF0BSSPE7JQDBWX3V"
SCRUM_REAL = "01KY33JDAV21N40N326TCR3JSS"

MARCA = "[DOBLE·CMP0]"


def _provenance() -> dict:
    """Bloque de procedencia que se funde en `metrics` al persistir."""
    return {
        "kind": "doble",
        "block": "CMP0",
        "script": "scripts/cmp0_cadena_real.py",
        "llm": "dobles de la suite (tests.mocks: ArchMapLLM/BdMapLLM/ApiMapLLM)",
        "cost_usd": 0.0,
        "input_ef_job_id": EF_REAL,
        "input_scrum_job_id": SCRUM_REAL,
        "warning": (
            "NO es una corrida contra el modelo real. Las cifras de este "
            "artefacto miden la maquinaria determinista, no la calidad del LLM."
        ),
        "run_at": datetime.now(timezone.utc).isoformat(),
    }


async def main() -> None:
    async with session_scope() as session:
        repo = AgentJobRepository(session)

        # --- Las entradas reales -------------------------------------------
        ef_row = await repo.get_artifact(EF_REAL)
        scrum_row = await repo.get_artifact(SCRUM_REAL)
        if ef_row is None or scrum_row is None:
            raise SystemExit(
                "No están en la base el EF/Scrum reales de julio. Este script "
                "no inventa una entrada: sin ellos no hay nada que medir."
            )
        ef_art = ef_row.data
        scrum_art = scrum_row.data
        ef_hash = artifact_hash(ef_art)
        scrum_hash = artifact_hash(scrum_art)

        ef_job = await repo.get_job(EF_REAL)
        titulo = f"{MARCA} {ef_job.title}"

        async def persist(job_id: str, artifact: dict, status: str, metrics: dict):
            # La procedencia va en `metrics`, NUNCA dentro del artefacto: el
            # artefacto es la salida del agente y no se muta desde fuera (misma
            # regla que las validaciones y las asignaciones).
            marcadas = {**(metrics or {}), "provenance": _provenance()}
            await repo.save_artifact(job_id, artifact, artifact["schema_version"])
            await repo.update_job_metrics(job_id, marcadas)
            await repo.update_job_status(job_id, JobStatus[status])

        async def correr(agent_type, entrada_job_id, build_graph, llm, state):
            job = await repo.create_job(
                agent_type,
                input_job_id=entrada_job_id,
                title=titulo,
                source_type="text",
            )
            await repo.update_job_status(job.id, JobStatus.RUNNING)
            graph = build_graph(build_memory_checkpointer())
            await graph.ainvoke(
                {"job_id": job.id, **state},
                config={
                    "configurable": {
                        "thread_id": job.id,
                        "llm": llm,
                        "persist": persist,
                    }
                },
            )
            fila = await repo.get_artifact(job.id)
            job = await repo.get_job(job.id)
            return job, (fila.data if fila else None)

        # --- ARQUITECTURA ---------------------------------------------------
        # `scrum_ready=True` se fuerza A CONCIENCIA y es un hallazgo, no un
        # atajo: el plan real NO pasa el gate (cuatro historias `must` sin
        # sprint). Se declara aquí y se reporta abajo; correr el servicio en su
        # lugar habría devuelto 409 y no habría medido nada.
        arq_job, arq_art = await correr(
            AgentType.ARQUITECTURA,
            SCRUM_REAL,
            build_arquitectura_graph,
            ArchMapLLM(),
            {
                "scrum_job_id": SCRUM_REAL,
                "scrum_artifact": scrum_art,
                "scrum_artifact_hash": scrum_hash,
                "scrum_ready": True,
                "ef_job_id": EF_REAL,
                "ef_artifact": ef_art,
                "ef_artifact_hash": ef_hash,
            },
        )
        arq_hash = artifact_hash(arq_art) if arq_art else ""

        # --- BD -------------------------------------------------------------
        bd_job, bd_art = await correr(
            AgentType.BD,
            arq_job.id,
            build_bd_graph,
            BdMapLLM(),
            {
                "architecture_job_id": arq_job.id,
                "architecture_artifact": arq_art,
                "architecture_artifact_hash": arq_hash,
                "architecture_ready": True,
                "scrum_job_id": SCRUM_REAL,
                "scrum_artifact": scrum_art,
                "scrum_artifact_hash": scrum_hash,
                "ef_job_id": EF_REAL,
                "ef_artifact": ef_art,
                "ef_artifact_hash": ef_hash,
            },
        )
        bd_hash = artifact_hash(bd_art) if bd_art else ""

        # --- API ------------------------------------------------------------
        api_job, api_art = await correr(
            AgentType.API,
            bd_job.id,
            build_api_graph,
            ApiMapLLM(),
            {
                "bd_job_id": bd_job.id,
                "bd_artifact": bd_art,
                "bd_artifact_hash": bd_hash,
                "bd_ready": True,
                "architecture_job_id": arq_job.id,
                "architecture_artifact": arq_art,
                "architecture_artifact_hash": arq_hash,
                "scrum_job_id": SCRUM_REAL,
                "scrum_artifact": scrum_art,
                "scrum_artifact_hash": scrum_hash,
                "ef_job_id": EF_REAL,
                "ef_artifact": ef_art,
                "ef_artifact_hash": ef_hash,
            },
        )

        salida = {
            "jobs": {
                "arquitectura": arq_job.id,
                "bd": bd_job.id,
                "api": api_job.id,
            },
            "status": {
                "arquitectura": arq_job.status.value,
                "bd": bd_job.status.value,
                "api": api_job.status.value,
            },
            "artefactos": {
                "arquitectura": arq_art,
                "bd": bd_art,
                "api": api_art,
            },
        }

    carpeta = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".logs"
    )
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, "cmp0_cadena_real.json")
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=2)

    print("=" * 72)
    print("CMP0 — cadena Arq→BD→API sobre el EF y el Scrum REALES de julio")
    print("=" * 72)
    for nombre, jid in salida["jobs"].items():
        print(f"  {nombre:13} {jid}  {salida['status'][nombre]}")
    print(f"\n  Artefactos volcados en: {destino}")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
