"""QC4.5 — el extractor determinista de anclas: HTML entra, anclas salen.

Este módulo es la mitad barata del Modo C, y la que decide si el resto sirve de
algo. ``SURFACE_MAP`` (QC5) es el cortafuegos anti-invención del modo —el gemelo
de ``CRITERION_MAP``, ``MODEL_MAP`` y ``RESOURCE_MAP``— y un cortafuegos solo vale
lo que valga la lista cerrada que le da de comer. Esa lista se fabrica aquí, en
Python, **antes** de gastar un token: el modelo no elige *qué* hay, solo redacta
*cómo* se prueba lo que hay.

De ahí las tres cosas que este módulo NO hace, y que no son omisiones:

* **No sale a la red, no abre un navegador y no pulsa nada.** Recibe el HTML como
  cadena (§6.2 del diseño del Modo C: *el extractor no conoce el navegador*). Es
  lo que permite ejercer el 99% del Modo C en un host donde Chromium no arranca.
* **No llama al LLM.** Un atributo de validación es un hecho del documento; pedirle
  a un modelo que lo lea sería pagar por una alucinación posible donde hay una
  certeza gratis.
* **No escribe nada, ni lee de ``tests/``.** Es una función pura: mismas entradas,
  mismas salidas, mismo orden.

**El vocabulario de anclas es CERRADO y un atributo es UN ancla** (§2.1). Que
``required`` y ``maxlength`` del mismo campo sean dos anclas y no una no es
burocracia: habilitan casos distintos y se pueden romper por separado, así que
fundirlas escondería media rotura. Lo que no está en :data:`ATRIBUTOS_ANCLA` no se
ancla — y eso incluye ``value``, que es el dato y no el límite.

**Sin selector estable no se emite ancla.** Un ancla que no se puede reconstruir en
la corrida siguiente no sirve para lo único que hace útil a una suite de
caracterización: comparar dos corridas. Un hueco se ve en la cobertura; un ancla
que no resuelve es un caso que fallará por el motivo equivocado, y eso es ruido con
aspecto de hallazgo.

**La divergencia F2, que este módulo hace visible y no resuelve.** El saneador vacía
todo atributo ``value`` antes de comitear una fixture, porque un ``value`` es un
dato de producción; el ``value`` de un ``<option>``, en cambio, es el **conjunto de
lo aceptado**, es decir un límite citable. Distinguirlos exige saber dentro de qué
elemento se está —árbol y ancestros—, y el candado de fixtures tiene prohibido
construir un árbol (la regla está escrita en ``sanitize.py``). Consecuencia asumida
y **fijada con un test**: sobre HTML crudo el extractor ve el enum de un
``<select>``; sobre la fixture saneada del mismo ``<select>`` no ve ninguno. No se
parchea aquí: un enum inventado a partir de valores vacíos sería exactamente el
error que este agente no puede cometer.
"""

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

from ai.agents.qa.explore import dom

#: Los controles de los que se extraen anclas. ``<button>`` no está: su ``type``
#: no restringe un dato, decide si envía — eso lo gobierna la política de pulsado
#: (``clicking.py``), que es una decisión de seguridad y no un ancla de prueba.
CONTROLES = frozenset({"input", "select", "textarea"})

#: **El vocabulario de anclas, cerrado, con el caso de cada entrada al lado.** Una
#: lista de atributos sin su caso escrito es indistinguible de una lista copiada de
#: la especificación de HTML, y entonces nadie sabe por qué falta el que falta.
ATRIBUTOS_ANCLA: dict[str, str] = {
    "required": "enviar el campo vacío tiene que ser rechazado",
    "maxlength": "un carácter por encima del límite no debe aceptarse",
    "minlength": "un carácter por debajo del mínimo no debe aceptarse",
    "pattern": "un valor que no case con la expresión debe rechazarse",
    "min": "un valor por debajo del mínimo debe rechazarse",
    "max": "un valor por encima del máximo debe rechazarse",
    "step": "un valor que no sea múltiplo del paso debe rechazarse",
    "type": "un valor con forma ajena al tipo debe rechazarse",
    "readonly": "el campo no acepta edición y su valor no cambia al enviar",
    "accept": "un fichero con extensión fuera de la lista debe rechazarse",
    "multiple": "el control admite más de un valor a la vez",
}

