"""El saneador: el paso obligatorio entre capturar una página y comitearla.

Una captura de una aplicación autenticada es un volcado de datos de producción, y
el repositorio es para siempre. Por eso entre el explorador y el disco hay una
función que no se puede saltar: :func:`escenario_saneado` **revienta** si lo que
va a escribir todavía viola el candado, en vez de dejarlo pasar con un aviso.

El criterio es el ajuste **A3** del diseño del Modo C: *se conserva la estructura
y los rótulos, se borran los datos*.

* **Estructura**: ``<form>``, ``<input>``, ``<select>``, ``<label>``, encabezados
  y los atributos de validación (``required``, ``maxlength``, ``pattern``…). Son
  lo que ancla un caso de prueba, y sin ellos la fixture no sirve para nada.
* **Rótulos**: el texto que la aplicación muestra —incluidos **los mensajes de
  error renderizados y las opciones de un ``<select>``, aunque estén dentro de una
  tabla**—. Ese texto es justo la evidencia que QA-D2 acepta citada verbatim, así
  que borrar un ``<tbody>`` entero se llevaría señal por delante.
* **Datos**: el ``value`` de cada control, el texto suelto de las celdas de datos,
  las secuencias largas de dígitos (guía, RUC, DNI), los tokens y el host real.

Tres decisiones que conviene justificar porque no están en la tabla del diseño:

1. **Los manejadores en línea (``onclick``…) se borran por el mismo motivo que
   ``<script>``**: son código, no estructura ni rótulo, y un ``onclick`` capturado
   arrastra rutas con identificadores reales. Consecuencia asumida: una trampa que
   dependa de un manejador —el clic que dispara un ``POST``— **no** se reproduce
   capturándola; se escribe a mano en ``trampas/``, que es donde vive lo
   deliberadamente hostil.
2. **Las URLs absolutas del host explorado se reescriben a su *path***. Si no, la
   fixture llevaría escrito el mapa de la infraestructura, que es exactamente lo
   que la capa 1 del guard mantiene fuera del prompt (A1).
3. **Reconocer un mensaje por su ``class``/``id`` se hace por piezas exactas, y la
   concesión no cruza hacia dentro de una tabla.** Las dos mitades arreglan la
   misma fuga, que fallaba hacia CONSERVAR: por subcadena, ``class="terror"``
   casaba con ``error`` y salvaba el dato de una celda, y un
   ``class="error-boundary"`` —un envoltorio de React— alrededor de una tabla la
   salvaba entera. Ninguna de las dos hereda nada, porque fuera de una celda el
   texto se conserva igual: una marca por encima de la tabla no aportaba señal,
   solo podía conservar datos de producción. El mismo corte se aplica a ``role``
   y ``aria-live``, que comparten el contador de la concesión.

   **La frontera exacta es «en la fila, en la celda o por debajo».** Un
   ``<tr class="fila-error">`` cuenta: la fila es la unidad que una aplicación
   marca cuando rechaza un registro, y ese texto es la evidencia verbatim de
   QA-D2. Un ``<tbody class="mensaje-error">`` **no** cuenta, y tampoco
   ``<table>``, ``<thead>`` ni ``<tfoot>``: tienen la misma forma de falso
   positivo que el ``<div class="error-boundary">`` —envuelven la tabla entera—,
   así que se les aplica el corte igual que a un ancestro cualquiera.

4. **El valor de un atributo que el usuario LEE es texto, y se gobierna como
   el texto de una celda.** El caso que lo obliga es nuestro propio panel:
   ``<td><button aria-label="Acciones de Juan Pérez Quispe">⋮</button></td>``. La
   pasada de accesibilidad mete el nombre del sujeto de la fila DENTRO de un
   atributo, donde ni el vaciado de celdas lo veía ni el candado lo buscaba —el
   nombre sobrevivía al saneado y se comiteaba—. La regla **no** es una lista de
   nombres de atributo (ese es el error de forma que se corrigió en
   :data:`PIEZAS_DE_MENSAJE`) sino una pregunta con respuesta estructural:
   *¿renderiza el navegador este valor?* En el espacio ``aria-`` la responde la
   propia especificación, que declara el tipo de valor de cada estado y propiedad;
   así que se enumera la mitad **cerrada** —tokens, booleanos, números e IDREF
   (:data:`ARIA_SIN_PROSA`)— y **todo lo demás en ese espacio es prosa por
   defecto**. La inversión es lo que hace que la regla no envejezca: un
   ``aria-rowindextext`` —prosa, y justo dentro de una celda— queda cubierto sin
   que nadie lo haya escrito, y lo que la especificación añada mañana entra por el
   lado benigno (se vacía de más, no se comitea de menos). Fuera de ``aria-`` HTML
   no da ningún marcador, así que ahí sí hay una lista
   (:data:`ATRIBUTOS_RENDERIZADOS`) — pero decide qué se **borra**, que es la
   dirección barata, y cada entrada lleva su caso escrito abajo.

**Los atributos renderizados, uno por uno** (:data:`ATRIBUTOS_RENDERIZADOS`). Aquí
el caso no es «lo vimos en un sistema» sino «el navegador lo pinta», que es
comprobable sin explorar nada:

* ``title`` → el navegador lo pinta como *tooltip* al posar el cursor.
* ``alt`` → sustituye a la imagen cuando no carga, y lo lee el lector de pantalla.
* ``placeholder`` → se pinta dentro del control mientras está vacío.

  **Residual con dueño:** un ``placeholder`` de FORMATO dentro de una celda —una
  edición en línea, ``<td><input placeholder="RUC de 11 dígitos"></td>``— se vacía
  con el resto del texto de la celda, y ahí se pierde señal: ese texto es un límite
  citable **verbatim**, exactamente el estatus que QA-D2 exige para un caso de
  borde. La dirección es la barata (se pierde señal, no se comitea un dato) y el
  descarte queda anotado, así que quien captura lo ve. Pero el arreglo tiene dueño:
  es la mitad pendiente de (b) —**``aria-`` y sus vecinos como FUENTE DE RÓTULO**, y
  no solo como texto que se lee—, y **este es su primer test** el día que se abra.
* ``label`` → es el rótulo visible de un ``<option>``/``<optgroup>``/``<track>``.
* ``abbr`` → la forma corta del encabezado que anuncia el lector de pantalla.
* ``download`` → el nombre de fichero que ve quien descarga
  (``guia-########.pdf`` lleva el identificador dentro).

**``aria-describedby`` no está en ninguna de las dos listas, y es correcto**: su
valor es una lista de IDREF, no prosa. El texto de la descripción vive en el
elemento al que apunta, y ahí ya lo gobierna el mismo régimen que a cualquier otro
texto. Residual declarado: si ese elemento está FUERA de la celda —un
``<span class="sr-only">`` colgado al final del documento— su texto se conserva,
igual que se conserva todo el texto fuera de una celda, porque fuera de la celda el
texto es la evidencia.

**El vocabulario, pieza por pieza.** :data:`PIEZAS_DE_MENSAJE` tiene **17** piezas
y la lista es auditable a propósito: cada una lleva escrito su caso, porque una
lista de literales sin su caso al lado es indistinguible de una lista completada a
mano. La regla para añadir la dieciochoava es una sola —**una pieza = un caso
verificado en un sistema que exploramos de verdad**— y hay tres etiquetas:

* ``observado``: marca un mensaje en HTML que **este** repositorio renderiza.
* ``prospectivo``: su caso es una convención que se puede nombrar, en un sistema
  que NO hemos explorado. Vale como red secundaria; no cuenta como evidencia.
* ``heredado sin caso``: entró con la primera versión de la lista y no tiene ni lo
  uno ni lo otro. Se queda porque quitarla no es gratis —una fixture o un test
  puede depender de ella— pero **no** justifica añadir sus variantes.

La lista, una por línea, con su caso:

* ``destructive`` — **observado**: ``<p role="alert" class="… text-destructive">``
  en ``frontend/src/components/ui/field.tsx``. Es el error de campo de la casa.
* ``alert`` — **prospectivo**: Bootstrap escribe ``class="alert alert-danger"``. El
  token viaja en el **mismo atributo** que ``danger``, así que es la misma
  evidencia, no una variante deducida de ella.
* ``danger`` — **prospectivo**: Bootstrap en sistemas de terceros (``text-danger``,
  ``alert-danger``). **No observado en este repositorio.**
* ``error`` — **prospectivo**: el legado PHP/ExtJS (``x-form-error-msg``; §12.6 del
  diseño del Modo C). Nuestro frontend **no** lo usa —rotula con ``role="alert"``
  y ``text-destructive``—; sí lo usan las fixtures de ``qa_explore/``, y una
  fixture que escribimos nosotros no es una observación.
* ``invalid`` — **prospectivo**: ExtJS (``x-form-invalid-field``). Aparece en
  nuestro frontend, pero como prefijo de variante de Tailwind
  (``aria-invalid:border-destructive``) sobre un control: es una **aparición sin
  caso**, y además un vector de falso positivo, no una justificación.
* ``warning`` — **heredado sin caso**. Bootstrap tiene ``alert-warning``, pero
  tomarla por eso sería recorrer el enum de sufijos (``success``, ``info``…), que
  es exactamente la simetría prohibida.
* ``aviso`` — **heredado sin caso**.
* ``mensaje`` — **heredado sin caso**; lo usan las fixtures (``mensaje-error``,
  ``mensaje-ayuda``), que escribimos nosotros.
* ``message`` — **heredado sin caso**.
* ``help`` — **heredado sin caso**. Y con un falso positivo a la vista: Tailwind
  tiene ``cursor-help``, que casa por esta pieza sin ser un mensaje.
* ``hint`` — **heredado sin caso**, y con el caso EN CONTRA delante: el ``hint`` de
  ``ui/field.tsx`` se rotula ``text-meta-foreground``.
* ``ayuda`` — **heredado sin caso**; lo usan las fixtures (``mensaje-ayuda``).
* ``feedback`` — **heredado sin caso**.
* ``validation`` — **heredado sin caso**.
* ``validacion`` — **heredado sin caso**.
* ``required`` — **heredado sin caso**. En nuestro frontend ``required`` es un
  atributo de ``<input>``, nunca una pieza de ``class``.
* ``requerido`` — **heredado sin caso**.

**Candidato anotado y deliberadamente FUERA de la lista:** ``messages``, el plural
canónico de Django. Entra el día que se explore un sistema que lo emita, no antes.

**Tres piezas se fueron (de 20 a 17): ``errors``, ``errores`` y ``mensajes``.** El
conjunto llevaba esos tres plurales y no llevaba ``messages``, que es justo el
plural que un framework de verdad emite. Una asimetría así no sale de casos
observados: sale de completar plurales a mano. Y la dirección importa —quedarse
corto solo vacía el texto de una celda, ensanchar conserva datos de producción—,
así que ensanchar la fuga en el mismo commit que la cerró no se sostenía.

El candado (:func:`violaciones`) es lo que prueba que la línea quedó donde debía:
ninguna fixture con una secuencia de 8+ dígitos, ni el dominio de la casa, ni un
atributo ``value`` con contenido, ni un atributo de texto visible con contenido
dentro de una celda de datos. Es el mismo criterio con el que ``redact_dsn``
protege la introspección de INV2, aplicado al artefacto de test.

**REGLA DEL CANDADO: puede mirar una VENTANA DE TEXTO; nunca construir un árbol ni
consultar ancestros.** No es el criterio de esta vez, es el límite del sitio. El
candado tiene que valer igual para un ``.html``, un ``manifest.json`` y un README
—tres formatos de los que solo uno es un documento— y tiene que poder entenderlo
entero quien lo lee: un candado en el que hay que confiar sin entenderlo no es un
candado. Una ventana de subcadena (:data:`PATRON_CELDA`) cumple las dos cosas; un
árbol no cumple ninguna.

El corolario es la parte útil: **si una comprobación necesita el padre de algo, la
señal no es «hazla mejor», es que esa comprobación no va aquí.** Va en el saneador,
que sí parsea y sí tiene la pila de ancestros, y cuya salida vuelve a pasar por este
candado antes de tocar el disco. Así se resolvió F2 —distinguir el ``value`` de un
enum de dominio del ``value`` de un dato exige saber dentro de qué se está, es decir
árbol y ancestros— y así se resolverá la siguiente: el candado no crece hacia el
DOM, se queda tonto y la comprobación se muda.
"""

