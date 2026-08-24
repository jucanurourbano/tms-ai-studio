"""Contratos compartidos de la capa de proveedores de LLM.

Un proveedor **no es un modelo**: es un modelo *más* su política de reintentos,
*más* su tabla de precios (y, cuando exista más de uno, su límite de tasa y su
sello de procedencia). Por eso la fábrica devuelve un ``LLMClient`` **completo**
y nunca el cliente crudo del SDK: si devolviera el crudo, la política volvería a
escribirse en el sitio que lo envuelve —que es justo el acoplamiento que este
paquete existe para eliminar.

Ver ``docs/diseno-multiproveedor-llm.md`` (LLM-D1).
"""

from dataclasses import dataclass
from typing import Callable, Literal, Optional

# El protocolo vive donde lo importan los ~30 nodos generativos; aquí solo se
# reexporta para que la capa de proveedores no dependa del paquete de agentes
# por una cadena más larga de la necesaria.
from ai.agents.base.structured import LLMClient

# Proveedor por defecto de TODO el sistema. Es **irrenunciable**: sin ninguna
# configuración presente, el sistema usa Anthropic. El default nunca puede ser un
# proveedor de pruebas — un despliegue mal configurado tiene que degradar hacia
# el lado seguro, no hacia el barato.
DEFAULT_PROVIDER = "anthropic"

# Clasificación de la fuente que alimenta la llamada. Sin default a propósito
# (LLM-D9): olvidar clasificar debe ser un ``TypeError`` ruidoso, no una fuga
# silenciosa hacia un proveedor que no sea Anthropic.
DataClass = Literal["real", "sintetico"]
DATA_CLASSES: tuple[str, ...] = ("real", "sintetico")


class ProviderError(Exception):
    """Error de la capa de proveedores de LLM."""


class ProviderConfigError(ProviderError):
    """Configuración de proveedor/modelo inválida (falla cerrada, no adivina)."""


@dataclass(frozen=True)
class ProviderSpec:
    """Todo lo que define a un proveedor: cliente, reintentos y precio.

    ``default_model`` y ``price_per_mtok`` son **callables** y no valores: los
    lee de ``settings`` en el momento de usarlos, de modo que cambiar el modelo o
    la tarifa en el entorno surta efecto sin reimportar el módulo (y sin que un
    test que ajuste ``settings`` quede mirando una foto vieja).
    """

    name: str
    default_model: Callable[[], str]
    build_client: Callable[..., LLMClient]
    is_retryable: Callable[[BaseException], bool]
    wait_hint: Callable[[BaseException], Optional[float]]
    price_per_mtok: Callable[[str], tuple[float, float]]


__all__ = [
    "DATA_CLASSES",
    "DEFAULT_PROVIDER",
    "DataClass",
    "LLMClient",
    "ProviderConfigError",
    "ProviderError",
    "ProviderSpec",
]
