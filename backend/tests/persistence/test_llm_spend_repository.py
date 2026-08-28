"""GAS1 — el libro mayor en la base: los totales, el corte de mes y ``metrics.real``.

Aquí se ejerce lo que el sumidero en memoria de la suite NO puede ejercer: que la
consulta que decide el freno sume lo que tiene que sumar contra un motor real
(SQLite), que el corte de mes en ``America/Lima`` funcione con fechas
persistidas, y que un job ``FAILED`` deje de reportar cero.
"""

from datetime import datetime, timezone
from decimal import Decimal

from ai.llm.budget import SpendRow, limites_del_mes
from app.models.agent import AgentType, JobStatus
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


async def _job(session, agent=AgentType.QA) -> str:
    return (await AgentJobRepository(session).create_job(agent)).id


# ---------------------------------------------------------------------------
# Los totales que deciden el freno
# ---------------------------------------------------------------------------


async def test_totales_suma_el_mes_y_el_job_en_una_consulta(session):
    repo = LlmSpendRepository(session)
    job_a, job_b = await _job(session), await _job(session)

    await repo.anotar(fila(job_id=job_a, cost_usd=Decimal("1.500000")))
    await repo.anotar(fila(job_id=job_a, cost_usd=Decimal("0.250000")))
    await repo.anotar(fila(job_id=job_b, cost_usd=Decimal("2.000000")))
    await repo.anotar(fila(job_id=None, cost_usd=Decimal("0.100000")))

    desde, hasta = limites_del_mes()
    totales = await repo.totales(desde=desde, hasta=hasta, job_id=job_a)
    assert totales.job_usd == Decimal("1.750000")
    # El mes cuenta TODO, incluida la ingesta sin job: si no contara, el mes
    # tendría una fuga por el único sitio que ingiere documentos reales.
    assert totales.mes_usd == Decimal("3.850000")


async def test_sin_job_id_el_total_del_job_es_cero_y_no_suma_las_huerfanas(session):
    """``job_id=None`` no debe casar con las filas que también tienen ``NULL``:
    sería atribuirle a la ingesta de documentos el gasto de todas las demás."""
    repo = LlmSpendRepository(session)
    await repo.anotar(fila(job_id=None, cost_usd=Decimal("5.000000")))

    desde, hasta = limites_del_mes()
    totales = await repo.totales(desde=desde, hasta=hasta, job_id=None)
    assert totales.job_usd == Decimal("0")
    assert totales.mes_usd == Decimal("5.000000")


async def test_el_mes_se_corta_en_lima_sobre_fechas_YA_persistidas(session):
    """El corte, ejercido de punta a punta.

    La fila de las 21:00 del 31 de agosto en Lima es del 1 de septiembre en UTC.
    Pertenece a AGOSTO: un contenedor en UTC que rodara de mes a las 19:00 de
    Lima partiría el gasto de un día entre dos meses.
    """
    repo = LlmSpendRepository(session)
    await repo.anotar(
        fila(  # 31/08 21:00 Lima
            created_at=datetime(2026, 9, 1, 2, 0, tzinfo=timezone.utc),
            cost_usd=Decimal("1.000000"),
        )
    )
    await repo.anotar(
        fila(  # 01/09 00:30 Lima — ya es septiembre
            created_at=datetime(2026, 9, 1, 5, 30, tzinfo=timezone.utc),
            cost_usd=Decimal("7.000000"),
        )
    )

    ago_desde, ago_hasta = limites_del_mes(
        datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    )
    agosto = await repo.totales(desde=ago_desde, hasta=ago_hasta, job_id=None)
    assert agosto.mes_usd == Decimal("1.000000")

    sep_desde, sep_hasta = limites_del_mes(
        datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    )
    septiembre = await repo.totales(desde=sep_desde, hasta=sep_hasta, job_id=None)
    assert septiembre.mes_usd == Decimal("7.000000")


async def test_un_job_que_cruza_el_corte_de_mes_sigue_contando_entero(session):
    """Una corrida puede empezar el 31 a las 23:50 y acabar el 1 a las 00:10. Su
    freno tiene que ver las dos mitades o dejaría de frenar a medianoche."""
    repo = LlmSpendRepository(session)
    job = await _job(session)
    await repo.anotar(
        fila(
            job_id=job,
            created_at=datetime(2026, 9, 1, 4, 50, tzinfo=timezone.utc),
            cost_usd=Decimal("2.000000"),
        )
    )
    await repo.anotar(
        fila(
            job_id=job,
            created_at=datetime(2026, 9, 1, 5, 10, tzinfo=timezone.utc),
            cost_usd=Decimal("3.000000"),
        )
    )
    desde, hasta = limites_del_mes(datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc))
    totales = await repo.totales(desde=desde, hasta=hasta, job_id=job)
    assert totales.job_usd == Decimal("5.000000")
    assert totales.mes_usd == Decimal("3.000000")  # solo la mitad de septiembre


# ---------------------------------------------------------------------------
# GAS-D9 — metrics.real, un solo sitio para los seis agentes y para FAILED
# ---------------------------------------------------------------------------