import re
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from typing import Any, Iterable, Optional, Sequence
from urllib.parse import urlparse

from ai.agents.qa.explore.dom import TAGS_VACIOS

#: Origen con el que se re-alojan las fixtures. El host real nunca se comitea, así
#: que el escenario guardado vive en un host inventado —el mismo que ya usan los
#: dobles de QC3, comprobado por test— y el guard lo autoriza como a cualquier otro.
ORIGEN_DE_FIXTURE = "https://tms.interno"

#: Dominios de la organización. No se comitean ni aunque nadie los pase como
#: argumento: el saneador los conoce y el candado los busca.
DOMINIOS_DE_LA_CASA = ("urbano.com.pe", "urbano.pe")

#: Elementos que se borran con su contenido. No son estructura observable: son
#: código y presentación, y los dos pueden llevar dentro rutas y credenciales.
ELEMENTOS_SUPRIMIDOS = frozenset({"script", "style"})

#: Los únicos ``<meta>`` que sobreviven. El resto es sesión, CSRF y telemetría.
META_CONSERVADAS = frozenset({"charset", "viewport"})

#: Atributos que se conservan **presentes y vacíos**: el hueco es parte de la
#: estructura (dice que el control tiene valor) y el contenido es el dato.
ATRIBUTOS_VACIADOS = frozenset({"value"})

