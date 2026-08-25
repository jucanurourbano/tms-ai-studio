"""QC4.5 — el extractor determinista: HTML entra, anclas salen.

Tres candados viven aquí, y son los del bloque: **cero navegador** (el extractor
recibe una cadena, no una página), **sin selector no se emite ancla** y
**extracción idempotente y estable**. Y una cuarta cosa que no es un candado sino
una grieta fijada: la divergencia **F2**, que este fichero deja escrita con un test
en vez de con una nota.
"""

import ast
from pathlib import Path

import pytest

from ai.agents.qa.explore import dom, extract
from ai.agents.qa.explore.extract import (
    ANCLA_ENUM,
    ATRIBUTOS_ANCLA,
    CANDIDATOS_FUERA,
    ESTRATEGIAS_DE_ANCLA,
    Ancla,
    anchor_ref,
    anclas_de,
    selector_de_ancla,
    veces_por_selector,
)
from ai.agents.qa.explore.sanitize import sanear_html
from tests.agents.qa.explore_fixtures import DIRECTORIO, cargar, escenarios

BACKEND = Path(__file__).resolve().parents[3]
MODULO = BACKEND / "ai" / "agents" / "qa" / "explore" / "extract.py"

FORMULARIO = """<!DOCTYPE html>
<html><body>
  <form id="nueva-guia">
    <label for="ruc">RUC</label>
    <input id="ruc" name="ruc" type="text" required maxlength="11" pattern="[0-9]{11}">
    <select name="estado">
      <option value="">Todos</option>
      <option value="ACTIVO">Activo</option>
      <option value="ANULADO">Anulado</option>
    </select>
    <input name="servicio" id="express" type="radio">
    <input name="servicio" id="regular" type="radio" required>
    <input aria-label="Buscar guía" type="search" maxlength="20">
    <div><input required></div>
    <button type="button" data-testid="cancelar">Cancelar</button>
  </form>
</body></html>
"""


def _refs(html: str, path: str = "/guias/nueva") -> list[str]:
    return [ancla.ref for ancla in anclas_de(html, path)]


def _paginas(escenario: str) -> list[tuple[str, str]]:
    """Las páginas servidas de un escenario. Una entrada de solo redirección no
    tiene HTML: el manifiesto modela la respuesta, no una página."""
    fixture = cargar(escenario)
    return [
        (path, fixture.html(entrada["file"]))
        for path, entrada in sorted(fixture.manifest["pages"].items())
        if entrada.get("file")
    ]


def _por_atributo(html: str, path: str = "/guias/nueva") -> dict[str, list[Ancla]]:
    grupos: dict[str, list[Ancla]] = {}
    for ancla in anclas_de(html, path):
        grupos.setdefault(ancla.attribute, []).append(ancla)
    return grupos


# --- el vocabulario: cerrado, y un atributo = un ancla -----------------------

#: Un HTML mínimo por entrada del vocabulario. La tabla no es decorativa: el test
#: de abajo exige que **toda** entrada tenga la suya, así que ampliar el
#: vocabulario obliga a escribir aquí el caso que lo justifica.
HTML_POR_ATRIBUTO = {
    "required": '<input name="c" required>',
    "maxlength": '<input name="c" maxlength="11">',
    "minlength": '<input name="c" minlength="11">',
    "pattern": '<input name="c" pattern="[0-9]{11}">',
    "min": '<input name="c" min="0">',
    "max": '<input name="c" max="70">',
    "step": '<input name="c" step="0.01">',
    "type": '<input name="c" type="number">',
    "readonly": '<input name="c" readonly>',
    "accept": '<input name="c" type="file" accept=".pdf">',
    "multiple": '<select name="c" multiple><option value="A">A</option></select>',
}


@pytest.mark.parametrize("atributo", sorted(ATRIBUTOS_ANCLA))
def test_cada_atributo_del_vocabulario_produce_su_ancla(atributo):
    anclas = anclas_de(HTML_POR_ATRIBUTO[atributo], "/x")
    encontrada = [ancla for ancla in anclas if ancla.attribute == atributo]
    assert len(encontrada) == 1, f"{atributo}: {[a.attribute for a in anclas]}"
    assert encontrada[0].caso, "Un ancla sin caso no habilita ninguna prueba."


