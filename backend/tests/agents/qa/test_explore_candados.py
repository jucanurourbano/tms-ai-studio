"""Candados del Modo C: lo que no se puede escribir, no lo que acordamos no hacer.

Estos tests son de **código fuente** a propósito, siguiendo el precedente de
``tests/llm/test_construcciones.py``: *"un test de comportamiento no ve al que
mañana escriba otra construcción directa; un grep sí, y falla en el momento en que
se escribe"*. Aquí lo que se vigila es más caro que una llamada facturada: escribir
en una aplicación de producción, sacar una captura de pantalla con datos reales o
mandarle al proveedor del modelo el mapa de la infraestructura.
"""

import ast
from pathlib import Path

import pytest

# El binding se resuelve al IMPORTAR este módulo, que es antes de que las fixtures
# autouse parcheen el atributo del módulo ``driver``. Así queda una referencia a la
# función REAL con la que comprobar su comportamiento sin cortafuegos — y de paso
# se demuestra por qué ``session.py`` tiene que llamarla por el módulo.
from ai.agents.qa.explore.driver import DriverNoDisponibleError
from ai.agents.qa.explore.driver import build_driver as build_driver_real
from ai.agents.qa.explore.session import ExploreSession
from ai.agents.qa.explore.target import (
    alcance_para_prompt,
    assert_target_authorized,
)
from tests import firewall
from tests.agents.qa.explore_helpers import HOST, URL_BASE, configurar

BACKEND = Path(__file__).resolve().parents[3]

# --- candado 1: nada que escriba en el navegador -----------------------------

#: Métodos del navegador que **escriben** o **capturan**. Ninguno puede aparecer
#: en el código, ni siquiera cuando exista Playwright (QC5): el nivel 2 (teclear)
#: está fuera de v1 porque un ``keyup`` cuya petición muere abortada hace que el
#: explorador **observe que no hubo validación** —una observación falsa, que es lo
#: único que este agente no puede producir—; y una captura de una app autenticada
#: es un volcado de datos reales de producción en un artefacto que se exporta.
METODOS_PROHIBIDOS = frozenset(
    {
        "fill",
        "type",
        "press",
        "press_sequentially",
        "set_input_files",
        "select_option",
        "check",
        "uncheck",
        "set_checked",
        "evaluate",
        "evaluate_handle",
        "dispatch_event",
        "screenshot",
        "tap",
        "drag_and_drop",
    }
)

#: El único sitio que podrá teclear es el CLI de login (QC6), y por eso vive
#: FUERA de la ruta de exploración: resolverlo con una excepción dentro de
#: ``ExploreSession`` destruiría este candado.
PERMITIDOS_ESCRITURA = {"ai/agents/qa/explore/login.py"}

#: ``click`` sí existe, y **solo** dentro de este método.
DUENO_DEL_CLIC = ("ai/agents/qa/explore/session.py", "pulsar_si_procede")


def _fuentes():
    for paquete in ("app", "ai"):
        for ruta in sorted((BACKEND / paquete).rglob("*.py")):
            relativa = ruta.relative_to(BACKEND).as_posix()
            yield relativa, ast.parse(ruta.read_text(encoding="utf-8"))


def _llamadas_a_metodo(arbol) -> list[tuple[str, int]]:
    return [
        (nodo.func.attr, nodo.lineno)
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
    ]


def test_ninguna_escritura_ni_captura_en_el_navegador():
    infractores = [
        f"{relativa}:{linea} ({nombre})"
        for relativa, arbol in _fuentes()
        if relativa not in PERMITIDOS_ESCRITURA
        for nombre, linea in _llamadas_a_metodo(arbol)
        if nombre in METODOS_PROHIBIDOS
    ]
    assert (
        infractores == []
    ), "Métodos que escriben en el navegador o capturan pantalla: " + ", ".join(
        infractores
    )


def test_el_clic_solo_vive_en_pulsar_si_procede():
    """Los nodos no reciben el driver: reciben la sesión. Y la sesión solo pulsa
    en el método que aplica la lista blanca."""
    fichero, metodo = DUENO_DEL_CLIC
    fuera: list[str] = []
    for relativa, arbol in _fuentes():
        clics = [
            linea for nombre, linea in _llamadas_a_metodo(arbol) if nombre == "click"
        ]
        if not clics:
            continue
        if relativa != fichero:
            fuera += [f"{relativa}:{linea}" for linea in clics]
            continue
        permitidas = {
            nodo.lineno
            for definicion in ast.walk(arbol)
            if isinstance(definicion, (ast.FunctionDef, ast.AsyncFunctionDef))
            and definicion.name == metodo
            for nodo in ast.walk(definicion)
            if isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr == "click"
        }
        fuera += [f"{relativa}:{linea}" for linea in clics if linea not in permitidas]
    assert fuera == [], f"Clics fuera de {fichero}::{metodo}: " + ", ".join(fuera)


def test_qc3_no_introduce_playwright():
    """Criterio del bloque: cero líneas de Playwright. **QC5 borra este test.**

    Y borrarlo es un acto visible en la revisión, que es exactamente el punto: la
    valla (``sin_navegador_real``) tiene que estar puesta antes de que llegue el
    animal.
    """
    requisitos = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    assert "playwright" not in requisitos.lower()
    importadores = [
        relativa
        for relativa, arbol in _fuentes()
        for nodo in ast.walk(arbol)
        if (
            isinstance(nodo, ast.Import)
            and any("playwright" in alias.name for alias in nodo.names)
        )
        or (isinstance(nodo, ast.ImportFrom) and "playwright" in (nodo.module or ""))
    ]
    assert importadores == []


# --- candado 2: la costura del navegador no se puede esquivar ----------------


