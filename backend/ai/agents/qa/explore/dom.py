"""Un DOM mínimo, de biblioteca estándar, para decidir sobre HTML sin navegador.

Dos razones para no traer un parser nuevo:

1. **La costura del Modo C es que el extractor no conoce el navegador**: la
   política de pulsado y (en QC5) ``SURFACE_MAP`` reciben **HTML como cadena**.
   Todo lo que se decida aquí es determinista, gratis y ejercitable sin red, sin
   servidor local y sin Chromium — que en este host no arranca.
2. Lo que hace falta saber de un elemento es su etiqueta, sus atributos y si
   tiene un ``<form>`` por encima. Eso no justifica una dependencia.

``html.parser`` es tolerante con el HTML roto, que es el HTML que hay. La pila de
ancestros es **best-effort** (un ``<p>`` sin cerrar la desalinea), pero la única
pregunta de la que depende una decisión de seguridad —¿estoy dentro de un
formulario?— se responde con un contador propio de ``<form>``, que no depende de
la pila: los formularios no anidan y se cierran, y si alguien no lo cerrara el
contador se queda **en** el formulario, que es el lado seguro del error.
"""

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable, Optional

#: Elementos sin cierre: no se apilan, o el primer ``<input>`` desalinearía todo.
TAGS_VACIOS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

#: Orden de preferencia del selector canónico (§2.1 del diseño). Un ancla fijada
#: por posición estructural es frágil —un ``<div>`` nuevo la rompe—; QC5 la añade
#: con su ``selector_strategy`` para que quien lea el plan sepa cuáles lo son.
#: Aquí, sin estrategia estable, **no se inventa una**: se devuelve ``None``.
ESTRATEGIAS = ("name", "id", "data-testid")


@dataclass(frozen=True)
class Selector:
    """Selector CSS de un elemento, con la estrategia que lo produjo."""

    valor: str
    estrategia: str


@dataclass(frozen=True)
class Elemento:
    """Un elemento del HTML observado, con lo justo para decidir sobre él."""

    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    ancestros: tuple[str, ...] = ()
    en_formulario: bool = False
    linea: int = 0

    def attr(self, nombre: str) -> Optional[str]:
        """Valor del atributo (``""`` si es booleano y está presente)."""
        return self.attrs.get(nombre.lower())

    def tiene(self, nombre: str) -> bool:
        return nombre.lower() in self.attrs


class _Lector(HTMLParser):
    """Recolecta elementos con su contexto. No interpreta, no ejecuta, no red."""

    def __init__(self, tags: Optional[frozenset[str]]) -> None:
        super().__init__(convert_charrefs=True)
        self._tags = tags
        self._pila: list[str] = []
        self._formularios = 0
        self.encontrados: list[Elemento] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "form":
            self._formularios += 1
        if self._tags is None or tag in self._tags:
            linea, _ = self.getpos()
            self.encontrados.append(
                Elemento(
                    tag=tag,
                    attrs={
                        (nombre or "").lower(): (valor if valor is not None else "")
                        for nombre, valor in attrs
                    },
                    ancestros=tuple(self._pila),
                    en_formulario=self._formularios > 0,
                    linea=linea,
                )
            )
        if tag not in TAGS_VACIOS:
            self._pila.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:
        # ``<div/>`` o ``<input/>``: se registra sin tocar la pila. Se sobreescribe
        # el default (starttag + endtag) porque ese par apilaría y desapilaría un
        # elemento que nunca tuvo contenido.
        tag = tag.lower()
        if self._tags is None or tag in self._tags:
            linea, _ = self.getpos()
            self.encontrados.append(
                Elemento(
                    tag=tag,
                    attrs={
                        (nombre or "").lower(): (valor if valor is not None else "")
                        for nombre, valor in attrs
                    },
                    ancestros=tuple(self._pila),
                    en_formulario=self._formularios > 0,
                    linea=linea,
                )
            )

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "form" and self._formularios > 0:
            self._formularios -= 1
        if tag in self._pila:
            # Se desapila hasta el último abierto con ese nombre: así un
            # ``</div>`` de más no vacía la pila entera.
            while self._pila:
                ultimo = self._pila.pop()
                if ultimo == tag:
                    break


def elementos(html: str, *, tags: Optional[Iterable[str]] = None) -> list[Elemento]:
    """Elementos del HTML, en orden de aparición. ``tags`` filtra por etiqueta."""
    lector = _Lector(frozenset(t.lower() for t in tags) if tags else None)
    lector.feed(html or "")
    lector.close()
    return lector.encontrados


def _escapar(valor: str) -> str:
    return valor.replace("\\", "\\\\").replace('"', '\\"')


def selector_de(elemento: Elemento) -> Optional[Selector]:
    """Selector canónico del elemento, o ``None`` si no hay uno estable.

    ``None`` es una respuesta legítima y **fail-closed**: sin selector estable no
    se pulsa y no se ancla, porque un ancla que no se puede reconstruir en la
    corrida siguiente no sirve para lo único que hace útil a una suite de
    caracterización — comparar dos corridas.
    """
    for estrategia in ESTRATEGIAS:
        valor = elemento.attr(estrategia)
        if not valor:
            continue
        if estrategia == "id":
            return Selector(f'{elemento.tag}[id="{_escapar(valor)}"]', "id")
        return Selector(f'{elemento.tag}[{estrategia}="{_escapar(valor)}"]', estrategia)
    return None
