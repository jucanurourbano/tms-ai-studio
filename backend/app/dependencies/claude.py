"""Compatibilidad del proveedor Anthropic — la implementación vive en ``ai/llm``.

Todo lo que había aquí (constructor del cliente, ``_RETRYABLE``,
``retry_after_seconds``, ``estimate_cost``) se movió a
``ai/llm/providers/anthropic.py``, donde puede convivir con la política de otros
proveedores sin que la de Anthropic se cuele en ellos. Este módulo sobrevive por
dos razones concretas, no por inercia:

1. **``get_claude_client`` es la costura del cortafuegos de tests.**
   ``tests/conftest.py`` parchea este símbolo por su ruta de importación para que
   ningún test alcance la API real (REGLA DE PRESUPUESTO). LLM1 generaliza esa
   protección a la fábrica y a la red; hasta entonces, mover la costura sería
   quedarse sin ella.
2. **``estimate_cost(in, out)``** lo importan los seis ``assemble.py``. Aquí
   mantiene su firma de siempre y delega en la tarifa del proveedor; pasa a ser
   por proveedor —con su procedencia— en LLM4.

REGLA DE PRESUPUESTO: no se llama a la API real sin autorización explícita.
En desarrollo y tests siempre se usan mocks (ver CLAUDE.md).
"""

from typing import Awaitable, Callable, Optional, TypeVar

from ai.llm.base import DEFAULT_PROVIDER
from ai.llm.pricing import estimate_cost as _estimate_cost
from ai.llm.providers.anthropic import _RETRYABLE
from ai.llm.providers.anthropic import SPEC as _SPEC
from ai.llm.providers.anthropic import build_chat_model
from ai.llm.providers.anthropic import retry_after_seconds as _retry_after_seconds
from ai.llm.retry import call_with_retry as _call_with_retry

T = TypeVar("T")

# Reexportado: los tests lo usan como candado de que la política de Anthropic no
# cambió al generalizarse (``ai/llm/providers/anthropic.py`` es la fuente).
__all__ = [
    "_RETRYABLE",
    "call_with_retry",
    "estimate_cost",
    "get_claude_client",
    "retry_after_seconds",
]


def get_claude_client(**overrides):
    """Construye el cliente ChatAnthropic con parámetros desde settings.

    Se mantiene como función propia (y no como alias importado) porque es el
    punto que parchea el cortafuegos de tests: sustituir este nombre tiene que
    seguir bastando para dejar a la suite sin acceso a la API real.
    """
    return build_chat_model(**overrides)


def retry_after_seconds(exc: BaseException) -> Optional[float]:
    """Extrae el header ``retry-after`` de una excepción de Anthropic, si existe."""
    return _retry_after_seconds(exc)


async def call_with_retry(
    coro_factory: Callable[[], Awaitable[T]], *, max_attempts: int = 5
) -> T:
    """Ejecuta ``coro_factory`` con la política de reintentos de Anthropic."""
    return await _call_with_retry(coro_factory, spec=_SPEC, max_attempts=max_attempts)


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Costo en USD según la tarifa de Anthropic (``CLAUDE_PRICE_*``)."""
    return _estimate_cost(input_tokens, output_tokens, provider=DEFAULT_PROVIDER)
