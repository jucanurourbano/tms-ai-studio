"""Test del cortafuegos contra las llamadas reales (REGLA DE PRESUPUESTO).

Los nodos generativos caen en el cliente real cuando nadie inyecta un mock por
``config``. Un test nuevo que se olvide del mock intentaría una llamada real, así
que ``tests/conftest.py`` lo bloquea de forma autouse. Este test verifica **el
cortafuegos en sí**: si alguien lo quita o lo rompe, esto falla.

No es una precaución teórica: durante BD3, tres tests del bloque anterior dejaron
de tener stub en el nodo TABLES y llegaron a la API (rechazada con 400, sin coste).
De ahí viene esta protección.

LLM1 la generaliza a cuatro capas (LLM-D12) y añade el criterio central del
bloque: ``test_toda_capa_cubre_a_todo_proveedor_registrado`` falla si mañana se
registra un proveedor sin cobertura de cortafuegos. La protección tiene que
cubrir al proveedor que nadie ha escrito todavía.
"""

import socket

import httpx
import pytest

from ai.agents.base.structured import ClaudeLLMClient
from ai.llm import PROVIDERS, get_llm
from app.config.settings import settings
from tests import firewall

# ---------------------------------------------------------------------------
# Capa 3 — la costura histórica (tests de LLM0, intactos)
# ---------------------------------------------------------------------------


async def test_el_cliente_real_de_anthropic_esta_bloqueado_en_tests():
    with pytest.raises(AssertionError, match="REGLA DE PRESUPUESTO"):
        await ClaudeLLMClient().complete_json(system="s", user="u")


def test_el_cortafuegos_nombra_como_arreglarlo():
    """El mensaje debe decir qué hacer, no solo que algo falló."""
    from app.dependencies.claude import get_claude_client

    with pytest.raises(AssertionError) as exc:
        get_claude_client()
    mensaje = str(exc.value)
    assert "config['configurable']['llm']" in mensaje
    assert "tests/mocks.py" in mensaje


# ---------------------------------------------------------------------------
# Capa 1 — la fábrica
# ---------------------------------------------------------------------------


async def test_el_cliente_que_devuelve_la_fabrica_no_puede_llamar():
    llm = get_llm("ef", data_class="real")
    with pytest.raises(AssertionError, match="REGLA DE PRESUPUESTO"):
        await llm.complete_json(system="s", user="u")


def test_la_capa_de_la_fabrica_no_falsea_al_cliente():
    """Tapa la boca, no la identidad.

    Si el cortafuegos devolviera un doble, los tests que inspeccionan la fábrica
    estarían comprobando el doble y no el proveedor — y dejarían de detectar una
    resolución equivocada, que es justo lo que vigilan.
    """
    llm = get_llm("bd", data_class="sintetico")
    assert llm.provider == "anthropic"
    assert llm.model == settings.CLAUDE_MODEL
    assert llm.data_class == "sintetico"


# ---------------------------------------------------------------------------
# Capa 2 — los constructores de cada SDK
# ---------------------------------------------------------------------------


def test_construir_el_sdk_directamente_tambien_esta_bloqueado():
    """Quien se salte la fábrica con un import directo tampoco llega."""
    from langchain_anthropic import ChatAnthropic

    with pytest.raises(AssertionError, match="REGLA DE PRESUPUESTO"):
        ChatAnthropic(model="claude-sonnet-5")


def test_el_sdk_crudo_de_anthropic_tambien_esta_bloqueado():
    import anthropic

    with pytest.raises(AssertionError, match="REGLA DE PRESUPUESTO"):
        anthropic.Anthropic(api_key="x")
    with pytest.raises(AssertionError, match="REGLA DE PRESUPUESTO"):
        anthropic.AsyncAnthropic(api_key="x")


# ---------------------------------------------------------------------------
# Capa 4 — la red
# ---------------------------------------------------------------------------