#: Un atributo cuyo nombre contenga cualquiera de estos trozos se borra entero.
#:
#: **La asimetría con** :data:`PIEZAS_DE_MENSAJE` **es deliberada, no un descuido:
#: las dos listas empujan en direcciones opuestas.** Esta decide qué se BORRA, así
#: que casar de más es gratis (se pierde un atributo de presentación) y casar de
#: menos es una fuga. Por eso sigue siendo por subcadena: ``csrfmiddlewaretoken``
#: —el nombre real del campo de Django— es UNA pieza, y con comparación exacta el
#: token sobreviviría; lo mismo ``data-sessionid`` o ``authtoken``. La otra decide
#: qué se CONSERVA dentro de una celda de datos, así que casar de más conserva
#: datos de producción: ahí la comparación tiene que ser exacta.
NOMBRES_SENSIBLES = (
    "token",
    "csrf",
    "xsrf",
    "session",
    "sesion",
    "nonce",
    "jwt",
    "auth",
    "cookie",
    "secret",
)

#: Atributos ARIA cuyo valor **NO** es prosa. La lista está cerrada por la
#: especificación ARIA, que declara el tipo de valor de cada estado y propiedad:
#: aquí están todos los de tipo ``true/false``, ``tristate``, ``token``,
#: ``token list``, ``integer``, ``number``, ``ID reference`` e
#: ``ID reference list``.
#:
#: **Se enumera esta mitad y no la contraria a propósito.** La mitad de prosa es
#: la abierta —crece con la especificación y con lo que cada framework decida
#: rotular— y es la peligrosa: lo que no esté en ella se comitea. La mitad de
#: tokens es la cerrada, y dejarse una entrada fuera solo cuesta vaciar un token
#: dentro de una celda: se pierde señal, no se filtra un dato. Es la misma
#: asimetría de :data:`NOMBRES_SENSIBLES`, resuelta al revés porque aquí lo que se
#: enumera es la excepción.
ARIA_SIN_PROSA = frozenset(
    {
        # true/false y tristate
        "aria-atomic",
        "aria-busy",
        "aria-checked",
        "aria-disabled",
        "aria-expanded",
        "aria-grabbed",
        "aria-hidden",
        "aria-modal",
        "aria-multiline",
        "aria-multiselectable",
        "aria-pressed",
        "aria-readonly",
        "aria-required",
        "aria-selected",
        # token y token list
        "aria-autocomplete",
        "aria-current",
        "aria-dropeffect",
        "aria-haspopup",
        "aria-invalid",
        "aria-live",
        "aria-orientation",
        "aria-relevant",
        "aria-sort",
        # ID reference y ID reference list
        "aria-activedescendant",
        "aria-controls",
        "aria-describedby",
        "aria-details",
        "aria-errormessage",
        "aria-flowto",
        "aria-labelledby",
        "aria-owns",
        # integer y number
        "aria-colcount",
        "aria-colindex",
        "aria-colspan",
        "aria-level",
        "aria-posinset",
        "aria-rowcount",
        "aria-rowindex",
        "aria-rowspan",
        "aria-setsize",
        "aria-valuemax",
        "aria-valuemin",
        "aria-valuenow",
    }
)

