"""Política de reintentos **por proveedor**.

Antes de este paquete la política era una tupla de excepciones importadas de
``anthropic``. Ese era el punto más peligroso del acoplamiento: con otro
proveedor esas excepciones no se lanzan **nunca**, así que ``call_with_retry``
dejaría de reintentar en silencio. Aquí la decisión la toma el ``ProviderSpec``
(``is_retryable`` / ``wait_hint``), no una tupla de un SDK concreto.

Para Anthropic el comportamiento es **idéntico al anterior**, y así lo fija un
test candado (``tests/llm/test_anthropic_policy.py``).
"""

from typing import Awaitable, Callable, TypeVar

from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt

from ai.llm.base import ProviderSpec

T = TypeVar("T")


def wait_strategy(spec: ProviderSpec) -> Callable[..., float]:
    """Espera respetando la pista del proveedor; si no hay, backoff exponencial."""

    def _wait(retry_state) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if exc is not None:
            hint = spec.wait_hint(exc)
            if hint is not None:
                return hint
        return min(2.0**retry_state.attempt_number, 30.0)

    return _wait


async def call_with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    spec: ProviderSpec,
    max_attempts: int = 5,
) -> T:
    """Ejecuta ``coro_factory`` con la política de reintentos de ``spec``."""
    async for attempt in AsyncRetrying(
        retry=retry_if_exception(spec.is_retryable),
        stop=stop_after_attempt(max_attempts),
        wait=wait_strategy(spec),
        reraise=True,
    ):
        with attempt:
            return await coro_factory()
    raise RuntimeError("call_with_retry: sin intentos")  # pragma: no cover
