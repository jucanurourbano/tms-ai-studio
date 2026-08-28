"""GAS2 — la consulta del mes: el desglose y la honestidad del dato.

Lo que se ejerce aqui es la diferencia entre una cifra y una cifra que se puede
usar para decidir: que ``by_stage`` separe el gasto por nodo (que es el
antes/despues que el plan necesita medir), que el gasto sin nodo atribuido se vea
como un hueco y no como un cero, y que la fraccion estimada de GAS-D4 llegue
hasta arriba en vez de quedarse dentro del repositorio.
"""

from datetime import datetime, timezone
from decimal import Decimal

from ai.llm.budget import SpendRow, limites_del_mes
from app.models.agent import AgentType
from app.models.spend import fuente_del_total
from app.repositories.agent_job_repository import AgentJobRepository
from app.repositories.llm_spend_repository import LlmSpendRepository


def fila(**kwargs) -> SpendRow:
    base = dict(
        agent_role="qa",
        provider="anthropic",
        model="claude-sonnet-5",
        usage_source="real",
        input_tokens=1000,
        output_tokens=200,
        cost_usd=Decimal("0.010000"),
    )
    base.update(kwargs)
    return SpendRow(**base)


async def _mes(session) -> dict:
    desde, hasta = limites_del_mes()
    return await LlmSpendRepository(session).resumen_del_mes(desde=desde, hasta=hasta)


# ---------------------------------------------------------------------------
# El desglose por nodo: la fila que tiene que demostrar el recorte
# ---------------------------------------------------------------------------


async def test_by_stage_separa_el_gasto_por_nodo_del_grafo(session):
    """``EDGE_CASES`` costaba X: sin esta fila, esa frase no se puede sostener."""
    repo = LlmSpendRepository(session)
    for _ in range(3):
        await repo.anotar(fila(stage="EDGE_CASES", cost_usd=Decimal("0.100000")))
    await repo.anotar(fila(stage="TEST_DESIGN", cost_usd=Decimal("0.050000")))

    por_nodo = {
        (f["agent_role"], f["stage"]): f for f in (await _mes(session))["by_stage"]
    }
    assert por_nodo[("qa", "EDGE_CASES")]["cost_usd"] == Decimal("0.300000")
    assert por_nodo[("qa", "EDGE_CASES")]["calls"] == 3
    assert por_nodo[("qa", "TEST_DESIGN")]["cost_usd"] == Decimal("0.050000")


async def test_el_gasto_sin_nodo_sale_como_fila_propia_y_no_como_cero(session):
    """GAS-D10: los nodos que no son *map* quedan en ``NULL``. Ese gasto EXISTE y
    tiene que verse; confundirlo con un cero diria que esos nodos no gastan."""
    repo = LlmSpendRepository(session)
    await repo.anotar(fila(stage="EDGE_CASES", cost_usd=Decimal("0.100000")))
    await repo.anotar(fila(agent_role="ef", stage=None, cost_usd=Decimal("0.700000")))

    sin_nodo = [f for f in (await _mes(session))["by_stage"] if f["stage"] is None]
    assert len(sin_nodo) == 1
    assert sin_nodo[0]["agent_role"] == "ef"
    assert sin_nodo[0]["cost_usd"] == Decimal("0.700000")


async def test_el_desglose_va_de_mas_caro_a_mas_barato(session):
    """Lo que hay que recortar se lee primero, sin ordenar a mano."""
    repo = LlmSpendRepository(session)
    await repo.anotar(fila(agent_role="ef", cost_usd=Decimal("0.010000")))
    await repo.anotar(fila(agent_role="qa", cost_usd=Decimal("5.000000")))
    await repo.anotar(fila(agent_role="bd", cost_usd=Decimal("0.500000")))

    assert [f["agent_role"] for f in (await _mes(session))["by_agent"]] == [
        "qa",
        "bd",
        "ef",
    ]


# ---------------------------------------------------------------------------
# Los jobs mas caros
# ---------------------------------------------------------------------------