#: Atributos **fuera** del espacio ``aria-`` cuyo valor el navegador renderiza.
#: HTML no tiene un prefijo que los agrupe, así que esta mitad sí es una lista; el
#: caso de cada entrada está en el docstring del módulo, y es comprobable sin
#: explorar nada («el navegador lo pinta»). Decide qué se BORRA, así que casar de
#: más solo cuesta un atributo de presentación.
ATRIBUTOS_RENDERIZADOS = frozenset(
    {"title", "alt", "placeholder", "label", "abbr", "download"}
)

#: Atributos cuyo valor puede ser una URL absoluta al host explorado.
ATRIBUTOS_URL = frozenset(
    {"href", "action", "src", "formaction", "poster", "cite", "data-url", "content"}
)

#: Elementos que **rotulan**: su texto es evidencia, no dato, incluso dentro de
#: una tabla. Es la mitad de A3 que evita que el saneador se lleve la señal.
TAGS_ROTULO = frozenset(
    {
        "label",
        "option",
        "optgroup",
        "legend",
        "caption",
        "th",
        "summary",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }
)

#: Envoltorios de una tabla. Son estructura, nunca un mensaje: una marca puesta
#: **aquí** tiene la misma forma de falso positivo que el
#: ``<div class="error-boundary">`` —cubre la tabla entera— así que ni se hereda ni
#: cuenta para el propio elemento. Es la mitad de arriba de la frontera «en la
#: fila, en la celda o por debajo».
ENVOLTORIOS_TABULARES = frozenset({"table", "thead", "tbody", "tfoot"})

#: Elementos de estructura tabular. Abrir cualquiera de ellos **corta la herencia**
#: de la concesión de mensaje: solo cuenta una marca puesta en la fila, en la celda
#: o por debajo. Sin este corte, un ``<div class="error-boundary">`` —un envoltorio
#: de React, no un mensaje— alrededor de una tabla conservaba la tabla entera. Y no
#: se pierde nada: fuera de una celda el texto se conserva de todas formas, así
#: que una marca por encima de la tabla nunca aportaba, solo podía conservar de más.
#:
#: ``<tr>`` está aquí —corta lo que hereda— pero **no** en
#: :data:`ENVOLTORIOS_TABULARES`: su propia marca sí cuenta, porque la fila es la
#: unidad que una aplicación marca cuando rechaza un registro.
TAGS_TABULARES = ENVOLTORIOS_TABULARES | {"tr"}

#: Piezas de ``class``/``id`` con las que una aplicación marca un mensaje. Un
#: mensaje de error renderizado es una validación observada: sobrevive.
#:
#: **Se comparan como piezas EXACTAS, nunca por subcadena.** Por subcadena,
#: ``<td class="terror">`` casaba con ``error`` y conservaba el dato de la celda:
#: una fuga que fallaba hacia conservar, que es la dirección mala. El valor se
#: trocea por sus separadores (:data:`PATRON_PIEZAS`) y cada pieza se busca aquí.
#:
#: La lista es de piezas literales a propósito: añadir una variante es una línea y
#: no cambia la semántica de nadie. Casar de menos solo vacía el texto de una celda
#: —se pierde señal, no se filtra un dato—, así que el default es benigno.
#:
#: **El caso de cada pieza está escrito en el docstring del módulo, una por línea**
#: (``observado`` / ``prospectivo`` / ``heredado sin caso``). Se añade una pieza
#: cuando hay **un caso verificado en un sistema que exploramos de verdad**, y
#: completarla «por simetría» —el plural de otra, el resto del enum de sufijos de
#: Bootstrap— **está prohibido**: el motivo está en §12.6 del diseño del Modo C.
PIEZAS_DE_MENSAJE = frozenset(
    {
        "error",
        "invalid",
        "warning",
        "alert",
        "aviso",
        "danger",
        "destructive",
        "mensaje",
        "message",
        "help",
        "hint",
        "ayuda",
        "feedback",
        "validation",
        "validacion",
        "required",
        "requerido",
    }
)

