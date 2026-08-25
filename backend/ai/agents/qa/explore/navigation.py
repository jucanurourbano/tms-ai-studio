"""Capa 5 del guard: la allowlist se re-verifica en CADA navegación.

INV2 necesitaba cuatro capas porque **una base de datos no redirige**. Una
aplicación web sí: un ``302`` a otro host, un enlace externo, un
``window.location``. Cada uno es una salida de la jaula, y una comprobación hecha
solo al arrancar habría autorizado la primera navegación y ninguna de las
siguientes — que son exactamente las que el destino elige, no nosotros.

Toda navegación revalida, en este orden: la exploración sigue habilitada, el
esquema es ``http``/``https``, el host está en la allowlist **vigente** y el
origen es el del destino (mismo origen: esquema + host + puerto).

Lo que cae fuera **no se sigue y se registra** (``ExploreSession``); de ahí que la
forma normal de esta capa sea un *veredicto* y no una excepción: una excepción
por cada enlace externo abortaría la exploración entera por un enlace a Twitter.
:func:`assert_navigation_allowed` existe para la navegación de entrada, donde
fallar es lo correcto.

**Residual declarado, no escondido:** *DNS rebinding* — el host allowlisted
resolviendo a otra IP entre la comprobación y la conexión — no está mitigado.
Mitigarlo exige fijar la IP resuelta y llevarla al navegador; se documenta en vez
de fingir que no existe.
"""

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

from ai.agents.qa.explore.target import ExploreTarget, redact_url
from app.config.settings import settings
from app.errors import ForbiddenError

#: Los dos únicos esquemas navegables.
ESQUEMAS_PERMITIDOS = ("http", "https")

#: Esquemas nombrados uno a uno para que el mensaje de rechazo sea útil. La regla
#: efectiva es la lista blanca de arriba: lo que no está en ella se rechaza,
#: incluido el esquema que nadie ha inventado todavía.
ESQUEMAS_RECHAZADOS = (
    "file",
    "data",
    "blob",
    "javascript",
    "about",
    "ftp",
    "mailto",
    "tel",
    "ws",
    "wss",
    "chrome",
    "view-source",
)

_PUERTOS_POR_ESQUEMA = {"http": 80, "https": 443}


@dataclass(frozen=True)
class VeredictoNavegacion:
    """¿Se puede navegar ahí? Y si no, por qué — para poder registrarlo."""

    permitida: bool
    url: str
    motivo: str


def _origen(url: str) -> str:
    partes = urlparse(url)
    esquema = (partes.scheme or "").lower()
    host = (partes.hostname or "").lower()
    puerto = partes.port or _PUERTOS_POR_ESQUEMA.get(esquema, 0)
    return f"{esquema}://{host}:{puerto}"


def evaluar_navegacion(
    target: ExploreTarget, url: str, *, base: Optional[str] = None
) -> VeredictoNavegacion:
    """Revalida un destino de navegación. Falla cerrado en cada comprobación.

    ``base`` permite resolver enlaces relativos tal como lo haría el navegador —
    y por tanto también los peligrosos: ``urljoin`` sobre ``//otro.host/x``
    produce un absoluto a otro host, que esta función rechaza como cualquier otro.
    """
    crudo = (url or "").strip()
    if not crudo:
        return VeredictoNavegacion(False, "", "URL vacía.")

    absoluta = urljoin(base, crudo) if base else crudo
    publica = redact_url(absoluta)

    if not settings.QA_EXPLORE_ENABLED:
        return VeredictoNavegacion(
            False, publica, "La exploración está desactivada en el despliegue."
        )

    partes = urlparse(absoluta)
    esquema = (partes.scheme or "").lower()
    if esquema not in ESQUEMAS_PERMITIDOS:
        detalle = (
            f"el esquema «{esquema}»" if esquema else "una URL sin esquema absoluto"
        )
        return VeredictoNavegacion(
            False,
            publica,
            f"Solo se navega http/https; se rechaza {detalle}.",
        )

    host = (partes.hostname or "").lower()
    if not host:
        return VeredictoNavegacion(False, publica, "URL sin host.")

    permitidos = {h.strip().lower() for h in settings.QA_EXPLORE_ALLOWED_HOSTS}
    if not permitidos:
        return VeredictoNavegacion(
            False, publica, "No hay ningún host autorizado (allowlist vacía)."
        )
    if host not in permitidos:
        return VeredictoNavegacion(
            False, publica, f"El host «{host}» no está en la allowlist."
        )

    if _origen(absoluta) != target.origin:
        return VeredictoNavegacion(
            False,
            publica,
            f"Fuera del origen explorado ({target.origin}): «{_origen(absoluta)}».",
        )

    return VeredictoNavegacion(True, absoluta, "Autorizada.")


def assert_navigation_allowed(
    target: ExploreTarget, url: str, *, base: Optional[str] = None
) -> str:
    """Igual que :func:`evaluar_navegacion`, pero fallando. Devuelve la URL."""
    veredicto = evaluar_navegacion(target, url, base=base)
    if not veredicto.permitida:
        raise ForbiddenError(
            f"Navegación no autorizada a «{veredicto.url}»: {veredicto.motivo}"
        )
    return veredicto.url
