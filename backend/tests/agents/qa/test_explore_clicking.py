"""La política de pulsado (§3.2, nivel 1): lista blanca evaluada sobre el DOM.

El test que da nombre a este archivo es el del ``<button>`` sin ``type``: en HTML,
un ``<button>`` dentro de un ``<form>`` es ``type="submit"`` por defecto, así que
una lista blanca "los ``<button>`` se pueden pulsar" sería una lista blanca de
envíos. El resto de los tests protege los bordes de esa misma lista.
"""

import pytest

from ai.agents.qa.explore.clicking import elementos_pulsables, es_pulsable
from ai.agents.qa.explore.dom import elementos, selector_de


def uno(html: str, tag: str):
    """Primer elemento con esa etiqueta."""
    return elementos(html, tags=[tag])[0]


def _mismo_origen(href: str) -> bool:
    """Política de navegación de mentira: solo autoriza rutas internas."""
    return href.startswith("/") or href.startswith("https://tms.interno/")


# --- la trampa del <button> --------------------------------------------------


def test_un_button_sin_type_dentro_de_un_form_no_es_pulsable():
    html = """
    <form name="guia" action="/guias" method="post">
      <button id="guardar">Guardar</button>
    </form>
    """
    veredicto = es_pulsable(uno(html, "button"))
    assert not veredicto.pulsable
    assert "submit" in veredicto.motivo


def test_un_button_type_submit_explicito_tampoco():
    html = '<form><button type="submit" id="g">Guardar</button></form>'
    assert not es_pulsable(uno(html, "button")).pulsable


def test_un_button_sin_type_FUERA_de_un_form_tampoco_es_pulsable():
    """Un ``<button form="otro">`` envía un formulario que no es su ancestro, así
    que la exigencia del type explícito no depende de estar dentro de uno."""
    html = '<div><button id="x">Abrir</button></div>'
    assert not es_pulsable(uno(html, "button")).pulsable


def test_un_button_type_button_explicito_si_es_pulsable():
    html = '<form><button type="button" id="add">Añadir línea</button></form>'
    veredicto = es_pulsable(uno(html, "button"))
    assert veredicto.pulsable
    assert "explícito" in veredicto.motivo


def test_un_button_role_tab_sin_type_no_se_cuela_por_el_rol():
    """El rol no exime del type: un ``<button role="tab">`` sin type envía igual."""
    html = '<form><button role="tab" id="t1">Datos</button></form>'
    assert not es_pulsable(uno(html, "button")).pulsable


def test_un_button_type_button_deshabilitado_no_se_pulsa():
    html = '<button type="button" id="x" disabled>Añadir</button>'
    assert not es_pulsable(uno(html, "button")).pulsable
    html = '<button type="button" id="x" aria-disabled="true">Añadir</button>'
    assert not es_pulsable(uno(html, "button")).pulsable


# --- lo que revela campos condicionales (el valor del nivel 1) ---------------


def test_una_pestana_dentro_de_un_formulario_si_es_pulsable():
    """No se bloquea "todo lo que esté dentro de un form": eso dejaría fuera
    pestañas y acordeones, que son la mayor parte del valor del nivel 1."""
    html = '<form><div role="tab" id="datos">Datos del envío</div></form>'
    assert es_pulsable(uno(html, "div")).pulsable


def test_un_acordeon_con_aria_expanded_es_pulsable():
    html = '<div aria-expanded="false" data-testid="mas">Más opciones</div>'
    assert es_pulsable(uno(html, "div")).pulsable


def test_un_summary_es_pulsable():
    html = '<details><summary id="s">Detalle</summary><p>x</p></details>'
    assert es_pulsable(uno(html, "summary")).pulsable


def test_un_div_cualquiera_no_es_pulsable():
    html = '<div id="cabecera">Guías</div>'
    veredicto = es_pulsable(uno(html, "div"))
    assert not veredicto.pulsable
    assert "lista blanca" in veredicto.motivo


# --- controles de formulario: nivel 2 fuera de v1 ----------------------------


@pytest.mark.parametrize(
    "html,tag",
    [
        ('<input type="submit" id="e" value="Enviar">', "input"),
        ('<input type="checkbox" id="c">', "input"),
        ('<input type="button" id="b" value="Añadir">', "input"),
        ('<select id="s"><option>a</option></select>', "select"),
        ('<textarea id="t"></textarea>', "textarea"),
        ('<label id="l" for="c">Acepto</label>', "label"),
    ],
)
def test_ningun_control_de_formulario_se_pulsa(html, tag):
    """Marcar una casilla ya es cambiar el estado del formulario, y pulsar una
    etiqueta activa su control."""
    assert not es_pulsable(uno(html, tag)).pulsable


