"""El saneador (QC4): conserva la estructura y los rótulos, borra los datos.

La asimetría que gobierna el bloque es la del repositorio, no la del agente: una
fixture a la que le falta un atributo se nota el día que un test no encuentra el
ancla; una fixture con el RUC de un cliente dentro ya está comiteada para siempre.
Por eso el saneador borra por defecto y el candado (``violaciones``) es lo que
prueba que la línea quedó donde debía.
"""

import re
from datetime import datetime, timezone

import pytest

from ai.agents.qa.explore import sanitize
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


# --- el vocabulario es auditable, y eso es un test ---------------------------
#
# Una lista de literales cuyo caso vive en un docstring solo es auditable si los dos
# no pueden separarse. Sin este candado, añadir una pieza al ``frozenset`` sin
# tocar la prosa deja una lista que *dice* llevar su origen anotado y no lo lleva.

#: El formato de una línea de la lista del docstring: pieza y etiqueta.
LINEA_DEL_VOCABULARIO = re.compile(
    r"^\* ``([a-z]+)`` — \*\*(observado|prospectivo|heredado sin caso)\*\*",
    re.MULTILINE,
)


def _vocabulario_documentado() -> dict[str, str]:
    return dict(LINEA_DEL_VOCABULARIO.findall(sanitize.__doc__ or ""))


def test_el_docstring_documenta_exactamente_las_piezas_que_hay():
    """El candado de la decisión: cada pieza lleva su caso escrito, ni una de más
    ni una de menos. Si esto se rompe, la lista dejó de ser auditable."""
    assert set(_vocabulario_documentado()) == set(sanitize.PIEZAS_DE_MENSAJE)


def test_son_diecisiete_piezas():
    """De 20 a 17: salieron ``errors``, ``errores`` y ``mensajes``. El número está
    aquí para que reducirlo o ampliarlo sea una decisión, no un descuido."""
    assert len(sanitize.PIEZAS_DE_MENSAJE) == 17


def test_una_sola_pieza_tiene_caso_observado():
    """El resultado incómodo de la auditoría, fijado para que no se olvide: el
    vocabulario no se derivó de observaciones, se heredó. De ahí que el peso recaiga
    en las señales estructurales (``role``, ``aria-live``, ``TAGS_ROTULO``) y que
    ampliar la lista exija evidencia de un sistema explorado (§12.6 del diseño)."""
    documentado = _vocabulario_documentado()
    observadas = [p for p, caso in documentado.items() if caso == "observado"]
    assert observadas == ["destructive"]


@pytest.mark.parametrize("plural", ["errors", "errores", "mensajes", "messages"])
def test_los_plurales_no_vuelven_por_simetria(plural):
    """Los tres primeros se fueron por no tener caso; ``messages`` —el canónico de
    Django— está **anotado como candidato y fuera**. Completar la lista por simetría
    ensancha la dirección irreversible: casar de menos vacía el texto de una celda,
    casar de más comitea un dato de producción."""
    assert plural not in sanitize.PIEZAS_DE_MENSAJE


# --- reconocer un mensaje: piezas exactas, sin herencia hacia la tabla --------
#
# La fuga que cierra este bloque fallaba hacia CONSERVAR, que es la dirección mala:
# lo que sobrevive dentro de un ``<tbody>`` son datos de producción comiteados.


def test_una_pieza_que_solo_contiene_a_la_marca_no_es_un_mensaje():
    """``terror`` casaba con ``error`` por subcadena y salvaba el dato."""
    sucio = (
        '<table><tbody><tr><td class="terror">Andina S.A.C.</td></tr></tbody></table>'
    )
    assert "Andina" not in sanear_html(sucio).html


def test_un_envoltorio_marcado_no_conserva_el_tbody_que_envuelve():
    """``error-boundary`` es un envoltorio de React, no un mensaje. Y aunque
    ``error`` sí es una de sus piezas, la concesión no cruza hacia dentro de una
    tabla: por encima de la celda no aportaba señal, solo podía conservar datos."""
    sucio = (
        '<div class="error-boundary"><table><tbody>'
        "<tr><td>Comercializadora Andina S.A.C.</td></tr>"
        "</tbody></table></div>"
    )
    assert "Andina" not in sanear_html(sucio).html


