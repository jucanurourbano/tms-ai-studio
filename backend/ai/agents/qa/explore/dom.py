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
    """Un elemento del HTML observado, con lo justo para decidir sobre él.

    Los tres últimos campos son **hechos del parse**, y por eso viven aquí y no en
    quien los usa: reconstruirlos después obligaría a volver a recorrer el HTML con
    otro mecanismo, y dos parsers del mismo documento se separan el día que uno de
    los dos tropieza con etiquetas mal cerradas.

    * ``origen`` es el texto **literal** de la etiqueta de apertura, tal cual está
      escrito en el documento. Es lo que hace citable una observación: la evidencia
      de un ancla tiene que ser subcadena exacta del DOM (§2.4 del diseño del Modo
      C), y un ``maxlength="11"`` alucinado como ``12`` muere ahí.
    * ``ruta`` es el camino estructural ``nth-of-type`` desde la raíz. Es la última
      estrategia de selector, la frágil, y **por eso nace marcada** allí donde se
      usa.
    * ``inicio`` es el desplazamiento absoluto de la etiqueta de apertura dentro del
      HTML, para recortar el fragmento literal de un elemento con contenido.
    """

    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    ancestros: tuple[str, ...] = ()
    en_formulario: bool = False
    linea: int = 0
    origen: str = ""
    ruta: tuple[str, ...] = ()
    inicio: int = 0

    def attr(self, nombre: str) -> Optional[str]:
        """Valor del atributo (``""`` si es booleano y está presente)."""
        return self.attrs.get(nombre.lower())

    def tiene(self, nombre: str) -> bool:
        return nombre.lower() in self.attrs


@dataclass
class _Abierto:
    """Un elemento abierto: su etiqueta, su paso en la ruta y sus hijos contados.

    Los hijos se cuentan **por marco** —cada elemento lleva su propia cuenta— y no
    en un contador global: ``nth-of-type`` es la posición entre hermanos, no en el
    documento.
    """

    tag: str
    paso: str
    hijos: dict[str, int] = field(default_factory=dict)


def _inicios_de_linea(html: str) -> list[int]:
    """Desplazamiento absoluto donde empieza cada línea.

    ``HTMLParser.getpos()`` da línea y columna; el recorte de un fragmento
    literal necesita un índice sobre la cadena, y esta tabla es la conversión.
    """
    inicios = [0]
    posicion = html.find("\n")
    while posicion != -1:
        inicios.append(posicion + 1)
        posicion = html.find("\n", posicion + 1)
    return inicios


class _Lector(HTMLParser):
    """Recolecta elementos con su contexto. No interpreta, no ejecuta, no red."""

    def __init__(self, tags: Optional[frozenset[str]], html: str) -> None:
        super().__init__(convert_charrefs=True)
        self._tags = tags
        self._inicios = _inicios_de_linea(html)
        self._abiertos: list[_Abierto] = []
        self._raiz: dict[str, int] = {}
        self._formularios = 0
        self.encontrados: list[Elemento] = []

    def _registrar(self, tag: str, attrs) -> str:
        """Anota el elemento y devuelve su paso en la ruta estructural.

        La cuenta de hermanos se lleva **antes** de filtrar por ``tags``: si no,
        pedir solo los ``<input>`` cambiaría el ``nth-of-type`` de un ``<input>``,
        y un selector que depende de qué se preguntó no es un selector.
        """
        hijos = self._abiertos[-1].hijos if self._abiertos else self._raiz
        indice = hijos[tag] = hijos.get(tag, 0) + 1
        paso = f"{tag}:nth-of-type({indice})"
        if self._tags is not None and tag not in self._tags:
            return paso
        linea, columna = self.getpos()
        self.encontrados.append(
            Elemento(
                tag=tag,
                attrs={
                    (nombre or "").lower(): (valor if valor is not None else "")
                    for nombre, valor in attrs
                },
                ancestros=tuple(abierto.tag for abierto in self._abiertos),
                en_formulario=self._formularios > 0,
                linea=linea,
                origen=self.get_starttag_text() or "",
                ruta=tuple(abierto.paso for abierto in self._abiertos) + (paso,),
                inicio=self._inicios[linea - 1] + columna,
            )
        )
        return paso

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "form":
            self._formularios += 1
        paso = self._registrar(tag, attrs)
        if tag not in TAGS_VACIOS:
            self._abiertos.append(_Abierto(tag=tag, paso=paso))

    def handle_startendtag(self, tag: str, attrs) -> None:
        # ``<div/>`` o ``<input/>``: se registra sin tocar la pila. Se sobreescribe
        # el default (starttag + endtag) porque ese par apilaría y desapilaría un
        # elemento que nunca tuvo contenido.
        self._registrar(tag.lower(), attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "form" and self._formularios > 0:
            self._formularios -= 1
        if any(abierto.tag == tag for abierto in self._abiertos):
            # Se desapila hasta el último abierto con ese nombre: así un
            # ``</div>`` de más no vacía la pila entera.
            while self._abiertos:
                if self._abiertos.pop().tag == tag:
                    break


def elementos(html: str, *, tags: Optional[Iterable[str]] = None) -> list[Elemento]:
    """Elementos del HTML, en orden de aparición. ``tags`` filtra por etiqueta."""
    html = html or ""
    lector = _Lector(frozenset(t.lower() for t in tags) if tags else None, html)
    lector.feed(html)
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
        selector = selector_por_atributo(elemento, estrategia)
        if selector is not None:
            return selector
    return None


def selector_por_atributo(elemento: Elemento, atributo: str) -> Optional[Selector]:
    """El selector del elemento por UN atributo, o ``None`` si no lo lleva.

    Existe como pieza suelta porque quien ancla necesita **todos** los candidatos
    y no solo el primero: si el primero resulta ambiguo —dos radios del mismo
    grupo comparten ``name``— hay que poder probar el siguiente. Construir ahí esa
    cadena a mano sería una segunda copia de la forma del selector, y dos copias
    se separan el día que una de las dos aprenda a escapar un carácter nuevo.
    """
    valor = elemento.attr(atributo)
    if not valor:
        return None
    return Selector(f'{elemento.tag}[{atributo}="{_escapar(valor)}"]', atributo)


def selector_estructural(elemento: Elemento) -> str:
    """El camino ``nth-of-type`` completo, o ``""`` si el elemento no tiene ruta.

    Verboso a propósito: se escribe el índice **siempre**, incluso cuando el
    elemento es hijo único de su tipo. Omitirlo cuando sobra exigiría una segunda
    pasada que contara los hermanos definitivos, y el precio de esa pasada se paga
    en cada página para ahorrar caracteres en un selector que se lee una vez —
    cuando falla.

    Cadena vacía y no ``None`` porque quien lo usa ya decide con la vacuidad: sin
    ruta no hay selector, y sin selector no hay ancla.
    """
    return " > ".join(elemento.ruta)
