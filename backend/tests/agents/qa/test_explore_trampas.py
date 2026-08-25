"""Las trampas del Modo C, ejercidas contra HTML congelado (QC4).

El ``manifest.json`` sustituye al navegador: da ``status``, redirecciones, la URL
final y el resultado de cada clic, de modo que la **capa 5** —revalidar esquema,
host, allowlist y origen en CADA navegación— se ejerce entera sin navegar, sin
servidor local y sin red. En este host, además, no hay alternativa: Chromium no
arranca.

Una advertencia que hay que dejar escrita: el doble **modela** el aborto de la
capa 3 en red (todo método ≠ ``GET``/``HEAD``), no lo demuestra. Hoy no hay
intercepción porque no hay navegador. Lo que estos tests fijan es la
**expectativa** contra la que QC5 tendrá que quedar verde, con la fixture ya
escrita y esperándolo.
"""

import pytest

from ai.agents.qa.explore.clicking import es_pulsable
from ai.agents.qa.explore.dom import elementos
from ai.agents.qa.explore.navigation import evaluar_navegacion
from ai.agents.qa.explore.session import ExploreSession
from ai.agents.qa.explore.target import assert_target_authorized
from tests.agents.qa.explore_fixtures import cargar, driver_de, escenarios
from tests.agents.qa.explore_helpers import HOST, configurar


def _por_testid(html: str, tag: str) -> dict:
    return {
        elemento.attr("data-testid"): elemento
        for elemento in elementos(html, tags=[tag])
    }


async def _sesion(monkeypatch, nombre: str):
    configurar(monkeypatch)
    escenario, driver = driver_de(nombre)
    sesion = ExploreSession(assert_target_authorized("tms-qa"), driver=driver)
    return escenario, driver, sesion


# --- el manifiesto como navegador --------------------------------------------


@pytest.mark.parametrize("nombre", escenarios())
def test_cada_escenario_tiene_un_manifiesto_coherente(nombre):
    """Un manifiesto que apunta a un fichero que no existe es una fixture que se
    cae en QC5, cuando ya no se sabe si falla el guard o la fixture."""
    escenario = cargar(nombre)
    paginas = escenario.manifest["pages"]
    assert escenario.manifest["entry"] in paginas
    assert set(escenario.manifest["visit_order"]) <= set(paginas)
    for entrada in list(paginas.values()) + list(
        escenario.manifest.get("clicks", {}).values()
    ):
        if entrada.get("file"):
            assert (escenario.raiz / entrada["file"]).is_file()
        else:
            assert entrada.get("location"), "Una página sin fichero redirige o no es"


@pytest.mark.parametrize("nombre", escenarios())
def test_todos_los_escenarios_viven_en_el_mismo_host_inventado(nombre):
    """Un solo host de fixture, el de los dobles de QC3: dos parecidos serían dos
    allowlists que configurar y una capa 5 que se ejerce a medias."""
    assert cargar(nombre).host == HOST


async def test_el_manifiesto_ejerce_la_entrada_y_su_redireccion(monkeypatch):
    """``/`` responde 302 a ``/login``: la redirección es una navegación nueva y
    se revalida como tal, sin que haga falta un servidor que la emita."""
    escenario, driver, sesion = await _sesion(monkeypatch, "tms_guias")
    entrada = await sesion.abrir()
    assert entrada.path == "/login"
    assert "Acceso al sistema de guías" in entrada.html
    assert driver.navegaciones == [escenario.url("/"), escenario.url("/login")]


async def test_el_recorrido_completo_de_una_aplicacion_observada(monkeypatch):
    escenario, _, sesion = await _sesion(monkeypatch, "tms_guias")
    entrada = await sesion.abrir()
    lista = await sesion.visitar(escenario.url("/guias"), depth=1, desde=entrada)
    alta = await sesion.visitar(escenario.url("/guias/nueva"), depth=2, desde=lista)
    assert [pagina.path for pagina in sesion.paginas] == [
        "/login",
        "/guias",
        "/guias/nueva",
    ]
    assert 'pattern="[0-9]{11}"' in alta.html
    assert sesion.salidas_bloqueadas == []


