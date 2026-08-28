"""Mide la LÍNEA BASE del «antes» de los puntos 2 y 3 del plan, sin gastar un token.

Para poder decir «``EDGE_CASES`` costaba X y ahora cuesta Y» hace falta la X. La
X medida con el libro mayor no existe y no puede existir: **ninguna corrida de la
historia del proyecto registró el ``usage``** del proveedor —``TokenMetrics.source``
vale ``"estimado"`` en los seis agentes—, así que el «antes» de todo lo anterior a
GAS1 es forzosamente **reconstruido**. Este script lo reconstruye de la única
forma que no es una conjetura: **ejecutando nuestro propio código** y midiendo lo
que produce, que es determinista.

Lo que mide (nuestro código, exacto y reproducible byte a byte):

* cuántas llamadas hace cada nodo,
* con qué prompts y de qué tamaño (``estimate_tokens``, el mismo ``len // 4`` que
  los nodos apuntan hoy),
* cuánto de esa entrada es **preámbulo repetido** —el ``system`` idéntico
  reenviado una vez por ítem—, que es exactamente lo que los puntos 2 y 3
  pretenden recortar.

Lo que NO mide, y por eso la línea base se declara reconstruida y no medida: el
``usage`` real. Las tres causas del subconteo (§3 del diseño) siguen fuera, y una
de ellas —el loop de reparación, que factura hasta 3 veces y se apunta 1— crece
con el número de llamadas, de modo que la reconstrucción **subestima** el
desperdicio del nodo de 110 llamadas. El sesgo es conservador en la dirección que
importa: el recorte real será mayor que el que estas cifras prometen.

El LLM es el doble de la suite y no se toca la red ni el libro mayor: el script
solo LEE de la base de datos. Ejecutar esto cuesta 0,00 USD.

Uso (desde backend/, con el venv y Postgres arriba)::

    .venv/bin/python scripts/medir_linea_base.py [scrum_job_id]

Ver ``docs/diseno-control-de-gasto.md`` §3.bis.
"""

import asyncio
import hashlib
import os
import sys
from collections import defaultdict

# Permite ejecutar el archivo directamente (agrega backend/ al path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.agents.scrum.common import glossary_with_context  # noqa: E402
from ai.agents.scrum.estimate import build_estimate_user  # noqa: E402
from ai.agents.scrum.prioritize import build_prioritize_user  # noqa: E402
from ai.agents.scrum.prompts import build_system  # noqa: E402
from ai.orchestrator import build_qa_graph  # noqa: E402
from ai.orchestrator.checkpointer import build_memory_checkpointer  # noqa: E402
from ai.tools.chunker import estimate_tokens  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.dependencies.database import session_scope  # noqa: E402
from app.repositories.agent_job_repository import AgentJobRepository  # noqa: E402

# El doble del LLM es el MISMO que usa la suite y el seed. Si cambia, cambian los
# tres: la línea base no puede medir un pipeline distinto del que se prueba.
from tests.mocks import QaRichLLM  # noqa: E402

#: El plan Scrum real de 31 historias y 110 criterios (2026-07-21). Es el único
#: del historial a escala de un requerimiento de verdad; los otros dos en verde
#: son los del seed (once criterios) y medir contra ellos mediría la fixture.
PLAN_POR_DEFECTO = "01KY33JDAV21N40N326TCR3JSS"

REGISTRO: list[dict] = []


class Espia:
    """Envuelve el doble del LLM y anota cada llamada con su nodo.

    Implementa ``for_stage`` a propósito: es la misma costura por la que el libro
    mayor atribuye la fila (GAS-D10), así que lo que aquí se atribuye a un nodo es
    lo que allí se atribuirá al mismo nodo — incluido el hueco de los que no la
    usan, que sale como ``(sin etiqueta)`` en vez de repartirse a ojo.
    """

    def __init__(self, inner, stage: str | None = None) -> None:
        self._inner, self._stage = inner, stage

    def for_stage(self, stage: str) -> "Espia":
        return Espia(self._inner, stage)

    async def complete_json(self, *, system: str, user: str) -> str:
        salida = await self._inner.complete_json(system=system, user=user)
        REGISTRO.append(
            {
                "stage": self._stage or "(sin etiqueta)",
                "sys": system,
                "in": estimate_tokens(system + user),
                "out": estimate_tokens(salida),
                "firma_sys": hashlib.sha256(system.encode()).hexdigest()[:12],
                "firma_par": hashlib.sha256((system + user).encode()).hexdigest()[:12],
            }
        )
        return salida


