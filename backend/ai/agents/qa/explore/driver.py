"""La costura con el navegador — y, desde QC5, el navegador de verdad.

QC3 construyó la valla antes que el animal: este fichero era un contrato vacío y
un ``build_driver`` que fallaba diciendo que el driver llegaría aquí. Llegó. Lo
que **no** cambia, porque era el motivo de construirlo en ese orden:

1. El cortafuegos de tests parchea :func:`build_driver`, así que un test que
   intente arrancar un navegador falla con un mensaje que dice cómo arreglarlo —
   en vez de salir a la red. Hace falta porque la capa 4 de LLM1 parchea
   ``socket.socket.connect`` **en este proceso**, y el navegador es otro: sus
   sockets no pasan por ese parche. Es la única capa que existe para ese riesgo, y
   ahora que Playwright está instalado es **más** necesaria, no menos.
2. ``ExploreSession`` recibe el driver **inyectado**, de modo que la suite ejerce
   el Modo C entero sin navegador, sin servidor local y sin red.
3. El protocolo sigue siendo **estrecho a propósito**: ``goto``, ``click``,
   ``close``. No hay ``fill``, ni ``type``, ni ``screenshot``, ni ``evaluate``. Un
   nodo no tiene acceso al objeto con el que se podría escribir porque el objeto
   no lo ofrece, y el candado AST lo impide.

**La política no vive aquí.** Este módulo es una cáscara: pregunta a
``network.evaluar_peticion`` y obedece. Es lo que permite ejercer la capa 3 entera
contra HTML de fixtures, y lo que deja este fichero con la única parte que de
verdad necesita un navegador para probarse — que es la que **no** se prueba en la
suite (criterio 7: ninguna exploración real, ni siquiera una vez).

**El import de Playwright vive dentro de las funciones**, no en la cabecera. No es
estilo: es la REGLA R1 al revés. Un import a nivel de módulo resolvería
``async_playwright`` al importar y el parche del cortafuegos —que sustituye el
atributo del módulo— no alcanzaría a ese enlace ya resuelto. Dentro de la función
se resuelve en cada llamada, y el cortafuegos lo ve.
"""

from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

