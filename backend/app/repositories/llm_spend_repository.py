"""Repositorio del libro mayor de gasto (capa repositories).

Dos operaciones y una consulta cada una. El freno hace **una** lectura por
llamada al modelo, y eso está elegido a conciencia frente a un acumulador en
memoria: una llamada al modelo tarda entre 5 y 60 segundos, una consulta indexada
de 1 ms es gratis, y un contador dentro del cliente **subcontaría** el job — el
EF construye dos clientes por corrida (``llm`` y ``critique_llm``), justamente en
el agente cuyo ``CRITIQUE`` no tiene techo de entrada.

Ver ``docs/diseno-control-de-gasto.md`` §5 y §6.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Integer, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm.budget import SpendRow, Totales
from app.models.spend import LlmSpend

CERO = Decimal("0")


def _a_decimal(valor) -> Decimal:
    """Normaliza a ``Decimal``.

    Postgres devuelve ``Decimal`` para ``NUMERIC``; SQLite —el motor de la
    suite— devuelve ``float``. Se normaliza aquí y no en quien llama para que la
    comparación contra el tope sea del mismo tipo en los dos motores.
    """
    if valor is None:
        return CERO
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


class LlmSpendRepository:
    """Anota llamadas y suma lo gastado en las dos ventanas que deciden."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def anotar(self, fila: SpendRow) -> LlmSpend:
        """Escribe una fila del libro mayor.

        ``created_at`` se fija en UTC desde Python (ver ``app/models/spend.py``):
        el corte del mes se calcula en ``LLM_BUDGET_TZ`` comparando instantes
        UTC, y en SQLite una fecha con offset se guarda perdiéndolo.
        """
        registro = LlmSpend(
            job_id=fila.job_id,
            agent_role=fila.agent_role,
            stage=fila.stage,
            provider=fila.provider,
            model=fila.model,
            usage_source=fila.usage_source,
            input_tokens=fila.input_tokens,
            output_tokens=fila.output_tokens,
            cache_read_tokens=fila.cache_read_tokens,
            cache_write_tokens=fila.cache_write_tokens,
            reasoning_tokens=fila.reasoning_tokens,
            cost_usd=fila.cost_usd,
            duration_ms=fila.duration_ms,
            created_at=(fila.created_at or datetime.now(timezone.utc)).astimezone(
                timezone.utc
            ),
        )
        self.session.add(registro)
        await self.session.flush()
        return registro

    async def totales(
        self, *, desde: datetime, hasta: datetime, job_id: Optional[str]
    ) -> Totales:
        """Gastado en el mes y gastado por el job, en **una** consulta.

        El ``WHERE`` acota a las filas que pueden aportar a cualquiera de los dos
        totales (mes **o** job) para no recorrer el libro mayor entero en cada
        llamada; los dos índices —``created_at`` y ``job_id``— lo sostienen. Se
        incluye el job aunque caiga fuera del mes porque una corrida puede cruzar
        el corte de medianoche del último día.
        """
        en_el_mes = and_(LlmSpend.created_at >= desde, LlmSpend.created_at < hasta)
        del_job = LlmSpend.job_id == job_id

        consulta = select(
            func.coalesce(func.sum(case((en_el_mes, LlmSpend.cost_usd), else_=0)), 0),
            func.coalesce(func.sum(case((del_job, LlmSpend.cost_usd), else_=0)), 0),
        )
        consulta = consulta.where(or_(en_el_mes, del_job) if job_id else en_el_mes)

        fila = (await self.session.execute(consulta)).one()
        return Totales(
            mes_usd=_a_decimal(fila[0]),
            job_usd=_a_decimal(fila[1]) if job_id else CERO,
        )

    async def resumen_del_job(self, job_id: str) -> Optional[dict]:
        """Lo que el libro mayor sabe de un job, para ``metrics.real`` (GAS-D9).

        Devuelve ``None`` si el job no tiene ni una llamada anotada: un job sin
        filas **no es** un job de costo cero (mismo criterio que GAS-D4 con el
        ``usage``), y escribir un bloque de ceros ocultaría la diferencia entre
        "no gastó" y "no se midió".
        """
        estimadas = case((LlmSpend.usage_source == "estimado", 1), else_=0)
        consulta = select(
            func.count(LlmSpend.id),
            func.coalesce(func.sum(LlmSpend.input_tokens), 0),
            func.coalesce(func.sum(LlmSpend.output_tokens), 0),
            func.coalesce(func.sum(LlmSpend.cost_usd), 0),
            func.coalesce(func.sum(estimadas), 0).cast(Integer),
            func.coalesce(func.sum(LlmSpend.cache_read_tokens), 0),
            func.coalesce(func.sum(LlmSpend.cache_write_tokens), 0),
            func.coalesce(func.sum(LlmSpend.reasoning_tokens), 0),
        ).where(LlmSpend.job_id == job_id)

        fila = (await self.session.execute(consulta)).one()
        llamadas = int(fila[0] or 0)
        if llamadas == 0:
            return None

        estimadas_n = int(fila[4] or 0)
        return {
            "calls": llamadas,
            "input_tokens": int(fila[1] or 0),
            "output_tokens": int(fila[2] or 0),
            "cost_usd": f"{_a_decimal(fila[3]):.6f}",
            "estimated_calls": estimadas_n,
            # `usage_source` del job: "real" solo si TODAS lo son. Una sola fila
            # estimada hace que el total del job sea aproximado, y eso tiene que
            # verse en el mismo sitio donde se lee la cifra.
            "usage_source": "real" if estimadas_n == 0 else "mixto",
            "cache_read_tokens": int(fila[5] or 0),
            "cache_write_tokens": int(fila[6] or 0),
            "reasoning_tokens": int(fila[7] or 0),
        }