def test_toda_entrada_del_vocabulario_lleva_su_caso_y_su_html():
    """Una lista de atributos sin el caso de cada uno al lado es indistinguible de
    una lista copiada de la especificación de HTML: nadie sabe por qué falta el
    que falta. Es la misma regla que gobierna ``PIEZAS_DE_MENSAJE``."""
    assert set(HTML_POR_ATRIBUTO) == set(ATRIBUTOS_ANCLA)
    assert all(caso.strip() for caso in ATRIBUTOS_ANCLA.values())


def test_un_atributo_es_un_ancla_y_no_una_por_campo():
    """``required`` y ``maxlength`` del mismo campo habilitan casos distintos y se
    pueden romper por separado: fundirlos escondería media rotura."""
    anclas = anclas_de('<input name="ruc" required maxlength="11">', "/x")
    assert [ancla.attribute for ancla in anclas] == ["required", "maxlength"]
    assert len({ancla.ref for ancla in anclas}) == 2
    assert len({ancla.selector for ancla in anclas}) == 1


@pytest.mark.parametrize("candidato", CANDIDATOS_FUERA)
def test_los_candidatos_anotados_fuera_del_vocabulario_no_anclan(candidato):
    """``value`` es el dato, no el límite — y es justo lo que el saneador vacía."""
    html = f'<input name="c" {candidato}="algo">'
    assert candidato not in {ancla.attribute for ancla in anclas_de(html, "/x")}


@pytest.mark.parametrize(
    "tipo, ancla_esperada",
    [
        ("number", True),
        ("email", True),
        ("file", True),
        ("text", False),
        ("password", False),
        ("hidden", False),
        ("radio", False),
    ],
)
def test_type_ancla_solo_cuando_restringe_la_forma_del_dato(tipo, ancla_esperada):
    """Un caso «escribe texto en un campo de texto» es ruido que entierra al que
    importa. Y no se pierde nada: el límite real de ese campo vive en
    ``maxlength``/``pattern``/``required``, que sí se anclan."""
    anclas = anclas_de(f'<input name="c" type="{tipo}">', "/x")
    assert ("type" in {a.attribute for a in anclas}) is ancla_esperada


def test_solo_se_extraen_anclas_de_los_controles():
    """Un ``<button type="button">`` no ancla: su ``type`` no restringe un dato,
    decide si envía, y eso lo gobierna la política de pulsado."""
    selectores = {ancla.selector for ancla in anclas_de(FORMULARIO, "/guias/nueva")}
    assert not any("button" in selector for selector in selectores)


# --- la forma canónica del ref (§2.1) ----------------------------------------


def test_la_forma_canonica_del_ref():
    assert (
        anchor_ref("/guias/nueva", 'input[name="ruc"]', "maxlength")
        == 'UI:/guias/nueva#input[name="ruc"]@maxlength'
    )


def test_el_ref_es_una_funcion_pura():
    """Dos exploraciones de la misma pantalla tienen que dar la misma cadena, o no
    se pueden comparar dos corridas — que es lo único que hace útil a una suite de
    caracterización."""
    argumentos = ("/guias", 'input[name="ruc"]', "required")
    assert anchor_ref(*argumentos) == anchor_ref(*argumentos)


@pytest.mark.parametrize(
    "path",
    [
        "https://tms.urbano.com.pe/guias",
        "//tms.urbano.com.pe/guias",
        "http://localhost:3000/guias",
        "guias/nueva",
        "/guias nueva",
        "",
        "   ",
    ],
)
def test_el_ref_rechaza_todo_lo_que_no_sea_un_path(path):
    """El host viene del alias y **no** viaja en el ref: una URL colada aquí
    llevaría el mapa de la infraestructura a un CSV que se exporta (capa 4 / A1).
    Se rechaza en vez de recortarse: recortar en silencio acepta la equivocación de
    quien llama y la repite en la siguiente."""
    with pytest.raises(ValueError):
        anchor_ref(path, 'input[name="ruc"]', "required")
    with pytest.raises(ValueError):
        anclas_de('<input name="ruc" required>', path)