#: Con qué se trocean ``class`` e ``id``: cualquier corrida de caracteres que no
#: sea alfanumérica. Cubre los separadores de la casa (``-``, ``_``, ``:``, espacio)
#: y también los de Tailwind (``md:text-destructive/50``).
PATRON_PIEZAS = re.compile(r"[^a-z0-9]+")

#: Roles ARIA que declaran un mensaje al usuario.
ROLES_DE_MENSAJE = frozenset({"alert", "alertdialog", "status"})

#: Una secuencia larga de dígitos es un identificador de negocio (guía, RUC, DNI).
PATRON_DIGITOS = re.compile(r"\d{8,}")

#: Con qué se sustituye. No son dígitos, así que el candado no se muerde la cola.
MASCARA = "########"

#: El atributo ``value`` con contenido, en cualquiera de las tres formas que
#: admite HTML. El ``(?<![-\w])`` evita confundirlo con ``data-value``.
PATRON_VALUE = re.compile(
    r"""(?<![-\w])value\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>"']+))""",
    re.IGNORECASE,
)

#: La **ventana** de una celda de datos, en texto plano. Es la cosa más tonta que
#: sirve para la cuarta comprobación del candado: una subcadena entre ``<td`` y
#: ``</td>``, sin árbol, sin ancestros y sin anidamiento. El candado no mira el DOM
#: —eso es justo lo que lo hace confiable sobre un ``.html``, un ``.json`` y un
#: README— pero un ``aria-label`` con contenido FUERA de una celda es legítimo, así
#: que sin saber dónde está no hay comprobación posible.
PATRON_CELDA = re.compile(r"<td\b.*?</td\s*>", re.IGNORECASE | re.DOTALL)

#: Una etiqueta de apertura y su bloque de atributos, dentro de esa ventana.
PATRON_ETIQUETA = re.compile(r"<([a-z][a-z0-9:-]*)\b([^>]*)>", re.IGNORECASE)

#: Un atributo con valor, en las tres formas que admite HTML.
PATRON_ATRIBUTO = re.compile(
    r"""([a-zA-Z_:][-\w:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>"']+))"""
)

_DESCARTADO: Any = object()


@dataclass(frozen=True)
class Retirado:
    """Algo que el saneador quitó. Los descartes nunca son silenciosos."""

    clase: str
    detalle: str


@dataclass(frozen=True)
class ResultadoSaneado:
    """El HTML limpio y el inventario de lo que se le quitó."""

    html: str
    retirados: tuple[Retirado, ...] = ()

    def clases_retiradas(self) -> set[str]:
        return {retirado.clase for retirado in self.retirados}


@dataclass(frozen=True)
class Violacion:
    """Un candado roto, con la línea para poder arreglarlo."""

    clase: str
    detalle: str
    linea: int

    def __str__(self) -> str:  # pragma: no cover - solo para el mensaje del test
        return f"línea {self.linea}: {self.detalle}"


class CapturaSuciaError(RuntimeError):
    """Lo saneado sigue violando el candado: no se escribe nada."""


def _hosts_efectivos(hosts: Iterable[str]) -> tuple[str, ...]:
    """Los hosts a ocultar, más los dominios de la casa. Nunca menos."""
    declarados = tuple(h.strip().lower() for h in hosts if (h or "").strip())
    return declarados + DOMINIOS_DE_LA_CASA


def _es_de_la_casa(host: str, prohibidos: Sequence[str]) -> bool:
    host = (host or "").lower()
    return any(host == p or host.endswith("." + p) for p in prohibidos)


def _piezas(*valores: Optional[str]) -> set[str]:
    """Trocea cada valor por separado y devuelve la unión de sus piezas.

    Por separado a propósito: si se concatenaran ``class`` e ``id`` antes de
    trocear, dos valores inocentes podrían formar una pieza que ninguno de los
    dos tiene.
    """
    piezas: set[str] = set()
    for valor in valores:
        piezas.update(p for p in PATRON_PIEZAS.split((valor or "").lower()) if p)
    return piezas


def _es_rotulo(tag: str, attrs: dict[str, Optional[str]]) -> bool:
    """¿Este elemento **rotula**? Su texto es evidencia, no dato.

    Vive aquí, y no dentro del saneador, porque el candado tiene que reconocer un
    rótulo exactamente igual: dos copias de esta pregunta se separan el día que
    alguien añada una señal a una sola de ellas.
    """
    if tag in TAGS_ROTULO:
        return True
    if (attrs.get("role") or "").strip().lower() in ROLES_DE_MENSAJE:
        return True
    if "aria-live" in attrs:
        return True
    return bool(_piezas(attrs.get("class"), attrs.get("id")) & PIEZAS_DE_MENSAJE)


def _es_texto_visible(nombre: str) -> bool:
    """¿Renderiza el navegador el valor de este atributo?

    Si la respuesta es sí, el valor es **texto que lee un usuario** y se gobierna
    como el texto de una celda: dentro de una celda de datos se vacía, fuera se
    conserva enmascarado. La pregunta se responde por **estructura**: en el
    espacio ``aria-`` la especificación declara el tipo de cada atributo, así que
    se enumera la mitad cerrada (:data:`ARIA_SIN_PROSA`) y lo demás es prosa por
    defecto; fuera de ``aria-`` HTML no agrupa nada y queda la lista
    :data:`ATRIBUTOS_RENDERIZADOS`, con el caso de cada entrada en el docstring
    del módulo.
    """
    nombre = nombre.lower()
    if nombre.startswith("aria-"):
        return nombre not in ARIA_SIN_PROSA
    return nombre in ATRIBUTOS_RENDERIZADOS


