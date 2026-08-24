"""Costo estimado de una llamada, **por proveedor**.

El costo dejó de ser una constante global el día que dejó de haber un solo
proveedor: reportar la tarifa de Anthropic sobre una corrida de otro proveedor no
sería una métrica imprecisa, sería una métrica **falsa**. Aquí cada proveedor
declara su tarifa en su ``ProviderSpec`` y esta capa solo hace la aritmética.

Para Anthropic los números salen de ``CLAUDE_PRICE_*`` (retrocompatible con el
``.env`` actual) y el resultado es idéntico al de antes, incluido el redondeo.
"""

from typing import Optional

from ai.llm.base import DEFAULT_PROVIDER


def compute_cost(
    input_tokens: int, output_tokens: int, prices: tuple[float, float]
) -> float:
    """Costo en USD dados los precios ``(entrada, salida)`` por millón de tokens."""
    entrada, salida = prices
    cost = input_tokens / 1_000_000 * entrada + output_tokens / 1_000_000 * salida
    return round(cost, 6)


def price_per_mtok(
    provider: str = DEFAULT_PROVIDER, model: Optional[str] = None
) -> tuple[float, float]:
    """Tarifa ``(entrada, salida)`` en USD/MTok del par proveedor+modelo."""
    # Import perezoso: el registro importa los proveedores y los proveedores
    # importan este módulo para la aritmética. Resolverlo aquí evita el ciclo sin
    # duplicar la fórmula en cada proveedor.
    from ai.llm.registry import get_spec

    spec = get_spec(provider)
    return spec.price_per_mtok(model or spec.default_model())


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    *,
    provider: str = DEFAULT_PROVIDER,
    model: Optional[str] = None,
) -> float:
    """Costo en USD de una llamada al par proveedor+modelo indicado."""
    return compute_cost(input_tokens, output_tokens, price_per_mtok(provider, model))
