"""QC4.5 + QC5 — el extractor determinista de anclas: HTML entra, anclas salen.

Este módulo es la mitad barata del Modo C, y la que decide si el resto sirve de
algo. ``SURFACE_MAP`` es el cortafuegos anti-invención del modo —el gemelo de
``CRITERION_MAP``, ``MODEL_MAP`` y ``RESOURCE_MAP``— y un cortafuegos solo vale lo
que valga la lista cerrada que le da de comer. Esa lista se fabrica aquí, en
Python, **antes** de gastar un token: el modelo no elige *qué* hay, solo redacta
*cómo* se prueba lo que hay.

De ahí las tres cosas que este módulo NO hace, y que no son omisiones:

* **No sale a la red, no abre un navegador y no pulsa nada.** Recibe el HTML como
  cadena (§6.2 del diseño del Modo C: *el extractor no conoce el navegador*). Es
  lo que permite ejercer el Modo C entero en la suite, sin arrancar Chromium ni
  una sola vez.
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

**Todo descarte dice POR QUÉ** (:class:`Descarte`). Es la diferencia entre una
decisión fail-closed y una ausencia: lo primero se audita, lo segundo se deduce —
mal— de que algo no está.

Lo que QC5 añadió, y por qué:

* **El conjunto de un enum se topa, nunca se recorta** (A6). Se reutiliza
  ``common.enum_evidence``: el tope se escribe UNA vez y lo comparten los dos modos.
  Por encima del tope el ancla **sigue en pie** con la huella, y su evidencia pasa a
  ser la etiqueta de apertura del ``<select>`` — que es el motivo por el que el tope
  vive aquí y no en ``SURFACE_MAP``: la etiqueta de apertura literal solo la tiene
  quien parseó, y reconstruirla después exigiría un segundo parser del mismo
  documento.
* **Ninguna evidencia alcanza el límite de rotura de una celda de Excel**
  (``CELDA_EXCEL_MAX_CHARS``). Si el literal no cabe, **no se emite el ancla**: no se
  puede recortar sin dejar de ser cita literal, y la cita literal es lo que sostiene
  la verificación verbatim contra el DOM (§2.4.3).
* **Los enums falsos no anclan** (C4, :func:`motivo_no_es_catalogo`): un ``<select>``
  de clientes o de colaboradores es un volcado de producción con forma de catálogo.
* **Los grupos de ``radio``/``checkbox`` son conjuntos cerrados** (C2), agrupados por
  ``name`` igual que ``@enum`` agrupa las ``<option>`` por prefijo de ruta.
* **Ningún ``anchor_ref`` cambia entre corridas si no cambió la aplicación** (C5): un
  selector que interpola un identificador de fila no ancla por ese atributo.

**La divergencia F2, que este módulo hace visible y no resuelve.** El saneador vacía
todo atributo ``value`` antes de comitear una fixture, porque un ``value`` es un
dato de producción; el ``value`` de un ``<option>``, en cambio, es el **conjunto de
lo aceptado**, es decir un límite citable. El obstáculo real es el discriminador —
conservar el ``value`` de un ``<option>`` conserva **cualquier** lista— y ese
discriminador es el de C4, que ya vive aquí. Aplicarlo al saneador es un cambio
propio y está fuera de este bloque. Consecuencia asumida y **fijada con un test**:
sobre HTML crudo el extractor ve el enum de un ``<select>``; sobre la fixture
saneada del mismo ``<select>`` no ve ninguno. Un enum inventado a partir de valores
vacíos sería exactamente el error que este agente no puede cometer.
"""

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

from ai.agents.qa.common import CELDA_EXCEL_MAX_CHARS, enum_evidence
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

#: El ancla que no es un atributo: el conjunto de valores aceptados. Se llama
#: ``enum`` y no ``options`` porque lo que ancla el caso es el **conjunto cerrado**,
#: no el número de opciones. Lo producen dos formas del mismo hecho: las
#: ``<option>`` de un ``<select>`` y los ``radio``/``checkbox`` que comparten
#: ``name`` (C2).
ANCLA_ENUM = "enum"

#: El caso del ancla de enum, en la misma forma que los del vocabulario.
CASO_ENUM = "un valor fuera del conjunto de opciones debe rechazarse"