#: El ancla que no es un atributo: el conjunto de valores aceptados por un
#: ``<select>``. Se llama ``enum`` y no ``options`` porque lo que ancla el caso es
#: el **conjunto cerrado**, no el número de opciones.
ANCLA_ENUM = "enum"

#: El caso del ancla de enum, en la misma forma que los del vocabulario.
CASO_ENUM = "un valor fuera del conjunto de opciones debe rechazarse"

#: Valores de ``type`` que **restringen la forma del dato**. Los demás (``text``,
#: ``password``, ``search``, ``hidden``, ``checkbox``, ``radio``, ``submit``…) no
#: restringen nada, y un caso «escribe texto en un campo de texto» es ruido que
#: entierra al que importa — el mismo motivo por el que las preguntas al DBA se
#: agrupan por clase de vacío. Lo que se pierde al no anclarlos es cero: el límite
#: real de esos campos vive en ``maxlength``/``pattern``/``required``, que sí se
#: anclan.
TIPOS_QUE_RESTRINGEN = frozenset(
    {
        "number",
        "email",
        "url",
        "tel",
        "date",
        "time",
        "datetime-local",
        "month",
        "week",
        "range",
        "color",
        "file",
    }
)

#: **Candidatos anotados y deliberadamente FUERA del vocabulario**, con su motivo,
#: por la misma razón que ``messages`` está anotado fuera de ``PIEZAS_DE_MENSAJE``:
#:
#: * ``value`` → es el dato, no el límite. Es justo lo que el saneador vacía.
#: * ``disabled`` → un campo deshabilitado no se envía, así que no hay nada que
#:   probar sobre su validación; lo que se prueba es que esté deshabilitado, y eso
#:   es un caso de estado de la pantalla, no un límite de dato.
#: * ``placeholder`` → puede llevar el formato («RUC de 11 dígitos») y por tanto un
#:   límite citable, pero es **texto**, no una restricción que el navegador imponga.
#:   Anclarlo mezclaría lo observado con lo insinuado. Es la mitad pendiente de
#:   ``aria-``/``placeholder`` **como fuente de rótulo**, con dueño escrito en
#:   ``sanitize.py``.
#: * ``inputmode``/``autocomplete`` → sugerencias al teclado y al gestor de
#:   contraseñas. No rechazan nada.
CANDIDATOS_FUERA = ("value", "disabled", "placeholder", "inputmode", "autocomplete")

#: La estrategia de último recurso: la posición estructural. **Nace marcada como
#: frágil** —un ``<div>`` nuevo la rompe— para que quien lea el plan sepa cuáles
#: son antes de que fallen (§2.1: ``CRITIQUE`` emitirá un ``Risk`` con su
#: porcentaje).
ESTRATEGIA_ESTRUCTURAL = "structural"

#: El orden de preferencia del selector de un ancla. **Extiende** el de pulsar
#: (:data:`dom.ESTRATEGIAS`) en vez de copiarlo, que es lo que impide que las dos
#: listas se separen.
#:
#: Las dos que se añaden aquí **no** se añaden a la de pulsar, y la asimetría es
#: deliberada: un selector que una traducción rompe (``aria-label``) o que un
#: envoltorio nuevo rompe (``structural``) es suficiente para **anclar** un caso
#: que una persona va a leer, y no es suficiente para **pulsar** contra una
#: aplicación viva, donde equivocarse de elemento es una acción, no una nota.
ESTRATEGIAS_POR_ATRIBUTO = dom.ESTRATEGIAS + ("aria-label",)
ESTRATEGIAS_DE_ANCLA = ESTRATEGIAS_POR_ATRIBUTO + (ESTRATEGIA_ESTRUCTURAL,)

