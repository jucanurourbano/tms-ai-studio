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


# --- F1: el texto que se esconde en un atributo ------------------------------
#
# La fuga que cierra este bloque es la del panel de usuarios de la casa: la pasada
# de accesibilidad mete el nombre del sujeto de la fila DENTRO de un atributo, donde
# ni el vaciado de celdas lo veía —mira el cuerpo, no los atributos— ni el candado
# lo buscaba. Un nombre no lo salva ningún patrón de dígitos: se comiteaba.

#: El caso F1 exacto, tal cual sale de nuestro panel: icono dentro del botón y el
#: nombre en el ``aria-label``, que es lo único que lo identifica.
F1 = (
    "<table><tbody>"
    '<tr><td><button type="button" aria-label="Acciones de Juan Perez Quispe">'
    "⋮</button></td></tr>"
    "</tbody></table>"
)


def test_f1_el_nombre_del_sujeto_de_la_fila_no_sobrevive_en_un_aria_label():
    """El caso que obliga al bloque. Contra el código anterior este test falla:
    el ``aria-label`` salía intacto de la celda."""
    saneado = sanear_html(F1).html
    assert "Juan Perez Quispe" not in saneado
    assert 'aria-label=""' in saneado, "el hueco es estructura: se conserva vacío"


def test_f1_el_candado_lo_ve_y_no_devuelve_la_lista_vacia():
    """La otra mitad, y la que importa para las trampas: se escriben a mano y no
    pasan por el saneador, así que la garantía no puede vivir solo en él."""
    encontradas = violaciones(F1)
    assert [v.clase for v in encontradas] == ["texto"]
    assert "aria-label" in encontradas[0].detalle


def test_f1_lo_saneado_pasa_su_propio_candado():
    """Si no, ``escenario_saneado`` reventaría sobre su propia salida y el bloque
    sería inconsistente."""
    assert violaciones(sanear_html(F1).html) == []


def test_f1_el_descarte_no_es_silencioso():
    """``CLAUDE.md`` §8 aplicado al atributo: el retirado dice cuál era."""
    retirados = sanear_html(F1).retirados
    assert any(
        r.clase == "dato" and "aria-label" in r.detalle for r in retirados
    ), retirados


@pytest.mark.parametrize(
    "atributo, valor",
    [
        ("aria-label", "Acciones de Juan Perez Quispe"),
        ("aria-description", "Guía del cliente Andina S.A.C."),
        ("title", "Comercializadora Andina S.A.C."),
        ("alt", "Firma de Juan Perez Quispe"),
        ("placeholder", "Juan Perez Quispe"),
        ("label", "Andina S.A.C."),
        ("abbr", "Andina"),
        ("download", "guia-de-Juan-Perez.pdf"),
    ],
)
def test_todo_atributo_que_el_navegador_renderiza_se_vacia_en_una_celda(
    atributo, valor
):
    """El régimen es el del texto de la celda, y es el mismo para los seis
    atributos de HTML y para la prosa de ``aria-``."""
    sucio = f'<table><tbody><tr><td><span {atributo}="{valor}">x</span></td></tr></tbody></table>'
    assert valor not in sanear_html(sucio).html


# --- la regla es estructural, no una lista de nombres ------------------------


def test_un_aria_de_prosa_que_nadie_escribio_ya_esta_cubierto():
    """La prueba de que la regla no es una lista: ``aria-rowindextext`` es prosa
    **y vive justo dentro de una celda**, y queda cubierto porque lo que se
    enumera es la mitad cerrada (tokens, booleanos, números, IDREF)."""
    sucio = (
        "<table><tbody><tr>"
        '<td aria-rowindextext="Guía de Juan Perez Quispe">x</td>'
        "</tr></tbody></table>"
    )
    assert "Juan Perez Quispe" not in sanear_html(sucio).html


def test_un_aria_que_la_especificacion_anada_manana_entra_por_el_lado_benigno():
    """Un atributo ``aria-`` desconocido se trata como prosa: si lo era, no se
    comitea; si era un token, se pierde señal. La lista abierta es la peligrosa,
    así que la que se enumera es la otra."""
    assert sanitize._es_texto_visible("aria-loquesea") is True


@pytest.mark.parametrize(
    "atributo, valor",
    [
        ("aria-expanded", "true"),
        ("aria-live", "polite"),
        ("aria-describedby", "ayuda-ruc"),
        ("aria-colindex", "3"),
        ("aria-invalid", "true"),
    ],
)
def test_los_atributos_aria_que_no_son_prosa_sobreviven_en_la_celda(atributo, valor):
    """Son estructura —el estado de un acordeón, la región viva, el IDREF de la
    descripción— y sin ellos la fixture pierde el ancla de un caso."""
    sucio = (
        f'<table><tbody><tr><td><button type="button" {atributo}="{valor}">'
        "x</button></td></tr></tbody></table>"
    )
    assert f'{atributo}="{valor}"' in sanear_html(sucio).html


def test_aria_describedby_no_es_prosa_y_su_texto_se_gobierna_donde_vive():
    """El valor es un IDREF: lo que el usuario lee es el texto del elemento
    apuntado, y ahí ya lo gobierna el mismo régimen. Residual declarado: si ese
    elemento está fuera de la celda, su texto se conserva —fuera de la celda el
    texto es la evidencia—. (El id se elige neutro a propósito: un ``id="ayuda"``
    casa con una pieza de mensaje y el ``<span>`` se conservaría por rótulo, que es
    otra decisión y no la que este test fija.)"""
    assert "aria-describedby" in sanitize.ARIA_SIN_PROSA
    sucio = (
        "<table><tbody><tr>"
        '<td><input aria-describedby="d-ruc"><span id="d-ruc">Andina S.A.C.</span></td>'
        "</tr></tbody></table>"
    )
    assert "Andina" not in sanear_html(sucio).html