async def test_un_job_sin_llamadas_no_recibe_un_bloque_de_ceros(session):
    """Un job sin filas NO es un job de costo cero (mismo criterio que GAS-D4 con
    el ``usage``): escribir ceros ocultaría "no gastó" detrás de "no se midió"."""
    repo = AgentJobRepository(session)
    job = await repo.create_job(AgentType.EF)
    actualizado = await repo.update_job_metrics(job.id, {"cost": 0.1})
    assert "real" not in actualizado.metrics


async def test_metrics_real_aparece_en_un_job_COMPLETED_con_su_ratio(session):
    jobs = AgentJobRepository(session)
    gasto = LlmSpendRepository(session)
    job = await jobs.create_job(AgentType.EF)

    await gasto.anotar(
        fila(
            job_id=job.id,
            input_tokens=7000,
            output_tokens=8000,
            cost_usd=Decimal("0.141000"),
        )
    )
    await gasto.anotar(
        fila(
            job_id=job.id,
            input_tokens=7210,
            output_tokens=7980,
            cost_usd=Decimal("0.141330"),
        )
    )

    actualizado = await jobs.update_job_metrics(
        job.id, {"tokens": {"input": 5061, "output": 6133}, "cost": 0.107178}
    )
    real = actualizado.metrics["real"]
    assert real["calls"] == 2
    assert real["input_tokens"] == 14210
    assert real["output_tokens"] == 15980
    assert real["cost_usd"] == "0.282330"
    assert real["usage_source"] == "real"
    assert real["estimated_calls"] == 0
    # El 2,4-3,1x deja de ser folclore y pasa a ser una columna medida.
    assert real["ratio_sobre_estimado"] == 2.63
    # Y la estimación se CONSERVA intacta al lado, marcada como lo que es.
    assert actualizado.metrics["cost"] == 0.107178
    assert "estimada" in real["estimacion_sigue_en"]


async def test_metrics_real_aparece_TAMBIEN_en_un_job_FAILED(session):
    """H1: 6 de los 7 jobs ``FAILED`` del historial reportan 0 tokens y $0.0
    habiendo gastado. Un cuarto del historial ciego. Esto lo cierra."""
    jobs = AgentJobRepository(session)
    gasto = LlmSpendRepository(session)
    job = await jobs.create_job(AgentType.QA)
    await gasto.anotar(fila(job_id=job.id, cost_usd=Decimal("1.930000")))

    # Lo que escribe la rama `except` del runner: solo duración, sin estimación.
    actualizado = await jobs.update_job_metrics(
        job.id, {"duration": 42.5, "failed": True}
    )
    await jobs.update_job_status(job.id, JobStatus.FAILED, error="tope del job")

    assert actualizado.metrics["real"]["cost_usd"] == "1.930000"
    assert actualizado.metrics["duration"] == 42.5


async def test_el_ratio_no_revienta_cuando_la_estimacion_es_CERO(session):
    """El caso de los seis ``FAILED`` de H1: no hay estimación que comparar.
    Dividir ahí no da "infinito interesante", da una excepción."""
    jobs = AgentJobRepository(session)
    gasto = LlmSpendRepository(session)
    job = await jobs.create_job(AgentType.BD)
    await gasto.anotar(fila(job_id=job.id, cost_usd=Decimal("0.500000")))

    actualizado = await jobs.update_job_metrics(job.id, {"duration": 3.0})
    assert actualizado.metrics["real"]["ratio_sobre_estimado"] is None
    assert actualizado.metrics["real"]["cost_usd"] == "0.500000"


async def test_una_sola_fila_estimada_vuelve_MIXTO_el_total_del_job(session):
    """La honestidad de GAS-D4 tiene que verse en el mismo sitio donde se lee la
    cifra, no solo en el diseño."""
    jobs = AgentJobRepository(session)
    gasto = LlmSpendRepository(session)
    job = await jobs.create_job(AgentType.API)
    await gasto.anotar(fila(job_id=job.id))
    await gasto.anotar(fila(job_id=job.id, usage_source="estimado"))

    real = (await jobs.update_job_metrics(job.id, {"cost": 0.02})).metrics["real"]
    assert real["usage_source"] == "mixto"
    assert real["estimated_calls"] == 1


async def test_borrar_un_job_no_cambia_el_total_del_mes(session):
    """``ON DELETE SET NULL``: el total del mes no puede moverse porque alguien
    borró un job, y la fila conserva su ``agent_role``."""
    from sqlalchemy import select

    from app.models.spend import LlmSpend

    jobs = AgentJobRepository(session)
    gasto = LlmSpendRepository(session)
    job = await jobs.create_job(AgentType.SCRUM)
    await gasto.anotar(
        fila(job_id=job.id, agent_role="scrum", cost_usd=Decimal("4.000000"))
    )
    await session.flush()

    desde, hasta = limites_del_mes()
    antes = (await gasto.totales(desde=desde, hasta=hasta, job_id=None)).mes_usd

    # SQLite no aplica FK por defecto: se simula el efecto del `SET NULL`, que es
    # lo que este test comprueba (el importe sobrevive al huérfano).
    huerfana = (await session.execute(select(LlmSpend))).scalars().one()
    huerfana.job_id = None
    await session.flush()

    despues = (await gasto.totales(desde=desde, hasta=hasta, job_id=None)).mes_usd
    assert despues == antes == Decimal("4.000000")
    assert huerfana.agent_role == "scrum"