def test_el_cortafuegos_del_navegador_da_un_mensaje_util():
    """Criterio 4: un test que intente arrancar navegador falla explicando cómo
    arreglarlo, en vez de salir a la red."""
    from ai.agents.qa.explore import driver as modulo

    with pytest.raises(AssertionError) as error:
        modulo.build_driver(timeout_ms=1000)
    assert "Inyecta un doble" in str(error.value)
    assert firewall.MENSAJE_NAVEGADOR == str(error.value)


async def test_una_sesion_sin_driver_inyectado_choca_con_el_cortafuegos(monkeypatch):
    """La costura es real: no hace falta que el test se acuerde de pedir nada."""
    configurar(monkeypatch)
    destino = assert_target_authorized("tms-qa")
    with pytest.raises(AssertionError, match="navegador REAL"):
        await ExploreSession(destino).visitar(URL_BASE)


def test_nuestra_fabrica_esta_en_la_lista_de_blindadas():
    assert "ai.agents.qa.explore.driver.build_driver" in firewall.FABRICAS_DE_NAVEGADOR


def test_sin_cortafuegos_la_fabrica_falla_explicando_que_no_hay_driver():
    """En producción no devuelve un doble silencioso: un driver de mentira
    exploraría cero páginas y el artefacto diría "no se observó nada", que es
    indistinguible de una aplicación vacía."""
    with pytest.raises(DriverNoDisponibleError, match="QC5"):
        build_driver_real(timeout_ms=1000)


def test_build_driver_no_se_importa_por_nombre_en_ninguna_parte():
    """Un ``from … import build_driver`` resuelve el enlace al importar y el
    parche del cortafuegos —que sustituye el atributo del módulo— no lo
    alcanzaría. Es la misma lección que la capa 1 del cortafuegos del LLM."""
    infractores = [
        f"{relativa}:{nodo.lineno}"
        for relativa, arbol in _fuentes()
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom)
        and any(alias.name == "build_driver" for alias in nodo.names)
        and relativa != "ai/agents/qa/explore/__init__.py"
    ]
    assert infractores == [], "Importan build_driver por nombre: " + ", ".join(
        infractores
    )


# --- candado 3: el destino tiene un único lector -----------------------------

LECTORES_AUTORIZADOS = {
    "QA_EXPLORE_TARGETS": {"ai/agents/qa/explore/target.py"},
    "QA_EXPLORE_ALLOWED_HOSTS": {
        "ai/agents/qa/explore/target.py",
        "ai/agents/qa/explore/navigation.py",
    },
}


@pytest.mark.parametrize("ajuste", sorted(LECTORES_AUTORIZADOS))
def test_los_destinos_tienen_un_unico_lector(ajuste):
    """Un segundo lector es un segundo sitio donde una capa puede no aplicarse:
    exactamente el problema que la fábrica de LLM vino a resolver."""
    autorizados = LECTORES_AUTORIZADOS[ajuste] | {"app/config/settings.py"}
    lectores = [
        relativa
        for relativa, _ in _fuentes()
        if ajuste in (BACKEND / relativa).read_text(encoding="utf-8")
        and relativa not in autorizados
    ]
    assert lectores == [], f"Leen {ajuste} sin pasar por el guard: " + ", ".join(
        lectores
    )


# --- candado 4: ninguna afordancia de URL libre en la API --------------------


def test_ningun_esquema_de_la_api_acepta_una_url_de_exploracion():
    """La pantalla no debe ofrecer lo que el backend rechaza, y el backend no
    tiene dónde recibirlo: los campos no existen (capa 1)."""
    sospechosos = ("url", "host", "endpoint", "dsn", "base_url")
    hallados: list[str] = []
    for ruta in sorted((BACKEND / "app" / "schemas").glob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
                nombre = nodo.target.id.lower()
                if any(s in nombre for s in sospechosos):
                    hallados.append(f"{ruta.name}:{nodo.lineno} ({nodo.target.id})")
    assert (
        hallados == []
    ), "Campos de request con forma de URL/host (afordancia de SSRF): " + ", ".join(
        hallados
    )


# --- candado 5: A1, el alias no viaja al prompt ------------------------------


def test_ni_el_alias_ni_el_host_llegan_al_modelo(monkeypatch):
    """A1. El modelo no necesita saber contra qué aplicación se exploró para
    redactar un caso sobre un campo ``ruc`` con ``maxlength=11``, y lo que no
    necesita saber no se le manda.

    QC5 amplía ``alcance_para_prompt`` con las anclas observadas: ampliarlo AHÍ
    —y no en el prompt— es lo que mantiene este candado vivo, porque cubre por
    construcción todo lo que se añada después.
    """
    configurar(
        monkeypatch,
        destinos={
            "tms-prod-urbano-aws": {
                "url": f"https://qa:s3cr3t0@{HOST}/",
                "readonly_verified": True,
            }
        },
    )
    destino = assert_target_authorized("tms-prod-urbano-aws")
    proyeccion = str(alcance_para_prompt(destino, ["/guias/nueva", "/guias/lista"]))
    assert "tms-prod-urbano-aws" not in proyeccion
    assert HOST not in proyeccion
    assert "s3cr3t0" not in proyeccion
    assert "/guias/nueva" in proyeccion


def test_la_proyeccion_al_prompt_solo_tiene_paths_y_clase_de_datos():
    """Si mañana aparece una clave nueva, este test obliga a justificarla."""
    from ai.agents.qa.explore.target import ExploreTarget

    destino = ExploreTarget(alias="tms-qa", url=URL_BASE, readonly_verified=True)
    assert set(alcance_para_prompt(destino, ["/"])) == {
        "origen",
        "data_class",
        "paths",
    }
