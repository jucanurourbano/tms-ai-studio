"""``ExploreSession``: la jaula en movimiento, con el navegador inyectado.

Todo aquí se ejerce con un driver falso. No es una comodidad: la capa 4 del
cortafuegos es **ciega al navegador** (otro proceso, otros sockets), así que un
test con navegador real saldría a la red sin que nadie lo viera. Y en este host
Chromium tampoco arranca.
"""

import pytest

from ai.agents.qa.explore.dom import elementos
from ai.agents.qa.explore.driver import RespuestaNavegacion
from ai.agents.qa.explore.limits import LimitesExploracion
from ai.agents.qa.explore.session import ExploreSession
from ai.agents.qa.explore.target import assert_target_authorized
from app.errors import ForbiddenError
from tests.agents.qa.explore_helpers import (
    HOST,
    URL_BASE,
    DriverFalso,
    configurar,
    pagina,
)

LISTA = "https://tms.interno/guias/lista"
NUEVA = "https://tms.interno/guias/nueva"

HTML_LISTA = """
<html><body>
  <a href="/guias/nueva" id="nueva">Nueva guía</a>
  <a href="https://evil.com/x" id="fuera">Externo</a>
</body></html>
"""

HTML_NUEVA = """
<html><body>
  <form name="guia" action="/guias" method="post">
    <input name="ruc" required maxlength="11" pattern="[0-9]{11}">
    <button type="button" name="agregar">Añadir línea</button>
    <button name="guardar">Guardar</button>
  </form>
</body></html>
"""


@pytest.fixture
def destino(monkeypatch):
    configurar(monkeypatch)
    return assert_target_authorized("tms-qa")


def sesion(destino, driver, **topes):
    limites = LimitesExploracion(
        max_pages=topes.get("max_pages", 10),
        max_depth=topes.get("max_depth", 2),
        timeout_ms=topes.get("timeout_ms", 1000),
        total_budget_s=topes.get("total_budget_s", 300),
        max_clicks_per_page=topes.get("max_clicks_per_page", 3),
    )
    reloj = topes.get("reloj")
    return ExploreSession(
        destino,
        driver=driver,
        limites=limites,
        **({"reloj": reloj} if reloj else {}),
    )


# --- navegación y capa 5 en movimiento ---------------------------------------


async def test_abrir_visita_la_url_base_y_guarda_el_path(destino):
    driver = DriverFalso(paginas={URL_BASE: pagina(URL_BASE, HTML_LISTA)})
    s = sesion(destino, driver)
    p = await s.abrir()
    assert p is not None
    assert p.path == "/"
    assert s.paths == ["/"]
    assert s.dom(p) == HTML_LISTA


async def test_abrir_revienta_si_el_destino_no_esta_autorizado(destino, monkeypatch):
    """En la entrada, un destino fuera de la jaula es una configuración inválida."""
    configurar(monkeypatch, hosts=["otra.cosa"])
    with pytest.raises(ForbiddenError):
        await sesion(destino, DriverFalso()).abrir()


async def test_un_enlace_externo_no_se_visita_y_se_registra(destino):
    driver = DriverFalso(paginas={URL_BASE: pagina(URL_BASE, HTML_LISTA)})
    s = sesion(destino, driver)
    origen = await s.abrir()
    assert await s.visitar("https://evil.com/x", desde=origen) is None
    assert driver.navegaciones == [URL_BASE]  # no se llegó a navegar
    salida = s.salidas_bloqueadas[0]
    assert "allowlist" in salida.motivo
    assert salida.desde == "/"


async def test_una_redireccion_fuera_de_host_no_se_sigue_y_se_registra(destino):
    """El caso que obliga a tener capa 5: la BD no redirige, la aplicación sí."""
    driver = DriverFalso(
        paginas={
            URL_BASE: RespuestaNavegacion(
                status=302, url=URL_BASE, location="https://evil.com/robado"
            )
        }
    )
    s = sesion(destino, driver)
    assert await s.abrir() is None
    assert s.paginas == []
    salida = s.salidas_bloqueadas[0]
    assert "302" in salida.motivo
    assert "evil.com" in salida.url