async def test_top_jobs_agrupa_por_job_y_excluye_las_filas_sin_job(session):
    """La ingesta del inventario no es *un* job: agrupar sus filas inventaria uno
    gigante que no existe. Su gasto sigue contando en el total y en ``by_agent``."""
    jobs = AgentJobRepository(session)
    repo = LlmSpendRepository(session)
    caro = (await jobs.create_job(AgentType.QA)).id
    barato = (await jobs.create_job(AgentType.EF)).id

    await repo.anotar(fila(job_id=caro, cost_usd=Decimal("1.000000")))
    await repo.anotar(fila(job_id=caro, cost_usd=Decimal("0.500000")))
    await repo.anotar(fila(job_id=barato, cost_usd=Decimal("0.200000")))
    await repo.anotar(
        fila(job_id=None, agent_role="inventory_doc", cost_usd=Decimal("9.000000"))
    )

    resumen = await _mes(session)
    assert [(f["job_id"], f["cost_usd"]) for f in resumen["top_jobs"]] == [
        (caro, Decimal("1.500000")),
        (barato, Decimal("0.200000")),
    ]
    assert resumen["spent_usd"] == Decimal("10.700000")
    ingesta = [f for f in resumen["by_agent"] if f["agent_role"] == "inventory_doc"]
    assert ingesta[0]["cost_usd"] == Decimal("9.000000")


# ---------------------------------------------------------------------------
# La honestidad del dato (GAS-D4)
# ---------------------------------------------------------------------------


async def test_el_costo_estimado_se_suma_aparte_del_total(session):
    """No basta con contar llamadas estimadas: lo que importa para leer la cifra
    es cuanto DINERO de ella se dedujo."""
    repo = LlmSpendRepository(session)
    await repo.anotar(fila(cost_usd=Decimal("3.000000")))
    await repo.anotar(fila(usage_source="estimado", cost_usd=Decimal("1.000000")))

    resumen = await _mes(session)
    assert resumen["spent_usd"] == Decimal("4.000000")
    assert resumen["estimated_cost_usd"] == Decimal("1.000000")
    assert resumen["estimated_calls"] == 1
    assert resumen["calls"] == 2


async def test_las_estimadas_tambien_se_cuentan_dentro_de_cada_agrupacion(session):
    """Si el desglose no dijera cuales de sus filas son estimadas, un nodo entero
    aproximado se leeria igual que uno medido."""
    repo = LlmSpendRepository(session)
    await repo.anotar(fila(stage="CRITIQUE", usage_source="estimado"))
    await repo.anotar(fila(stage="CRITIQUE"))

    critique = [
        f for f in (await _mes(session))["by_stage"] if f["stage"] == "CRITIQUE"
    ]
    assert critique[0]["estimated_calls"] == 1
    assert critique[0]["calls"] == 2


async def test_el_mes_solo_cuenta_las_filas_del_mes(session):
    """El corte de GAS-D8, ejercido tambien por esta consulta: una fila de otro
    mes no puede aparecer en el desglose ni mover el total."""
    repo = LlmSpendRepository(session)
    await repo.anotar(fila(cost_usd=Decimal("2.000000")))
    await repo.anotar(
        fila(
            cost_usd=Decimal("99.000000"),
            created_at=datetime(2020, 1, 15, tzinfo=timezone.utc),
        )
    )

    resumen = await _mes(session)
    assert resumen["spent_usd"] == Decimal("2.000000")
    assert resumen["calls"] == 1


# ---------------------------------------------------------------------------
# El vocabulario del total (criterio 2: "mixto" tiene que ser visible)
# ---------------------------------------------------------------------------


def test_fuente_del_total_distingue_las_cuatro_situaciones():
    assert fuente_del_total(10, 0) == "real"
    assert fuente_del_total(10, 3) == "mixto"
    # Todas estimadas NO es "mixto": decirlo afirmaria que algo se midio.
    assert fuente_del_total(10, 10) == "estimado"
    # Y cero llamadas no es "real": no hay medicion de la que presumir.
    assert fuente_del_total(0, 0) == "sin_datos"


async def test_un_job_con_todas_las_llamadas_estimadas_dice_estimado(session):
    jobs = AgentJobRepository(session)
    repo = LlmSpendRepository(session)
    job = (await jobs.create_job(AgentType.EF)).id
    await repo.anotar(fila(job_id=job, usage_source="estimado"))
    await repo.anotar(fila(job_id=job, usage_source="estimado"))

    real = (await jobs.update_job_metrics(job, {"cost": 0.02})).metrics["real"]
    assert real["usage_source"] == "estimado"
