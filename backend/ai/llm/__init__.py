"""Capa de proveedores de LLM del ISDF.

``get_llm`` es la **única puerta pública**: los agentes siguen viendo el
protocolo ``LLMClient`` (``complete_json(system, user) -> str``) y no se enteran
de qué proveedor hay debajo, ni de su política de reintentos, ni de su tarifa.

Ver ``docs/diseno-multiproveedor-llm.md``.
"""

from ai.llm.base import (
    DATA_CLASSES,
    DEFAULT_PROVIDER,
    DataClass,
    LLMClient,
    ProviderConfigError,
    ProviderError,
    ProviderSpec,
)
from ai.llm.factory import get_llm, resolve_model, resolve_provider
from ai.llm.registry import PROVIDERS, get_spec

__all__ = [
    "DATA_CLASSES",
    "DEFAULT_PROVIDER",
    "PROVIDERS",
    "DataClass",
    "LLMClient",
    "ProviderConfigError",
    "ProviderError",
    "ProviderSpec",
    "get_llm",
    "get_spec",
    "resolve_model",
    "resolve_provider",
]