async def test_una_redireccion_dentro_del_origen_si_se_sigue(destino):
    driver = DriverFalso(
        paginas={
            URL_BASE: RespuestaNavegacion(
                status=302, url=URL_BASE, location="/guias/lista"
            ),
            LISTA: pagina(LISTA, HTML_LISTA),
        }
    )
    s = sesion(destino, driver)
    p = await s.abrir()
    assert p is not None and p.path == "/guias/lista"


async def test_una_cadena_infinita_de_redirecciones_se_corta(destino):
    driver = DriverFalso(
        paginas={
            URL_BASE: RespuestaNavegacion(status=302, url=URL_BASE, location="/a"),
            "https://tms.interno/a": RespuestaNavegacion(
                status=302, url="https://tms.interno/a", location="/b"
            ),
            "https://tms.interno/b": RespuestaNavegacion(
                status=302, url="https://tms.interno/b", location="/a"
            ),
        }
    )
    s = sesion(destino, driver)
    assert await s.abrir() is None
    assert any("redirecciones" in x.motivo for x in s.salidas_bloqueadas)


async def test_si_el_driver_termina_fuera_del_origen_se_descarta_el_contenido(
    destino,
):
    """Un driver que sigue redirecciones por su cuenta no puede colar un DOM de
    otro host: un DOM ajeno no es observación del sistema explorado."""
    driver = DriverFalso(
        paginas={
            URL_BASE: RespuestaNavegacion(
                status=200, url="https://evil.com/inicio", html="<h1>otro sitio</h1>"
            )
        }
    )
    s = sesion(destino, driver)
    assert await s.abrir() is None
    assert s.paginas == []
    assert "fuera de la jaula" in s.salidas_bloqueadas[0].motivo


async def test_la_misma_url_no_se_visita_dos_veces(destino):
    driver = DriverFalso(paginas={URL_BASE: pagina(URL_BASE, HTML_LISTA)})
    s = sesion(destino, driver)
    primera = await s.abrir()
    segunda = await s.visitar(URL_BASE)
    assert primera is segunda
    assert driver.navegaciones == [URL_BASE]


# --- presupuesto y radio de acción ------------------------------------------


async def test_el_tope_de_paginas_se_declara_con_lo_que_queda_pendiente(destino):
    """Lo que quede sin recorrer se enumera: nunca se trunca en silencio."""
    driver = DriverFalso(
        paginas={
            URL_BASE: pagina(URL_BASE, HTML_LISTA),
            LISTA: pagina(LISTA, HTML_LISTA),
        }
    )
    s = sesion(destino, driver, max_pages=1)
    await s.abrir()
    assert await s.visitar(LISTA) is None
    assert s.presupuesto_agotado
    assert s.pendientes == [LISTA]
    assert "Tope de páginas" in s.resumen()["budget_reason"]


async def test_la_profundidad_maxima_detiene_el_descenso(destino):
    driver = DriverFalso(paginas={URL_BASE: pagina(URL_BASE, HTML_LISTA)})
    s = sesion(destino, driver, max_depth=1)
    assert await s.visitar(URL_BASE, depth=2) is None
    assert "Profundidad" in s.resumen()["budget_reason"]


async def test_el_presupuesto_de_tiempo_detiene_la_exploracion(destino):
    """Reloj inyectado: el tope se comprueba de verdad y el test no espera."""
    # La primera lectura fija el arranque; las siguientes ya están fuera de plazo.
    lecturas = [0.0]
    driver = DriverFalso(
        paginas={
            URL_BASE: pagina(URL_BASE, HTML_LISTA),
            LISTA: pagina(LISTA, HTML_LISTA),
        }
    )

    def reloj() -> float:
        return lecturas.pop(0) if lecturas else 400.0

    s = sesion(destino, driver, total_budget_s=300, reloj=reloj)
    assert await s.abrir() is not None
    assert await s.visitar(LISTA) is None
    assert s.presupuesto_agotado
    assert "tiempo" in s.resumen()["budget_reason"]


# --- interacción ------------------------------------------------------------