#: Los ``type`` de ``<input>`` que forman un conjunto cerrado por ``name`` (C2).
#: Un grupo de ``radio`` es un enum con otra sintaxis: el navegador envía UNO de
#: los ``value`` declarados. Un grupo de ``checkbox`` es el mismo conjunto con
#: cardinalidad múltiple; lo que ancla es igualmente **de dónde salen** los valores.
TIPOS_AGRUPABLES = frozenset({"radio", "checkbox"})

#: Cuántos miembros hace falta para que un grupo sea un conjunto. **Dos.** Un
#: ``checkbox`` suelto no declara un conjunto de aceptados: declara un sí/no, y su
#: ancla útil es ``required``. Emitir ``@enum`` sobre un conjunto de uno sería un
#: caso «un valor fuera del conjunto» donde el conjunto no es una restricción.
MINIMO_DE_GRUPO = 2

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
#: * ``value`` → es el dato, no el límite. Es justo lo que el saneador vacía. (La
#:   excepción aparente son las ``<option>`` y los ``radio``/``checkbox``, donde el
#:   ``value`` no es el dato de un campo sino el **conjunto de lo aceptado**: por eso
#:   ancla como ``@enum`` y no como ``@value``.)
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


# ---------------------------------------------------------------------------
# C4 y C5 — el mismo hecho, dos consecuencias
#
# Las dos preguntas de abajo se responden con la misma noción: **¿esto tiene
# forma de identificador de fila?** Un id de fila no es una especificación: nace
# de la base de datos, cambia de un entorno a otro y no dice nada de lo que la
# aplicación acepta.
#
# * En un **valor** (C4) significa que el ``<select>`` es una lista de datos, no
#   un catálogo de dominio, y su conjunto no ancla.
# * En un **selector** (C5) significa que el ``anchor_ref`` cambiaría entre
#   corridas sin que cambie la aplicación, y una suite de caracterización con
#   refs inestables no caracteriza nada.
# ---------------------------------------------------------------------------

#: Un valor con forma de **código**: sin espacios, corto y del alfabeto de un
#: código. Un valor con espacios («COMERCIAL ANDINA S.A.C.», «Juan Pérez García»)
#: no es un código: es un dato.
PATRON_CODIGO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,31}$")

#: ULID (26 caracteres, base32 de Crockford — sin I, L, O ni U).
PATRON_ULID = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")

#: UUID en su forma canónica.
PATRON_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

#: Hexadecimal largo: un hash o un id binario en texto. Ningún código de dominio
#: son 24 caracteres seguidos del alfabeto ``[0-9a-f]``.
PATRON_HEX_LARGO = re.compile(r"[0-9a-fA-F]{24,}")

#: Una tirada larga de dígitos dentro de un selector: el número de la fila.
PATRON_DIGITOS_LARGOS = re.compile(r"\d{6,}")

#: Una plantilla que llegó al DOM **sin renderizar** (``{storyId}``, ``${id}``,
#: ``{{ item.id }}``, ``<%= id %>``, ``#{id}``). Es el caso literal de C5, y el más
#: fácil de reconocer: si el marcador sigue ahí, el ref lleva escrito un agujero.
PATRON_PLANTILLA = re.compile(r"\{\{?[^{}]*\}\}?|\$\{[^{}]*\}|<%[^%]*%>|#\{[^{}]*\}")

#: Longitud a partir de la cual una cadena con minúsculas, mayúsculas Y dígitos se
#: lee como un identificador opaco (base64, nanoid, token). Las tres clases juntas
#: son lo que la distingue de un código descriptivo largo: ``ESTADO_MUY_LARGO`` no
#: tiene minúsculas ni dígitos y por tanto no cae aquí.
LARGO_DE_OPACO = 20

#: Longitud mínima de un entero para que una serie uniforme de enteros se acepte
#: como catálogo. Ver :func:`motivo_no_es_catalogo`, regla 3.
DIGITOS_MINIMOS_DE_CODIGO = 4


def parece_identificador_opaco(valor: str) -> bool:
    """¿Este valor es un id de fila disfrazado de código?

    ULID, UUID, hex largo o una cadena larga que mezcla minúsculas, mayúsculas y
    dígitos. Deliberadamente **no** incluye "es un entero": los códigos de dominio
    reales son numéricos con frecuencia (un ubigeo es ``150101``), y esa
    ambigüedad la resuelve aparte la regla 3 de :func:`motivo_no_es_catalogo`.
    """
    texto = (valor or "").strip()
    if not texto:
        return False
    if PATRON_UUID.fullmatch(texto) or PATRON_ULID.fullmatch(texto):
        return True
    if PATRON_HEX_LARGO.fullmatch(texto):
        return True
    if len(texto) >= LARGO_DE_OPACO:
        tiene = (
            any(c.islower() for c in texto),
            any(c.isupper() for c in texto),
            any(c.isdigit() for c in texto),
        )
        return all(tiene)
    return False


