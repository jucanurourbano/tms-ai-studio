"""Cortafuegos de la suite: cuatro capas contra una llamada real (LLM1).

REGLA DE PRESUPUESTO (``CLAUDE.md`` §9): nunca se llama a una API real desde los
tests. Hasta LLM0 esa regla la sostenía **un** ``monkeypatch`` sobre **un**
símbolo de Anthropic. Con más de un proveedor eso deja de escalar: añadir un
``_boom`` por proveedor es volver a resolver el mismo problema cada vez, y el
fallo llega el día en que alguien registra el tercero sin leer el ``conftest``.

Las capas, de la más específica a la que de verdad generaliza (LLM-D12):

1. **La fábrica** — ``ai.llm.get_llm`` sigue devolviendo el cliente REAL del
   proveedor (mismo ``provider``, mismo ``model``, misma ``data_class``: los
   tests que inspeccionan la fábrica siguen viendo la verdad) pero con su
   ``complete_json`` desactivado. Cubre por construcción a **todo** proveedor
   registrado, incluido el que nadie ha escrito todavía.
2. **Los constructores de cada SDK** — cubre a quien se salte la fábrica con un
   import directo. Es la única capa que hay que mantener a mano, y por eso
   ``PROVIDERS`` y ``SDK_CONSTRUCTORS`` se comparan en un test: registrar un
   proveedor sin declarar sus constructores rompe la suite.
3. **``get_claude_client``** — se conserva **tal cual**: es la costura histórica
   y la que parchean los tests que ya existen.
4. **La red** — un guard sobre ``socket.socket.connect``/``connect_ex`` que
   rechaza cualquier destino que no sea local. No hay que actualizarlo nunca:
   cubre a un proveedor futuro, a un ``httpx`` suelto en un test nuevo, a un
   webhook. Es la única capa cuyo alcance no depende de que alguien la recuerde.

Las capas 1–3 dan el mensaje ÚTIL (dicen cómo arreglarlo); la 4 da la garantía.
"""

import importlib
import ipaddress
import socket
from dataclasses import replace
from typing import Any, Optional

import pytest

from ai.llm.registry import PROVIDERS

# Mensaje único de las capas que saben qué se intentaba hacer. Se mantiene
# literal el texto que ya buscaban los tests de LLM0.
MENSAJE_LLM = (
    "Un test intentó usar el cliente REAL de Anthropic. Inyecta un mock "
    "en config['configurable']['llm'] (ver tests/mocks.py). "
    "REGLA DE PRESUPUESTO: nunca se llama a la API real en tests."
)


def _mensaje_proveedor(proveedor: str) -> str:
    """Mismo mensaje, nombrando al proveedor cuando no es Anthropic."""
    if proveedor == "anthropic":
        return MENSAJE_LLM
    return (
        f"Un test intentó usar el cliente REAL del proveedor '{proveedor}'. "
        "Inyecta un mock en config['configurable']['llm'] (ver tests/mocks.py). "
        "REGLA DE PRESUPUESTO: nunca se llama a la API real en tests."
    )


# --------------------------------------------------------------------------
# Capa 1 — la fábrica
# --------------------------------------------------------------------------


def blindar_fabrica(monkeypatch: pytest.MonkeyPatch) -> None:
    """Desactiva ``complete_json`` en el cliente que devuelve la fábrica.

    Se envuelve ``build_client`` de cada ``ProviderSpec`` en vez de sustituir
    ``get_llm``: los consumidores hacen ``from ai.llm import get_llm`` (seis de
    ellos a nivel de módulo), así que parchear el nombre en ``ai.llm.factory`` no
    alcanzaría a sus enlaces ya resueltos — habría que perseguir uno por uno los
    quince sitios, que es exactamente el trabajo manual que esta capa evita.
    ``get_spec`` lee ``PROVIDERS`` en cada llamada, de modo que tocar el registro
    llega a todos los enlaces sin excepción.

    El cliente devuelto es el REAL, solo con la boca tapada: quien pregunte por
    ``provider``, ``model`` o ``data_class`` recibe el valor de verdad.
    """
    for nombre, spec in list(PROVIDERS.items()):
        monkeypatch.setitem(
            PROVIDERS, nombre, replace(spec, build_client=_amordazar(spec))
        )


def _amordazar(spec):
    """Devuelve un ``build_client`` que construye igual y no puede llamar."""
    constructor = spec.build_client
    mensaje = _mensaje_proveedor(spec.name)

    def _build(**kwargs):
        cliente = constructor(**kwargs)

        async def _boom(*_args, **_kwargs):
            raise AssertionError(mensaje)

        # Atributo de instancia: sombrea el método sin tocar la clase, así que
        # el cliente conserva todo lo demás intacto y no hay estado global que
        # restaurar más allá del propio registro.
        cliente.complete_json = _boom
        return cliente

    return _build


# --------------------------------------------------------------------------
# Capa 2 — los constructores de cada SDK
# --------------------------------------------------------------------------

# Constructores que crean un cliente HTTP hacia el proveedor, por proveedor
# registrado. Es la ÚNICA tabla de este módulo que hay que mantener a mano; el
# test parametrizado de ``test_budget_guard.py`` exige una entrada por cada
# nombre de ``PROVIDERS``, así que olvidarla rompe la suite en vez de abrir un
# camino a la red que nadie mira.
SDK_CONSTRUCTORS: dict[str, tuple[str, ...]] = {
    "anthropic": (
        "langchain_anthropic.ChatAnthropic",
        "anthropic.Anthropic",
        "anthropic.AsyncAnthropic",
    ),
}