async def test_solo_se_pulsa_lo_que_la_lista_blanca_permite(destino):
    driver = DriverFalso(paginas={NUEVA: pagina(NUEVA, HTML_NUEVA)})
    s = sesion(destino, driver)
    p = await s.visitar(NUEVA)
    agregar, guardar = elementos(s.dom(p), tags=["button"])

    veredicto, html = await s.pulsar_si_procede(p, agregar)
    assert veredicto.pulsable and html
    assert driver.pulsados == ['button[name="agregar"]']

    veredicto, html = await s.pulsar_si_procede(p, guardar)
    assert not veredicto.pulsable and html is None
    assert driver.pulsados == ['button[name="agregar"]']  # no se pulsó el submit


async def test_el_presupuesto_de_clics_por_pagina_es_real(destino):
    """Un acordeón recursivo no convierte la exploración en un generador de carga."""
    driver = DriverFalso(paginas={NUEVA: pagina(NUEVA, HTML_NUEVA)})
    s = sesion(destino, driver, max_clicks_per_page=2)
    p = await s.visitar(NUEVA)
    agregar = elementos(s.dom(p), tags=["button"])[0]
    for _ in range(2):
        assert (await s.pulsar_si_procede(p, agregar))[0].pulsable
    veredicto, _ = await s.pulsar_si_procede(p, agregar)
    assert not veredicto.pulsable
    assert "Presupuesto de clics" in veredicto.motivo
    assert len(driver.pulsados) == 2


async def test_un_clic_que_lleva_fuera_de_la_jaula_se_registra(destino):
    driver = DriverFalso(
        paginas={NUEVA: pagina(NUEVA, HTML_NUEVA)},
        clics={
            'button[name="agregar"]': RespuestaNavegacion(
                status=200, url="https://evil.com/", html="<h1>fuera</h1>"
            )
        },
    )
    s = sesion(destino, driver)
    p = await s.visitar(NUEVA)
    agregar = elementos(s.dom(p), tags=["button"])[0]
    veredicto, html = await s.pulsar_si_procede(p, agregar)
    assert not veredicto.pulsable and html is None
    assert "salió de la jaula" in s.salidas_bloqueadas[0].motivo


# --- capa 4 y propiedad del contexto ----------------------------------------


async def test_la_credencial_no_llega_a_la_pagina_observada(monkeypatch):
    configurar(
        monkeypatch,
        destinos={
            "tms-qa": {
                "url": f"https://qa:s3cr3t0@{HOST}/",
                "readonly_verified": True,
            }
        },
    )
    destino = assert_target_authorized("tms-qa")
    pedida = f"https://qa:s3cr3t0@{HOST}/"
    driver = DriverFalso(paginas={pedida: pagina(pedida, HTML_LISTA)})
    s = sesion(destino, driver)
    p = await s.abrir()
    assert "s3cr3t0" not in p.url
    assert "s3cr3t0" not in str(s.resumen())


async def test_ningun_atributo_publico_devuelve_el_driver(destino):
    """§3.3.1: un nodo no tiene acceso al objeto con el que se podría escribir."""
    driver = DriverFalso()
    s = sesion(destino, driver)
    publicos = [
        getattr(s, nombre)
        for nombre in dir(s)
        if not nombre.startswith("_") and not callable(getattr(s, nombre, None))
    ]
    assert driver not in publicos


async def test_la_sesion_no_cierra_un_driver_que_no_creo(destino):
    """El doble inyectado lo cierra quien lo inyectó."""
    driver = DriverFalso()
    await sesion(destino, driver).cerrar()
    assert not driver.cerrado


async def test_el_resumen_declara_el_radio_de_accion_efectivo(destino):
    driver = DriverFalso(paginas={URL_BASE: pagina(URL_BASE, HTML_LISTA)})
    s = sesion(destino, driver, max_pages=7)
    await s.abrir()
    resumen = s.resumen()
    assert resumen["alias"] == "tms-qa"
    assert resumen["host"] == HOST
    assert resumen["data_class"] == "real"
    assert resumen["limits"]["max_pages"] == 7
    assert resumen["pages_visited"] == ["/"]
    assert resumen["budget_exhausted"] is False
