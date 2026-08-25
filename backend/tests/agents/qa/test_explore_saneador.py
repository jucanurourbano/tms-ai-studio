"""El saneador (QC4): conserva la estructura y los rótulos, borra los datos.

La asimetría que gobierna el bloque es la del repositorio, no la del agente: una
fixture a la que le falta un atributo se nota el día que un test no encuentra el
ancla; una fixture con el RUC de un cliente dentro ya está comiteada para siempre.
Por eso el saneador borra por defecto y el candado (``violaciones``) es lo que
prueba que la línea quedó donde debía.
"""

from datetime import datetime, timezone

import pytest

from ai.agents.qa.explore.sanitize import (
    MASCARA,
    ORIGEN_DE_FIXTURE,
    CapturaSuciaError,
    escenario_saneado,
    sanear_html,
    violaciones,
)
from ai.agents.qa.explore.session import PaginaObservada
from tests.agents.qa.explore_helpers import HOST

#: Una captura cruda con todo lo que una aplicación real trae dentro.
CRUDA = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="csrf-token" content="9f3a-token-de-sesion">
<script>var usuario = {"ruc": "20512345678"};</script>
<style>body { background: url(https://tms.urbano.com.pe/fondo.png); }</style>
</head>
<body>
<!-- render 2026-08-25 por el servidor de aplicaciones -->
<h1>Guías del shipper</h1>
<p id="lote" data-lote="20260825000117">Lote de impresión 20260825000117</p>
<form id="alta" action="https://tms.urbano.com.pe/guias?origen=web" method="post"
      data-csrf="abc123">
  <label for="ruc">RUC del shipper</label>
  <input id="ruc" name="ruc" type="text" required maxlength="11" pattern="[0-9]{11}"
         value="20512345678" onchange="validar(this)">
  <span class="mensaje-error" role="alert">El RUC debe tener 11 dígitos.</span>
  <select id="ubigeo" name="ubigeo" required>
    <option value="150122">Lima / Lima / Miraflores</option>
  </select>
</form>
<table>
  <thead><tr><th>Guía</th><th>Cliente</th><th>Estado</th></tr></thead>
  <tbody>
    <tr>
      <td>00012345678</td>
      <td>Comercializadora Andina S.A.C.</td>
      <td><span class="estado-error">Sin checkpoint registrado</span></td>
      <td><select name="destino"><option value="040101">Cusco</option></select></td>
    </tr>
  </tbody>
</table>
</body></html>"""

HOSTS = ["tms.urbano.com.pe"]


@pytest.fixture(scope="module")
def saneada():
    return sanear_html(CRUDA, hosts_a_ocultar=HOSTS)


# --- lo que se conserva: sin esto la fixture no sirve para nada ---------------


@pytest.mark.parametrize(
    "trozo",
    [
        '<form id="alta"',
        '<input id="ruc" name="ruc" type="text" required maxlength="11"',
        'pattern="[0-9]{11}"',
        '<label for="ruc">RUC del shipper</label>',
        "<h1>Guías del shipper</h1>",
        '<select id="ubigeo" name="ubigeo" required>',
    ],
)
def test_conserva_la_estructura_y_los_atributos_de_validacion(saneada, trozo):
    """Los atributos de validación SON el ancla de un caso de borde (QA-D2)."""
    assert trozo in saneada.html


def test_conserva_los_atributos_booleanos_sin_inventarles_valor(saneada):
    """``required`` no se convierte en ``required=""``: cambiaría el HTML."""
    assert "required maxlength" in saneada.html
    assert 'required=""' not in saneada.html


def test_los_mensajes_de_error_renderizados_sobreviven_dentro_de_la_tabla(saneada):
    """A3, la mitad que evita llevarse la señal. Un mensaje de error renderizado
    dentro de un ``<tbody>`` **es** la validación observable."""
    assert '<span class="estado-error">Sin checkpoint registrado</span>' in saneada.html


def test_las_opciones_de_un_select_sobreviven_dentro_de_la_tabla(saneada):
    """Un ``<select>`` en una celda es un enum observado: su texto es rótulo."""
    assert '<option value="">Cusco</option>' in saneada.html
    assert '<option value="">Lima / Lima / Miraflores</option>' in saneada.html


def test_los_encabezados_de_tabla_sobreviven(saneada):
    assert "<th>Guía</th><th>Cliente</th><th>Estado</th>" in saneada.html


# --- lo que se borra ----------------------------------------------------------


def test_vacia_el_atributo_de_valor_sin_quitarlo(saneada):
    """El hueco es estructura (dice que el control tiene valor); el dato no."""
    assert 'value=""' in saneada.html
    assert violaciones(saneada.html, hosts_prohibidos=HOSTS) == []


def test_borra_script_y_style_con_su_contenido(saneada):
    assert "<script" not in saneada.html
    assert "<style" not in saneada.html
    assert "var usuario" not in saneada.html
    assert "background: url" not in saneada.html


def test_borra_los_manejadores_en_linea_por_el_mismo_motivo_que_script(saneada):
    assert "onchange" not in saneada.html
    assert "validar(this)" not in saneada.html


def test_borra_los_atributos_con_nombre_sensible(saneada):
    assert "data-csrf" not in saneada.html
    assert "abc123" not in saneada.html


def test_borra_los_meta_de_sesion_y_conserva_el_charset(saneada):
    assert '<meta charset="utf-8">' in saneada.html
    assert "csrf-token" not in saneada.html


def test_borra_los_comentarios(saneada):
    assert "servidor de aplicaciones" not in saneada.html


def test_enmascara_las_secuencias_largas_de_digitos(saneada):
    """Fuera de una celda de datos el texto se conserva —es la evidencia
    verbatim— así que la máscara es lo único que separa un rótulo de un
    identificador de negocio metido dentro de él. También en los atributos."""
    assert f"Lote de impresión {MASCARA}" in saneada.html
    assert f'data-lote="{MASCARA}"' in saneada.html
    assert "20512345678" not in saneada.html


def test_vacia_el_texto_suelto_de_las_celdas_de_datos(saneada):
    """A3, la otra mitad: dentro de un ``<tbody>``, lo que no está rotulado es
    dato — un nombre de cliente no lo salva ningún patrón de dígitos."""
    assert "Comercializadora Andina" not in saneada.html
    assert "<td></td>" in saneada.html


def test_reescribe_las_urls_absolutas_del_host_explorado(saneada):
    """Una fixture no lleva escrito el mapa de la infraestructura (A1)."""
    assert 'action="/guias?origen=web"' in saneada.html
    assert "tms.urbano.com.pe" not in saneada.html


def test_oculta_el_dominio_de_la_casa_aunque_nadie_lo_pase():
    """El saneador conoce los dominios de la organización: no depende de que
    quien captura se acuerde de declararlos."""
    sucio = '<a href="https://otro.urbano.com.pe/panel">Panel</a>'
    assert 'href="/panel"' in sanear_html(sucio).html


def test_los_descartes_nunca_son_silenciosos(saneada):
    """La regla de la casa (``CLAUDE.md`` §8), aplicada al saneador."""
    assert saneada.clases_retiradas() >= {
        "comentario",
        "dato",
        "elemento",
        "host",
        "manejador",
        "meta",
        "token",
        "value",
    }


# --- propiedades --------------------------------------------------------------


def test_lo_saneado_ya_no_viola_el_candado(saneada):
    assert violaciones(saneada.html, hosts_prohibidos=HOSTS) == []


def test_sanear_es_idempotente(saneada):
    """Hace falta para poder pasar el saneador sobre una fixture ya comiteada
    sin dañarla: si no lo fuera, cada pasada erosionaría el HTML."""
    assert sanear_html(saneada.html, hosts_a_ocultar=HOSTS).html == saneada.html


def test_un_html_roto_no_revienta_al_saneador():
    """El HTML que hay es el HTML roto; ``html.parser`` es tolerante y esto lo
    fija: un cierre huérfano no puede tumbar una captura."""
    resultado = sanear_html("<div><p>hola</div></p></span>")
    assert "hola" in resultado.html


# --- el escenario: donde el saneador deja de ser opcional ---------------------


def _pagina(path: str, html: str, *, status: int = 200, depth: int = 0):
    return PaginaObservada(
        url=f"https://tms.interno{path}",
        path=path,
        status=status,
        depth=depth,
        html=html,
        observed_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )


def test_el_escenario_sanea_y_arma_el_manifiesto():
    escenario = escenario_saneado(
        [_pagina("/login", CRUDA), _pagina("/guias/nueva", CRUDA, depth=1)],
        hosts_a_ocultar=HOSTS,
    )
    assert sorted(escenario.archivos) == ["00_login.html", "01_guias_nueva.html"]
    assert escenario.manifest["origin"] == ORIGEN_DE_FIXTURE
    assert escenario.manifest["entry"] == "/login"
    assert escenario.manifest["visit_order"] == ["/login", "/guias/nueva"]
    assert escenario.manifest["pages"]["/guias/nueva"] == {
        "status": 200,
        "file": "01_guias_nueva.html",
        "depth": 1,
    }


def test_el_manifiesto_re_aloja_el_escenario_en_un_host_inventado():
    """El origen real no se comitea. Y el inventado es el mismo que ya usan los
    dobles de QC3: un solo host de fixture, comprobado, no dos parecidos."""
    assert ORIGEN_DE_FIXTURE == f"https://{HOST}"


def test_no_se_escribe_nada_si_lo_saneado_sigue_sucio():
    """El saneador **no** es un oráculo de PII sobre texto libre: un dominio de
    la casa dentro de un párrafo no es una URL y sobrevive. Por eso el candado se
    aplica ANTES de escribir y esto revienta, en vez de avisar por consola — un
    aviso se lee cuando ya está comiteado."""
    sucia = _pagina("/ayuda", "<p>Escríbenos a soporte@urbano.com.pe</p>")
    with pytest.raises(CapturaSuciaError) as error:
        escenario_saneado([sucia])
    assert "00_ayuda.html" in str(error.value)
    assert "urbano.com.pe" in str(error.value)


def test_un_escenario_limpio_no_revienta():
    limpio = _pagina("/", "<h1>Panel</h1>")
    assert escenario_saneado([limpio]).archivos["00_raiz.html"] == "<h1>Panel</h1>"
