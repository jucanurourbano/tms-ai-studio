"""El sumidero real del libro mayor y el preflight de los servicios (GAS1).

``ai/llm/`` **no importa ``app.repositories``**: la capa de proveedores no tiene
por qué crecer una dependencia hacia la persistencia, y la suite instala un doble
sin arrastrar una base de datos. La implementación con Postgres vive aquí y se
instala al arrancar (``main.py``), que es también la razón por la que el sumidero
por defecto **niega**: un despliegue que se olvide de instalarlo deja de
funcionar en vez de gastar sin medir (GAS-D7).

Ver ``docs/diseno-control-de-gasto.md`` §6.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from ai.llm import budget as _budget
from ai.llm.pricing import price_per_mtok
from app.config.settings import settings
from app.core.logger import logger
from app.errors import ConflictError


class DatabaseSpendSink:
    """Libro mayor sobre la base de datos de la plataforma.

    Cada operación abre su propia sesión: el freno corre dentro de una llamada al
    modelo, fuera del ciclo de request y con varios workers concurrentes, así que
    compartir una sesión sería compartir una transacción entre corrutinas.
    """

    async def totales(
        self, *, desde: datetime, hasta: datetime, job_id: Optional[str]
    ) -> _budget.Totales:
        from app.dependencies.database import session_scope
        from app.repositories.llm_spend_repository import LlmSpendRepository

        async with session_scope() as session:
            return await LlmSpendRepository(session).totales(
                desde=desde, hasta=hasta, job_id=job_id
            )

    async def anotar(self, fila: _budget.SpendRow) -> None:
        from app.dependencies.database import session_scope
        from app.repositories.llm_spend_repository import LlmSpendRepository

        async with session_scope() as session:
            await LlmSpendRepository(session).anotar(fila)


def install_db_sink() -> None:
    """Instala el libro mayor de verdad. Lo llama el ``lifespan`` de la app."""
    _budget.install_sink(DatabaseSpendSink())
    logger.info(
        "Control de gasto activo: tope del job %.2f USD, techo del mes %.2f USD, "
        "objetivo %.2f USD (mes de calendario en %s).",
        settings.LLM_JOB_CAP_USD,
        settings.LLM_MONTHLY_CAP_USD,
        settings.LLM_MONTHLY_TARGET_USD,
        settings.LLM_BUDGET_TZ,
    )


async def preflight_mensual() -> None:
    """Cortesía antes de encolar un job: 409 si el mes ya no da para más.

    Es **redundante** con el freno del cliente, y a propósito. Sin esto el
    usuario ve un job que arranca, corre y muere; con esto ve el mensaje antes de
    esperar. El que **garantiza** es el freno de ``MeteredLLMClient``, que corre
    antes de cada llamada; éste solo adelanta la noticia.

    Un libro mayor ilegible NO frena el preflight: quien niega en ese caso es el
    cliente, con su mensaje, y duplicar aquí el fail-closed convertiría una
    cortesía en un segundo sitio donde el arranque puede romperse por su cuenta.
    """
    from ai.llm.metering import costo_maximo_de_una_llamada

    sumidero = _budget.current_sink()
    desde, hasta = _budget.limites_del_mes()
    try:
        totales = await sumidero.totales(desde=desde, hasta=hasta, job_id=None)
    except Exception:
        return

    tope_llamada = costo_maximo_de_una_llamada(price_per_mtok())
    try:
        _budget.verificar_mes(totales.mes_usd, tope_llamada)
    except _budget.BudgetExceededError as exc:
        raise ConflictError(str(exc)) from exc


def objetivo_del_mes() -> Decimal:
    """El número que NO bloquea (GAS-D6). Se reporta; nunca frena."""
    return Decimal(str(settings.LLM_MONTHLY_TARGET_USD))


__all__ = [
    "DatabaseSpendSink",
    "install_db_sink",
    "objetivo_del_mes",
    "preflight_mensual",
]
