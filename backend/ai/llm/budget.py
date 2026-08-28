"""El freno: topes de gasto y el sumidero donde vive el libro mayor (GAS1).

Tres números y solo dos frenan (GAS-D6):

* **``LLM_JOB_CAP_USD``** — freno del job. Es el que más veces va a salvar el
  objetivo mensual: un techo de 100 USD no impide que **una sola corrida** se
  coma el mes en una tarde, y el ``CRITIQUE`` sin acotar tiene exactamente esa
  forma.
* **``LLM_MONTHLY_CAP_USD``** — el techo duro del mes.
* **``LLM_MONTHLY_TARGET_USD``** — el objetivo. **No bloquea nunca**: se reporta.
  Un objetivo que solo se manifiesta cuando el freno actúa se cumple por
  accidente.

Dos decisiones que gobiernan este módulo:

**El tope se comprueba con MARGEN, no al filo (GAS-D5).** Con concurrencia hay
varias llamadas en vuelo que leen "por debajo del tope" y lo cruzan juntas. La
alternativa era un protocolo de reserva: dos escrituras por llamada, y una fuga
cada vez que un proceso muere entre ellas. En su lugar se niega cuando
``gastado + margen > tope``, con ``margen = llamadas_en_vuelo x costo_máximo_de
una_llamada``. Así el tope duro **no se cruza nunca**; el precio es un pedazo de
techo inutilizable, y se declara en vez de descubrirse.

**Un libro mayor ilegible NIEGA la llamada (GAS-D7).** Es lo más fácil de dejar
al revés. El sumidero por defecto es ``SumideroQueNiega``: sin instalar uno de
verdad no se gasta un centavo, así que un despliegue mal configurado deja de
funcionar en vez de gastar sin medir. ``ai/llm/`` **no importa
``app.repositories``**: la implementación con base de datos vive en ``app/`` y se
instala al arrancar (``main.py``), y la suite instala un doble sin tocar nada más.

REGLA R1: ``current_sink`` se llama por su módulo (``_budget.current_sink()``),
nunca importada por nombre — ver ``tests/test_costuras_parcheables.py``.

Ver ``docs/diseno-control-de-gasto.md`` §4 y §6.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Protocol
from zoneinfo import ZoneInfo

from ai.errors import AgentError
from app.config.settings import settings

CENTIMOS = Decimal("0.000001")


class BudgetError(AgentError):
    """Base de los errores del control de gasto (409: conflicto con el estado)."""

    http_status = 409


class BudgetUnavailableError(BudgetError):
    """No se pudo leer el libro mayor, así que la llamada se niega (GAS-D7).

    Es el lado correcto del error: sin libro mayor no hay gasto. Lo contrario
    —seguir gastando cuando el instrumento está roto— es el único resultado peor
    que pararse.
    """


class BudgetExceededError(BudgetError):
    """Un tope de gasto frenó la llamada **antes** de hacerla."""


@dataclass(frozen=True)
class SpendRow:
    """Una fila del libro mayor: lo que se anota después de cada llamada."""

    agent_role: str
    provider: str
    model: str
    usage_source: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    job_id: Optional[str] = None
    stage: Optional[str] = None
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    duration_ms: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class Totales:
    """Lo gastado hasta ahora, en las dos ventanas que deciden."""

    mes_usd: Decimal
    job_usd: Decimal


class SpendSink(Protocol):
    """Dónde se apunta el gasto y de dónde se leen los totales.

    Dos operaciones y nada más. La implementación real (Postgres) vive en
    ``app/services/spend_sink.py`` y se instala en el ``lifespan``; así este
    paquete no crece una dependencia hacia la capa de persistencia.
    """

    async def totales(
        self, *, desde: datetime, hasta: datetime, job_id: Optional[str]
    ) -> Totales: ...

    async def anotar(self, fila: SpendRow) -> None: ...


class SumideroQueNiega:
    """Sumidero por defecto: no sabe cuánto se lleva gastado, así que no deja gastar."""

    def __init__(self, motivo: str = "no hay libro mayor instalado") -> None:
        self._motivo = motivo

    async def totales(
        self, *, desde: datetime, hasta: datetime, job_id: Optional[str]
    ) -> Totales:
        raise BudgetUnavailableError(
            "No se puede llamar al modelo porque no se puede leer el libro mayor "
            f"de gasto ({self._motivo}). El control de gasto es fail-closed: sin "
            "libro mayor no hay gasto. Instala el sumidero al arrancar "
            "(app.services.spend_sink.install_db_sink)."
        )

    async def anotar(self, fila: SpendRow) -> None:  # pragma: no cover - inalcanzable
        raise BudgetUnavailableError(
            "No hay libro mayor donde anotar el gasto "
            f"({self._motivo}). Esta llamada no debería haber ocurrido."
        )


_SINK: SpendSink = SumideroQueNiega()


def current_sink() -> SpendSink:
    """El sumidero instalado. Por defecto, el que niega (GAS-D7)."""
    return _SINK


def install_sink(sink: SpendSink) -> None:
    """Instala el sumidero del libro mayor (lo hace el ``lifespan`` de la app)."""
    global _SINK
    _SINK = sink


def reset_sink() -> None:
    """Vuelve al sumidero que niega. Existe para los tests del fail-closed."""
    global _SINK
    _SINK = SumideroQueNiega()


# ---------------------------------------------------------------------------
# El mes, en LLM_BUDGET_TZ y no en la del servidor (GAS-D8)
# ---------------------------------------------------------------------------


def _zona() -> ZoneInfo:
    """Lector ÚNICO de ``LLM_BUDGET_TZ``."""
    return ZoneInfo(settings.LLM_BUDGET_TZ)


def limites_del_mes(ahora: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """``[inicio, fin)`` del mes de calendario en ``LLM_BUDGET_TZ``, en UTC.

    No la zona local del servidor: un contenedor en UTC rueda de mes a las 19:00
    de Lima y partiría el gasto de un día entre dos meses.

    Residual declarado: el periodo de facturación de Anthropic no es
    necesariamente el mes calendario, así que el mes del libro mayor y el de la
    factura pueden diferir en hasta un día de gasto. Quien concilie contra la
    consola necesita saberlo.
    """
    zona = _zona()
    instante = (ahora or datetime.now(timezone.utc)).astimezone(zona)
    inicio = instante.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if inicio.month == 12:
        fin = inicio.replace(year=inicio.year + 1, month=1)
    else:
        fin = inicio.replace(month=inicio.month + 1)
    return inicio.astimezone(timezone.utc), fin.astimezone(timezone.utc)


def etiqueta_del_mes(ahora: Optional[datetime] = None) -> str:
    """``"2026-08"``: el mes al que pertenece ``ahora`` en ``LLM_BUDGET_TZ``."""
    instante = (ahora or datetime.now(timezone.utc)).astimezone(_zona())
    return f"{instante.year:04d}-{instante.month:02d}"


# ---------------------------------------------------------------------------
# Los márgenes (GAS-D5) y la verificación
# ---------------------------------------------------------------------------


def margen_del_mes(costo_maximo_llamada: Decimal) -> Decimal:
    """Reserva del techo mensual: las llamadas que pueden estar en vuelo."""
    return costo_maximo_llamada * Decimal(settings.LLM_BUDGET_HEADROOM_CALLS)


def margen_del_job(costo_maximo_llamada: Decimal) -> Decimal:
    """Reserva del freno del job: la concurrencia dentro de una corrida."""
    return costo_maximo_llamada * Decimal(settings.LLM_JOB_HEADROOM_CALLS)


def _usd(valor: Decimal) -> str:
    return f"{valor.quantize(Decimal('0.0001')):,.4f}"


def _mensaje(
    *,
    ambito: str,
    variable: str,
    tope: Decimal,
    gastado: Decimal,
    costo_maximo_llamada: Decimal,
    llamadas_en_vuelo: int,
    detalle: str,
) -> str:
    """El mensaje del freno dice cuánto llevaba y cuánto pedía lo que lo cruzó.

    Sin esas dos cifras, subir el tope es a ciegas: se sabe que frenó pero no si
    frenó por poco o por mucho, ni cuánto habría hecho falta. Con ellas, la
    decisión de subirlo es una decisión y no una corazonada.
    """
    margen = costo_maximo_llamada * Decimal(llamadas_en_vuelo)
    return (
        f"Freno de gasto: se alcanzó el tope {ambito} ({variable} = "
        f"{_usd(tope)} USD). {detalle} lleva gastados {_usd(gastado)} USD y la "
        f"llamada que lo cruzó puede costar hasta {_usd(costo_maximo_llamada)} "
        f"USD, más un margen reservado de {_usd(margen)} USD "
        f"({llamadas_en_vuelo} llamadas en vuelo x "
        f"{_usd(costo_maximo_llamada)}). Si el gasto es esperado, sube "
        f"{variable} en el entorno."
    )


def verificar_mes(gastado: Decimal, costo_maximo_llamada: Decimal) -> None:
    """Niega si el techo del mes se cruzaría contando el margen. Fail-closed."""
    tope = Decimal(str(settings.LLM_MONTHLY_CAP_USD))
    if gastado + margen_del_mes(costo_maximo_llamada) > tope:
        raise BudgetExceededError(
            _mensaje(
                ambito="del mes",
                variable="LLM_MONTHLY_CAP_USD",
                tope=tope,
                gastado=gastado,
                costo_maximo_llamada=costo_maximo_llamada,
                llamadas_en_vuelo=settings.LLM_BUDGET_HEADROOM_CALLS,
                detalle=f"El mes {etiqueta_del_mes()}",
            ),
            code="budget_monthly_cap",
        )


def verificar_job(
    gastado: Decimal, costo_maximo_llamada: Decimal, *, job_id: Optional[str]
) -> None:
    """Niega si el freno del job se cruzaría contando el margen.

    Sin ``job_id`` no hay job que frenar (la ingesta de documentos del inventario
    no tiene uno): esa llamada solo responde ante el techo del mes, y por eso su
    fila se anota igual — si no contara, el mes tendría una fuga.
    """
    if job_id is None:
        return
    tope = Decimal(str(settings.LLM_JOB_CAP_USD))
    if gastado + margen_del_job(costo_maximo_llamada) > tope:
        raise BudgetExceededError(
            _mensaje(
                ambito="del job",
                variable="LLM_JOB_CAP_USD",
                tope=tope,
                gastado=gastado,
                costo_maximo_llamada=costo_maximo_llamada,
                llamadas_en_vuelo=settings.LLM_JOB_HEADROOM_CALLS,
                detalle=f"El job {job_id}",
            ),
            code="budget_job_cap",
        )


def verificar(
    totales: Totales, costo_maximo_llamada: Decimal, *, job_id: Optional[str]
) -> None:
    """Los dos frenos, en orden: primero el del job, después el del mes.

    El del job va primero a propósito: es el que se cruza de verdad, y su mensaje
    es el útil. Que un job desbocado se anuncie como "se acabó el mes" mandaría a
    revisar el sitio equivocado.
    """
    verificar_job(totales.job_usd, costo_maximo_llamada, job_id=job_id)
    verificar_mes(totales.mes_usd, costo_maximo_llamada)


__all__ = [
    "BudgetError",
    "BudgetExceededError",
    "BudgetUnavailableError",
    "SpendRow",
    "SpendSink",
    "SumideroQueNiega",
    "Totales",
    "current_sink",
    "etiqueta_del_mes",
    "install_sink",
    "limites_del_mes",
    "margen_del_job",
    "margen_del_mes",
    "reset_sink",
    "verificar",
    "verificar_job",
    "verificar_mes",
]
