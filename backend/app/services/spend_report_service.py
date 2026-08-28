"""Lo que se mira del gasto: el mes, sus topes y su desglose (GAS2).

GAS1 puso el freno; este módulo pone la ventana. La razón es la del propio
diseño: **un tope que no se mira se conoce bloqueando**, y enterarse del techo
mensual porque un job murió a mitad de corrida es la peor forma de enterarse.

Tres cosas que este servicio hace y conviene no perder de vista:

* **Reporta el objetivo aunque no frene.** ``LLM_MONTHLY_TARGET_USD`` no bloquea
  nunca (GAS-D6); si no se publica en ningún sitio, se cumple por accidente. Es
  el número contra el que hay que comparar toda cifra —25-30 USD—, no el techo
  de 100.
* **Dice qué parte de la cifra está medida y qué parte es una estimación**
  (GAS-D4). Una respuesta que no lo diga presenta como conocido algo que se
  dedujo, y a partir de ahí el resto del desglose se lee con una confianza que
  no tiene.
* **No frena nada.** Es solo lectura: quien garantiza el tope es
  ``MeteredLLMClient``, antes de cada llamada.

Ver ``docs/diseno-control-de-gasto.md`` §7.2.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm import budget as _budget
from app.config.settings import settings
from app.models.spend import fuente_del_total
from app.repositories.llm_spend_repository import LlmSpendRepository

CERO = Decimal("0")


def _usd(valor: Decimal) -> str:
    """Dinero como cadena de seis decimales, la precision de la columna.

    Cadena y no ``float``: es el mismo criterio por el que ``cost_usd`` es
    ``NUMERIC(12,6)`` y no coma flotante. Serializar a ``float`` para el JSON
    volveria a meter el error que la columna evita, y encima en el numero que se
    compara contra un tope.
    """
    return f"{valor:.6f}"


def _pct(parte: Decimal, total: Decimal) -> Optional[float]:
    """Porcentaje, o ``None`` si el denominador es cero.

    Un tope de 0 USD es una configuracion legitima —el que quiere no gastar nada
    la usa— y ahi el porcentaje no existe. Devolver 0.0 diria "vas al 0% del
    tope" justo cuando cualquier gasto ya lo ha cruzado.
    """
    if total <= CERO:
        return None
    return round(float(parte / total) * 100, 1)


def _fraccion(parte: Decimal, total: Decimal) -> float:
    return round(float(parte / total), 4) if total > CERO else 0.0


async def resumen_mensual(
    session: AsyncSession, *, ahora: Optional[datetime] = None
) -> dict:
    """El mes en curso: gastado, topes, honestidad del dato y desglose.

    ``ahora`` es inyectable para los tests del corte de mes; en produccion se
    resuelve dentro de ``limites_del_mes``, que es el lector unico de
    ``LLM_BUDGET_TZ`` (GAS-D8).
    """
    desde, hasta = _budget.limites_del_mes(ahora)
    datos = await LlmSpendRepository(session).resumen_del_mes(desde=desde, hasta=hasta)

    gastado: Decimal = datos["spent_usd"]
    estimado: Decimal = datos["estimated_cost_usd"]
    tope = Decimal(str(settings.LLM_MONTHLY_CAP_USD))
    objetivo = Decimal(str(settings.LLM_MONTHLY_TARGET_USD))

    return {
        "month": _budget.etiqueta_del_mes(ahora),
        "timezone": settings.LLM_BUDGET_TZ,
        "period": {"from": desde.isoformat(), "to": hasta.isoformat()},
        "spent_usd": _usd(gastado),
        "target_usd": _usd(objetivo),
        "cap_usd": _usd(tope),
        "job_cap_usd": _usd(Decimal(str(settings.LLM_JOB_CAP_USD))),
        "target_pct": _pct(gastado, objetivo),
        "cap_pct": _pct(gastado, tope),
        "calls": datos["calls"],
        "input_tokens": datos["input_tokens"],
        "output_tokens": datos["output_tokens"],
        # La honestidad de GAS-D4, en tres campos que dicen lo mismo desde tres
        # angulos: cuantas llamadas se estimaron, cuanto dinero representan y
        # que clase de dato es el total. `estimated_fraction` es fraccion del
        # DINERO y no de las llamadas: la de llamadas ya es derivable de los dos
        # contadores, y una sola llamada cara estimada mueve la cifra mucho mas
        # que cien baratas.
        "estimated_calls": datos["estimated_calls"],
        "estimated_cost_usd": _usd(estimado),
        "estimated_fraction": _fraccion(estimado, gastado),
        "usage_source": fuente_del_total(datos["calls"], datos["estimated_calls"]),
        "by_agent": [_serializar(f) for f in datos["by_agent"]],
        "by_stage": [_serializar(f) for f in datos["by_stage"]],
        "top_jobs": [_serializar(f) for f in datos["top_jobs"]],
    }


def _serializar(fila: dict) -> dict:
    """Pasa el ``Decimal`` de una fila del desglose a cadena, sin tocar el resto.

    Se conserva ``stage: null`` tal cual: es el gasto que no esta atribuido a
    ningun nodo (GAS-D10), y ponerle una etiqueta aqui lo volveria un nodo mas.
    Nombrarlo es cosa de la vista.
    """
    salida = dict(fila)
    salida["cost_usd"] = _usd(fila["cost_usd"])
    return salida


__all__ = ["resumen_mensual"]
