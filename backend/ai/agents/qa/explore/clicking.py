"""Capa 3, mitad DOM: qué se puede pulsar. Lista blanca, evaluada sobre el HTML.

La capa 3 de la PARTE II define lo que **sale** del navegador (abortar en red todo
método ≠ ``GET``/``HEAD``). No define lo que se **toca** dentro, y ahí está el
problema real: la mayor parte del DOM de una SPA no existe hasta que alguien abre
una pestaña o un acordeón.

Tres niveles (§3.2 del diseño del Modo C):

* **Nivel 0 — leer.** Siempre permitido. Los atributos de validación ya están en
  el HTML servido: descubrir campos **no requiere interacción**.
* **Nivel 1 — pulsar lo demostrablemente inocuo.** Es lo que decide este módulo.
* **Nivel 2 — teclear: FUERA DE v1.** No por el riesgo de escritura (la red lo
  aborta) sino por algo peor: si un ``keyup`` dispara un autoguardado y la
  petición muere abortada, el explorador **observa que no hubo validación** y
  emite un caso que afirma un comportamiento falso. El aborto convierte un riesgo
  de escritura en un riesgo de **observación falsa**, que es lo único que este
  agente no puede producir.

> **La trampa que hay que nombrar:** ``<button>`` **sin** atributo ``type`` dentro
> de un ``<form>`` es ``type="submit"`` por defecto en HTML. Una lista blanca "los
> ``<button>`` se pueden pulsar" sería una lista blanca de envíos. Por eso el
> ``type="button"`` se exige **explícito en el atributo**, nunca inferido — y se
> exige incluso fuera de un formulario, porque un ``<button form="otro">`` envía
> un formulario que no es su ancestro.

Lo que **no** se bloquea es "todo lo que esté dentro de un ``<form>``": eso
dejaría fuera pestañas y acordeones, que viven dentro de formularios y son la
mayor parte del valor del nivel 1. Se bloquea lo que **puede enviar**: los
controles de envío y cualquier elemento con atributos ``form*`` que envíen desde
fuera.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from ai.agents.qa.explore.dom import Elemento, Selector, elementos, selector_de

#: Etiquetas que nunca se pulsan. Los controles de formulario quedan fuera por el
#: nivel 2 (no se teclea, no se marca, no se selecciona: marcar una casilla ya es
#: cambiar el estado del formulario) y ``label`` porque pulsarlo activa su control.
TAGS_NUNCA = frozenset(
    {
        "input",
        "textarea",
        "select",
        "option",
        "optgroup",
        "label",
        "form",
        "iframe",
        "object",
        "embed",
        "script",
    }
)

#: Atributos que permiten enviar un formulario desde cualquier parte del documento.
ATRIBUTOS_DE_ENVIO = ("formaction", "formmethod", "formenctype", "formtarget", "form")

#: Etiquetas y atributos que se examinan al recorrer una página.
_TAGS_CANDIDATOS = frozenset(
    {"a", "button", "summary", "div", "span", "li", "td", "th", "h1", "h2", "h3"}
)

#: Roles que declaran un control de navegación o de expansión.
ROLES_PERMITIDOS = frozenset({"tab", "button"})


@dataclass(frozen=True)
class Veredicto:
    """¿Se puede pulsar? Y si no, por qué — el motivo se registra, no se calla."""

    pulsable: bool
    motivo: str


def _es_fragmento(href: str) -> bool:
    return href.startswith("#")


def es_pulsable(
    elemento: Elemento,
    *,
    permite_navegar: Optional[Callable[[str], bool]] = None,
) -> Veredicto:
    """Aplica la lista blanca del nivel 1. Primera regla que encaja, gana.

    ``permite_navegar`` lo inyecta ``ExploreSession`` con la **misma** función que
    autoriza una navegación (capa 5). Es a propósito: si el destino de un enlace
    se juzgara aquí con otro criterio, la política de pulsado y la de navegación
    podrían divergir, y la divergencia siempre se descubre por el lado malo. Sin
    inyectarla, ningún enlace absoluto es pulsable (fail-closed).
    """
    tag = elemento.tag

    if elemento.tiene("disabled") or (elemento.attr("aria-disabled") or "") == "true":
        return Veredicto(False, "El elemento está deshabilitado.")

    if tag == "button":
        tipo = (elemento.attr("type") or "").strip().lower()
        if tipo != "button":
            declarado = f"type=«{tipo}»" if tipo else "sin atributo type"
            return Veredicto(
                False,
                f"<button> {declarado}: en HTML un <button> sin type explícito es "
                'type="submit". Solo se pulsa un <button type="button">.',
            )

    if tag in TAGS_NUNCA:
        return Veredicto(
            False,
            f"<{tag}> no se pulsa: es un control de formulario o un contenedor "
            "cuyo efecto no se puede acotar leyendo el DOM.",
        )

    for atributo in ATRIBUTOS_DE_ENVIO:
        if elemento.tiene(atributo):
            return Veredicto(
                False,
                f"Declara «{atributo}»: puede enviar un formulario desde fuera de él.",
            )

    if elemento.tiene("download"):
        return Veredicto(False, "Es una descarga.")

    objetivo = (elemento.attr("target") or "").strip().lower()
    if objetivo not in ("", "_self"):
        return Veredicto(
            False,
            f"Abre en «{objetivo}»: una pestaña nueva sale del contexto controlado.",
        )

    if tag == "a":
        href = (elemento.attr("href") or "").strip()
        if not href:
            return Veredicto(False, "<a> sin href: no navega a ninguna parte.")
        if _es_fragmento(href):
            return Veredicto(True, "Enlace a un fragmento de la misma página.")
        if permite_navegar is None:
            return Veredicto(
                False,
                "No hay política de navegación inyectada: ningún enlace absoluto "
                "se pulsa sin revalidar su destino.",
            )
        if not permite_navegar(href):
            return Veredicto(False, "El destino del enlace no está autorizado.")
        return Veredicto(True, "Enlace autorizado del mismo origen.")

    if tag == "summary":
        return Veredicto(True, "<summary>: despliega su <details>.")

    if tag == "button":
        return Veredicto(True, '<button type="button"> explícito.')

    rol = (elemento.attr("role") or "").strip().lower()
    if rol in ROLES_PERMITIDOS:
        return Veredicto(True, f"role=«{rol}»: control de navegación o expansión.")

    if elemento.tiene("aria-expanded"):
        return Veredicto(True, "Declara aria-expanded: control de expansión.")

    return Veredicto(
        False, f"<{tag}> no está en la lista blanca de elementos pulsables."
    )


def elementos_pulsables(
    html: str,
    *,
    permite_navegar: Optional[Callable[[str], bool]] = None,
) -> list[tuple[Elemento, Selector]]:
    """Elementos pulsables **y** con selector estable, en orden de aparición.

    Los dos filtros son independientes y los dos son fail-closed: sin veredicto
    favorable no se pulsa, y sin selector estable tampoco —un clic que no se puede
    describir es un clic que la corrida siguiente no puede repetir.
    """
    candidatos: list[tuple[Elemento, Selector]] = []
    for elemento in elementos(html, tags=_TAGS_CANDIDATOS):
        if not es_pulsable(elemento, permite_navegar=permite_navegar).pulsable:
            continue
        selector = selector_de(elemento)
        if selector is None:
            continue
        candidatos.append((elemento, selector))
    return candidatos
