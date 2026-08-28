"""GAS1 — qué queda cuando el freno se cruza a MITAD de una corrida.

Es el escenario más probable de todos: el tope no se alcanza al empezar un job,
se alcanza en la llamada 40 de 110. El reparto tiene que ser estructural y no
depender de que nadie se acuerde:

* el **libro mayor** conserva las 39 llamadas que sí ocurrieron;
* **no queda artefacto**, ni completo ni parcial;
* el **job** queda ``FAILED`` con el motivo y con lo que costó fallar;
* y el **semáforo del siguiente agente no puede leer mal nada**, porque no hay
  nada que leer.

Lo que estos tests vigilan de verdad es la primera condición de todas: que un
``BudgetExceededError`` **no se pueda confundir con un ítem en cuarentena**. Si
alguien lo capturase en un ``except`` ancho del camino del LLM, el pipeline
seguiría hasta ``ASSEMBLE`` y produciría un artefacto que parece entero y le
faltan 70 casos — la forma exacta del error que este proyecto no puede cometer:
un artefacto que pasa la ejecución certificando una mentira.
"""

from decimal import Decimal

import pytest
from pydantic import BaseModel

from ai.agents.base.structured import complete_structured, run_structured_map
from ai.llm import budget
from ai.llm.metering import Completion, MeteredLLMClient, Usage
from ai.orchestrator import build_ef_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from app.config.settings import settings
from tests.mocks import DimAwareLLM

TEXTO = (
    "# Proceso de Siniestros\n\n"
    "Registro y seguimiento de siniestros ligados a guías de envío.\n\n"
    "- Reportar el siniestro\n- Registrar la guía\n- Cerrar\n"
)


class Esquema(BaseModel):
    valor: int


class InternoQueSeFrena:
    """Responde bien ``n`` veces y a la siguiente el freno lo para."""

    provider = "anthropic"
    model = "claude-sonnet-5"
    data_class = "real"

    def __init__(self, gratis: int) -> None:
        self.gratis = gratis
        self.llamadas = 0

    async def complete(self, *, system, user) -> Completion:
        self.llamadas += 1
        return Completion(text='{"valor": 1}', usage=Usage(100, 10))


class SumideroQueSeAgota:
    """Deja pasar ``gratis`` llamadas y a partir de ahí el job está en el tope."""

    def __init__(self, gratis: int) -> None:
        self.gratis = gratis
        self.filas: list = []

    async def totales(self, *, desde, hasta, job_id):
        agotado = len(self.filas) >= self.gratis
        return budget.Totales(
            mes_usd=Decimal("0"),
            job_usd=Decimal(str(settings.LLM_JOB_CAP_USD)) if agotado else Decimal("0"),
        )

    async def anotar(self, fila) -> None:
        self.filas.append(fila)


# ---------------------------------------------------------------------------
# El freno NO es una cuarentena
# ---------------------------------------------------------------------------


async def test_el_freno_no_se_confunde_con_un_esquema_invalido(monkeypatch):
    """``complete_structured`` repara ante JSON/esquema inválido. Un freno de
    presupuesto no es ninguna de las dos cosas: reintentarlo sería insistir en
    gastar justo cuando se acaba de decir que no hay con qué."""
    sumidero = SumideroQueSeAgota(gratis=0)
    monkeypatch.setattr("ai.llm.budget._SINK", sumidero)
    llm = MeteredLLMClient(InternoQueSeFrena(0), agent_role="qa", job_id="J-1")

    with pytest.raises(budget.BudgetExceededError):
        await complete_structured(
            llm, system="s", user="u", schema=Esquema, stage="PRUEBA"
        )


async def test_el_freno_tumba_el_map_en_vez_de_dejar_items_en_cuarentena(monkeypatch):
    """La cuarentena existe para "el modelo contestó mal": el ítem se marca y el
    job sigue. Si el freno cayera ahí, 70 ítems quedarían "en cuarentena" y el
    artefacto saldría con la cobertura mermada y el semáforo opinando sobre él."""
    sumidero = SumideroQueSeAgota(gratis=2)
    monkeypatch.setattr("ai.llm.budget._SINK", sumidero)
    llm = MeteredLLMClient(InternoQueSeFrena(2), agent_role="qa", job_id="J-1")

    with pytest.raises(budget.BudgetExceededError):
        await run_structured_map(
            llm,
            [{"ref": f"R-{n}"} for n in range(6)],
            build_system=lambda i: "s",
            build_user=lambda i: "u",
            schema=Esquema,
            ref_of=lambda i: i["ref"],
            stage="EDGE_CASES",
            estimate_tokens=len,
            concurrency=1,
        )

    # Lo que SÍ quedó: las llamadas que de verdad se hicieron, con su nodo.
    assert len(sumidero.filas) == 2
    assert {f.stage for f in sumidero.filas} == {"EDGE_CASES"}


