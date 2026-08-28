"""Control de gasto: lo que se mira para no conocer el tope bloqueando (GAS2).

Solo lectura. El freno vive en ``MeteredLLMClient`` y corre antes de cada
llamada al modelo (GAS1); esto es la ventana por la que se ve lo que ese freno
esta protegiendo.

**Permiso: ``config`` READ** (hoy, ``admin``). Es dato de costo de la
organizacion. Un ``analista`` al que se le frena un job no necesita el desglose
de todo el mes: necesita saber por que se le nego el suyo, y eso ya viaja en el
mensaje del 409 y en el ``error`` del job ``FAILED``.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import AccessLevel, Module
from app.dependencies.database import get_session
from app.dependencies.permissions import require_module
from app.services.spend_report_service import resumen_mensual
from shared.responses.api_response import ApiResponse

router = APIRouter(
    prefix="/gasto",
    tags=["Control de gasto"],
    dependencies=[Depends(require_module(Module.CONFIG, AccessLevel.READ))],
)


@router.get("/mensual", summary="Gasto del mes en curso, con su desglose")
async def gasto_mensual(session: AsyncSession = Depends(get_session)) -> ApiResponse:
    """Gastado en el mes, los tres topes y el desglose por agente, nodo y job.

    El mes es de calendario en ``LLM_BUDGET_TZ`` (GAS-D8), no en la zona del
    servidor. ``usage_source`` y ``estimated_fraction`` dicen que parte de la
    cifra esta medida y que parte es una estimacion (GAS-D4): si no es
    ``"real"``, el resto de la respuesta es aproximado y lo dice ahi mismo.

    ``by_stage`` es el desglose por nodo del grafo (GAS-D10). El gasto que no
    esta atribuido a ningun nodo sale con ``stage: null``: es un hueco que se ve,
    no un cero.
    """
    return ApiResponse.ok(data=await resumen_mensual(session))