class _Saneador(HTMLParser):
    """Reescribe el HTML conservando la forma y vaciando el contenido.

    ``convert_charrefs=False`` a propósito: las entidades se re-emiten tal cual
    en vez de decodificarse y volver a escaparse, de modo que el saneado es
    **idempotente** —sanear dos veces da lo mismo que sanear una—, que es lo que
    permite ejecutarlo sobre una fixture ya comiteada sin dañarla.
    """

    def __init__(self, hosts_prohibidos: Sequence[str]) -> None:
        super().__init__(convert_charrefs=False)
        self._hosts = hosts_prohibidos
        self._piezas: list[str] = []
        self._retirados: list[Retirado] = []
        #: (tag, suprimido, celda, rotulo, concesión heredada que hay que restaurar)
        self._pila: list[tuple[str, bool, bool, bool, Optional[int]]] = []
        self._suprimidos = 0
        self._celdas = 0
        self._rotulos = 0

    # --- resultado ------------------------------------------------------------

    def resultado(self) -> ResultadoSaneado:
        return ResultadoSaneado(
            html="".join(self._piezas), retirados=tuple(self._retirados)
        )

    def _anotar(self, clase: str, detalle: str) -> None:
        self._retirados.append(Retirado(clase=clase, detalle=detalle))

    # --- el texto que lee un usuario -----------------------------------------

    def _gobernar_texto(self, texto: str, *, origen: str, vaciar: bool) -> str:
        """El **único** sitio donde se decide qué pasa con el texto visible.

        Da igual si viene del cuerpo de una celda o del valor de un atributo que el
        navegador renderiza: el régimen es el mismo y está escrito una sola vez.
        Por eso gobernar un atributo nuevo es añadirlo a la pregunta de
        :func:`_es_texto_visible`, no repetir aquí la decisión.
        """
        if vaciar:
            if not texto.strip():
                return texto
            self._anotar(
                "dato", f"Contenido de {origen} ({len(texto.strip())} caracteres)"
            )
            return _solo_espacios(texto)
        return self._enmascarar(texto, origen=origen)

    # --- atributos ------------------------------------------------------------

    def _acortar_url(self, valor: str) -> str:
        partes = urlparse(valor)
        if partes.scheme.lower() not in ("http", "https"):
            return valor
        if not _es_de_la_casa(partes.hostname or "", self._hosts):
            return valor
        camino = partes.path or "/"
        if partes.query:
            camino = f"{camino}?{partes.query}"
        if partes.fragment:
            camino = f"{camino}#{partes.fragment}"
        self._anotar("host", f"URL absoluta reescrita a «{camino}»")
        return camino

    def _enmascarar(self, texto: str, *, origen: str) -> str:
        limpio = PATRON_DIGITOS.sub(MASCARA, texto)
        if limpio != texto:
            self._anotar("digitos", f"Secuencia larga de dígitos en {origen}")
        return limpio

    def _sanear_atributo(
        self, nombre: str, valor: Optional[str], *, vaciar_texto: bool
    ) -> Any:
        nombre = nombre.lower()
        if nombre.startswith("on"):
            self._anotar("manejador", f"Atributo «{nombre}»")
            return _DESCARTADO
        if any(marca in nombre for marca in NOMBRES_SENSIBLES):
            self._anotar("token", f"Atributo «{nombre}»")
            return _DESCARTADO
        if nombre in ATRIBUTOS_VACIADOS:
            if valor:
                self._anotar("value", f"Contenido de «{nombre}»")
            return ""
        if valor is None:
            return None
        if nombre in ATRIBUTOS_URL:
            valor = self._acortar_url(valor)
        # El valor que el navegador renderiza es texto que lee un usuario, así que
        # se gobierna igual que el texto de una celda. Sin esto, la pasada de
        # accesibilidad metía el nombre del sujeto de la fila en un `aria-label` y
        # el vaciado de celdas —que solo miraba el cuerpo— no lo veía.
        if _es_texto_visible(nombre):
            return self._gobernar_texto(
                valor, origen=f"el atributo «{nombre}»", vaciar=vaciar_texto
            )
        return self._enmascarar(valor, origen=f"el atributo «{nombre}»")

    def _apertura(self, tag: str, attrs, cierre_propio: bool, vaciar: bool) -> str:
        partes = [tag]
        for nombre, valor in attrs:
            saneado = self._sanear_atributo(nombre or "", valor, vaciar_texto=vaciar)
            if saneado is _DESCARTADO:
                continue
            if saneado is None:
                partes.append((nombre or "").lower())
            else:
                partes.append(
                    f'{(nombre or "").lower()}="{escape(saneado, quote=True)}"'
                )
        return "<" + " ".join(partes) + ("/>" if cierre_propio else ">")

    # --- ganchos del parser ---------------------------------------------------

    def _abrir(self, tag: str, attrs, cierre_propio: bool) -> None:
        tag = tag.lower()
        mapa = {(n or "").lower(): v for n, v in attrs}

        suprimido = tag in ELEMENTOS_SUPRIMIDOS
        if suprimido:
            self._anotar("elemento", f"<{tag}> con su contenido")
        elif tag == "meta" and not (set(mapa) & META_CONSERVADAS):
            self._anotar("meta", f"<meta {' '.join(sorted(mapa)) or 'vacío'}>")
            return

        celda = tag == "td"
        # Un ``<tbody class="mensaje-error">`` es un envoltorio, no un mensaje: su
        # marca no cuenta ni para sí misma. La fila sí, y por eso ``<tr>`` no está
        # en este conjunto.
        rotulo = tag not in ENVOLTORIOS_TABULARES and _es_rotulo(tag, mapa)

        # El régimen de los atributos de ESTE elemento suma su propia condición: un
        # ``<td aria-label=…>`` ya está en la celda que abre, y un
        # ``<label title=…>`` rotula sus propios atributos igual que su texto. Los
        # contadores todavía no se han incrementado, así que se suman aquí.
        vaciar = bool(self._celdas + int(celda)) and not (self._rotulos + int(rotulo))

        if not suprimido and self._suprimidos == 0:
            self._piezas.append(self._apertura(tag, attrs, cierre_propio, vaciar))

        if cierre_propio or tag in TAGS_VACIOS:
            return

        # La estructura tabular corta la herencia de la concesión de mensaje: lo
        # que valga aquí dentro tiene que estar marcado desde la fila, la celda o
        # por debajo. La marca del propio elemento se suma después del corte, así
        # que un ``<tr>`` marcado se concede a sí mismo lo que no hereda.
        guardado: Optional[int] = None
        if tag in TAGS_TABULARES:
            guardado = self._rotulos
            self._rotulos = 0

        self._pila.append((tag, suprimido, celda, rotulo, guardado))
        self._suprimidos += int(suprimido)
        self._celdas += int(celda)
        self._rotulos += int(rotulo)

    def handle_starttag(self, tag: str, attrs) -> None:
        self._abrir(tag, attrs, cierre_propio=False)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self._abrir(tag, attrs, cierre_propio=True)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not any(marco[0] == tag for marco in self._pila):
            # Cierre huérfano: se descarta, como haría el navegador.
            return
        while self._pila:
            nombre, suprimido, celda, rotulo, guardado = self._pila.pop()
            self._suprimidos -= int(suprimido)
            self._celdas -= int(celda)
            self._rotulos -= int(rotulo)
            if guardado is not None:
                self._rotulos = guardado
            if not suprimido and self._suprimidos == 0:
                self._piezas.append(f"</{nombre}>")
            if nombre == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._suprimidos:
            return
        en_celda = bool(self._celdas) and not self._rotulos
        self._piezas.append(
            self._gobernar_texto(
                data,
                origen="la celda" if en_celda else "el texto",
                vaciar=en_celda,
            )
        )

    def handle_entityref(self, name: str) -> None:
        if self._suprimidos or (self._celdas and not self._rotulos):
            return
        self._piezas.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._suprimidos or (self._celdas and not self._rotulos):
            return
        self._piezas.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._anotar("comentario", f"Comentario de {len(data)} caracteres")

    def handle_decl(self, decl: str) -> None:
        self._piezas.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self._anotar("instruccion", "Instrucción de proceso")