#: Cuáles de ellas producen un ancla **frágil**. Solo la estructural, y
#: ``aria-label`` no está por un motivo que conviene decir: un ``aria-label`` que
#: cambia es un cambio en lo que el usuario lee, y una suite de caracterización
#: **debe** enterarse de eso; un ``<div>`` de maquetación que aparece no cambia
#: nada observable y aun así rompería el ancla. Frágil no es «puede cambiar», es
#: «puede romperse sin que haya cambiado nada que importe».
ESTRATEGIAS_FRAGILES = frozenset({ESTRATEGIA_ESTRUCTURAL})

#: Una etiqueta que se puede escribir como selector de tipo en CSS. Un
#: ``<asp:TextBox>`` de WebForms **no** lo es: ``asp:textbox`` se leería como
#: pseudo-clase. Ver :func:`selector_de_ancla`.
PATRON_TAG_CSS = re.compile(r"^[a-z][a-z0-9-]*$")

#: Con qué se separan los valores de un enum al presentarlos en ``value``. La
#: evidencia autoritativa es el fragmento literal, no esta cadena.
SEPARADOR_ENUM = " | "


@dataclass(frozen=True)
class Ancla:
    """Un ancla observada: un atributo de un control, con su evidencia literal.

    **Dataclass local a propósito, sin depender del contrato de QC1.** El
    ``QaArtifact`` v1.1.0 y su ``SurfaceAnchor`` todavía no existen, y hacer que
    este módulo los espere lo ataría al orden de los bloques: QC5 traduce esta
    forma a aquella, que es una función de tres líneas, y mientras tanto el
    extractor se puede probar y usar hoy.
    """

    ref: str
    path: str
    selector: str
    selector_strategy: str
    attribute: str
    value: str
    evidence: str
    linea: int

    @property
    def fragil(self) -> bool:
        """¿El ancla se puede romper sin que cambie nada observable?"""
        return self.selector_strategy in ESTRATEGIAS_FRAGILES

    @property
    def caso(self) -> str:
        """El caso que este ancla habilita, del vocabulario cerrado."""
        if self.attribute == ANCLA_ENUM:
            return CASO_ENUM
        return ATRIBUTOS_ANCLA[self.attribute]


def anchor_ref(path: str, selector: str, atributo: str) -> str:
    """La forma canónica de §2.1: ``UI:<path>#<selector>@<atributo>``.

    Función pura y única fabricante de refs. Dos exploraciones de la misma
    pantalla tienen que producir la misma cadena o no se pueden comparar dos
    corridas, que es lo único que hace útil a una suite de caracterización.

    **Recibe un *path*, nunca una URL, y lo comprueba.** No es cosmética: el host
    viene del alias y no se guarda en el ref (capa 4 — el destino no viaja en el
    artefacto más de lo necesario, y el alias ni siquiera llega al prompt, A1). Una
    URL que se colara aquí llevaría el mapa de la infraestructura a un CSV que se
    exporta, así que se rechaza en vez de recortarse: recortar en silencio acepta
    la equivocación de quien llama y la repite en la siguiente.
    """
    _assert_path(path)
    if not selector.strip():
        raise ValueError("Un ancla sin selector no se puede reconstruir: no hay ref.")
    if not atributo.strip():
        raise ValueError("Un ancla es un atributo: sin atributo no hay ref.")
    return f"UI:{path}#{selector}@{atributo}"