def _usd(entrada: int, salida: int = 0) -> float:
    return (
        entrada * settings.CLAUDE_PRICE_INPUT_PER_MTOK
        + salida * settings.CLAUDE_PRICE_OUTPUT_PER_MTOK
    ) / 1e6


async def _cargar(job_id: str) -> tuple[dict, dict, str]:
    """Lee el plan Scrum y su EF de origen. Solo lectura."""
    async with session_scope() as session:
        repo = AgentJobRepository(session)
        scrum_job = await repo.get_job(job_id)
        if scrum_job is None:
            raise SystemExit(f"No existe el job Scrum {job_id}.")
        scrum = await repo.get_artifact(job_id)
        ef = await repo.get_artifact(scrum_job.input_job_id)
        if scrum is None or ef is None:
            raise SystemExit("El plan o su EF de origen no tienen artefacto.")
        return scrum.data, ef.data, scrum_job.input_job_id


async def _correr_qa(scrum: dict, ef: dict, scrum_job_id: str, ef_job_id: str) -> dict:
    """Corre el pipeline REAL de QA con el doble del LLM. No persiste nada."""
    recogido: dict = {}

    async def persist(job_id, artifact, status, metrics):  # noqa: ANN001
        recogido["metrics"] = metrics

    grafo = build_qa_graph(build_memory_checkpointer())
    await grafo.ainvoke(
        {
            "job_id": "LINEA-BASE",
            "scrum_job_id": scrum_job_id,
            "scrum_artifact": scrum,
            "scrum_artifact_hash": "linea-base",
            # El gate ya se evaluó fuera: aquí se mide el volumen del pipeline,
            # no se decide si el plan puede pasar (ver §3.bis, punto 4).
            "scrum_ready": True,
            "ef_job_id": ef_job_id,
            "ef_artifact": ef,
            "ef_artifact_hash": "linea-base",
            "started_at": 0.0,
        },
        config={
            "configurable": {
                "thread_id": "LINEA-BASE",
                "llm": Espia(QaRichLLM()),
                "today": "2026-08-28",
                "persist": persist,
            }
        },
    )
    return recogido.get("metrics", {})