def _solo_espacios(data: str) -> str:
    """Conserva el sangrado de una celda vaciada: la fixture sigue siendo legible."""
    delante = data[: len(data) - len(data.lstrip())]
    detras = data[len(data.rstrip()) :]
    return delante + detras


def sanear_html(html: str, *, hosts_a_ocultar: Iterable[str] = ()) -> ResultadoSaneado:
    """Aplica A3 a una página capturada. No toca la red ni el disco."""
    saneador = _Saneador(_hosts_efectivos(hosts_a_ocultar))
    saneador.feed(html or "")
    saneador.close()
    return saneador.resultado()


def _atributos_de(bloque: str) -> dict[str, str]:
    """Los atributos de una etiqueta, sin construir nada parecido a un DOM."""
    return {
        nombre.lower(): next(v for v in (dobles, simples, suelto) if v is not None)
        for nombre, dobles, simples, suelto in PATRON_ATRIBUTO.findall(bloque)
    }


def _texto_visible_en_celdas(texto: str) -> list[Violacion]:
    """La cuarta comprobación: un nombre metido en un atributo de una celda.

    El caso es el panel de usuarios de la casa —``<td><button aria-label="Acciones
    de …">``— y lo que lo hace peligroso es que ni el vaciado de celdas del
    saneador lo veía (mira el cuerpo, no los atributos) ni el candado lo buscaba.
    Hace falta aquí, y no solo en el saneador, porque **las trampas se escriben a
    mano y nunca pasan por él**.

    La escapatoria de rótulo es la del saneador —la misma :func:`_es_rotulo`, no
    una copia— aplicada a la etiqueta que lleva el atributo. Residual declarado:
    mira esa etiqueta, no sus ancestros, así que un ``<td class="mensaje-error">``
    con un botón dentro salta aquí y no allí. Es la dirección segura —el candado
    puede ser más estricto que el saneador, nunca al revés— y se arregla a mano.
    """
    encontradas: list[Violacion] = []
    for celda in PATRON_CELDA.finditer(texto):
        for etiqueta in PATRON_ETIQUETA.finditer(celda.group(0)):
            atributos = _atributos_de(etiqueta.group(2))
            if _es_rotulo(etiqueta.group(1).lower(), atributos):
                continue
            inicio = celda.start() + etiqueta.start()
            for nombre, valor in sorted(atributos.items()):
                if valor.strip() and _es_texto_visible(nombre):
                    encontradas.append(
                        Violacion(
                            "texto",
                            f"El atributo «{nombre}» lleva «{valor}» dentro de una "
                            "celda de datos: lo que el usuario lee es texto, y el "
                            "texto de una celda no se comitea.",
                            texto.count("\n", 0, inicio) + 1,
                        )
                    )
    return encontradas