def motivo_de_inestabilidad(valor: str) -> Optional[str]:
    """Por qué este valor de atributo haría inestable un ``anchor_ref`` (C5).

    ``None`` si es estable. Se mira el **valor del atributo**, no el selector ya
    construido: la etiqueta y las comillas del selector no pueden ser inestables,
    y mirar el valor deja el mismo criterio para las cinco estrategias.
    """
    texto = valor or ""
    if PATRON_PLANTILLA.search(texto):
        return "lleva una plantilla sin renderizar"
    if PATRON_UUID.search(texto) or PATRON_ULID.search(texto):
        return "lleva un identificador de fila (ULID/UUID)"
    if PATRON_HEX_LARGO.search(texto):
        return "lleva un identificador hexadecimal"
    if PATRON_DIGITOS_LARGOS.search(texto):
        return "lleva el número de una fila"
    return None


def motivo_no_es_catalogo(valores: Sequence[str]) -> Optional[str]:
    """¿Por qué este conjunto NO es un catálogo de dominio? ``None`` si lo es (C4).

    **Mira solo los ``value``, nunca los rótulos**, y ésa es la decisión del
    criterio. Leer el texto para decidir mete el texto en el camino de la decisión,
    y el texto es justo lo que no queremos que viaje. Además no discrimina: «La
    Libertad» y «Juan Pérez» son estructuralmente idénticos, así que cualquier regla
    sobre rótulos o mata las provincias o deja pasar los nombres.

    Tres reglas, y **todas** tienen que pasar:

    1. **Forma de código.** Un valor con espacios o largo es un dato.
    2. **No es un id opaco.** Un ULID en el ``value`` significa que el conjunto son
       filas de una tabla, no una especificación: cambia de entorno a entorno y un
       caso anclado a él no compara nada entre corridas. (Se comprueba antes que la
       1, para que el motivo que lee una persona sea el exacto y no el que mide.)
    3. **No es una secuencia sustituta.** Si TODOS los valores son enteros, se exige
       longitud uniforme y de al menos :data:`DIGITOS_MINIMOS_DE_CODIGO` dígitos: un
       ubigeo (``150101``) pasa, un ``1, 2, …, N`` de claves primarias no.

    **El motivo describe la REGLA que falló, y no cita ningún valor.** Un motivo
    viaja al artefacto, al CSV y al PDF exactamente igual que una evidencia: citar
    un nombre de cliente para explicar por qué no se citan los nombres de los
    clientes sería la misma fuga entrando por la puerta de atrás. Quién es el
    infractor se ve abriendo la página; qué regla falló, no.

    **Fail-closed ante la duda**: un solo valor que falle descarta el conjunto
    entero. La asimetría manda — un hueco se ve en la cobertura, mientras que un
    conjunto falso filtra datos de producción al prompt y al PDF **y** produce un
    caso que se pondrá rojo cada vez que alguien dé de alta un cliente, sin que haya
    cambiado nada en la aplicación.
    """
    limpios = [(v or "").strip() for v in valores]
    limpios = [v for v in limpios if v]
    if not limpios:
        return "no hay ningún valor que forme el conjunto"

    # El id opaco se comprueba PRIMERO aunque la regla 1 esté escrita antes: un
    # UUID mide 36 caracteres y la regla del código lo atraparía por largo, dando
    # un motivo cierto pero inútil («no tiene forma de código») donde hay uno
    # exacto. El motivo lo lee una persona; que diga lo que pasa no es cosmética.
    if any(parece_identificador_opaco(valor) for valor in limpios):
        return (
            "hay valores con forma de identificador de fila (ULID, UUID o "
            "hexadecimal): el conjunto son filas de una tabla, no una "
            "especificación"
        )
    if any(not PATRON_CODIGO.fullmatch(valor) for valor in limpios):
        return (
            "hay valores sin forma de código (espacios, más de 32 caracteres o "
            "alfabeto ajeno): son datos, no valores de dominio"
        )

    if all(valor.isdigit() for valor in limpios):
        largos = {len(valor) for valor in limpios}
        if len(largos) > 1 or min(largos) < DIGITOS_MINIMOS_DE_CODIGO:
            return (
                "secuencia sustituta: todos los valores son enteros sin longitud "
                f"uniforme de al menos {DIGITOS_MINIMOS_DE_CODIGO} dígitos, que es "
                "la forma de una clave primaria y no la de un código"
            )
    return None


