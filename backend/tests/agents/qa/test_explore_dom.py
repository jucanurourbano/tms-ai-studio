"""El DOM mínimo: lo justo para decidir, sin dependencias y sin navegador.

La pregunta de la que depende una decisión de seguridad es "¿estoy dentro de un
formulario?", así que es la única que no se responde con la pila best-effort.
"""

from ai.agents.qa.explore.dom import elementos, selector_de


def test_un_input_no_desalinea_la_pila_de_ancestros():
    """Los elementos vacíos no se apilan: si ``<input>`` se apilara, el primero
    de un formulario dejaría todo lo siguiente colgando de él."""
    html = "<form><input name=a><button type='button' id='b'>x</button></form>"
    boton = elementos(html, tags=["button"])[0]
    assert boton.ancestros == ("form",)
    assert boton.en_formulario


def test_un_elemento_autocerrado_no_toca_la_pila():
    html = "<div><br/><span id='s'>x</span></div>"
    span = elementos(html, tags=["span"])[0]
    assert span.ancestros == ("div",)


def test_fuera_del_formulario_se_ve_que_esta_fuera():
    html = "<form><input name=a></form><div role='button' id='d'>x</div>"
    div = elementos(html, tags=["div"])[0]
    assert not div.en_formulario


def test_un_formulario_sin_cerrar_deja_el_error_del_lado_seguro():
    """Si el contador no vuelve a cero, todo lo posterior se considera dentro del
    formulario. Es el lado correcto del error."""
    html = "<form><input name=a><div role='button' id='d'>x</div>"
    div = elementos(html, tags=["div"])[0]
    assert div.en_formulario


def test_un_cierre_de_mas_no_vacia_la_pila():
    html = "<section><div></div></div><span id='s'>x</span></section>"
    span = elementos(html, tags=["span"])[0]
    assert "section" in span.ancestros


def test_los_atributos_booleanos_estan_presentes_con_valor_vacio():
    campo = elementos("<input name='ruc' required maxlength='11'>")[0]
    assert campo.tiene("required")
    assert campo.attr("required") == ""
    assert campo.attr("maxlength") == "11"


def test_el_orden_del_selector_canonico_es_fijo():
    """``[name]`` › ``#id`` › ``[data-testid]``: el mismo elemento produce el mismo
    selector en dos corridas, que es lo que permite compararlas."""
    html = "<button type='button' name='n' id='i' data-testid='t'>x</button>"
    assert selector_de(elementos(html, tags=["button"])[0]).valor == (
        'button[name="n"]'
    )
    html = "<button type='button' id='i' data-testid='t'>x</button>"
    seleccion = selector_de(elementos(html, tags=["button"])[0])
    assert seleccion.valor == 'button[id="i"]'
    assert seleccion.estrategia == "id"
    html = "<button type='button' data-testid='t'>x</button>"
    assert selector_de(elementos(html, tags=["button"])[0]).estrategia == (
        "data-testid"
    )


def test_sin_atributo_estable_no_se_inventa_un_selector():
    """QC5 añadirá el selector estructural **con su ``selector_strategy``**, para
    que quien lea el plan sepa qué anclas son frágiles. Inventarlo aquí, sin ese
    campo, sería frágil y además callado."""
    assert selector_de(elementos("<a href='/x'>x</a>", tags=["a"])[0]) is None


def test_un_valor_con_comillas_no_rompe_el_selector():
    html = "<button type='button' name='di&quot;cho'>x</button>"
    assert '\\"' in selector_de(elementos(html, tags=["button"])[0]).valor