def _tabla_qa() -> None:
    por_nodo: dict[str, dict] = defaultdict(
        lambda: {"llamadas": 0, "in": 0, "out": 0, "sys": set(), "par": set()}
    )
    for fila in REGISTRO:
        d = por_nodo[fila["stage"]]
        d["llamadas"] += 1
        d["in"] += fila["in"]
        d["out"] += fila["out"]
        d["sys"].add(fila["firma_sys"])
        d["par"].add(fila["firma_par"])

    print(
        f"{'nodo':16} {'llam':>5} {'firmas':>7} {'in_tok':>9} {'out_tok':>8} {'USD':>8}"
    )
    total = {"llamadas": 0, "in": 0, "out": 0}
    for nodo, d in sorted(por_nodo.items(), key=lambda kv: -kv[1]["in"]):
        print(
            f"{nodo:16} {d['llamadas']:5} {len(d['sys']):7} {d['in']:9,} "
            f"{d['out']:8,} {_usd(d['in'], d['out']):8.4f}"
        )
        for clave in total:
            total[clave] += d[clave]
    print("-" * 60)
    print(
        f"{'TOTAL':16} {total['llamadas']:5} {'':7} {total['in']:9,} "
        f"{total['out']:8,} {_usd(total['in'], total['out']):8.4f}"
    )

    print()
    print("Preámbulo repetido (el `system` idéntico, reenviado una vez por ítem):")
    for nodo, d in sorted(por_nodo.items()):
        filas = [f for f in REGISTRO if f["stage"] == nodo]
        repetido = sum(estimate_tokens(f["sys"]) for f in filas)
        unico = sum(
            estimate_tokens(s)
            for s in {f["firma_sys"]: f["sys"] for f in filas}.values()
        )
        print(
            f"  {nodo:16} {repetido:8,} tok reenviados · {unico:6,} si se envía una vez "
            f"· desperdicio {repetido - unico:8,} tok (${_usd(repetido - unico):.4f})"
        )

    print()
    print("Si el map se agrupara en lotes (el «110 → 1» realista):")
    for nodo, d in sorted(por_nodo.items()):
        filas = [f for f in REGISTRO if f["stage"] == nodo]
        if len(filas) < 2:
            continue
        sys_tok = estimate_tokens(filas[0]["sys"])
        payload = sum(f["in"] - sys_tok for f in filas)
        for lote in (10, 20):
            llamadas = -(-len(filas) // lote)
            entrada = llamadas * sys_tok + payload
            ahorro = d["in"] - entrada
            print(
                f"  {nodo:16} lotes de {lote:2} → {llamadas:3} llamadas, "
                f"entrada {entrada:8,} tok · ahorro {ahorro:8,} tok "
                f"(${_usd(ahorro):.4f}) · salida por llamada x{lote}"
            )


def _tabla_scrum(scrum: dict) -> None:
    """ESTIMATE + PRIORITIZE: las 62 llamadas del punto 3.

    No hace falta el grafo: los dos nodos son *map* de una llamada por historia y
    sus prompts los construyen estas mismas funciones, sobre las historias reales
    del plan. Medir el prompt no necesita respuesta.
    """
    historias = scrum.get("stories") or []
    glosario = glossary_with_context(None)
    print(
        f"{'nodo':12} {'llam':>5} {'sys_tok':>8} {'payload':>8} {'in_tok':>9} "
        f"{'USD':>8} {'lote 1':>9} {'ahorro':>8}"
    )
    for nodo, plantilla, build_user in (
        ("ESTIMATE", "estimate.md", build_estimate_user),
        ("PRIORITIZE", "prioritize.md", build_prioritize_user),
    ):
        sys_tok = estimate_tokens(build_system(plantilla, glosario))
        payload = sum(estimate_tokens(build_user(h)) for h in historias)
        entrada = len(historias) * sys_tok + payload
        consolidado = sys_tok + payload
        print(
            f"{nodo:12} {len(historias):5} {sys_tok:8,} {payload:8,} {entrada:9,} "
            f"{_usd(entrada):8.4f} {consolidado:9,} {entrada - consolidado:8,}"
        )


def _freno(estimado_usd: float) -> None:
    """Qué haría el freno del job con esta corrida, con los topes de hoy."""
    from decimal import Decimal

    from ai.llm.budget import margen_del_job
    from ai.llm.metering import costo_maximo_de_una_llamada

    maximo = costo_maximo_de_una_llamada(
        (settings.CLAUDE_PRICE_INPUT_PER_MTOK, settings.CLAUDE_PRICE_OUTPUT_PER_MTOK)
    )
    margen = margen_del_job(maximo)
    tope = Decimal(str(settings.LLM_JOB_CAP_USD))
    utilizable = tope - margen
    print(
        f"Tope del job {tope} USD − margen {margen} (=3 llamadas en vuelo x {maximo}) "
        f"⇒ utilizable {utilizable} USD"
    )
    print(f"Estimado de la corrida: {estimado_usd:.4f} USD")
    factor = float(utilizable) / estimado_usd if estimado_usd else 0.0
    print(
        f"El freno actúa si el factor real supera x{factor:.2f} "
        f"(el mecanismo del §3 lo sitúa entre x2,4 y x3,1)"
    )


async def main() -> None:
    job_id = sys.argv[1] if len(sys.argv) > 1 else PLAN_POR_DEFECTO
    scrum, ef, ef_job_id = await _cargar(job_id)
    historias = len(scrum.get("stories") or [])
    criterios = sum(len(h.get("acceptance_criteria") or []) for h in scrum["stories"])

    print("=" * 72)
    print(f"LÍNEA BASE RECONSTRUIDA — plan {job_id}")
    print(f"{historias} historias · {criterios} criterios · 0,00 USD gastados en medir")
    print("=" * 72)
    metricas = await _correr_qa(scrum, ef, job_id, ef_job_id)
    print("\n-- QA modo A (punto 2) " + "-" * 49)
    _tabla_qa()
    print("\n-- Scrum ESTIMATE + PRIORITIZE (punto 3) " + "-" * 31)
    _tabla_scrum(scrum)
    print("\n-- El freno, con los topes de hoy " + "-" * 38)
    tokens = metricas.get("tokens") or {}
    _freno(float(metricas.get("cost") or 0.0))
    print(
        f"\nEl agente habría apuntado: {tokens.get('input', 0):,} in / "
        f"{tokens.get('output', 0):,} out · {metricas.get('cost', 0):.4f} USD "
        f"({tokens.get('source')})"
    )
    print("Esa cifra es la ESTIMADA. La real no existe: nadie leyó el `usage`.")


if __name__ == "__main__":
    asyncio.run(main())
