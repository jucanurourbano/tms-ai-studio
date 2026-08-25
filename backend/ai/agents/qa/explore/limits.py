"""Topes de la exploración: enteros positivos **validados**, nunca "sin límite".

Un crawler sin techo contra una aplicación viva es un generador de carga. Y hay
un segundo motivo, de alcance y no de cortesía (QA-D25.4): el Modo C **observa
para derivar casos**; el futuro Agente Testing **ejecuta** casos, y un ejecutor
necesita corridas repetidas y sin techo. Que ``0`` sea **inválido** y no
"infinito" es uno de los cuatro impedimentos en código para que el Modo C no se
deslice hacia ese papel: no puede pedir lo que un ejecutor necesita.

Los valores efectivos se reportan en ``target`` del artefacto (QC7): un tope que
recorta en silencio se leería como cobertura completa.
"""

from dataclasses import dataclass
from typing import Optional

from ai.errors import PipelineError
from app.config.settings import settings


@dataclass(frozen=True)
class LimitesExploracion:
    """Radio de acción efectivo de una exploración."""

    max_pages: int
    max_depth: int
    timeout_ms: int
    total_budget_s: int
    max_clicks_per_page: int

    def como_dict(self) -> dict[str, int]:
        """Forma serializable para ``target`` del artefacto y para los logs."""
        return {
            "max_pages": self.max_pages,
            "max_depth": self.max_depth,
            "timeout_ms": self.timeout_ms,
            "total_budget_s": self.total_budget_s,
            "max_clicks_per_page": self.max_clicks_per_page,
        }


def _positivo(nombre: str, valor: object) -> int:
    """Exige un entero > 0. ``0`` no significa infinito: es inválido."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise PipelineError(
            f"El tope de exploración «{nombre}» debe ser un entero positivo "
            f"(recibido: {valor!r})."
        )
    if valor <= 0:
        raise PipelineError(
            f"El tope de exploración «{nombre}» debe ser mayor que 0 (recibido: "
            f"{valor}). Un 0 NO significa «sin límite»: la exploración no admite "
            "corridas sin techo contra una aplicación viva."
        )
    return valor


def limites_efectivos(
    *,
    max_pages: Optional[int] = None,
    max_depth: Optional[int] = None,
    timeout_ms: Optional[int] = None,
    total_budget_s: Optional[int] = None,
    max_clicks_per_page: Optional[int] = None,
) -> LimitesExploracion:
    """Topes del despliegue, con la posibilidad de **bajarlos** por job.

    Lo que no se informa viene de ``settings``. Cada valor pasa por
    :func:`_positivo`, así que un ``.env`` con ``QA_EXPLORE_MAX_PAGES=0`` no abre
    una exploración infinita: rompe el arranque del job con un mensaje que lo dice.
    """
    return LimitesExploracion(
        max_pages=_positivo(
            "max_pages",
            settings.QA_EXPLORE_MAX_PAGES if max_pages is None else max_pages,
        ),
        max_depth=_positivo(
            "max_depth",
            settings.QA_EXPLORE_MAX_DEPTH if max_depth is None else max_depth,
        ),
        timeout_ms=_positivo(
            "timeout_ms",
            settings.QA_EXPLORE_TIMEOUT_MS if timeout_ms is None else timeout_ms,
        ),
        total_budget_s=_positivo(
            "total_budget_s",
            (
                settings.QA_EXPLORE_TOTAL_BUDGET_S
                if total_budget_s is None
                else total_budget_s
            ),
        ),
        max_clicks_per_page=_positivo(
            "max_clicks_per_page",
            (
                settings.QA_EXPLORE_MAX_CLICKS_PER_PAGE
                if max_clicks_per_page is None
                else max_clicks_per_page
            ),
        ),
    )