def _capturar_originales() -> dict[str, Any]:
    """Guarda los constructores REALES al importar, antes de que nadie parchee."""
    originales: dict[str, Any] = {}
    for rutas in SDK_CONSTRUCTORS.values():
        for ruta in rutas:
            modulo, _, atributo = ruta.rpartition(".")
            try:
                mod = importlib.import_module(modulo)
            except ImportError:  # pragma: no cover - depende del entorno
                continue
            if hasattr(mod, atributo):
                originales[ruta] = getattr(mod, atributo)
    return originales


_SDK_ORIGINALES: dict[str, Any] = _capturar_originales()


def blindar_sdks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hace explotar la construcción directa del cliente de cualquier SDK.

    Un SDK **no instalado** no se parchea y no se reporta como hueco: si no se
    puede importar, tampoco se puede construir, y la capa 4 seguiría cubriendo
    el caso aunque se instalara a mitad de una corrida.
    """
    for proveedor, rutas in SDK_CONSTRUCTORS.items():
        mensaje = _mensaje_proveedor(proveedor)
        for ruta in rutas:
            _parchear_si_existe(monkeypatch, ruta, mensaje)


def _parchear_si_existe(
    monkeypatch: pytest.MonkeyPatch, ruta: str, mensaje: str
) -> bool:
    modulo, _, atributo = ruta.rpartition(".")
    try:
        __import__(modulo)
    except ImportError:  # pragma: no cover - depende del entorno
        return False

    def _boom(*_args, **_kwargs):
        raise AssertionError(mensaje)

    monkeypatch.setattr(ruta, _boom, raising=False)
    return True


def liberar_sdks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Levanta **solo** la capa 2, para los tests que prueban el constructor.

    Construir el cliente no es llamar a la API: no abre conexión, no consume
    tokens y no cuesta nada. Hay dos tests cuyo objeto ES el constructor
    (``tests/orchestrator/test_claude.py``: que el modelo salga de ``settings`` y
    que ``max_tokens`` sea explícito, que documenta un truncamiento real de
    EXTRACT), y comprobar eso exige construir de verdad.

    La excepción es **estrecha y explícita**: se pide por nombre, deja las capas
    1, 3 y 4 en pie, y por tanto la garantía de que no sale un solo paquete a la
    red sigue siendo la misma. Un ``ainvoke`` sobre el cliente así construido
    choca con la capa 4.
    """
    for ruta, original in _SDK_ORIGINALES.items():
        monkeypatch.setattr(ruta, original)


# --------------------------------------------------------------------------
# Capa 4 — la red
# --------------------------------------------------------------------------

MENSAJE_RED = (
    "Un test intentó abrir una conexión de red a {destino}. "
    "Usa un doble (httpx.MockTransport, un mock del cliente) en vez de salir "
    "a la red. REGLA DE PRESUPUESTO: nunca se llama a una API real en tests."
)

_HOSTS_LOCALES = {"localhost", "localhost.localdomain", ""}


def es_destino_local(address: Any) -> bool:
    """¿El destino de un ``connect`` es local?

    Local = socket unix (la dirección es una ruta, no una tupla) o una IP de
    loopback/no especificada. Postgres, Redis y cualquier servidor de prueba en
    ``127.0.0.1``/``::1`` pasan sin fricción; un host externo, no.

    Un **nombre** que no sea ``localhost`` se considera externo aunque resolviera
    a loopback: el guard falla cerrado, que es la dirección correcta del error.
    """
    if not isinstance(address, (tuple, list)):
        return True  # AF_UNIX: la dirección es una ruta del sistema de ficheros
    if not address:
        return True
    host = address[0]
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    if not isinstance(host, str):
        return False
    if host.lower() in _HOSTS_LOCALES:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


def _destino(address: Any) -> str:
    if isinstance(address, (tuple, list)) and address:
        puerto = address[1] if len(address) > 1 else "?"
        return f"{address[0]}:{puerto}"
    return str(address)


def blindar_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rechaza todo ``connect`` hacia un host que no sea local.

    Se parchean ``connect`` **y** ``connect_ex``: ``asyncio`` usa el primero y
    algunos clientes el segundo, y dejar uno abierto sería dejar la capa abierta.

    No toca la resolución de nombres: ``getaddrinfo`` no pasa por
    ``socket.socket``, así que un test que resuelva un nombre sigue resolviendo
    —y falla después, al conectar, que es donde el mensaje es útil.
    """
    connect_real = socket.socket.connect
    connect_ex_real = socket.socket.connect_ex

    def connect(self, address, *args, **kwargs):
        _verificar(address)
        return connect_real(self, address, *args, **kwargs)

    def connect_ex(self, address, *args, **kwargs):
        _verificar(address)
        return connect_ex_real(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)


def _verificar(address: Any) -> None:
    if not es_destino_local(address):
        raise AssertionError(MENSAJE_RED.format(destino=_destino(address)))


def cobertura_de_capas(proveedor: str) -> dict[str, Optional[bool]]:
    """Qué capas declaran cubrir a ``proveedor`` (para el test parametrizado)."""
    return {
        "fabrica": proveedor in PROVIDERS,
        "sdk": bool(SDK_CONSTRUCTORS.get(proveedor)),
    }
