"""Capa 5: la allowlist se re-verifica en CADA navegación.

INV2 necesitaba cuatro capas porque una base de datos no redirige. Estos tests
existen porque una aplicación web sí, y una comprobación hecha solo al arrancar
habría autorizado la primera navegación y ninguna de las que el destino elige.
"""

import pytest

from ai.agents.qa.explore.navigation import (
    assert_navigation_allowed,
    evaluar_navegacion,
)
from ai.agents.qa.explore.target import assert_target_authorized
from app.errors import ForbiddenError
from tests.agents.qa.explore_helpers import URL_BASE, configurar


@pytest.fixture
def destino(monkeypatch):
    configurar(monkeypatch)
    return assert_target_authorized("tms-qa")


# --- esquemas ----------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "data:text/html,<h1>hola",
        "javascript:alert(1)",
        "blob:https://tms.interno/abc",
        "about:blank",
        "ftp://tms.interno/x",
        "mailto:alguien@urbano.com.pe",
        "ws://tms.interno/socket",
        "view-source:https://tms.interno/",
    ],
)
def test_solo_se_navega_http_o_https(destino, url):
    veredicto = evaluar_navegacion(destino, url)
    assert not veredicto.permitida
    assert "http" in veredicto.motivo


def test_una_url_sin_esquema_absoluto_no_se_navega_sin_base(destino):
    """Sin página de partida, un relativo no se puede resolver: no se adivina."""
    assert not evaluar_navegacion(destino, "/guias/nueva").permitida


def test_un_relativo_se_resuelve_contra_la_pagina_actual(destino):
    veredicto = evaluar_navegacion(
        destino, "nueva", base="https://tms.interno/guias/lista"
    )
    assert veredicto.permitida
    assert veredicto.url == "https://tms.interno/guias/nueva"


# --- host y origen -----------------------------------------------------------


def test_un_host_fuera_de_la_allowlist_no_se_navega(destino):
    veredicto = evaluar_navegacion(destino, "https://evil.com/x")
    assert not veredicto.permitida
    assert "allowlist" in veredicto.motivo


def test_un_protocolo_relativo_no_es_un_atajo_al_exterior(destino):
    """``//evil.com/x`` resuelve a un absoluto de otro host: mismo rechazo."""
    veredicto = evaluar_navegacion(destino, "//evil.com/x", base=URL_BASE)
    assert not veredicto.permitida


def test_la_allowlist_se_relee_en_cada_navegacion(destino, monkeypatch):
    """Vaciarla a mitad de una exploración cierra la puerta en la navegación
    siguiente, no en la próxima corrida."""
    assert evaluar_navegacion(destino, URL_BASE).permitida
    configurar(monkeypatch, hosts=[])
    assert not evaluar_navegacion(destino, URL_BASE).permitida


def test_desactivar_la_exploracion_detiene_la_navegacion(destino, monkeypatch):
    from app.config.settings import settings

    monkeypatch.setattr(settings, "QA_EXPLORE_ENABLED", False)
    assert not evaluar_navegacion(destino, URL_BASE).permitida


def test_un_host_permitido_pero_de_otro_puerto_es_otro_origen(destino, monkeypatch):
    """El mismo-origen es esquema + host + puerto: un puerto distinto es otra app."""
    veredicto = evaluar_navegacion(destino, "https://tms.interno:8443/x")
    assert not veredicto.permitida
    assert "origen" in veredicto.motivo


def test_bajar_a_http_desde_https_es_salir_del_origen(destino, monkeypatch):
    veredicto = evaluar_navegacion(destino, "http://tms.interno/x")
    assert not veredicto.permitida


def test_una_url_vacia_no_navega(destino):
    assert not evaluar_navegacion(destino, "   ").permitida


# --- la forma dura, para la navegación de entrada ----------------------------


def test_assert_devuelve_la_url_cuando_autoriza(destino):
    assert assert_navigation_allowed(destino, URL_BASE) == URL_BASE


def test_assert_revienta_con_el_motivo_dentro(destino):
    with pytest.raises(ForbiddenError, match="allowlist"):
        assert_navigation_allowed(destino, "https://evil.com/")
