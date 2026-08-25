"""Dobles y configuración compartida de los tests del Modo C (QC3).

La costura del Modo C es que **el extractor no conoce el navegador**: la sesión
recibe el driver inyectado y todo lo demás trabaja sobre HTML como cadena. Por eso
esta suite ejerce el guard completo sin navegador, sin servidor local y sin red —
determinista y gratis, y encima obligatorio: en este host Chromium no arranca
(falta ``libnspr4`` y no hay ``sudo``).
"""

from dataclasses import dataclass, field
from typing import Optional

from ai.agents.qa.explore.driver import RespuestaNavegacion
from app.config.settings import settings

#: Destino de referencia: un host interno, no local, con solo lectura declarada.
HOST = "tms.interno"
URL_BASE = f"https://{HOST}/"


def configurar(
    monkeypatch,
    *,
    destinos: Optional[dict] = None,
    hosts: Optional[list[str]] = None,
    habilitado: bool = True,
) -> None:
    """Deja el despliegue con un destino declarado y autorizado."""
    monkeypatch.setattr(settings, "QA_EXPLORE_ENABLED", habilitado)
    monkeypatch.setattr(
        settings,
        "QA_EXPLORE_TARGETS",
        (
            destinos
            if destinos is not None
            else {"tms-qa": {"url": URL_BASE, "readonly_verified": True}}
        ),
    )
    monkeypatch.setattr(
        settings,
        "QA_EXPLORE_ALLOWED_HOSTS",
        [HOST] if hosts is None else hosts,
    )


@dataclass
class DriverFalso:
    """Un navegador de mentira: devuelve lo programado y **anota lo que se pidió**.

    No tiene ``fill``, ni ``type``, ni ``screenshot``: el protocolo real tampoco,
    y un doble más ancho que el original permitiría escribir tests que el código
    de producción no puede ejecutar.
    """

    paginas: dict[str, RespuestaNavegacion] = field(default_factory=dict)
    clics: dict[str, RespuestaNavegacion] = field(default_factory=dict)
    navegaciones: list[str] = field(default_factory=list)
    pulsados: list[str] = field(default_factory=list)
    cerrado: bool = False

    async def goto(self, url: str, *, timeout_ms: int) -> RespuestaNavegacion:
        self.navegaciones.append(url)
        return self.paginas.get(url) or RespuestaNavegacion(
            status=404, url=url, html="<html><body>no está</body></html>"
        )

    async def click(self, selector: str, *, timeout_ms: int) -> RespuestaNavegacion:
        self.pulsados.append(selector)
        return self.clics.get(selector) or RespuestaNavegacion(
            status=200,
            url=self.navegaciones[-1] if self.navegaciones else URL_BASE,
            html="<html><body>pulsado</body></html>",
        )

    async def close(self) -> None:
        self.cerrado = True


def pagina(url: str, html: str, *, status: int = 200) -> RespuestaNavegacion:
    """Atajo para programar una página del driver falso."""
    return RespuestaNavegacion(status=status, url=url, html=html)