def test_el_ref_exige_selector_y_atributo():
    with pytest.raises(ValueError, match="selector"):
        anchor_ref("/guias", "  ", "required")
    with pytest.raises(ValueError, match="atributo"):
        anchor_ref("/guias", 'input[name="ruc"]', "")


def test_ningun_ancla_de_una_pagina_comparte_ref_con_otra():
    """Dos anclas con el mismo ref son dos casos que no se pueden distinguir."""
    refs = _refs(FORMULARIO)
    assert len(refs) == len(set(refs))


# --- las cinco estrategias de selector, en orden -----------------------------


@pytest.mark.parametrize(
    "html, estrategia, selector",
    [
        (
            '<input name="ruc" id="i" data-testid="t" aria-label="a" required>',
            "name",
            'input[name="ruc"]',
        ),
        (
            '<input id="ruc" data-testid="t" aria-label="a" required>',
            "id",
            'input[id="ruc"]',
        ),
        (
            '<input data-testid="ruc" aria-label="a" required>',
            "data-testid",
            'input[data-testid="ruc"]',
        ),
        ('<input aria-label="RUC" required>', "aria-label", 'input[aria-label="RUC"]'),
        (
            "<div><input required></div>",
            "structural",
            "div:nth-of-type(1) > input:nth-of-type(1)",
        ),
    ],
)
def test_el_orden_de_preferencia_del_selector(html, estrategia, selector):
    ancla = anclas_de(html, "/x")[0]
    assert (ancla.selector_strategy, ancla.selector) == (estrategia, selector)


def test_el_orden_declarado_extiende_el_de_pulsar_en_vez_de_copiarlo():
    """Dos listas copiadas se separan; una que extiende a la otra no puede."""
    assert ESTRATEGIAS_DE_ANCLA[: len(dom.ESTRATEGIAS)] == dom.ESTRATEGIAS
    assert ESTRATEGIAS_DE_ANCLA == (
        "name",
        "id",
        "data-testid",
        "aria-label",
        "structural",
    )


def test_las_dos_estrategias_de_ancla_no_son_estrategias_de_pulsado():
    """Anclar un caso que una persona va a leer y pulsar contra una aplicación
    viva no piden lo mismo: equivocarse de elemento al pulsar es una acción."""
    frágil = dom.elementos('<input aria-label="RUC">')[0]
    assert dom.selector_de(frágil) is None


def test_un_selector_ambiguo_cae_a_la_siguiente_estrategia():
    """El caso que el prefijo del ejemplo de §2.1 (``form[...] input[...]``) NO
    resuelve: dos radios del mismo grupo comparten ``name`` **y** formulario."""
    html = (
        '<form><input name="s" id="a" required><input name="s" id="b" required></form>'
    )
    anclas = anclas_de(html, "/x")
    assert [ancla.selector for ancla in anclas] == ['input[id="a"]', 'input[id="b"]']
    assert {ancla.selector_strategy for ancla in anclas} == {"id"}


def test_el_structural_nace_marcado_y_los_demas_no():
    """Frágil no es «puede cambiar»: es «puede romperse sin que haya cambiado nada
    que importe». Un ``<div>`` de maquetación rompe el structural sin cambiar nada
    observable; un ``aria-label`` que cambia es un cambio que la suite DEBE ver."""
    anclas = {a.selector_strategy: a for a in anclas_de(FORMULARIO, "/guias/nueva")}
    assert anclas["structural"].fragil is True
    assert [a.fragil for e, a in anclas.items() if e != "structural"] == [False] * (
        len(anclas) - 1
    )


# --- candado: sin selector no se emite ancla (fail-closed) -------------------


def test_una_etiqueta_que_no_se_puede_escribir_en_css_no_ancla():
    """``<asp:TextBox>`` de WebForms: ``asp:textbox[name="ruc"]`` no selecciona
    nada —los dos puntos abren una pseudo-clase— así que el ancla daría un ref que
    no resuelve **nunca**. Se prefiere el hueco, que sí se ve en la cobertura, a un
    caso condenado a fallar por el motivo equivocado."""
    assert anclas_de('<asp:textbox name="ruc" required></asp:textbox>', "/x") == []
    assert anclas_de("<div><asp:panel><input required></asp:panel></div>", "/x") == []
    assert anclas_de("<div><span><input required></span></div>", "/x") != []