def _assert_path(path: str) -> str:
    """El path del ref: absoluto, sin host y sin espacios."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("El path del ancla es obligatorio.")
    if "://" in path or path.startswith("//"):
        raise ValueError(
            f"«{path}» es una URL, no un path. El host del destino no viaja en el "
            "ref: viene del alias y se queda fuera del artefacto (capa 4 / A1)."
        )
    if not path.startswith("/"):
        raise ValueError(f"«{path}» no es un path absoluto: tiene que empezar por «/».")
    if any(caracter.isspace() for caracter in path):
        raise ValueError(f"«{path}» lleva espacios: un path no los tiene sin escapar.")
    return path


def veces_por_selector(elementos: Sequence[dom.Elemento]) -> dict[str, int]:
    """Cuántos elementos casaría cada selector candidato del documento.

    Es la comprobación que sustituye al prefijo del ejemplo de §2.1
    (``form[name=guia] input[name=ruc]``). Ese prefijo existe para desambiguar y
    **no desambigua el caso que de verdad ocurre**: dos radios del mismo grupo
    dentro del mismo formulario comparten ``name`` y comparten formulario. Aquí se
    exige lo que aquel prefijo insinuaba —que el selector case con **un** elemento—
    y se comprueba de verdad, que es estrictamente más fuerte y además más corto.

    La cuenta es exacta, no heurística: la cadena de un candidato codifica etiqueta,
    atributo y valor, así que dos elementos que producen la misma cadena son los dos
    elementos que ese selector casaría.
    """
    veces: dict[str, int] = {}
    for elemento in elementos:
        for estrategia in ESTRATEGIAS_POR_ATRIBUTO:
            selector = dom.selector_por_atributo(elemento, estrategia)
            if selector is not None:
                veces[selector.valor] = veces.get(selector.valor, 0) + 1
        estructural = dom.selector_estructural(elemento)
        if estructural:
            veces[estructural] = veces.get(estructural, 0) + 1
    return veces


def selector_de_ancla(
    elemento: dom.Elemento, veces: Mapping[str, int]
) -> Optional[dom.Selector]:
    """El selector con el que se ancla el elemento, o ``None``. **Fail-closed.**

    Se prueban las estrategias en orden y se acepta la primera que además case con
    **un solo** elemento del documento. Devuelve ``None``, y entonces no se emite
    ancla, en dos situaciones que conviene nombrar porque las dos son reales:

    1. **La etiqueta no se puede escribir en CSS.** El legado de WebForms sirve
       ``<asp:TextBox name="ruc" required>``, y ``asp:textbox[name="ruc"]`` no
       selecciona nada: los dos puntos abren una pseudo-clase. Emitir ese ancla
       daría un ref que no resuelve nunca — un caso condenado a fallar por el
       motivo equivocado— así que se prefiere el hueco, que sí se ve en la
       cobertura.
    2. **Ningún candidato es único.** Con ``_Lector`` la ruta estructural es única
       por construcción, así que hoy esta rama la alcanza sobre todo quien construya
       un ``Elemento`` a mano. Se queda igual: en QC5 los elementos vendrán del
       navegador y ya no será cierto por construcción, y un candado que solo se
       escribe cuando hace falta se escribe tarde.
    """
    if not PATRON_TAG_CSS.match(elemento.tag):
        return None
    for estrategia in ESTRATEGIAS_POR_ATRIBUTO:
        selector = dom.selector_por_atributo(elemento, estrategia)
        if selector is not None and veces.get(selector.valor, 0) == 1:
            return selector
    if not all(PATRON_TAG_CSS.match(tag) for tag in elemento.ancestros):
        return None
    estructural = dom.selector_estructural(elemento)
    if not estructural or veces.get(estructural, 0) != 1:
        return None
    return dom.Selector(estructural, ESTRATEGIA_ESTRUCTURAL)


def anclas_de(html: str, path: str) -> list[Ancla]:
    """Las anclas del HTML de una página, en orden de documento. Nada más.

    Determinista y estable: el orden es el del documento y, dentro de cada control,
    el del vocabulario cerrado —nunca el de los atributos tal como los escribió la
    aplicación, que cambia entre despliegues sin que cambie nada—. Dos pasadas sobre
    el mismo HTML dan los mismos refs en el mismo orden.
    """
    _assert_path(path)
    elementos = dom.elementos(html)
    veces = veces_por_selector(elementos)
    anclas: list[Ancla] = []
    for elemento in elementos:
        if elemento.tag not in CONTROLES:
            continue
        selector = selector_de_ancla(elemento, veces)
        if selector is None:
            continue
        for atributo in ATRIBUTOS_ANCLA:
            if not elemento.tiene(atributo):
                continue
            valor = elemento.attr(atributo) or ""
            if atributo == "type" and valor.strip().lower() not in TIPOS_QUE_RESTRINGEN:
                continue
            anclas.append(
                _ancla(path, selector, atributo, valor, elemento.origen, elemento.linea)
            )
        if elemento.tag == "select":
            enum = _ancla_de_enum(html, elemento, elementos, path, selector)
            if enum is not None:
                anclas.append(enum)
    return anclas


def _ancla(
    path: str,
    selector: dom.Selector,
    atributo: str,
    valor: str,
    evidencia: str,
    linea: int,
) -> Ancla:
    return Ancla(
        ref=anchor_ref(path, selector.valor, atributo),
        path=path,
        selector=selector.valor,
        selector_strategy=selector.estrategia,
        attribute=atributo,
        value=valor,
        evidence=evidencia,
        linea=linea,
    )


def _ancla_de_enum(
    html: str,
    select: dom.Elemento,
    elementos: Sequence[dom.Elemento],
    path: str,
    selector: dom.Selector,
) -> Optional[Ancla]:
    """El conjunto de valores aceptados por un ``<select>``, o ``None``.

    Devuelve ``None`` —y el enum queda sin anclar— en tres casos, los tres por el
    mismo motivo: **un conjunto de aceptados a medias es peor que ninguno**. Un
    hueco se ve en la cobertura; un enum incompleto produce un caso que afirma que
    un valor legítimo debe rechazarse, y ese caso pasa la ejecución certificando
    una mentira.

    1. **El ``<select>`` no cierra.** Sin cierre no se sabe dónde acaba el conjunto.
    2. **Alguna opción no lleva atributo ``value``.** Entonces su valor enviado es
       su texto, y leer texto no es lo que hace este extractor: lee atributos. QC5,
       que necesita el texto rotulado como evidencia verbatim, es quien cierra esto.
    3. **Ninguna opción tiene ``value`` con contenido.** Es el caso de una fixture
       saneada —el saneador vacía todo ``value``— y es la divergencia **F2**, que
       este módulo hace visible con un test y no parchea.

    Una opción con ``value=""`` no invalida el enum por sí sola: es la opción de
    «sin selección», que no es un valor del dominio.
    """
    cierre = _fin_de_etiqueta(html, select.inicio, "select")
    if cierre is None:
        return None
    opciones = [
        opcion
        for opcion in elementos
        if opcion.tag == "option" and opcion.ruta[: len(select.ruta)] == select.ruta
    ]
    if not opciones or any(not opcion.tiene("value") for opcion in opciones):
        return None
    valores = [(opcion.attr("value") or "").strip() for opcion in opciones]
    aceptados = [valor for valor in valores if valor]
    if not aceptados:
        return None
    return _ancla(
        path,
        selector,
        ANCLA_ENUM,
        SEPARADOR_ENUM.join(aceptados),
        html[select.inicio : cierre],
        select.linea,
    )


def _fin_de_etiqueta(html: str, inicio: int, tag: str) -> Optional[int]:
    """Dónde acaba ``</tag>`` a partir de ``inicio``, o ``None`` si no cierra.

    Vale para ``<select>`` porque un ``<select>`` **no anida**: el primer cierre
    que aparece detrás es el suyo. No se generaliza a ``<div>`` por lo mismo.
    """
    posicion = html.lower().find(f"</{tag}", inicio)
    if posicion == -1:
        return None
    fin = html.find(">", posicion)
    return None if fin == -1 else fin + 1


def anclas_por_control(anclas: Iterable[Ancla]) -> dict[str, list[Ancla]]:
    """Las anclas agrupadas por selector, conservando el orden. Para presentarlas."""
    grupos: dict[str, list[Ancla]] = {}
    for ancla in anclas:
        grupos.setdefault(ancla.selector, []).append(ancla)
    return grupos
