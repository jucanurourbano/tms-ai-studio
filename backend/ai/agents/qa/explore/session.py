"""``ExploreSession``: la única clase del backend que conduce un navegador.

Es el primero de los cuatro mecanismos con los que la política de interacción se
hace cumplir **en código y no por convención** (§3.3 del diseño):

1. **Una sola clase dueña del contexto.** Los nodos no reciben el driver: reciben
   la sesión y llaman a :meth:`visitar`, :meth:`pulsar_si_procede` y :meth:`dom`.
   El driver se guarda con nombre mangled y ningún método lo devuelve, así que un
   nodo no tiene acceso al objeto con el que se podría escribir.
2. **Neutralización en el DOM** antes de cualquier interacción (``add_init_script``
   con el ``submit`` interceptado): llega con el driver real, en QC5.
3. **Candado por AST** sobre el código fuente: ni ``fill`` ni ``screenshot`` ni
   ``evaluate`` en ninguna parte, y ``click`` **solo** dentro de
   :meth:`pulsar_si_procede` (``tests/agents/qa/test_explore_candados.py``).
4. **Presupuesto de clics por página**, aquí. Un acordeón recursivo no convierte
   la exploración en un generador de carga.

Y la capa 5 en su forma operativa: **cada** navegación revalida esquema, host,
allowlist y origen — la de entrada, la que sigue un enlace, la que produce una
redirección y la URL final con la que vuelve el driver, por si la siguió él. Lo
que cae fuera **no se sigue y se registra**: un explorador que calla lo que no vio
produce una cobertura optimista, que es la peor clase.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from ai.agents.qa.explore import driver as _driver
from ai.agents.qa.explore.clicking import Veredicto, es_pulsable
from ai.agents.qa.explore.dom import Elemento, selector_de
from ai.agents.qa.explore.driver import BrowserDriver
from ai.agents.qa.explore.limits import LimitesExploracion, limites_efectivos
from ai.agents.qa.explore.navigation import (
    assert_navigation_allowed,
    evaluar_navegacion,
)
from ai.agents.qa.explore.target import ExploreTarget, redact_url

#: Tope de redirecciones seguidas en cadena. No es configurable: una cadena larga
#: de redirecciones dentro del mismo origen no aporta superficie nueva.
MAX_REDIRECCIONES = 5


@dataclass(frozen=True)
class PaginaObservada:
    """Una página que se llegó a ver, con su HTML y el instante de la captura.

    ``url`` viene **redactada** (sin credencial) desde el momento en que se crea:
    de aquí sale el ancla que acaba en el artefacto, el CSV y el PDF, y la
    credencial no debe poder llegar ahí ni por descuido.
    """

    url: str
    path: str
    status: int
    depth: int
    html: str
    observed_at: datetime


@dataclass(frozen=True)
class SalidaBloqueada:
    """Un destino que la capa 5 rechazó. Se registra, nunca se calla."""

    url: str
    motivo: str
    desde: Optional[str] = None


@dataclass
class _Presupuesto:
    """Contadores del radio de acción."""

    clics_por_pagina: dict[str, int] = field(default_factory=dict)
    agotado: bool = False
    motivo: Optional[str] = None
    pendientes: list[str] = field(default_factory=list)


class ExploreSession:
    """Conduce una exploración de solo lectura contra un destino autorizado."""

    def __init__(
        self,
        target: ExploreTarget,
        *,
        driver: Optional[BrowserDriver] = None,
        limites: Optional[LimitesExploracion] = None,
        reloj: Callable[[], float] = time.monotonic,
        ahora: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.target = target
        self.limites = limites or limites_efectivos()
        self._reloj = reloj
        self._ahora = ahora or (lambda: datetime.now(timezone.utc))
        # Mangled: no hay atributo ni método que devuelva el driver. Ver §3.3.1.
        self.__driver = driver
        self.__driver_propio = driver is None
        self._inicio: Optional[float] = None
        self._paginas: list[PaginaObservada] = []
        self._por_url: dict[str, PaginaObservada] = {}
        self._salidas: list[SalidaBloqueada] = []
        self._presupuesto = _Presupuesto()

    # --- lo que ven los nodos -------------------------------------------------

    @property
    def paginas(self) -> list[PaginaObservada]:
        return list(self._paginas)

    @property
    def paths(self) -> list[str]:
        """Los *paths* recorridos: lo único del destino que llega al prompt (A1)."""
        return [pagina.path for pagina in self._paginas]

    @property
    def salidas_bloqueadas(self) -> list[SalidaBloqueada]:
        return list(self._salidas)

    @property
    def presupuesto_agotado(self) -> bool:
        return self._presupuesto.agotado

    @property
    def pendientes(self) -> list[str]:
        """Lo que quedó sin recorrer al agotarse el presupuesto."""
        return list(self._presupuesto.pendientes)

    def dom(self, pagina: PaginaObservada) -> str:
        """El HTML observado de una página. El extractor no conoce el navegador."""
        return pagina.html

    def resumen(self) -> dict[str, Any]:
        """Lo que el artefacto declara de la exploración (sin credencial)."""
        return {
            "alias": self.target.alias,
            "host": self.target.host,
            "data_class": self.target.data_class,
            "limits": self.limites.como_dict(),
            "pages_visited": [pagina.path for pagina in self._paginas],
            "pages_skipped": [
                {"url": salida.url, "reason": salida.motivo, "from": salida.desde}
                for salida in self._salidas
            ],
            "pending": self.pendientes,
            "budget_exhausted": self._presupuesto.agotado,
            "budget_reason": self._presupuesto.motivo,
        }

    # --- navegación -----------------------------------------------------------

    async def abrir(self) -> Optional[PaginaObservada]:
        """Navegación de entrada. Aquí un destino no autorizado **sí** revienta.

        En el resto de la exploración un destino fuera de la jaula es un enlace
        externo que se anota y se ignora; en la entrada es una configuración
        inválida, y seguir adelante sería explorar otra cosa que la pedida.
        """
        assert_navigation_allowed(self.target, self.target.url)
        return await self.visitar(self.target.url)

    async def visitar(
        self,
        url: str,
        *,
        depth: int = 0,
        desde: Optional[PaginaObservada] = None,
        _redirecciones: int = 0,
    ) -> Optional[PaginaObservada]:
        """Visita una URL si la capa 5 y el presupuesto lo permiten."""
        base = desde.url if desde else None
        origen_path = desde.path if desde else None

        veredicto = evaluar_navegacion(self.target, url, base=base)
        if not veredicto.permitida:
            self._bloquear(veredicto.url, veredicto.motivo, origen_path)
            return None

        absoluta = veredicto.url
        ya_vista = self._por_url.get(absoluta)
        if ya_vista is not None:
            return ya_vista

        if depth > self.limites.max_depth:
            self._agotar(
                absoluta,
                f"Profundidad máxima alcanzada ({self.limites.max_depth}).",
            )
            return None
        if len(self._paginas) >= self.limites.max_pages:
            self._agotar(
                absoluta, f"Tope de páginas alcanzado ({self.limites.max_pages})."
            )
            return None
        if self._tiempo_agotado():
            self._agotar(
                absoluta,
                f"Presupuesto de tiempo agotado ({self.limites.total_budget_s}s).",
            )
            return None

        driver = self._driver_activo()
        respuesta = await driver.goto(absoluta, timeout_ms=self.limites.timeout_ms)

        if 300 <= respuesta.status < 400 and respuesta.location:
            return await self._seguir_redireccion(
                respuesta, absoluta, depth, desde, _redirecciones
            )

        # El driver puede haber seguido redirecciones por su cuenta: la URL con la
        # que vuelve se revalida igual que la que se pidió, y si cae fuera se
        # DESCARTA el contenido. Un DOM traído de otro host no es observación del
        # sistema explorado.
        final = evaluar_navegacion(self.target, respuesta.url or absoluta)
        if not final.permitida:
            self._bloquear(
                final.url,
                f"La navegación terminó fuera de la jaula: {final.motivo}",
                origen_path,
            )
            return None

        pagina = PaginaObservada(
            url=redact_url(final.url),
            path=_path_de(final.url),
            status=respuesta.status,
            depth=depth,
            html=respuesta.html or "",
            observed_at=self._ahora(),
        )
        self._paginas.append(pagina)
        self._por_url[absoluta] = pagina
        self._por_url.setdefault(final.url, pagina)
        return pagina

    async def _seguir_redireccion(
        self,
        respuesta: Any,
        pedida: str,
        depth: int,
        desde: Optional[PaginaObservada],
        redirecciones: int,
    ) -> Optional[PaginaObservada]:
        """Una redirección es una navegación nueva: se revalida como tal."""
        destino = evaluar_navegacion(self.target, respuesta.location, base=pedida)
        if not destino.permitida:
            self._bloquear(
                destino.url,
                f"Redirección {respuesta.status} no seguida: {destino.motivo}",
                _path_de(pedida),
            )
            return None
        if redirecciones >= MAX_REDIRECCIONES:
            self._bloquear(
                destino.url,
                f"Cadena de más de {MAX_REDIRECCIONES} redirecciones.",
                _path_de(pedida),
            )
            return None
        return await self.visitar(
            destino.url,
            depth=depth,
            desde=desde,
            _redirecciones=redirecciones + 1,
        )

    # --- interacción ----------------------------------------------------------

    async def pulsar_si_procede(
        self, pagina: PaginaObservada, elemento: Elemento
    ) -> tuple[Veredicto, Optional[str]]:
        """Pulsa el elemento **solo** si supera la lista blanca del nivel 1.

        Devuelve el veredicto y, si se pulsó, el HTML resultante. El veredicto
        negativo lleva su motivo: se registra, no se calla.
        """
        veredicto = es_pulsable(
            elemento,
            permite_navegar=lambda href: evaluar_navegacion(
                self.target, href, base=pagina.url
            ).permitida,
        )
        if not veredicto.pulsable:
            return veredicto, None

        selector = selector_de(elemento)
        if selector is None:
            return (
                Veredicto(
                    False,
                    "Sin selector estable ([name], #id o [data-testid]): un clic "
                    "que no se puede describir no se puede repetir.",
                ),
                None,
            )

        gastados = self._presupuesto.clics_por_pagina.get(pagina.url, 0)
        if gastados >= self.limites.max_clicks_per_page:
            return (
                Veredicto(
                    False,
                    "Presupuesto de clics de la página agotado "
                    f"({self.limites.max_clicks_per_page}).",
                ),
                None,
            )
        if self._tiempo_agotado():
            self._agotar(
                pagina.url,
                f"Presupuesto de tiempo agotado ({self.limites.total_budget_s}s).",
            )
            return Veredicto(False, "Presupuesto de tiempo agotado."), None

        self._presupuesto.clics_por_pagina[pagina.url] = gastados + 1
        driver = self._driver_activo()
        respuesta = await driver.click(
            selector.valor, timeout_ms=self.limites.timeout_ms
        )

        final = evaluar_navegacion(self.target, respuesta.url or pagina.url)
        if not final.permitida:
            self._bloquear(
                final.url,
                f"El clic salió de la jaula: {final.motivo}",
                pagina.path,
            )
            return Veredicto(False, "El clic llevó fuera del origen explorado."), None

        return veredicto, respuesta.html or ""

    # --- ciclo de vida --------------------------------------------------------

    async def cerrar(self) -> None:
        """Cierra el driver **solo si lo creó esta sesión**."""
        driver = self.__driver
        if driver is not None and self.__driver_propio:
            await driver.close()
            self.__driver = None

    # --- interno --------------------------------------------------------------

    def _driver_activo(self) -> BrowserDriver:
        """Crea el driver la primera vez que hace falta de verdad.

        Si nadie inyectó uno, se pide a ``build_driver`` — que es la costura
        que el cortafuegos de tests parchea. Un test que se olvide de inyectar su
        doble falla ahí con un mensaje que dice cómo arreglarlo, exactamente como
        ocurre con el cliente del LLM.
        """
        if self.__driver is None:
            # Se llama por el MÓDULO y no por un nombre importado: un
            # ``from … import build_driver`` resolvería el enlace al importar, y
            # el parche del cortafuegos —que sustituye el atributo del módulo— no
            # alcanzaría a este enlace ya resuelto. Es el mismo motivo por el que
            # la capa 1 envuelve ``build_client`` en vez de sustituir ``get_llm``.
            self.__driver = _driver.build_driver(
                timeout_ms=self.limites.timeout_ms,
                storage_state=self.target.storage_state,
            )
            self.__driver_propio = True
        if self._inicio is None:
            self._inicio = self._reloj()
        return self.__driver

    def _tiempo_agotado(self) -> bool:
        if self._inicio is None:
            return False
        return (self._reloj() - self._inicio) >= self.limites.total_budget_s

    def _bloquear(self, url: str, motivo: str, desde: Optional[str]) -> None:
        self._salidas.append(SalidaBloqueada(url=url, motivo=motivo, desde=desde))

    def _agotar(self, url: str, motivo: str) -> None:
        self._presupuesto.agotado = True
        self._presupuesto.motivo = motivo
        publica = redact_url(url)
        if publica not in self._presupuesto.pendientes:
            self._presupuesto.pendientes.append(publica)


def _path_de(url: str) -> str:
    """*Path* (con query) de una URL. El host se queda fuera a propósito (§2.1)."""
    partes = urlparse(url)
    camino = partes.path or "/"
    return f"{camino}?{partes.query}" if partes.query else camino