def test_sin_ningun_candidato_unico_no_hay_selector_y_por_tanto_no_hay_ancla():
    """La rama fail-closed, probada sobre la función y no sobre un HTML: hoy
    ``_Lector`` hace única la ruta estructural por construcción, y en QC5 los
    elementos vendrán del navegador, donde eso deja de ser cierto. Un candado que
    solo se escribe cuando hace falta se escribe tarde."""
    huerfano = dom.Elemento(tag="input", attrs={"required": ""})
    assert selector_de_ancla(huerfano, veces_por_selector([huerfano])) is None

    duplicado = dom.Elemento(
        tag="input", attrs={"name": "ruc"}, ruta=("input:nth-of-type(1)",)
    )
    veces = veces_por_selector([duplicado, duplicado])
    assert selector_de_ancla(duplicado, veces) is None


def test_la_cuenta_de_selectores_es_exacta_y_no_una_heuristica():
    elementos = dom.elementos('<input name="s"><input name="s"><input name="otro">')
    veces = veces_por_selector(elementos)
    assert veces['input[name="s"]'] == 2
    assert veces['input[name="otro"]'] == 1


# --- candado: extracción idempotente y estable ------------------------------


@pytest.mark.parametrize("escenario", escenarios())
def test_dos_pasadas_sobre_el_mismo_html_dan_lo_mismo(escenario):
    for pagina, html in _paginas(escenario):
        assert anclas_de(html, pagina) == anclas_de(html, pagina)


def test_el_orden_es_el_del_documento_y_el_del_vocabulario():
    """Dentro de un control manda el vocabulario, **nunca** el orden en que la
    aplicación escribió los atributos: ese orden cambia entre despliegues sin que
    cambie nada, y con él cambiarían los refs de una corrida a otra."""
    derecho = '<input name="c" required maxlength="11" pattern="x">'
    revuelto = '<input name="c" pattern="x" maxlength="11" required>'
    esperado = ["required", "maxlength", "pattern"]
    assert [a.attribute for a in anclas_de(derecho, "/x")] == esperado
    assert [a.attribute for a in anclas_de(revuelto, "/x")] == esperado


def test_el_orden_entre_controles_es_el_del_documento():
    html = '<input name="b" required><input name="a" required>'
    assert [a.selector for a in anclas_de(html, "/x")] == [
        'input[name="b"]',
        'input[name="a"]',
    ]


# --- la evidencia es literal -------------------------------------------------


@pytest.mark.parametrize("escenario", escenarios())
def test_toda_evidencia_es_subcadena_exacta_del_html(escenario):
    """Es el cortafuegos anti-invención del Modo C (§2.4): la evidencia de un caso
    tiene que ser subcadena literal del DOM del ancla. Un ``maxlength="11"``
    alucinado como ``12`` muere ahí — pero solo si lo que guardamos es literal."""
    for pagina, html in _paginas(escenario):
        for ancla in anclas_de(html, pagina):
            assert ancla.evidence in html
            if ancla.attribute not in {"required", "readonly", "multiple", ANCLA_ENUM}:
                assert ancla.value in ancla.evidence


def test_la_evidencia_de_un_enum_lleva_dentro_los_valores_aceptados():
    """El límite de un enum ES el conjunto, así que la evidencia tiene que
    enseñarlo: el fragmento literal del ``<select>``, no su etiqueta de apertura."""
    ancla = _por_atributo(FORMULARIO)[ANCLA_ENUM][0]
    assert ancla.value == "ACTIVO | ANULADO"
    assert ancla.evidence.startswith('<select name="estado">')
    assert ancla.evidence.endswith("</select>")
    assert 'value="ACTIVO"' in ancla.evidence


@pytest.mark.parametrize(
    "html, motivo",
    [
        ('<select name="e"><option value="A">A</option>', "no cierra"),
        ('<select name="e"><option>Activo</option></select>', "opción sin value"),
        ('<select name="e"><option value="">—</option></select>', "todos vacíos"),
        ('<select name="e"></select>', "sin opciones"),
    ],
)
def test_un_conjunto_de_aceptados_a_medias_no_se_ancla(html, motivo):
    """Un hueco se ve en la cobertura; un enum incompleto produce un caso que
    afirma que un valor legítimo debe rechazarse, y ese caso pasa la ejecución
    certificando una mentira."""
    assert ANCLA_ENUM not in _por_atributo(html, "/x"), motivo