@pytest.mark.parametrize(
    "atributo", ["formaction", "formmethod", "formenctype", "formtarget", "form"]
)
def test_un_elemento_que_puede_enviar_desde_fuera_no_se_pulsa(atributo):
    html = f'<button type="button" id="x" {atributo}="/guias">Enviar</button>'
    veredicto = es_pulsable(uno(html, "button"))
    assert not veredicto.pulsable
    assert atributo in veredicto.motivo


# --- enlaces: la política de pulsado ES la de navegación ---------------------


def test_un_enlace_interno_es_pulsable():
    html = '<a href="/guias/nueva" id="nueva">Nueva guía</a>'
    assert es_pulsable(uno(html, "a"), permite_navegar=_mismo_origen).pulsable


def test_un_enlace_externo_no_es_pulsable():
    html = '<a href="https://twitter.com/urbano" id="t">Síguenos</a>'
    veredicto = es_pulsable(uno(html, "a"), permite_navegar=_mismo_origen)
    assert not veredicto.pulsable
    assert "no está autorizado" in veredicto.motivo


def test_un_href_javascript_no_es_pulsable():
    html = '<a href="javascript:enviar()" id="j">Enviar</a>'
    assert not es_pulsable(uno(html, "a"), permite_navegar=_mismo_origen).pulsable


def test_un_fragmento_es_pulsable_sin_consultar_la_navegacion():
    html = '<a href="#seccion-2" id="s2">Sección 2</a>'
    assert es_pulsable(uno(html, "a")).pulsable


def test_sin_politica_de_navegacion_inyectada_ningun_absoluto_se_pulsa():
    """Fail-closed: no hay un criterio de repuesto que pueda divergir del real."""
    html = '<a href="/guias" id="g">Guías</a>'
    veredicto = es_pulsable(uno(html, "a"))
    assert not veredicto.pulsable
    assert "revalidar" in veredicto.motivo


def test_un_enlace_sin_href_no_es_pulsable():
    assert not es_pulsable(uno('<a id="x">Nada</a>', "a")).pulsable


def test_una_descarga_no_se_pulsa():
    html = '<a href="/reportes/guias.csv" id="d" download>Descargar</a>'
    veredicto = es_pulsable(uno(html, "a"), permite_navegar=_mismo_origen)
    assert not veredicto.pulsable
    assert "descarga" in veredicto.motivo


def test_un_enlace_a_otra_pestana_no_se_pulsa():
    """Una pestaña nueva sale del contexto controlado por la sesión."""
    html = '<a href="/guias" id="g" target="_blank">Guías</a>'
    assert not es_pulsable(uno(html, "a"), permite_navegar=_mismo_origen).pulsable


# --- el recorrido completo de una página -------------------------------------

PAGINA = """
<html><body>
  <nav>
    <a href="/guias/lista" id="nav-lista">Guías</a>
    <a href="https://ayuda.externo/manual" id="nav-ayuda">Ayuda</a>
  </nav>
  <form name="guia" action="/guias" method="post">
    <div role="tab" data-testid="tab-datos">Datos</div>
    <button type="button" name="agregar">Añadir línea</button>
    <button name="guardar">Guardar</button>
    <input type="submit" name="enviar" value="Enviar">
  </form>
  <a href="/salir">Salir sin selector estable</a>
</body></html>
"""


def test_una_pagina_entera_deja_pasar_solo_lo_inocuo():
    pulsables = elementos_pulsables(PAGINA, permite_navegar=_mismo_origen)
    selectores = [selector.valor for _, selector in pulsables]
    assert selectores == [
        'a[id="nav-lista"]',
        'div[data-testid="tab-datos"]',
        'button[name="agregar"]',
    ]


def test_lo_que_no_tiene_selector_estable_no_se_pulsa():
    """Un clic que no se puede describir es un clic que la corrida siguiente no
    puede repetir, y comparar dos corridas es lo único que hace útil a una suite
    de caracterización."""
    html = '<a href="/salir">Salir</a>'
    assert es_pulsable(uno(html, "a"), permite_navegar=_mismo_origen).pulsable
    assert elementos_pulsables(html, permite_navegar=_mismo_origen) == []
