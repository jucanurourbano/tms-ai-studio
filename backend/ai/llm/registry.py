"""Registro de proveedores disponibles.

Un dict, no una cadena de ``if``: añadir un proveedor es registrar un
``ProviderSpec`` y nada más. El cortafuegos de tests (LLM1) se parametriza sobre
este mismo dict, de modo que registrar un proveedor **sin** cortafuegos rompa la
suite en vez de abrir un camino a la red que nadie mira.
"""

from ai.llm.base import DEFAULT_PROVIDER, ProviderConfigError, ProviderSpec
from ai.llm.providers import anthropic as _anthropic

PROVIDERS: dict[str, ProviderSpec] = {
    _anthropic.SPEC.name: _anthropic.SPEC,
}


def get_spec(name: str) -> ProviderSpec:
    """Devuelve el ``ProviderSpec`` de ``name`` o falla explicando qué hay.

    No cae de vuelta al default: un nombre mal escrito en el ``.env`` que
    resolviera silenciosamente a Anthropic sería un ``.env`` que miente sobre lo
    que el sistema está haciendo.
    """
    spec = PROVIDERS.get(name)
    if spec is None:
        disponibles = ", ".join(sorted(PROVIDERS)) or "(ninguno)"
        raise ProviderConfigError(
            f"Proveedor de LLM desconocido: '{name}'. Registrados: {disponibles}."
        )
    return spec


__all__ = ["DEFAULT_PROVIDER", "PROVIDERS", "get_spec"]