def test_la_opcion_sin_seleccion_no_invalida_el_enum():
    html = '<select name="e"><option value="">—</option><option value="A">A</option></select>'
    assert _por_atributo(html, "/x")[ANCLA_ENUM][0].value == "A"


# --- F2: visible, fijada, y NO resuelta -------------------------------------


def test_f2_el_extractor_ve_el_enum_en_crudo_y_no_lo_ve_en_la_fixture_saneada():
    """**La divergencia F2, fijada con un test en vez de con una nota.**

    El saneador vacía todo atributo ``value`` porque un ``value`` es un dato de
    producción; el ``value`` de un ``<option>``, en cambio, es el conjunto de lo
    aceptado, es decir un límite citable. Distinguirlos exige saber dentro de qué
    elemento se está —árbol y ancestros— y el candado de fixtures tiene prohibido
    construir un árbol: la regla está escrita en ``sanitize.py`` y F2 es justo la
    comprobación que cae del lado equivocado de esa línea.

    Consecuencia asumida: un enum solo se ancla explorando de verdad. No se parchea
    aquí — un enum reconstruido a partir de valores vacíos sería el error que este
    agente no puede cometer."""
    crudo = '<select name="estado"><option value="ACTIVO">Activo</option></select>'
    assert _por_atributo(crudo, "/x")[ANCLA_ENUM][0].value == "ACTIVO"

    saneado = sanear_html(crudo).html
    assert 'value=""' in saneado
    assert ANCLA_ENUM not in _por_atributo(saneado, "/x")


def test_f2_tambien_sobre_la_fixture_comiteada_de_verdad():
    """El ``<select name="ubigeo">`` de ``02_guias_nueva.html`` conserva su
    ``required`` y pierde su enum. La grieta no es una hipótesis: está en el
    repositorio."""
    html = cargar("tms_guias").html_de("/guias/nueva")
    atributos = _por_atributo(html, "/guias/nueva")
    assert 'select[name="ubigeo"]' in {a.selector for a in atributos["required"]}
    assert ANCLA_ENUM not in atributos


# --- candados del bloque: el extractor no conoce el navegador ----------------

#: Lo único que este módulo puede importar. Lista **cerrada**: añadir un import es
#: una decisión que hay que justificar aquí, y eso es exactamente lo que se quiere
#: para el módulo que decide qué existe antes de que hable el modelo.
IMPORTS_PERMITIDOS = {
    "re",
    "dataclasses",
    "typing",
    "ai.agents.qa.explore",
    # Añadido en QC5, y la justificación es el criterio 5 de A6: el tope de la
    # evidencia de un enum se escribe UNA vez, en ``common``, y lo comparten los dos
    # modos. Tenía que aplicarse AQUÍ y no en ``SURFACE_MAP`` porque por encima del
    # tope la evidencia pasa a ser la etiqueta de apertura del ``<select>``, y esa
    # etiqueta literal solo la tiene quien parseó: reconstruirla después exigiría un
    # segundo parser del mismo documento, que es lo que §13.5 prohíbe.
    #
    # No debilita el candado, que sigue diciendo lo mismo: ni navegador, ni red, ni
    # disco, ni los módulos hermanos que conducen el navegador. La lista es CERRADA,
    # no congelada: cada entrada se justifica aquí.
    "ai.agents.qa.common",
}

#: Trozos que delatan a un literal que nombra un fichero del repositorio. El
#: extractor recibe HTML como cadena: si nombra un fichero es que lo va a abrir.
TROZOS_DE_RUTA = ("test", "fixture", ".html", ".json", "backend", "..")

#: Lo que abre, escribe o ejecuta. Ninguna tiene nada que hacer en una función
#: pura que recibe una cadena y devuelve una lista.
#: ``compile`` NO está: es ``re.compile``, y quitarlo del vocabulario del candado
#: por eso es preferible a listar excepciones — una excepción en un candado es un
#: candado con la llave debajo del felpudo.
LLAMADAS_PROHIBIDAS = frozenset(
    {"open", "read_text", "write_text", "mkdir", "exec", "eval"}
)