# --- lo que NO se puede llevar por delante -----------------------------------


def test_un_rotulo_genuino_fuera_de_una_celda_conserva_su_aria_label():
    """El icono sin texto es la mitad de los controles de una aplicación: si el
    saneador se llevara su nombre accesible, la fixture perdería el rótulo del
    control y QC4.5 se quedaría sin su cuarta estrategia de ancla."""
    sucio = '<button type="button" aria-label="Buscar guías">🔍</button>'
    assert 'aria-label="Buscar guías"' in sanear_html(sucio).html
    assert violaciones(sucio) == []


def test_los_placeholder_de_formato_sobreviven_fuera_de_la_celda():
    """El formato esperado es el ancla de un caso de borde (QA-D2)."""
    sucio = '<input name="emision" placeholder="DD/MM/AAAA">'
    assert 'placeholder="DD/MM/AAAA"' in sanear_html(sucio).html


def test_un_rotulo_dentro_de_la_celda_tambien_conserva_sus_atributos():
    """El régimen de los atributos es el del texto, escapatoria de rótulo
    incluida: un ``<label>`` en la celda rotula sus atributos igual que su texto,
    y la marca del propio ``<td>`` cuenta como cuenta para el cuerpo."""
    sucio = (
        "<table><tbody><tr>"
        '<td><label title="RUC del shipper">RUC</label></td>'
        '<td class="mensaje-error" aria-label="Peso no admitido">0 kg</td>'
        "</tr></tbody></table>"
    )
    saneado = sanear_html(sucio).html
    assert 'title="RUC del shipper"' in saneado
    assert 'aria-label="Peso no admitido"' in saneado


def test_residual_un_placeholder_de_formato_dentro_de_una_celda_se_pierde():
    """Declarado, no descubierto: una edición en línea dentro de la tabla pierde
    su pista de formato. Es la dirección barata —se pierde señal, no se comitea un
    dato— y el descarte queda anotado, así que quien captura lo ve."""
    sucio = (
        "<table><tbody><tr>"
        '<td><input name="emision" placeholder="DD/MM/AAAA"></td>'
        "</tr></tbody></table>"
    )
    resultado = sanear_html(sucio)
    assert "DD/MM/AAAA" not in resultado.html
    assert any("placeholder" in r.detalle for r in resultado.retirados)


def test_el_enmascarado_de_digitos_sigue_valiendo_en_los_atributos_de_texto():
    """Fuera de la celda el atributo se conserva, así que la máscara vuelve a ser
    lo único que separa un rótulo de un identificador de negocio."""
    sucio = '<a download="guia-20512345678.pdf" href="/g">Descargar</a>'
    assert f"guia-{MASCARA}.pdf" in sanear_html(sucio).html


def test_sanear_sigue_siendo_idempotente_con_atributos_de_texto():
    una = sanear_html(F1).html
    assert sanear_html(una).html == una


# --- el candado no muerde lo que debe conservarse ----------------------------


@pytest.mark.parametrize(
    "limpio",
    [
        '<button type="button" aria-label="Buscar guías">🔍</button>',
        '<input name="emision" placeholder="DD/MM/AAAA">',
        '<table><tbody><tr><td><label title="RUC">RUC</label></td></tr></tbody></table>',
        '<table><tbody><tr><td aria-expanded="true">x</td></tr></tbody></table>',
        '<table><tbody><tr><td><span class="mensaje-error" title="Sin stock">0</span></td></tr></tbody></table>',
    ],
)
def test_el_candado_de_texto_no_muerde_fuera_de_la_celda_ni_al_rotulo(limpio):
    """Si mordiera, la salida del saneador no pasaría su propio candado. La
    escapatoria de rótulo es la misma función en los dos, no una copia."""
    assert violaciones(limpio) == []


def test_el_candado_de_texto_dice_en_que_linea_esta():
    texto = "<table><tbody>\n<tr>\n" + F1.split("<tbody>")[1]
    encontradas = [v for v in violaciones(texto) if v.clase == "texto"]
    assert [v.linea for v in encontradas] == [3]


# --- el vocabulario de atributos renderizados también es auditable -----------

#: El formato de una línea de la lista del docstring: atributo y su caso. Las
#: flechas lo separan del vocabulario de :data:`PIEZAS_DE_MENSAJE`, que usa «—».
LINEA_DE_ATRIBUTO = re.compile(r"^\* ``([a-z]+)`` → ", re.MULTILINE)


def test_el_docstring_documenta_exactamente_los_atributos_renderizados():
    """Mismo régimen que las piezas de mensaje: una lista de literales cuyo caso
    vive en un docstring solo es auditable si los dos no pueden separarse."""
    documentados = set(LINEA_DE_ATRIBUTO.findall(sanitize.__doc__ or ""))
    assert documentados == set(sanitize.ATRIBUTOS_RENDERIZADOS)


def test_la_mitad_enumerada_de_aria_es_la_cerrada():
    """El candado de la decisión: lo que se enumera son los tokens, y la prosa es
    el default. Si alguien invirtiera la lista, esto salta."""
    assert "aria-label" not in sanitize.ARIA_SIN_PROSA
    assert "aria-live" in sanitize.ARIA_SIN_PROSA
    assert all(nombre.startswith("aria-") for nombre in sanitize.ARIA_SIN_PROSA)