async def test_el_enlace_externo_del_listado_no_se_sigue(monkeypatch):
    """Una pestaña nueva sale del contexto controlado, y el host tampoco está en
    la allowlist: las dos capas dicen que no, cada una por su cuenta."""
    escenario, driver, sesion = await _sesion(monkeypatch, "tms_guias")
    lista = await sesion.visitar(escenario.url("/guias"))
    enlaces = _por_testid(lista.html, "a")

    assert not es_pulsable(enlaces["redes"]).pulsable
    veredicto = evaluar_navegacion(sesion.target, enlaces["redes"].attr("href"))
    assert not veredicto.permitida
    assert "allowlist" in veredicto.motivo
    assert driver.pulsados == []


# --- trampa 1: el <button> sin type ------------------------------------------


async def test_un_button_sin_type_dentro_de_un_form_no_se_pulsa(monkeypatch):
    """La trampa que define la política: en HTML eso es ``type="submit"``, y una
    lista blanca de ``<button>`` sería una lista blanca de envíos."""
    escenario, driver, sesion = await _sesion(monkeypatch, "trampas")
    pagina = await sesion.visitar(escenario.url("/trampas/button-sin-type"))
    botones = _por_testid(pagina.html, "button")

    veredicto, html = await sesion.pulsar_si_procede(pagina, botones["cerrar"])
    assert not veredicto.pulsable
    assert "type" in veredicto.motivo
    assert html is None
    assert driver.pulsados == []


async def test_el_hermano_con_type_explicito_si_se_pulsa(monkeypatch):
    """La línea no está en «dentro de un form»: bloquear todo lo que viva en un
    formulario dejaría fuera pestañas y acordeones, que son el valor del nivel 1."""
    escenario, driver, sesion = await _sesion(monkeypatch, "trampas")
    pagina = await sesion.visitar(escenario.url("/trampas/button-sin-type"))
    botones = _por_testid(pagina.html, "button")

    veredicto, html = await sesion.pulsar_si_procede(pagina, botones["ayuda"])
    assert veredicto.pulsable
    assert driver.pulsados == ['button[data-testid="ayuda"]']
    assert html


async def test_un_boton_de_fuera_que_envia_un_form_ajeno_tampoco_se_pulsa(
    monkeypatch,
):
    """``<button type="button" form="cierre">``: el ``type`` es correcto y aun así
    envía. Por eso el atributo ``form`` se mira aparte."""
    escenario, _, sesion = await _sesion(monkeypatch, "trampas")
    pagina = await sesion.visitar(escenario.url("/trampas/button-sin-type"))
    botones = _por_testid(pagina.html, "button")

    veredicto = es_pulsable(botones["cerrar-remoto"])
    assert not veredicto.pulsable
    assert "form" in veredicto.motivo


# --- trampa 2: la redirección fuera del host ---------------------------------


async def test_una_redireccion_fuera_del_host_no_se_sigue_y_se_registra(monkeypatch):
    """El enlace es del mismo origen y la capa 5 lo autoriza — hace bien. Quien
    salta fuera es el servidor, en la respuesta, que es justo lo que una
    comprobación hecha solo al arrancar no habría visto."""
    escenario, driver, sesion = await _sesion(monkeypatch, "trampas")
    pagina = await sesion.visitar(escenario.url("/trampas/redirect"))
    enlaces = _por_testid(pagina.html, "a")
    assert es_pulsable(
        enlaces["portal"],
        permite_navegar=lambda href: evaluar_navegacion(
            sesion.target, href, base=pagina.url
        ).permitida,
    ).pulsable

    salida = await sesion.visitar(escenario.url("/portal"), depth=1, desde=pagina)

    assert salida is None
    bloqueada = sesion.salidas_bloqueadas[-1]
    assert "Redirección 302 no seguida" in bloqueada.motivo
    assert "allowlist" in bloqueada.motivo
    # El origen que se registra es la URL que REDIRIGIÓ, no la página que la
    # enlazaba: es el dato con el que se arregla una allowlist.
    assert bloqueada.desde == "/portal"
    assert not any("portal.externo.pe" in url for url in driver.navegaciones)