def _arbol(fuente: str = ""):
    return ast.parse(fuente or MODULO.read_text(encoding="utf-8"))


def _importados(arbol) -> set[str]:
    importados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            importados.add(nodo.module or "")
    return importados


def _llamadas(arbol) -> set[str]:
    return {
        nodo.func.id if isinstance(nodo.func, ast.Name) else nodo.func.attr
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call)
        and isinstance(nodo.func, (ast.Name, ast.Attribute))
    }


def _rutas_nombradas(arbol) -> list[str]:
    """Literales **ejecutables** que nombran un fichero del repositorio.

    Los docstrings quedan fuera: son prosa, y esta prosa habla de ``tests/`` y de
    fixtures precisamente para decir que no los toca. Mirarlos convertiría el
    candado en un test de vocabulario; lo que se vigila es lo que el código puede
    usar."""
    documentados = {
        nodo.body[0].value
        for nodo in ast.walk(arbol)
        if isinstance(
            nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
        and nodo.body
        and isinstance(nodo.body[0], ast.Expr)
        and isinstance(nodo.body[0].value, ast.Constant)
        and isinstance(nodo.body[0].value.value, str)
    }
    return [
        nodo.value
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Constant)
        and isinstance(nodo.value, str)
        and nodo not in documentados
        and any(trozo in nodo.value.lower() for trozo in TROZOS_DE_RUTA)
    ]


def test_el_extractor_solo_importa_lo_que_puede_justificar():
    """Cero Playwright, cero red, cero disco, y ni siquiera los módulos hermanos
    que conducen el navegador: la costura de §6.2 es que el extractor recibe **HTML
    como cadena**. Es lo que permite ejercer el 99% del Modo C en un host donde
    Chromium no arranca."""
    importados = _importados(_arbol())
    assert importados <= IMPORTS_PERMITIDOS, f"Imports sin justificar: {importados}"


def test_el_extractor_no_toca_el_disco_ni_espera_a_nada():
    """Criterio 6 del bloque: no escribe en el repositorio y no lee de las fixtures.
    Y síncrono a propósito: lo que no puede esperar no puede esperar a la red."""
    arbol = _arbol()
    assert not _llamadas(arbol) & LLAMADAS_PROHIBIDAS
    assert not [n for n in ast.walk(arbol) if isinstance(n, ast.AsyncFunctionDef)]
    rutas = _rutas_nombradas(arbol)
    assert rutas == [], f"El extractor nombra un fichero del repositorio: {rutas}"


@pytest.mark.parametrize(
    "fuente, mide",
    [
        ("import playwright", "importa"),
        ("from playwright.sync_api import sync_playwright", "importa"),
        ("from ai.agents.qa.explore.driver import build_driver", "importa"),
        ("import requests", "importa"),
        ('open("tests/fixtures/qa_explore/x.html")', "llama y nombra"),
        ('Path("../tests").read_text()', "llama y nombra"),
    ],
)
def test_los_candados_del_extractor_saltan_cuando_deben(fuente, mide):
    """**Verlos fallar.** Un candado que solo se ha visto pasar es indistinguible
    de una función que devuelve la lista vacía; el precedente es el candado de
    fixtures de QC4, que introduce la violación a propósito."""
    arbol = _arbol(fuente)
    infringe = (
        not _importados(arbol) <= IMPORTS_PERMITIDOS
        or bool(_llamadas(arbol) & LLAMADAS_PROHIBIDAS)
        or bool(_rutas_nombradas(arbol))
    )
    assert infringe, f"El candado no vio que esto {mide} lo prohibido: {fuente}"


def test_el_extractor_no_lee_ninguna_ruta_del_repositorio(monkeypatch):
    """El candado de arriba mira el código; este mira el comportamiento: con el
    directorio de fixtures fuera de alcance, extraer sigue funcionando."""

    def prohibido(*args, **kwargs):
        raise AssertionError("El extractor no abre ficheros.")

    monkeypatch.setattr("builtins.open", prohibido)
    assert anclas_de(FORMULARIO, "/guias/nueva")
    assert DIRECTORIO.exists()
