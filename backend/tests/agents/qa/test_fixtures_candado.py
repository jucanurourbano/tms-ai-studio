"""El candado sobre las fixtures del Modo C: un test, no una nota en el README.

Una captura de una aplicación autenticada es un volcado de datos de producción y
el repositorio es para siempre. El saneador borra por defecto, pero el saneador se
puede saltar —las trampas se escriben a mano— así que la garantía no puede vivir
en él: vive aquí, recorriendo **todos** los ficheros del árbol.

Y como cualquier candado, no basta con verlo pasar: hay que verlo fallar. La mitad
de este fichero introduce la violación a propósito y comprueba que salta, con su
clase y su línea. Un candado que solo se ha probado contra ficheros limpios es
indistinguible de una función que devuelve la lista vacía.
"""

from pathlib import Path

import pytest

from ai.agents.qa.explore.sanitize import DOMINIOS_DE_LA_CASA, violaciones
from tests.agents.qa.explore_fixtures import DIRECTORIO


def _ficheros() -> list[Path]:
    return sorted(ruta for ruta in DIRECTORIO.rglob("*") if ruta.is_file())


def _ids(rutas: list[Path]) -> list[str]:
    return [ruta.relative_to(DIRECTORIO).as_posix() for ruta in rutas]


FICHEROS = _ficheros()


# --- el candado sobre lo que hay comiteado -----------------------------------


@pytest.mark.parametrize("ruta", FICHEROS, ids=_ids(FICHEROS))
def test_ninguna_fixture_lleva_datos_de_produccion(ruta):
    encontradas = violaciones(ruta.read_text(encoding="utf-8"))
    assert encontradas == [], f"{ruta.name}: " + "; ".join(str(v) for v in encontradas)


def test_el_candado_cubre_todo_el_arbol_y_no_solo_el_html():
    """Un ``manifest.json`` con el host real dentro sería igual de definitivo que
    una captura cruda, y un README también se comitea."""
    extensiones = {ruta.suffix for ruta in FICHEROS}
    assert {".html", ".json", ".md"} <= extensiones
    assert len(FICHEROS) >= 10


# --- verlo fallar: las cuatro violaciones, introducidas a propósito ----------


@pytest.mark.parametrize(
    "clase, sucio",
    [
        ("digitos", "<td>00012345678</td>"),
        ("digitos", '<input name="guia" placeholder="20512345678">'),
        ("host", '<a href="https://tms.urbano.com.pe/guias">Guías</a>'),
        ("host", '{"origin": "https://otro.urbano.pe"}'),
        ("value", '<input name="ruc" value="20512345">'),
        ("value", "<option value='150122'>Miraflores</option>"),
        ("value", "<input value=abierto>"),
        (
            "texto",
            "<table><tbody><tr><td>"
            '<button type="button" aria-label="Acciones de Juan Perez Quispe">⋮</button>'
            "</td></tr></tbody></table>",
        ),
        ("texto", '<td><img alt="Firma de Juan Perez Quispe"></td>'),
    ],
)
def test_el_candado_salta_cuando_debe(clase, sucio):
    """La cuarta clase —``texto``— es la que cierra F1, y es justo la que más falta
    hace aquí: las trampas se escriben a mano y **nunca pasan por el saneador**, así
    que para ellas este candado es la única capa que existe."""
    encontradas = violaciones(sucio)
    assert clase in {v.clase for v in encontradas}, f"No detectó {clase} en {sucio}"


def test_la_violacion_dice_en_que_linea_esta():
    """Sin la línea, el candado dice «hay algo sucio» y deja el trabajo entero
    al humano: en una captura de 400 líneas eso es no decir nada."""
    texto = "<p>limpio</p>\n<p>limpio</p>\n<td>00012345678</td>\n"
    encontradas = violaciones(texto)
    assert [(v.clase, v.linea) for v in encontradas] == [("digitos", 3)]


def test_el_host_prohibido_se_puede_ampliar_por_llamada():
    """El host explorado no tiene por qué ser de la casa (un proveedor externo
    con la aplicación alojada), así que quien captura lo declara."""
    sucio = '<a href="https://tms.proveedor-externo.net/x">x</a>'
    assert violaciones(sucio) == []
    assert violaciones(sucio, hosts_prohibidos=["tms.proveedor-externo.net"])


def test_los_dominios_de_la_casa_no_dependen_de_que_nadie_los_declare():
    """El candado por defecto ya los conoce: es lo que hace que valga para el
    fichero que alguien añada mañana sin leer esto."""
    for dominio in DOMINIOS_DE_LA_CASA:
        assert violaciones(f"<p>{dominio}</p>")


# --- y no saltar cuando no debe ----------------------------------------------


@pytest.mark.parametrize(
    "limpio",
    [
        '<input name="ruc" value="">',
        '<option value="">Lima / Lima / Miraflores</option>',
        '{"clicks": {"a": {"status": 200, "file": "01.html"}}}',
        '<input maxlength="11" pattern="[0-9]{11}" minlength="11">',
        '<input data-value="algo">',
        "<p>Formato: tres letras y nueve dígitos.</p>",
        '<button type="button" aria-label="Buscar guías">🔍</button>',
        '<table><tbody><tr><td aria-expanded="true">Detalle</td></tr></tbody></table>',
    ],
)
def test_el_candado_no_muerde_lo_que_debe_conservarse(limpio):
    """El atributo vacío, el patrón de validación y un ``data-value`` no son
    datos: si el candado los tumbara, la salida del saneador no pasaría su
    propio candado y el bloque entero sería inconsistente."""
    assert violaciones(limpio) == []
