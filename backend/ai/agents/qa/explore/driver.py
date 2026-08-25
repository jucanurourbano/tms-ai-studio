"""La costura con el navegador — **hoy vacía a propósito**.

QC3 construye la valla antes del animal: aquí está el contrato que QC5 rellenará
con Playwright, y **ni una línea de Playwright** en este bloque. Que la costura
exista ya tiene tres consecuencias que no son de estilo:

1. El cortafuegos de tests parchea :func:`build_driver`, así que un test que
   intente arrancar un navegador falla con un mensaje que dice cómo arreglarlo —
   en vez de salir a la red. Hace falta porque la capa 4 de LLM1 parchea
   ``socket.socket.connect`` **en este proceso**, y el navegador es otro: sus
   sockets no pasan por ese parche. Es la única capa que existe para ese riesgo.
2. ``ExploreSession`` recibe el driver **inyectado**, de modo que la suite ejerce
   el 99% del Modo C sin navegador, sin servidor local y sin red.
3. El protocolo es **estrecho a propósito**: ``goto``, ``click``, ``close``. No hay
   ``fill``, ni ``type``, ni ``screenshot``, ni ``evaluate``. Un nodo no tiene
   acceso al objeto con el que se podría escribir porque el objeto no lo ofrece, y
   el candado AST (``tests/agents/qa/test_explore_candados.py``) impide que
   aparezca. Sobre las capturas de pantalla la razón es propia de la capa 4: una
   captura de una app autenticada es un volcado de datos reales de producción, y
   el artefacto se exporta a PDF.
"""

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from ai.errors import AgentError


class DriverNoDisponibleError(AgentError):
    """No hay navegador con el que explorar (y no se improvisa uno)."""

    http_status = 503


@dataclass(frozen=True)
class RespuestaNavegacion:
    """Lo que el navegador devuelve de una navegación o de un clic.

    ``url`` es la URL **final** (el driver puede haber seguido redirecciones por
    su cuenta) y ``location`` la cabecera de una redirección que no se siguió. Las
    dos se revalidan: ver ``ExploreSession``.
    """

    status: int
    url: str
    html: str = ""
    location: Optional[str] = None


@runtime_checkable
class BrowserDriver(Protocol):
    """Lo único que ``ExploreSession`` puede pedirle a un navegador."""

    async def goto(self, url: str, *, timeout_ms: int) -> RespuestaNavegacion:
        """Navega y devuelve el estado, la URL final y el HTML."""

    async def click(self, selector: str, *, timeout_ms: int) -> RespuestaNavegacion:
        """Pulsa un elemento ya autorizado por la política y devuelve el DOM."""

    async def close(self) -> None:
        """Cierra el contexto."""


def build_driver(
    *, timeout_ms: int, storage_state: Optional[str] = None
) -> BrowserDriver:
    """Construye el driver real. **En QC3 no hay ninguno y no se finge que sí.**

    Falla explicando la situación en vez de devolver un doble silencioso: un
    driver de mentira en producción exploraría cero páginas y el artefacto diría
    "no se observó nada", que es indistinguible de una aplicación vacía.
    """
    raise DriverNoDisponibleError(
        "No hay driver de navegador instalado: el Modo C todavía no puede "
        "explorar de verdad (QC5 lo añade sobre esta misma costura, con "
        "Playwright pinneado y la intercepción de red de la capa 3). Para ejercer "
        "la exploración hoy, inyecta un doble: ExploreSession(target, driver=…)."
    )