# --- trampa 3: el POST en el clic --------------------------------------------


async def test_el_dom_no_puede_saber_que_un_boton_manda_un_post(monkeypatch):
    """El residual declarado, con test. ``<button type="button">`` explícito: la
    lista blanca lo aprueba y hace bien, porque leyendo el DOM no hay forma de
    saber qué dispara. **La mitad de la capa 3 que para esto es la de red**, y
    llega en QC5 — esta fixture existe para que llegue con el caso escrito."""
    escenario, _, sesion = await _sesion(monkeypatch, "trampas")
    pagina = await sesion.visitar(escenario.url("/trampas/post"))
    boton = _por_testid(pagina.html, "button")["aprobar"]

    assert es_pulsable(boton).pulsable


async def test_el_clic_que_dispara_un_post_se_aborta_y_no_se_observa_nada(
    monkeypatch,
):
    """Lo que QC5 tendrá que reproducir con ``page.route``: la petición muere y
    el DOM se queda como estaba. La página «aprobada» existe en el escenario y
    **no** se llega a ver."""
    escenario, driver, sesion = await _sesion(monkeypatch, "trampas")
    pagina = await sesion.visitar(escenario.url("/trampas/post"))
    boton = _por_testid(pagina.html, "button")["aprobar"]

    veredicto, html = await sesion.pulsar_si_procede(pagina, boton)

    assert veredicto.pulsable
    assert driver.abortados == [
        {"selector": 'button[data-testid="aprobar"]', "method": "POST"}
    ]
    assert "APROBADO" not in html
    assert "pendiente de aprobación" in html
    assert "APROBADO" in escenario.html("fetch_post_en_click_aprobado.html")


# --- trampa 4: el href javascript: -------------------------------------------


async def test_un_href_javascript_no_se_pulsa(monkeypatch):
    """La política de pulsado consulta la MISMA función que autoriza una
    navegación: si tuviera criterio propio, los dos podrían divergir — y la
    divergencia siempre se descubre por el lado malo."""
    escenario, driver, sesion = await _sesion(monkeypatch, "trampas")
    pagina = await sesion.visitar(escenario.url("/trampas/javascript"))
    enlaces = _por_testid(pagina.html, "a")

    veredicto, html = await sesion.pulsar_si_procede(pagina, enlaces["menu"])
    assert not veredicto.pulsable
    assert html is None
    assert driver.pulsados == []
    assert not evaluar_navegacion(
        sesion.target, "javascript:void(0)", base=pagina.url
    ).permitida


async def test_una_descarga_no_se_pulsa(monkeypatch):
    escenario, _, sesion = await _sesion(monkeypatch, "trampas")
    pagina = await sesion.visitar(escenario.url("/trampas/javascript"))
    enlaces = _por_testid(pagina.html, "a")

    veredicto = es_pulsable(enlaces["descarga"])
    assert not veredicto.pulsable
    assert "descarga" in veredicto.motivo


# --- el motivo entero del nivel 1 --------------------------------------------


async def test_pulsar_una_pestana_revela_un_formulario_que_no_estaba(monkeypatch):
    """Sin el nivel 1, la mayor parte del DOM de una SPA no existe: el formulario
    que se quiere caracterizar aparece **después** del clic. Con la restricción de
    que lo pulsado sea demostrablemente inocuo, que es lo que separa esto de
    «pulsar por ahí a ver qué pasa»."""
    escenario, driver, sesion = await _sesion(monkeypatch, "spa_router")
    pagina = await sesion.visitar(escenario.url("/app"))
    assert 'name="tracking"' not in pagina.html

    pestana = _por_testid(pagina.html, "button")["pestana-envios"]
    veredicto, html = await sesion.pulsar_si_procede(pagina, pestana)

    assert veredicto.pulsable
    assert 'name="tracking"' in html
    assert 'pattern="[A-Z]{3}[0-9]{9}"' in html
    assert driver.pulsados == ['button[data-testid="pestana-envios"]']
    assert sesion.salidas_bloqueadas == []
