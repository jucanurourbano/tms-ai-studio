"""Capa 3, **mitad de red**: qué sale del navegador. Gemela de ``clicking.py``.

``clicking.py`` decide qué se **toca** leyendo el DOM. Este módulo decide qué se
**envía**, y es la mitad que el diseño (§13.2) llama la traducción literal de
``default_transaction_read_only=on``:

> *"No se depende de que las consultas sean SELECT: el propio Postgres rechaza
> cualquier escritura."* — INV2

El equivalente aquí **no** es "solo pulsamos enlaces" —eso es intención, y un
``<a>`` puede disparar un ``fetch``—: es **abortar toda petición cuyo método no
sea ``GET``/``HEAD``**. Un envío accidental muere dentro del navegador, antes de
salir.

**Dos líneas, y el orden importa.** Primero :data:`GUION_NEUTRALIZAR_SUBMIT`, que
impide que el envío llegue siquiera a formarse; después el aborto en red, que
recoge lo que el DOM no puede parar (un ``fetch`` escrito a mano dentro de un
manejador). Instalar solo la segunda funcionaría, pero dejaría al navegador
formando peticiones que luego mueren, y **una petición que muere abortada se
observa como "no hubo validación"** — que es la observación falsa que este agente
no puede producir (el mismo motivo por el que teclear está fuera de v1).

**La política vive aquí, en Python puro, y no dentro del manejador de Playwright**
por la razón de siempre en este paquete: así se ejerce entera sin navegador, sin
red y sin servidor local. El driver es una cáscara que pregunta y obedece.
"""

from dataclasses import dataclass
from typing import Optional

from ai.agents.qa.explore.navigation import evaluar_navegacion
from ai.agents.qa.explore.target import ExploreTarget, redact_url

#: Los dos únicos métodos que no cambian estado. Lista **blanca**: lo que no está
#: aquí se aborta, incluido el verbo que nadie ha inventado todavía.
METODOS_DE_LECTURA = frozenset({"GET", "HEAD"})

#: Neutralización del envío **en el DOM**, instalada con ``add_init_script`` antes
#: de que corra un solo script de la página y en cada documento nuevo.
#:
#: Tres cosas, y las tres hacen falta:
#:
#: 1. ``submit`` en **fase de captura** con ``stopImmediatePropagation``: el envío
#:    muere antes de que lo vea ningún manejador de la aplicación.
#: 2. ``HTMLFormElement.prototype.submit``, que **no dispara el evento** ``submit``
#:    y por tanto se escaparía del punto 1.
#: 3. ``requestSubmit``, que sí lo dispara pero también valida y enfoca: dejarlo
#:    vivo cambiaría lo que se ve en pantalla.
#:
#: No se toca nada más del documento: el explorador observa la aplicación, no una
#: versión mutilada de ella. Lo que se anula es **el envío**, no la validación —
#: el mensaje de error que el navegador renderiza es justo la evidencia que QA-D2
#: necesita citar.
GUION_NEUTRALIZAR_SUBMIT = """
(() => {
  const parar = (evento) => {
    evento.preventDefault();
    evento.stopImmediatePropagation();
  };
  document.addEventListener('submit', parar, true);
  try {
    const proto = window.HTMLFormElement && window.HTMLFormElement.prototype;
    if (proto) {
      proto.submit = function () {};
      proto.requestSubmit = function () {};
    }
  } catch (e) {}
})();
"""


@dataclass(frozen=True)
class VeredictoPeticion:
    """¿Sale esta petición del navegador? Y si no, por qué — para registrarlo."""

    permitida: bool
    motivo: str


def evaluar_peticion(
    target: ExploreTarget,
    *,
    metodo: str,
    url: str,
    es_navegacion: bool,
) -> VeredictoPeticion:
    """Decide una petición del navegador. **Fail-closed en las dos preguntas.**

    1. **El método** (capa 3): cualquier verbo que no sea ``GET``/``HEAD`` se
       aborta, sea de navegación o de un ``fetch``, sea al propio origen o a otro.
       Ésta es la regla que convierte "solo lectura" de intención en imposición.
    2. **El destino, solo si es una navegación** (capa 5): un ``302`` a otro host
       llega al navegador como una petición de documento nueva, así que el sitio
       donde se ataja es éste. Se delega en :func:`evaluar_navegacion`, que es el
       único que sabe leer la allowlist — dos lectores de la jaula son dos sitios
       donde una capa puede no aplicarse.

    **Un subrecurso ``GET`` a otro origen SÍ pasa, y conviene decir por qué.**
    Abortar el CSS o el JS que la aplicación carga de un CDN deja una página rota,
    y de una página rota se derivan casos que afirman comportamientos que el
    sistema no tiene: exactamente la observación falsa que el agente no puede
    producir. Se prefiere el riesgo menor —una petición de lectura a un tercero,
    que la propia aplicación hace de todos modos cuando la abre una persona— al
    riesgo mayor. Queda escrito como residual, no como descuido.
    """
    verbo = (metodo or "").strip().upper()
    if verbo not in METODOS_DE_LECTURA:
        return VeredictoPeticion(
            False,
            f"Método «{verbo or '?'}» abortado: la exploración es de SOLO LECTURA "
            f"y solo salen {', '.join(sorted(METODOS_DE_LECTURA))}.",
        )

    if es_navegacion:
        veredicto = evaluar_navegacion(target, url)
        if not veredicto.permitida:
            return VeredictoPeticion(
                False,
                f"Navegación a «{redact_url(url)}» abortada: {veredicto.motivo}",
            )

    return VeredictoPeticion(True, "Autorizada.")


async def preparar_contexto(contexto, target: ExploreTarget) -> None:
    """Instala las dos líneas de la capa 3 sobre un contexto de navegador.

    **En este orden, y el orden es el criterio**: primero la neutralización en el
    DOM (el envío no llega a formarse), después el aborto en red (lo que el DOM no
    puede parar). Al revés el navegador formaría envíos que mueren abortados, y un
    envío que muere se observa como "no hubo validación".

    Recibe el contexto por parámetro y no lo crea: así se ejerce con un doble que
    apunta el orden de las llamadas, sin arrancar un navegador (criterio 7 del
    bloque — ninguna exploración real, ni siquiera una vez).
    """
    await contexto.add_init_script(GUION_NEUTRALIZAR_SUBMIT)
    await contexto.route("**/*", _manejador(target))


def _manejador(target: ExploreTarget):
    """El manejador de ruta: pregunta a :func:`evaluar_peticion` y obedece."""

    async def _ruta(route, request) -> None:
        veredicto = evaluar_peticion(
            target,
            metodo=request.method,
            url=request.url,
            es_navegacion=bool(request.is_navigation_request()),
        )
        if veredicto.permitida:
            await route.continue_()
        else:
            await route.abort()

    return _ruta


def motivo_de_aborto(
    target: ExploreTarget, *, metodo: str, url: str, es_navegacion: bool
) -> Optional[str]:
    """El motivo por el que una petición se abortaría, o ``None`` si no lo hace.

    Existe para que el driver pueda **decir** por qué el navegador se negó, en vez
    de devolver un fallo mudo que la sesión registraría como "algo pasó".
    """
    veredicto = evaluar_peticion(
        target, metodo=metodo, url=url, es_navegacion=es_navegacion
    )
    return None if veredicto.permitida else veredicto.motivo
