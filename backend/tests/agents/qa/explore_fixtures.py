"""El ``manifest.json`` como navegador: la costura de QC4.

Un escenario de ``tests/fixtures/qa_explore/`` es HTML congelado más un manifiesto
que dice lo único que el HTML no puede decir: con qué ``status`` respondió cada
*path*, a dónde redirigió, con qué URL final volvió el navegador y qué pasó al
pulsar. Con eso, la **capa 5** —revalidar esquema, host, allowlist y origen en
CADA navegación— se ejerce entera sin navegar, sin servidor local y sin red.

Y una cosa que el doble modela **a propósito**: un clic declarado en el manifiesto
con un ``method`` distinto de ``GET``/``HEAD`` se **aborta** y devuelve la página
sin cambios. Eso es lo que la intercepción de red de la capa 3 hará en QC5; aquí
es la *especificación ejecutable* de ese comportamiento, no su demostración — hoy
no hay intercepción porque no hay navegador, y el test que lo usa lo dice.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from ai.agents.qa.explore.driver import RespuestaNavegacion

DIRECTORIO = Path(__file__).resolve().parents[2] / "fixtures" / "qa_explore"

#: Los únicos métodos que la capa 3 deja salir.
METODOS_DE_LECTURA = frozenset({"GET", "HEAD"})


@dataclass(frozen=True)
class EscenarioFixture:
    """Un escenario cargado: su manifiesto y sus páginas."""

    nombre: str
    manifest: dict[str, Any]
    raiz: Path

    @property
    def origen(self) -> str:
        return self.manifest["origin"]

    @property
    def host(self) -> str:
        return urlparse(self.origen).hostname or ""

    @property
    def entrada(self) -> str:
        return self.url(self.manifest["entry"])

    def url(self, path: str) -> str:
        return urljoin(self.origen + "/", path.lstrip("/"))

    def html(self, nombre: str) -> str:
        return (self.raiz / nombre).read_text(encoding="utf-8")

    def html_de(self, path: str) -> str:
        return self.html(self.manifest["pages"][path]["file"])


def cargar(nombre: str) -> EscenarioFixture:
    """Carga un escenario por su nombre de directorio."""
    raiz = DIRECTORIO / nombre
    manifest = json.loads((raiz / "manifest.json").read_text(encoding="utf-8"))
    return EscenarioFixture(nombre=nombre, manifest=manifest, raiz=raiz)


def escenarios() -> list[str]:
    """Los escenarios disponibles, para parametrizar."""
    return sorted(
        hijo.name for hijo in DIRECTORIO.iterdir() if (hijo / "manifest.json").is_file()
    )


def _path_de(url: str) -> str:
    partes = urlparse(url)
    camino = partes.path or "/"
    return f"{camino}?{partes.query}" if partes.query else camino


@dataclass
class DriverDeFixtures:
    """Un navegador de mentira alimentado por el manifiesto.

    Protocolo estrecho igual que el real (``goto``, ``click``, ``close``): sin
    ``fill``, sin ``type``, sin ``screenshot``. Un doble más ancho que el original
    permitiría escribir tests que el código de producción no puede ejecutar.
    """

    escenario: EscenarioFixture
    navegaciones: list[str] = field(default_factory=list)
    pulsados: list[str] = field(default_factory=list)
    abortados: list[dict[str, str]] = field(default_factory=list)
    cerrado: bool = False
    url_actual: str = ""
    html_actual: str = ""

    async def goto(self, url: str, *, timeout_ms: int) -> RespuestaNavegacion:
        self.navegaciones.append(url)
        entrada = self.escenario.manifest["pages"].get(_path_de(url))
        if entrada is None:
            return RespuestaNavegacion(
                status=404, url=url, html="<html><body>No existe</body></html>"
            )
        if entrada.get("location"):
            return RespuestaNavegacion(
                status=entrada.get("status", 302),
                url=url,
                html="",
                location=entrada["location"],
            )
        self.url_actual = entrada.get("url", url)
        self.html_actual = self.escenario.html(entrada["file"])
        return RespuestaNavegacion(
            status=entrada.get("status", 200),
            url=self.url_actual,
            html=self.html_actual,
        )

    async def click(self, selector: str, *, timeout_ms: int) -> RespuestaNavegacion:
        self.pulsados.append(selector)
        entrada = self.escenario.manifest.get("clicks", {}).get(selector)
        if entrada is None:
            return self._sin_cambios()

        metodo = (entrada.get("method") or "GET").upper()
        if metodo not in METODOS_DE_LECTURA:
            # Lo que hará ``page.route`` en QC5: la petición muere y el DOM se
            # queda como estaba. La página que el manifiesto guarda en ``file`` es
            # la que se habría visto SI hubiera salido — y no se devuelve.
            self.abortados.append({"selector": selector, "method": metodo})
            return self._sin_cambios()

        self.url_actual = entrada.get("url", self.url_actual)
        self.html_actual = self.escenario.html(entrada["file"])
        return RespuestaNavegacion(
            status=entrada.get("status", 200),
            url=self.url_actual,
            html=self.html_actual,
        )

    async def close(self) -> None:
        self.cerrado = True

    def _sin_cambios(self) -> RespuestaNavegacion:
        return RespuestaNavegacion(
            status=200, url=self.url_actual, html=self.html_actual
        )


def driver_de(nombre: str) -> tuple[EscenarioFixture, DriverDeFixtures]:
    """Atajo: escenario cargado y su driver, que es como se usan siempre."""
    escenario = cargar(nombre)
    return escenario, DriverDeFixtures(escenario)