async def test_el_freno_atraviesa_el_critique_del_ef(monkeypatch):
    """``_llm_pass`` captura ``JSONDecodeError``/``ValidationError`` para dejar
    una observación en vez de tumbar el job. El freno tiene que pasar de largo:
    es el llamador suelto y el de la entrada sin techo."""
    from ai.agents.ef.critique import _llm_pass

    sumidero = SumideroQueSeAgota(gratis=0)
    monkeypatch.setattr("ai.llm.budget._SINK", sumidero)
    llm = MeteredLLMClient(InternoQueSeFrena(0), agent_role="ef", job_id="J-1")

    with pytest.raises(budget.BudgetExceededError):
        await _llm_pass(llm, {"entities": []}, {})


# ---------------------------------------------------------------------------
# Lo que queda: ni artefacto, ni semáforo que pueda leerlo mal
# ---------------------------------------------------------------------------


async def test_una_corrida_frenada_a_mitad_NO_persiste_artefacto(monkeypatch, tmp_path):
    """La garantía es estructural: ``persist`` solo lo invoca el nodo ``PERSIST``,
    que es el último del grafo. Un fallo en el nodo 5 de 12 no llega ahí, así que
    no hay artefacto parcial porque no hay ninguna escritura intermedia."""
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    sumidero = SumideroQueSeAgota(gratis=3)
    monkeypatch.setattr("ai.llm.budget._SINK", sumidero)

    persistidos: list = []

    async def _persist(job_id, artifact, status, metrics):
        persistidos.append((job_id, status))

    llm = MeteredLLMClient(
        _LLMdeGrafo(DimAwareLLM()), agent_role="ef", job_id="J-FRENADO"
    )
    graph = build_ef_graph(build_memory_checkpointer())

    with pytest.raises(budget.BudgetExceededError):
        await graph.ainvoke(
            {
                "job_id": "J-FRENADO",
                "filename": "siniestros.txt",
                "content": TEXTO.encode("utf-8"),
            },
            {
                "configurable": {
                    "thread_id": "J-FRENADO",
                    "llm": llm,
                    "persist": _persist,
                }
            },
        )

    assert persistidos == [], (
        "Se persistió un artefacto de una corrida frenada a mitad. Ese artefacto "
        "llegaría al semáforo del siguiente agente con la cobertura incompleta."
    )
    # Y lo que sí quedó es el gasto: las llamadas que de verdad se hicieron.
    assert len(sumidero.filas) == 3


class _LLMdeGrafo:
    """Adapta el mock por dimensiones del EF al protocolo interno ``complete``."""

    provider = "anthropic"
    model = "claude-sonnet-5"
    data_class = "real"

    def __init__(self, mock) -> None:
        self._mock = mock

    async def complete(self, *, system, user) -> Completion:
        texto = await self._mock.complete_json(system=system, user=user)
        return Completion(text=texto, usage=Usage(100, 50))


async def test_un_job_FAILED_no_tiene_artefacto_y_el_gate_no_puede_leerlo(session):
    """La otra mitad de la garantía, del lado de la base.

    El gate del siguiente agente pregunta por el artefacto del job de entrada. Un
    job ``FAILED`` no tiene fila en ``agent_artifacts``, así que la pregunta
    "¿está listo?" no encuentra un artefacto incompleto que interpretar: no
    encuentra artefacto. Es ausencia de dato, no una comprobación que se pueda
    olvidar.
    """
    from app.models.agent import AgentType, JobStatus
    from app.repositories.agent_job_repository import AgentJobRepository
    from app.repositories.llm_spend_repository import LlmSpendRepository

    jobs = AgentJobRepository(session)
    job = await jobs.create_job(AgentType.QA)
    await LlmSpendRepository(session).anotar(
        budget.SpendRow(
            job_id=job.id,
            agent_role="qa",
            stage="EDGE_CASES",
            provider="anthropic",
            model="claude-sonnet-5",
            usage_source="real",
            input_tokens=100_000,
            output_tokens=8_000,
            cost_usd=Decimal("5.020000"),
        )
    )

    motivo = (
        "Freno de gasto: se alcanzó el tope del job (LLM_JOB_CAP_USD = 5.0000 USD)."
    )
    await jobs.update_job_metrics(job.id, {"duration": 61.2, "failed": True})
    await jobs.update_job_status(job.id, JobStatus.FAILED, error=motivo)

    recuperado = await jobs.get_job(job.id)
    assert recuperado.status == JobStatus.FAILED
    assert "LLM_JOB_CAP_USD" in recuperado.error
    # Dice cuánto costó fallar: el encargo #3, y H1 deja de reproducirse.
    assert recuperado.metrics["real"]["cost_usd"] == "5.020000"
    assert recuperado.metrics["real"]["calls"] == 1
    # Y no hay artefacto que el semáforo del siguiente agente pueda malinterpretar.
    assert await jobs.get_artifact(job.id) is None
