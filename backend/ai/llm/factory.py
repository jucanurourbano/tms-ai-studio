"""Fábrica de clientes LLM: la única puerta por la que se instancia un proveedor.

Antes de este paquete había **14 construcciones** del cliente repartidas por
servicios y nodos, más una que se saltaba incluso el runner
(``app/api/v1/inventario.py``, la ingesta de documentos reales). Cada una era un
sitio donde una política nueva podía no aplicarse. Ahora todas pasan por aquí.

**Resolución del proveedor**, de mayor a menor precedencia:

1. ``LLM_ROLE_OVERRIDES[agent_role]`` — "todo Anthropic menos el nodo que estoy
   depurando", que es el caso real de un banco de pruebas;
2. ``LLM_PROVIDER`` — el global;
3. ``anthropic`` — fail-safe: **el default nunca es un proveedor de pruebas**.

``agent_role`` se pasa **explícitamente** desde cada sitio (una cadena del enum
``AgentType`` más ``"inventory_doc"`` para la ingesta INV3). No se infiere del
stack ni de un ``contextvar``: un valor por defecto invisible es exactamente lo
que hace que un guardarraíl no se dispare.

``data_class`` es **keyword-only y sin default** (LLM-D9). Omitirlo es un
``TypeError`` en el arranque del job —ruidoso, inmediato, imposible de ignorar—
y no una fuga silenciosa. Con un solo proveedor registrado el valor todavía no
decide nada; la política que lo usa llega en LLM2, y la firma se pone hoy para
que ese bloque no tenga que volver a tocar los 15 sitios que llaman.
"""

from ai.llm.base import (
    DATA_CLASSES,
    DEFAULT_PROVIDER,
    DataClass,
    LLMClient,
    ProviderConfigError,
)
from ai.llm.registry import get_spec
from app.config.settings import settings


def resolve_provider(agent_role: str) -> str:
    """Nombre del proveedor que corresponde a ``agent_role`` (ver precedencia)."""
    overrides = settings.LLM_ROLE_OVERRIDES or {}
    nombre = overrides.get(agent_role) or settings.LLM_PROVIDER or DEFAULT_PROVIDER
    get_spec(nombre)  # falla cerrada si el nombre no está registrado
    return nombre


def resolve_model(provider: str) -> str:
    """Modelo efectivo del proveedor: override por proveedor o su default.

    El modelo se elige **por proveedor y no por rol** (LLM-D3): elegir modelo por
    rol es una decisión de calidad/costo de producción, y la producción es
    Anthropic con un solo modelo.
    """
    override = (settings.LLM_MODEL_OVERRIDES or {}).get(provider)
    return override or get_spec(provider).default_model()


def get_llm(agent_role: str, *, data_class: DataClass) -> LLMClient:
    """Devuelve el ``LLMClient`` del proveedor que corresponda a ``agent_role``.

    Devuelve un cliente **completo** (con su política de reintentos y su tarifa
    dentro), nunca el cliente crudo del SDK: ver ``ai/llm/base.py``.
    """
    if data_class not in DATA_CLASSES:
        validas = ", ".join(DATA_CLASSES)
        raise ProviderConfigError(
            f"data_class inválida: '{data_class}'. Valores admitidos: {validas}."
        )
    provider = resolve_provider(agent_role)
    spec = get_spec(provider)
    return spec.build_client(model=resolve_model(provider), data_class=data_class)