from ai.agents.qa.explore.network import preparar_contexto
from ai.agents.qa.explore.target import ExploreTarget, redact_url
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

    ``status=0`` con ``motivo_bloqueo`` es la forma en que el navegador dice **"me
    negué"**: la capa 3 abortó la petición. Se distingue de un fallo mudo a
    propósito — un explorador que registra "algo pasó" produce una cobertura que
    nadie puede auditar.
    """

    status: int
    url: str
    html: str = ""
    location: Optional[str] = None
    motivo_bloqueo: Optional[str] = None


@runtime_checkable
class BrowserDriver(Protocol):
    """Lo único que ``ExploreSession`` puede pedirle a un navegador."""

    async def goto(self, url: str, *, timeout_ms: int) -> RespuestaNavegacion:
        """Navega y devuelve el estado, la URL final y el HTML."""

    async def click(self, selector: str, *, timeout_ms: int) -> RespuestaNavegacion:
        """Pulsa un elemento ya autorizado por la política y devuelve el DOM."""

    async def close(self) -> None:
        """Cierra el contexto."""


class PlaywrightDriver:
    """Chromium headless, encerrado por la capa 3 antes de la primera navegación.

    **Se construye sin arrancar nada.** El navegador se lanza en la primera
    navegación de verdad, por el mismo motivo por el que ``ExploreSession`` crea el
    driver tarde: un job que muere en una validación previa no debe haber dejado un
    proceso de Chromium levantado.
    """

    def __init__(
        self,
        *,
        target: ExploreTarget,
        timeout_ms: int,
        storage_state: Optional[str] = None,
    ) -> None:
        self._target = target
        self._timeout_ms = timeout_ms
        self._storage_state = storage_state
        self._playwright: Any = None
        self._navegador: Any = None
        self._pagina: Any = None

    async def goto(self, url: str, *, timeout_ms: int) -> RespuestaNavegacion:
        pagina = await self._asegurar_pagina()
        try:
            respuesta = await pagina.goto(
                url, timeout=timeout_ms, wait_until="domcontentloaded"
            )
        except Exception as exc:  # el navegador se negó: capa 3 o capa 5
            return self._negado(pagina, url, exc)
        return await self._observar(pagina, respuesta, url)

    async def click(self, selector: str, *, timeout_ms: int) -> RespuestaNavegacion:
        pagina = await self._asegurar_pagina()
        try:
            # Único ``click`` del driver, y solo lo llama
            # ``ExploreSession.pulsar_si_procede``, que ya aplicó la lista blanca
            # del nivel 1 sobre el DOM. Aquí no se decide nada: se ejecuta.
            await pagina.click(selector, timeout=timeout_ms)
        except Exception as exc:
            return self._negado(pagina, pagina.url, exc)
        return await self._observar(pagina, None, pagina.url)

    async def close(self) -> None:
        """Cierra en orden inverso y **sin tapar el primer fallo con el segundo**."""
        for recurso in (self._navegador, self._playwright):
            if recurso is None:
                continue
            cerrar = getattr(recurso, "close", None) or getattr(recurso, "stop", None)
            if cerrar is not None:
                await cerrar()
        self._navegador = None
        self._playwright = None
        self._pagina = None

    # --- interno --------------------------------------------------------------

    async def _asegurar_pagina(self) -> Any:
        """Arranca Chromium y le pone la jaula ANTES de que exista una página."""
        if self._pagina is not None:
            return self._pagina

        # Import dentro de la función: ver la nota de R1 en el docstring del módulo.
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._navegador = await self._playwright.chromium.launch(headless=True)
        contexto = await self._navegador.new_context(
            storage_state=self._storage_state or None,
            accept_downloads=False,
            permissions=[],
        )
        contexto.set_default_timeout(self._timeout_ms)
        # La capa 3 se instala sobre el CONTEXTO, no sobre la página: así cubre
        # también a las páginas que la aplicación abra por su cuenta.
        await preparar_contexto(contexto, self._target)
        self._pagina = await contexto.new_page()
        return self._pagina

    async def _observar(
        self, pagina: Any, respuesta: Any, pedida: str
    ) -> RespuestaNavegacion:
        """Lee lo que se ve. ``content()`` es lo único que se le pide al DOM."""
        return RespuestaNavegacion(
            status=int(getattr(respuesta, "status", 0) or 200),
            url=pagina.url or pedida,
            html=await pagina.content(),
        )

    def _negado(self, pagina: Any, pedida: str, exc: Exception) -> RespuestaNavegacion:
        """Traduce la negativa del navegador a una respuesta que se puede registrar.

        El mensaje del navegador se **redacta**: lleva la URL completa, y una URL
        completa puede llevar la credencial de la cuenta de QA (capa 4).
        """
        return RespuestaNavegacion(
            status=0,
            url=getattr(pagina, "url", "") or pedida,
            motivo_bloqueo=(
                "El navegador no completó la petición (capa 3: solo lectura / "
                f"capa 5: fuera de la jaula): {redact_url(str(exc)).splitlines()[0]}"
            ),
        )


def build_driver(
    *,
    target: ExploreTarget,
    timeout_ms: int,
    storage_state: Optional[str] = None,
) -> BrowserDriver:
    """Construye el driver real. **Fail-closed si no hay navegador que construir.**

    Sigue sin devolver un doble silencioso cuando no puede: un driver de mentira
    en producción exploraría cero páginas y el artefacto diría "no se observó
    nada", que es indistinguible de una aplicación vacía.

    Recibe el ``target`` porque la jaula la instala el driver sobre el contexto, y
    un driver sin destino no tendría contra qué revalidar: la capa 3 no es un
    parámetro opcional que alguien pueda olvidar pasar.
    """
    try:
        import playwright.async_api  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise DriverNoDisponibleError(
            "No hay navegador instalado: falta el paquete «playwright» "
            f"({exc}). Está pinneado en requirements.txt junto con la revisión de "
            "Chromium que le corresponde."
        ) from exc

    return PlaywrightDriver(
        target=target, timeout_ms=timeout_ms, storage_state=storage_state
    )