def violaciones(texto: str, *, hosts_prohibidos: Iterable[str] = ()) -> list[Violacion]:
    """El candado sobre las fixtures. Cuatro comprobaciones, ni una más.

    Es deliberadamente tonto —trabaja sobre el texto, no sobre el DOM— porque
    tiene que valer igual para un ``.html``, un ``manifest.json`` y un README, y
    porque un candado que hay que entender para confiar en él no es un candado.
    Las tres primeras ni siquiera miran dónde está lo que encuentran: un RUC, el
    dominio de la casa y un ``value`` con contenido están de más en cualquier
    sitio. La cuarta —:func:`_texto_visible_en_celdas`— es la única que necesita
    saberlo, y por eso usa lo más tonto que sirve: una ventana de subcadena.

    El límite está escrito arriba, en el docstring del módulo, y es una **regla**:
    una ventana de texto sí, un árbol y sus ancestros nunca. Lo que necesite el
    padre no va aquí — va al saneador, cuya salida vuelve a pasar por este candado.
    """
    prohibidos = _hosts_efectivos(hosts_prohibidos)
    encontradas: list[Violacion] = []
    for numero, linea in enumerate((texto or "").splitlines(), start=1):
        digitos = PATRON_DIGITOS.search(linea)
        if digitos:
            encontradas.append(
                Violacion(
                    "digitos",
                    f"Secuencia de 8+ dígitos «{digitos.group(0)}»: parece un "
                    "identificador de negocio (guía, RUC, DNI).",
                    numero,
                )
            )
        minuscula = linea.lower()
        for host in prohibidos:
            if host in minuscula:
                encontradas.append(
                    Violacion(
                        "host",
                        f"Aparece el host «{host}»: una fixture no lleva escrito "
                        "el mapa de la infraestructura.",
                        numero,
                    )
                )
                break
        for hallazgo in PATRON_VALUE.finditer(linea):
            contenido = next(g for g in hallazgo.groups() if g is not None)
            if contenido:
                encontradas.append(
                    Violacion(
                        "value",
                        f"Atributo de valor con contenido «{contenido}»: el hueco "
                        "se conserva, el dato no.",
                        numero,
                    )
                )
    encontradas.extend(_texto_visible_en_celdas(texto or ""))
    # Estable: dentro de una misma línea se respeta el orden en que se hallaron.
    return sorted(encontradas, key=lambda violacion: violacion.linea)


@dataclass(frozen=True)
class Escenario:
    """Lo que se escribe en ``tests/fixtures/qa_explore/<escenario>/``."""

    archivos: dict[str, str] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
    retirados: tuple[Retirado, ...] = ()


def _nombre_de(indice: int, path: str) -> str:
    trozo = re.sub(r"[^a-z0-9]+", "_", (path or "/").lower()).strip("_")
    return f"{indice:02d}_{trozo or 'raiz'}.html"


def escenario_saneado(
    paginas: Sequence[Any],
    *,
    hosts_a_ocultar: Iterable[str] = (),
    origen: str = ORIGEN_DE_FIXTURE,
) -> Escenario:
    """Sanea las páginas observadas y arma el ``manifest.json`` del escenario.

    Aquí es donde el saneador deja de ser opcional: si después de sanear algo
    sigue violando el candado, esto **lanza** y no se escribe ni un fichero. Un
    aviso por consola se lee cuando ya está comiteado.
    """
    archivos: dict[str, str] = {}
    paginas_manifest: dict[str, Any] = {}
    orden: list[str] = []
    retirados: list[Retirado] = []

    for indice, pagina in enumerate(paginas):
        resultado = sanear_html(pagina.html, hosts_a_ocultar=hosts_a_ocultar)
        retirados.extend(resultado.retirados)
        nombre = _nombre_de(indice, pagina.path)
        archivos[nombre] = resultado.html
        paginas_manifest[pagina.path] = {
            "status": pagina.status,
            "file": nombre,
            "depth": pagina.depth,
        }
        orden.append(pagina.path)

    manifest = {
        "origin": origen,
        "entry": orden[0] if orden else "/",
        "visit_order": orden,
        "pages": paginas_manifest,
        "clicks": {},
    }

    sucios = {
        nombre: violaciones(contenido, hosts_prohibidos=hosts_a_ocultar)
        for nombre, contenido in archivos.items()
    }
    sucios = {nombre: v for nombre, v in sucios.items() if v}
    if sucios:
        detalle = "; ".join(
            f"{nombre}: " + ", ".join(str(v) for v in lista)
            for nombre, lista in sorted(sucios.items())
        )
        raise CapturaSuciaError(
            "La captura saneada todavía viola el candado de fixtures y por eso no "
            f"se escribe nada. {detalle}"
        )

    return Escenario(archivos=archivos, manifest=manifest, retirados=tuple(retirados))