def test_un_httpx_a_un_host_externo_falla_con_el_mensaje_de_la_regla():
    """El caso que ninguna capa anterior ve: una librería HTTP suelta.

    Se usa una IP y no un nombre a propósito: un test que vigila que no se sale
    a la red no puede depender de que la resolución de nombres funcione, o
    fallaría en un entorno sin DNS con un error que no tiene nada que ver.
    """
    with pytest.raises(AssertionError, match="REGLA DE PRESUPUESTO"):
        httpx.get("https://93.184.216.34/v1/messages", timeout=5)


def test_un_socket_a_un_host_externo_falla():
    with pytest.raises(AssertionError, match="REGLA DE PRESUPUESTO") as exc:
        with socket.socket() as s:
            s.connect(("93.184.216.34", 443))
    assert "93.184.216.34:443" in str(exc.value), "el mensaje debe nombrar el destino"


def test_connect_ex_no_es_una_puerta_trasera():
    """``connect_ex`` devuelve errno en vez de lanzar: dejarlo abierto abriría la capa."""
    with pytest.raises(AssertionError, match="REGLA DE PRESUPUESTO"):
        with socket.socket() as s:
            s.connect_ex(("93.184.216.34", 443))


@pytest.mark.parametrize(
    "address",
    [
        ("127.0.0.1", 5432),  # Postgres
        ("127.0.0.1", 6379),  # Redis
        ("localhost", 8000),  # un servidor de prueba
        ("::1", 8000),
        ("0.0.0.0", 8000),
        "/var/run/postgresql/.s.PGSQL.5432",  # socket unix
    ],
)
def test_los_destinos_locales_pasan_sin_friccion(address):
    """Criterio del bloque: la capa 4 no puede estorbar al entorno de desarrollo."""
    assert firewall.es_destino_local(address) is True


@pytest.mark.parametrize(
    "address",
    [
        ("api.anthropic.com", 443),
        ("generativelanguage.googleapis.com", 443),
        ("93.184.216.34", 443),
        ("8.8.8.8", 53),
    ],
)
def test_los_destinos_externos_no_pasan(address):
    assert firewall.es_destino_local(address) is False


def test_el_guard_de_red_no_toca_la_resolucion_de_nombres():
    """``getaddrinfo`` no pasa por ``socket.socket``: resolver sigue funcionando.

    Importa que sea así: si el guard rompiera la resolución, el fallo aparecería
    en sitios sin relación con la red del proveedor y habría que abrirle
    excepciones —que es como una protección se convierte en un colador.
    """
    assert socket.getaddrinfo("localhost", 80) != []


# ---------------------------------------------------------------------------
# El criterio central del bloque
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("proveedor", sorted(PROVIDERS))
def test_toda_capa_cubre_a_todo_proveedor_registrado(proveedor, monkeypatch):
    """Registrar un proveedor sin cortafuegos rompe la suite.

    Este es el criterio que justifica el bloque: no comprueba que Anthropic esté
    cubierto —eso ya lo hacían los tests de arriba— sino que **la cobertura es
    una función de ``PROVIDERS``**. Un proveedor nuevo entra por esta puerta o no
    entra.
    """
    cobertura = firewall.cobertura_de_capas(proveedor)
    assert cobertura["sdk"], (
        f"El proveedor '{proveedor}' no declara sus constructores de SDK en "
        "tests/firewall.py::SDK_CONSTRUCTORS (capa 2 del cortafuegos)."
    )

    monkeypatch.setattr(settings, "LLM_PROVIDER", proveedor)
    monkeypatch.setattr(settings, "LLM_ROLE_OVERRIDES", {})
    llm = get_llm("ef", data_class="sintetico")
    assert llm.provider == proveedor

    async def _llamar():
        await llm.complete_json(system="s", user="u")

    with pytest.raises(AssertionError, match="REGLA DE PRESUPUESTO"):
        __import__("asyncio").run(_llamar())


def test_un_proveedor_sin_constructores_declarados_se_detecta():
    """El candado anterior tiene que poder fallar; aquí se comprueba que falla."""
    assert firewall.cobertura_de_capas("proveedor-que-nadie-escribio") == {
        "fabrica": False,
        "sdk": False,
    }
