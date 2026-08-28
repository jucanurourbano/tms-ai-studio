"""Proveedor **Anthropic**: cliente, política de reintentos y tarifa.

Es el proveedor de **producción** y el único registrado. Todo lo que había
disperso entre ``app/dependencies/claude.py`` (constructor, ``_RETRYABLE``,
``retry_after_seconds``, ``estimate_cost``) y ``ai/agents/base/structured.py``
(el adaptador ``ClaudeLLMClient``) vive ahora aquí, junto, y **con el mismo
comportamiento byte a byte**: este bloque es un refactor, no un cambio.

REGLA DE PRESUPUESTO: no se llama a la API real sin autorización explícita. En
desarrollo y tests siempre se usan mocks (ver CLAUDE.md).
"""

from typing import Optional

from anthropic import APIConnectionError, InternalServerError, RateLimitError

from ai.agents.base.structured import message_text
from ai.llm.base import DataClass, ProviderSpec
from ai.llm.metering import Completion, usage_desde_mensaje
from ai.llm.pricing import compute_cost
from ai.llm.retry import call_with_retry
from app.config.settings import settings

# Excepciones a reintentar: rate limit, error de servidor, error de conexión.
# La tupla se conserva **idéntica**; lo que cambia es que ya no la lee un módulo
# genérico, sino el ``ProviderSpec`` de este proveedor (ver ``ai/llm/retry.py``).
_RETRYABLE = (RateLimitError, InternalServerError, APIConnectionError)


def default_model() -> str:
    """Modelo por defecto del proveedor, leído de ``settings`` al usarlo."""
    return settings.CLAUDE_MODEL


def build_chat_model(**overrides):
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


def is_retryable(exc: BaseException) -> bool:
    """¿Merece reintento? Misma respuesta que la tupla ``_RETRYABLE`` de siempre."""
    return isinstance(exc, _RETRYABLE)


def price_per_mtok(_model: str) -> tuple[float, float]:
    """Tarifa ``(entrada, salida)`` USD/MTok. Hoy una sola por proveedor.

    El modelo se recibe y se ignora a propósito: la firma es la del contrato de
    ``ProviderSpec`` y el día que Anthropic tenga dos modelos en uso, la tabla se
    abre aquí sin tocar a quien llama.
    """
    return (
        settings.CLAUDE_PRICE_INPUT_PER_MTOK,
        settings.CLAUDE_PRICE_OUTPUT_PER_MTOK,
    )


class AnthropicLLMClient:
    """Implementación real de ``LLMClient`` sobre ChatAnthropic (import perezoso).

    No se usa en tests (REGLA DE PRESUPUESTO): allí se inyecta un mock.
    """

    provider = "anthropic"

    def __init__(
        self,
        client=None,
        *,
        model: Optional[str] = None,
        data_class: Optional[DataClass] = None,
    ) -> None:
        self._client = client
        self._model = model
        # Se guarda para que el cliente pueda re-verificar la política en cada
        # llamada cuando exista un proveedor que no sea éste (LLM2). Anthropic es
        # el proveedor de producción: acepta cualquier clase de dato.
        self.data_class = data_class

    @property
    def model(self) -> str:
        """Modelo efectivo de este cliente (para tarifa y sello de procedencia)."""
        return self._model or default_model()

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Costo en USD de esta llamada, con la tarifa de ESTE proveedor."""
        return compute_cost(input_tokens, output_tokens, price_per_mtok(self.model))

    async def complete(self, *, system: str, user: str) -> Completion:
        """Protocolo INTERNO (GAS-D2): el texto **y** el consumo de la llamada.

        ``AIMessage.usage_metadata`` estaba ahí desde siempre y se tiraba a la
        basura una línea después de recibirlo, que es la razón por la que el
        costo del proyecto era una estimación (``len // 4``) subcontando entre
        2,4x y 3,1x. Leerlo cuesta exactamente esto.
        """
        # El cliente se resuelve a través de ``app.dependencies.claude`` a
        # propósito: ese símbolo es la costura que parchea el cortafuegos de
        # tests (REGLA DE PRESUPUESTO). Saltársela dejaría la suite sin
        # protección; LLM1 generaliza el cortafuegos a la fábrica y a la red.
        from app.dependencies.claude import get_claude_client

        overrides = {"model": self._model} if self._model else {}
        client = self._client or get_claude_client(**overrides)

        async def _call() -> Completion:
            msg = await client.ainvoke([("system", system), ("user", user)])
            # ``content`` puede ser string o lista de bloques (thinking+text) en
            # langchain-anthropic 1.x: extraer SIEMPRE el texto, nunca str(lista).
            return Completion(
                text=message_text(msg.content), usage=usage_desde_mensaje(msg)
            )

        return await call_with_retry(_call, spec=SPEC)

    async def complete_json(self, *, system: str, user: str) -> str:
        """La cara pública, intacta: los ~30 nodos generativos siguen viendo esto.

        Quien pase por la fábrica recibe este cliente envuelto en
        ``MeteredLLMClient``, que es quien comprueba el tope y anota la fila. Este
        método sigue existiendo para quien construya el proveedor a mano —los
        tests que le inyectan un chat falso— y para no cambiar el protocolo.
        """
        return (await self.complete(system=system, user=user)).text


def _build_client(*, model: str, data_class: DataClass) -> AnthropicLLMClient:
    """Constructor que usa la fábrica (firma común a todos los proveedores)."""
    return AnthropicLLMClient(model=model, data_class=data_class)


SPEC = ProviderSpec(
    name="anthropic",
    default_model=default_model,
    build_client=_build_client,
    is_retryable=is_retryable,
    wait_hint=retry_after_seconds,
    price_per_mtok=price_per_mtok,
)