@dataclass(frozen=True)
class Ancla:
    """Un ancla observada: un atributo de un control, con su evidencia literal.

    **Dataclass local a propósito, sin depender del contrato de QC1.** El
    ``QaArtifact`` v1.1.0 y su ``SurfaceAnchor`` todavía no existen, y hacer que
    este módulo los espere lo ataría al orden de los bloques: QC7 traduce esta
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


@dataclass(frozen=True)
class Descarte:
    """Algo que se pudo haber anclado y **no** se ancló, con su motivo.

    Existe porque una decisión fail-closed y un olvido se ven exactamente igual
    desde fuera: en los dos casos falta un ancla. La diferencia la hace decirlo. Lo
    que aquí se registra es lo que ``CRITIQUE`` convertirá en ``Observation`` y lo
    que ``scripts/anclas_de_html.py`` imprime para que una persona lo mire.
    """

    #: Clave del motivo, de :data:`MOTIVOS_DE_DESCARTE`.
    clave: str
    #: El motivo, ya redactado y con el detalle del caso concreto.
    motivo: str
    #: La etiqueta de apertura literal de lo descartado, para reconocerlo.
    origen: str
    linea: int


@dataclass(frozen=True)
class Extraccion:
    """Lo que se ancló y lo que no. La salida completa de una página."""

    anclas: list[Ancla]
    descartes: list[Descarte]


#: **Las clases de descarte, cerradas y con su explicación al lado**, misma regla
#: que :data:`ATRIBUTOS_ANCLA`: una lista de motivos sin explicar por qué existe
#: cada uno es una lista que nadie sabe mantener. El test del bloque exige que cada
#: clave se produzca con un HTML de ejemplo, así que añadir una obliga a escribir
#: el caso que la justifica.
MOTIVOS_DE_DESCARTE: dict[str, str] = {
    "etiqueta-no-css": (
        "la etiqueta no se puede escribir como selector CSS, así que el ref no "
        "resolvería nunca y el caso fallaría por el motivo equivocado"
    ),
    "sin-selector-unico": (
        "ningún candidato de selector casa con un solo elemento, y un ancla que no "
        "se puede reconstruir no sirve para comparar dos corridas"
    ),
    "selector-inestable": (
        "todos los candidatos de selector cambian entre corridas sin que cambie la "
        "aplicación (C5)"
    ),
    "evidencia-enorme": (
        "la cita literal rompería la celda del CSV que abre el analista, y "
        "recortarla dejaría de ser una cita literal"
    ),
    "enum-sin-cierre": (
        "el <select> no cierra, así que no se sabe dónde acaba el conjunto"
    ),
    "enum-sin-value": (
        "alguna opción no declara «value», así que su valor enviado es su texto y "
        "este extractor lee atributos, no texto"
    ),
    "enum-vacio": (
        "ninguna opción tiene «value» con contenido, que es lo que queda de un "
        "<select> tras el saneado de una captura (F2)"
    ),
    "enum-no-es-catalogo": (
        "el conjunto es una lista de datos, no un catálogo de dominio (C4)"
    ),
    "grupo-de-uno": (
        "un radio o checkbox suelto no declara un conjunto de aceptados: declara un "
        "sí/no, y su ancla útil es «required»"
    ),
}


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


def _selector_y_motivo(
    elemento: dom.Elemento, veces: Mapping[str, int]
) -> tuple[Optional[dom.Selector], Optional[str]]:
    """El selector del elemento, o el motivo por el que no hay ninguno.

    Se prueban las estrategias en orden y se acepta la primera que además (a) case
    con **un solo** elemento del documento y (b) no sea inestable (C5). Un
    candidato que falla cualquiera de las dos cae a la siguiente estrategia.
    """
    if not PATRON_TAG_CSS.match(elemento.tag):
        return None, "etiqueta-no-css"

    inestables = 0
    candidatos = 0
    for estrategia in ESTRATEGIAS_POR_ATRIBUTO:
        selector = dom.selector_por_atributo(elemento, estrategia)
        if selector is None:
            continue
        candidatos += 1
        if veces.get(selector.valor, 0) != 1:
            continue
        if motivo_de_inestabilidad(elemento.attr(estrategia) or "") is not None:
            inestables += 1
            continue
        return selector, None

    if not all(PATRON_TAG_CSS.match(tag) for tag in elemento.ancestros):
        return None, "etiqueta-no-css"
    estructural = dom.selector_estructural(elemento)
    if estructural and veces.get(estructural, 0) == 1:
        return dom.Selector(estructural, ESTRATEGIA_ESTRUCTURAL), None
    if inestables and inestables == candidatos:
        return None, "selector-inestable"
    return None, "sin-selector-unico"


def selector_de_ancla(
    elemento: dom.Elemento, veces: Mapping[str, int]
) -> Optional[dom.Selector]:
    """El selector con el que se ancla el elemento, o ``None``. **Fail-closed.**

    Devuelve ``None``, y entonces no se emite ancla, en tres situaciones que
    conviene nombrar porque las tres son reales:

    1. **La etiqueta no se puede escribir en CSS.** El legado de WebForms sirve
       ``<asp:TextBox name="ruc" required>``, y ``asp:textbox[name="ruc"]`` no
       selecciona nada: los dos puntos abren una pseudo-clase. Emitir ese ancla
       daría un ref que no resuelve nunca — un caso condenado a fallar por el
       motivo equivocado— así que se prefiere el hueco, que sí se ve en la
       cobertura.
    2. **Ningún candidato es único.**
    3. **Todos los candidatos son inestables** (C5) y tampoco hay ruta estructural.

    El motivo exacto lo da :func:`_selector_y_motivo`, y llega a la salida como un
    :class:`Descarte`: una decisión fail-closed que no se puede leer es
    indistinguible de un olvido.
    """
    return _selector_y_motivo(elemento, veces)[0]


def extraer(html: str, path: str) -> Extraccion:
    """Las anclas del HTML de una página **y** lo que se descartó, con su motivo.

    Determinista y estable: el orden es el del documento y, dentro de cada control,
    el del vocabulario cerrado —nunca el de los atributos tal como los escribió la
    aplicación, que cambia entre despliegues sin que cambie nada—. Dos pasadas sobre
    el mismo HTML dan los mismos refs en el mismo orden.
    """
    _assert_path(path)
    elementos = dom.elementos(html)
    veces = veces_por_selector(elementos)
    grupos = _grupos_por_nombre(elementos)

    anclas: list[Ancla] = []
    descartes: list[Descarte] = []
    for elemento in elementos:
        if elemento.tag not in CONTROLES:
            continue
        selector, motivo = _selector_y_motivo(elemento, veces)
        if selector is None:
            if _tiene_algo_que_anclar(elemento, grupos):
                descartes.append(_descarte(motivo or "sin-selector-unico", elemento))
            continue

        for atributo in ATRIBUTOS_ANCLA:
            if not elemento.tiene(atributo):
                continue
            valor = elemento.attr(atributo) or ""
            if atributo == "type" and valor.strip().lower() not in TIPOS_QUE_RESTRINGEN:
                continue
            ancla = _ancla(
                path, selector, atributo, valor, elemento.origen, elemento.linea
            )
            if ancla is None:
                descartes.append(_descarte("evidencia-enorme", elemento))
                continue
            anclas.append(ancla)

        if elemento.tag == "select":
            _resolver(
                _enum_de_select(html, elemento, elementos, path, selector),
                elemento,
                anclas,
                descartes,
            )

        nombre = _nombre_de_grupo(elemento)
        if nombre is not None and grupos.get(nombre, [None])[0] is elemento:
            _resolver(
                _enum_de_grupo(html, grupos[nombre], path),
                elemento,
                anclas,
                descartes,
            )

    return Extraccion(anclas=anclas, descartes=descartes)


def anclas_de(html: str, path: str) -> list[Ancla]:
    """Las anclas del HTML de una página, en orden de documento. Nada más.

    El atajo de :func:`extraer` para quien no necesita mirar los descartes.
    """
    return extraer(html, path).anclas


def descartes_de(html: str, path: str) -> list[Descarte]:
    """Lo que se pudo anclar y no se ancló, con su motivo."""
    return extraer(html, path).descartes


def _resolver(
    resultado: tuple[Optional[Ancla], Optional[str], str],
    elemento: dom.Elemento,
    anclas: list[Ancla],
    descartes: list[Descarte],
) -> None:
    """Coloca el resultado de un enum en su lista: o ancla, o descarte con motivo."""
    ancla, clave, detalle = resultado
    if ancla is not None:
        anclas.append(ancla)
    elif clave is not None:
        descartes.append(_descarte(clave, elemento, detalle))


def _descarte(clave: str, elemento: dom.Elemento, detalle: str = "") -> Descarte:
    motivo = MOTIVOS_DE_DESCARTE[clave]
    return Descarte(
        clave=clave,
        motivo=f"{motivo} ({detalle})" if detalle else motivo,
        origen=elemento.origen,
        linea=elemento.linea,
    )


def _tiene_algo_que_anclar(
    elemento: dom.Elemento, grupos: Mapping[str, list[dom.Elemento]]
) -> bool:
    """¿Este control habría producido algún ancla si tuviera selector?

    Sin esto, un ``<input type="text">`` sin atributos de validación aparecería
    como descarte: no hay hueco que enseñar, simplemente no había nada que anclar,
    y una lista de descartes llena de ruido no la mira nadie.
    """
    if any(elemento.tiene(atributo) for atributo in ATRIBUTOS_ANCLA):
        return True
    return elemento.tag == "select"


def _ancla(
    path: str,
    selector: dom.Selector,
    atributo: str,
    valor: str,
    evidencia: str,
    linea: int,
) -> Optional[Ancla]:
    """Un ancla, o ``None`` si su cita literal no cabe en la celda del analista.

    **Fail-closed y sin recorte** (A6, criterio 3: *ningún* ``evidence``). Recortar
    una cita deja de ser una cita, y la cita literal es lo que sostiene la
    verificación verbatim contra el DOM: una evidencia recortada podría dejar de ser
    subcadena del documento justo por donde se cortó. El hueco se ve en la
    cobertura; una evidencia que rompe el CSV se ve cuando el analista no puede
    abrir el fichero.
    """
    if len(evidencia) >= CELDA_EXCEL_MAX_CHARS:
        return None
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


def _valor_del_conjunto(aceptados: Sequence[str]) -> tuple[str, bool]:
    """El ``value`` del ancla de enum, y si el conjunto se degradó a huella.

    **Reutiliza ``common.enum_evidence``**, que es el criterio 5 de A6: el tope se
    escribe UNA vez y lo comparten los dos modos. Escribirlo aquí dejaría la mitad
    del Modo A sin tope o con una segunda copia de las constantes, y dos copias se
    separan en cuanto una se ajusta.
    """
    completo = SEPARADOR_ENUM.join(aceptados)
    valor = enum_evidence(aceptados, separator=SEPARADOR_ENUM)
    return valor, valor != completo


def _enum_de_select(
    html: str,
    select: dom.Elemento,
    elementos: Sequence[dom.Elemento],
    path: str,
    selector: dom.Selector,
) -> tuple[Optional[Ancla], Optional[str], str]:
    """El conjunto de valores aceptados por un ``<select>``, o su motivo de descarte.

    Se descarta —y el enum queda sin anclar— por varias vías, todas por el mismo
    motivo de fondo: **un conjunto de aceptados a medias es peor que ninguno**. Un
    hueco se ve en la cobertura; un enum incompleto produce un caso que afirma que
    un valor legítimo debe rechazarse, y ese caso pasa la ejecución certificando una
    mentira.

    Una opción con ``value=""`` no invalida el enum por sí sola: es la opción de
    «sin selección», que no es un valor del dominio.
    """
    cierre = _fin_de_etiqueta(html, select.inicio, "select")
    if cierre is None:
        return None, "enum-sin-cierre", ""
    opciones = [
        opcion
        for opcion in elementos
        if opcion.tag == "option" and opcion.ruta[: len(select.ruta)] == select.ruta
    ]
    if not opciones or any(not opcion.tiene("value") for opcion in opciones):
        return None, "enum-sin-value", ""
    valores = [(opcion.attr("value") or "").strip() for opcion in opciones]
    aceptados = [valor for valor in valores if valor]
    if not aceptados:
        return None, "enum-vacio", ""
    incumple = motivo_no_es_catalogo(aceptados)
    if incumple is not None:
        return None, "enum-no-es-catalogo", incumple

    valor, topado = _valor_del_conjunto(aceptados)
    # Por encima del tope la evidencia es la ETIQUETA DE APERTURA, no el contenido
    # (A6, criterio 2). Un `<select>` de 1.874 distritos deja de meter el catálogo
    # en el prompt, en el artefacto y en el CSV, y **el ancla sigue en pie**.
    evidencia = select.origen if topado else html[select.inicio : cierre]
    ancla = _ancla(path, selector, ANCLA_ENUM, valor, evidencia, select.linea)
    return (ancla, None, "") if ancla is not None else (None, "evidencia-enorme", "")


def _nombre_de_grupo(elemento: dom.Elemento) -> Optional[str]:
    """El ``name`` del grupo al que pertenece un ``radio``/``checkbox`` (C2)."""
    if elemento.tag != "input":
        return None
    if (elemento.attr("type") or "").strip().lower() not in TIPOS_AGRUPABLES:
        return None
    nombre = (elemento.attr("name") or "").strip()
    return nombre or None


def _grupos_por_nombre(
    elementos: Sequence[dom.Elemento],
) -> dict[str, list[dom.Elemento]]:
    """Los ``radio``/``checkbox`` del documento agrupados por ``name``, en orden."""
    grupos: dict[str, list[dom.Elemento]] = {}
    for elemento in elementos:
        nombre = _nombre_de_grupo(elemento)
        if nombre is not None:
            grupos.setdefault(nombre, []).append(elemento)
    return grupos


def _enum_de_grupo(
    html: str, miembros: Sequence[dom.Elemento], path: str
) -> tuple[Optional[Ancla], Optional[str], str]:
    """El conjunto de valores de un grupo de ``radio``/``checkbox`` (C2).

    Un grupo de ``radio`` es un enum con otra sintaxis: el navegador envía UNO de
    los ``value`` declarados, exactamente como un ``<select>``. La diferencia está
    en el **selector**: aquí el ``[name]`` casa con todos los miembros a propósito —
    eso ES el grupo—, así que la unicidad que se exige a un ancla de atributo no
    aplica y sería justo lo contrario de lo que hace falta.

    La evidencia es el tramo **literal y contiguo** que va del primer miembro al
    final de la etiqueta del último: sigue siendo subcadena exacta del documento
    (§2.4.3) y contiene el grupo entero. Si los miembros están desperdigados por la
    página, ese tramo crece — y si deja de caber en la celda del analista, el ancla
    no se emite, que es la misma regla de siempre.
    """
    primero = miembros[0]
    if len(miembros) < MINIMO_DE_GRUPO:
        return None, "grupo-de-uno", ""
    if any(not miembro.tiene("value") for miembro in miembros):
        return None, "enum-sin-value", ""
    valores = [(miembro.attr("value") or "").strip() for miembro in miembros]
    aceptados = [valor for valor in valores if valor]
    if not aceptados:
        return None, "enum-vacio", ""
    incumple = motivo_no_es_catalogo(aceptados)
    if incumple is not None:
        return None, "enum-no-es-catalogo", incumple

    selector = dom.selector_por_atributo(primero, "name")
    if selector is None:
        return None, "sin-selector-unico", ""
    inestable = motivo_de_inestabilidad(primero.attr("name") or "")
    if inestable is not None:
        return None, "selector-inestable", f"el «name» del grupo {inestable}"

    inicio = min(miembro.inicio for miembro in miembros)
    fin = max(miembro.inicio + len(miembro.origen) for miembro in miembros)
    valor, topado = _valor_del_conjunto(aceptados)
    # Un TRAMO del documento, no las etiquetas concatenadas: la concatenación no
    # es subcadena de nada y la verificación verbatim contra el DOM (§2.4.3) la
    # rechazaría. Si los miembros están desperdigados el tramo crece, y si deja de
    # caber en la celda del analista el ancla no se emite — la regla de siempre.
    evidencia = primero.origen if topado else html[inicio:fin]
    ancla = _ancla(path, selector, ANCLA_ENUM, valor, evidencia, primero.linea)
    return (ancla, None, "") if ancla is not None else (None, "evidencia-enorme", "")


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
