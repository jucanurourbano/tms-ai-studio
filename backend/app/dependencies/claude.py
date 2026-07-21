"""Cliente Claude (langchain-anthropic) y utilidades de reintento/costo.

REGLA DE PRESUPUESTO: no se llama a la API real sin autorización explícita.
En desarrollo y tests siempre se usan mocks (ver CLAUDE.md).
"""

from typing import Awaitable, Callable, Optional, TypeVar

from anthropic import APIConnectionError, InternalServerError, RateLimitError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
)

from app.config.settings import settings

T = TypeVar("T")

# Excepciones reintentar: rate limit, error de servidor, error de conexión.
_RETRYABLE = (RateLimitError, InternalServerError, APIConnectionError)


def get_claude_client(**overrides):
    """Construye el cliente ChatAnthropic con parámetros desde settings.

    Import perezoso de ``langchain_anthropic`` para no exigirlo al importar.
    """
    from langchain_anthropic import ChatAnthropic

    params: dict = {
        "model": settings.CLAUDE_MODEL,
        "timeout": settings.CLAUDE_TIMEOUT,
        # Explícito: evita que el default (4096, compartido con los tokens de
        # razonamiento) trunque la dimensión más grande de EXTRACT.
        "max_tokens": settings.CLAUDE_MAX_TOKENS,
        "max_retries": 0,  # el backoff lo maneja tenacity (respeta retry-after)
        "api_key": settings.ANTHROPIC_API_KEY or "placeholder-no-usada-en-dev",
    }
    params.update(overrides)
    return ChatAnthropic(**params)


def retry_after_seconds(exc: BaseException) -> Optional[float]:
    """Extrae el header ``retry-after`` de una excepción de Anthropic, si existe."""
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None)
        if headers:
            raw = headers.get("retry-after")
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    return None
    return None


def _wait(retry_state) -> float:
    """Espera respetando retry-after; si no hay, backoff exponencial con tope."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if exc is not None:
        ra = retry_after_seconds(exc)
        if ra is not None:
            return ra
    return min(2.0**retry_state.attempt_number, 30.0)


async def call_with_retry(
    coro_factory: Callable[[], Awaitable[T]], *, max_attempts: int = 5
) -> T:
    """Ejecuta ``coro_factory`` con reintentos (respetando retry-after)."""
    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(max_attempts),
        wait=_wait,
        reraise=True,
    ):
        with attempt:
            return await coro_factory()
    raise RuntimeError("call_with_retry: sin intentos")  # pragma: no cover


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Costo en USD según precios por millón de tokens de settings."""
    cost = (
        input_tokens / 1_000_000 * settings.CLAUDE_PRICE_INPUT_PER_MTOK
        + output_tokens / 1_000_000 * settings.CLAUDE_PRICE_OUTPUT_PER_MTOK
    )
    return round(cost, 6)