def test_el_corte_tabular_tampoco_hereda_desde_role_ni_aria_live():
    """``role`` y ``aria-live`` comparten el contador de la concesión, así que el
    corte los cubre igual: un panel de alerta con una tabla dentro sigue siendo
    una tabla de datos."""
    sucio = (
        '<div role="alert"><table><tbody>'
        "<tr><td>Comercializadora Andina S.A.C.</td></tr>"
        "</tbody></table></div>"
    )
    assert "Andina" not in sanear_html(sucio).html


def test_una_marca_en_el_tbody_no_cuenta():
    """La otra mitad de la frontera. Un ``<tbody class="mensaje-error">`` tiene la
    misma forma de falso positivo que el ``<div class="error-boundary">``: envuelve
    la tabla entera, así que no es un mensaje ni marcando el elemento mismo. El
    corte se aplica igual a ``<table>``, ``<thead>`` y ``<tfoot>``; ``<tr>`` es la
    excepción, y la excepción tiene su propio test."""
    for envoltorio in ("table", "tbody", "thead", "tfoot"):
        sucio = (
            f'<table><{envoltorio} class="mensaje-error">'
            "<tr><td>Comercializadora Andina S.A.C.</td></tr>"
            f"</{envoltorio}></table>"
        )
        assert "Andina" not in sanear_html(sucio).html, envoltorio


@pytest.mark.parametrize(
    "marca",
    ["text-destructive", "mensaje-error", "estado-error", "mensaje-ayuda"],
)
def test_las_marcas_legitimas_siguen_conservando_el_mensaje(marca):
    """Lo que la narrowing NO puede llevarse: el mensaje renderizado dentro de la
    celda, que es la evidencia verbatim que acepta QA-D2. ``text-destructive`` es
    la convención de Tailwind del frontend de la casa: casa por la pieza
    ``destructive``."""
    sucio = (
        "<table><tbody><tr><td>"
        f'<span class="{marca}">El RUC debe tener 11 dígitos.</span>'
        "</td></tr></tbody></table>"
    )
    assert "El RUC debe tener 11 dígitos." in sanear_html(sucio).html


def test_la_marca_puede_ir_en_la_propia_celda():
    """El corte tabular no se lleva la marca del ``<td>`` mismo: corta la
    herencia de los ancestros, no lo que está en la fila, en la celda o por
    debajo —que es la frontera real—."""
    sucio = '<table><tbody><tr><td class="mensaje-error">Sin stock</td></tr></tbody></table>'
    assert "Sin stock" in sanear_html(sucio).html


def test_la_marca_en_la_propia_fila_cuenta_y_conserva_sus_celdas():
    """Validación **por fila**: ``<tr class="fila-error">`` es el patrón real con el
    que una aplicación marca la fila rechazada, y ese texto es la evidencia verbatim
    que pide QA-D2. El corte tabular guarda y reinicia el contador **antes** de sumar
    la marca del propio elemento, así que la fila se concede a sí misma lo que no
    hereda de un envoltorio. Residual declarado: se conserva el texto de TODAS sus
    celdas, y lo que sigue defendiéndolas es el enmascarado de dígitos y el candado.
    """
    sucio = (
        "<table><tbody>"
        '<tr class="fila-error"><td>Peso 0 kg: no admitido</td></tr>'
        "</tbody></table>"
    )
    assert "Peso 0 kg: no admitido" in sanear_html(sucio).html


def test_las_piezas_de_class_y_de_id_no_se_concatenan():
    """Si se juntaran antes de trocear, dos valores inocentes formarían una pieza
    que ninguno de los dos tiene."""
    sucio = (
        "<table><tbody><tr>"
        '<td class="mens" id="aje">Comercializadora Andina S.A.C.</td>'
        "</tr></tbody></table>"
    )
    assert "Andina" not in sanear_html(sucio).html


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
