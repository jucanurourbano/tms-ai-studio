"""Capa 3, mitad de red: lo que sale del navegador (QC5).

QC4 dejó esto **modelado y no demostrado**: el doble de fixtures fingía el aborto
porque no había navegador que interceptar. Este fichero cierra el residual, y lo
cierra donde se puede cerrar sin navegador — la política es una función pura de
Python y el driver una cáscara que pregunta y obedece.

**Criterio 7 del bloque:** aquí no se arranca nada. Ni un navegador, ni un
servidor local, ni una petición. Lo que se ejerce es la decisión; que Playwright
la obedezca se comprueba con un doble que apunta lo que se le pidió y en qué
orden.
"""

import pytest

from ai.agents.qa.explore.network import (
    GUION_NEUTRALIZAR_SUBMIT,
    METODOS_DE_LECTURA,
    evaluar_peticion,
    motivo_de_aborto,
    preparar_contexto,
)
from ai.agents.qa.explore.target import assert_target_authorized
from tests.agents.qa.explore_helpers import HOST, URL_BASE, configurar


@pytest.fixture
def destino(monkeypatch):
    configurar(monkeypatch)
    return assert_target_authorized("tms-qa")


def _peticion(destino, metodo="GET", url=URL_BASE, navegacion=False):
    return evaluar_peticion(destino, metodo=metodo, url=url, es_navegacion=navegacion)


# --- la regla que convierte «solo lectura» en imposición ---------------------


@pytest.mark.parametrize("metodo", sorted(METODOS_DE_LECTURA))
def test_los_metodos_de_lectura_salen(destino, metodo):
    assert _peticion(destino, metodo=metodo).permitida


@pytest.mark.parametrize(
    "metodo", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"]
)
def test_todo_lo_que_no_es_lectura_se_aborta(destino, metodo):
    veredicto = _peticion(destino, metodo=metodo)
    assert not veredicto.permitida
    assert "SOLO LECTURA" in veredicto.motivo
    assert metodo in veredicto.motivo


def test_la_lista_es_blanca_y_no_negra(destino):
    """El verbo que nadie ha inventado todavía también se aborta. Una lista negra
    de métodos peligrosos sería una promesa que el siguiente incumple — la misma
    lección que A1 con los nombres de alias."""
    assert not _peticion(destino, metodo="MERGE").permitida
    assert not _peticion(destino, metodo="").permitida
    assert not _peticion(destino, metodo="get\nPOST").permitida


def test_el_metodo_no_distingue_mayusculas_pero_si_espacios(destino):
    assert _peticion(destino, metodo="get").permitida
    assert _peticion(destino, metodo=" Head ").permitida


def test_el_metodo_manda_aunque_el_destino_sea_el_propio_origen(destino):
    """Un ``fetch`` POST al mismo host es exactamente el caso peligroso: la capa 5
    lo autorizaría (es el origen explorado) y la capa 3 lo mata igual."""
    veredicto = _peticion(destino, metodo="POST", url=f"https://{HOST}/api/guias")
    assert not veredicto.permitida
    assert "SOLO LECTURA" in veredicto.motivo


# --- capa 5 desde dentro: la redirección llega como petición nueva ------------


def test_una_navegacion_fuera_de_la_jaula_se_aborta(destino):
    veredicto = _peticion(
        destino, url="https://portal.externo.pe/acceso", navegacion=True
    )
    assert not veredicto.permitida
    assert "allowlist" in veredicto.motivo


def test_un_subrecurso_a_otro_origen_SI_pasa_y_esto_es_deliberado(destino):
    """**Decisión declarada, no descuido.** Abortar el CSS o el JS que la
    aplicación carga de un CDN deja una página rota, y de una página rota se
    derivan casos que afirman comportamientos que el sistema no tiene: la
    observación falsa que este agente no puede producir. Se prefiere el riesgo
    menor —una petición de LECTURA a un tercero, que la aplicación hace igual
    cuando la abre una persona— al riesgo mayor."""
    assert _peticion(
        destino, url="https://cdn.externo.pe/app.js", navegacion=False
    ).permitida


def test_pero_ese_mismo_tercero_no_recibe_una_escritura(destino):
    """El límite de la decisión de arriba, para que no se lea como «los terceros
    pasan»: pasa la lectura, no el método."""
    assert not _peticion(
        destino, metodo="POST", url="https://cdn.externo.pe/beacon", navegacion=False
    ).permitida


@pytest.mark.parametrize("esquema", ["file:///etc/passwd", "data:text/html,x"])
def test_los_esquemas_rechazados_tampoco_navegan(destino, esquema):
    assert not _peticion(destino, url=esquema, navegacion=True).permitida


def test_el_motivo_de_aborto_se_puede_registrar(destino):
    """El driver tiene que poder DECIR por qué el navegador se negó: un fallo mudo
    se registraría como «algo pasó», y una cobertura así no la audita nadie."""
    assert (
        motivo_de_aborto(destino, metodo="GET", url=URL_BASE, es_navegacion=True)
        is None
    )
    motivo = motivo_de_aborto(destino, metodo="POST", url=URL_BASE, es_navegacion=False)
    assert motivo and "SOLO LECTURA" in motivo


def test_la_credencial_no_aparece_en_el_motivo(monkeypatch):
    """Capa 4: el motivo viaja a ``salidas_bloqueadas`` y de ahí al artefacto."""
    configurar(
        monkeypatch,
        destinos={
            "tms-qa": {
                "url": f"https://qa:s3cr3t0@{HOST}/",
                "readonly_verified": True,
            }
        },
    )
    objetivo = assert_target_authorized("tms-qa")
    motivo = motivo_de_aborto(
        objetivo,
        metodo="GET",
        url=f"https://qa:s3cr3t0@otro.externo.pe/x",
        es_navegacion=True,
    )
    assert motivo and "s3cr3t0" not in motivo


# --- la neutralización del submit, y su orden --------------------------------


def test_el_guion_neutraliza_las_tres_vias_de_envio():
    """Las tres hacen falta y ninguna cubre a las otras: el evento en captura no
    ve a ``form.submit()`` (que no lo dispara), y ``requestSubmit`` sí lo dispara
    pero además valida y enfoca."""
    assert "addEventListener('submit'" in GUION_NEUTRALIZAR_SUBMIT
    assert "true" in GUION_NEUTRALIZAR_SUBMIT  # fase de captura
    assert "stopImmediatePropagation" in GUION_NEUTRALIZAR_SUBMIT
    assert "proto.submit" in GUION_NEUTRALIZAR_SUBMIT
    assert "proto.requestSubmit" in GUION_NEUTRALIZAR_SUBMIT


def test_el_guion_no_toca_la_validacion_ni_el_resto_del_documento():
    """Lo que se anula es el ENVÍO. El mensaje de error que el navegador renderiza
    al validar es justo la evidencia que QA-D2 manda citar verbatim: un guion que
    apagara la validación convertiría al explorador en un mentiroso."""
    for prohibido in ("noValidate", "checkValidity", "reportValidity", "remove("):
        assert prohibido not in GUION_NEUTRALIZAR_SUBMIT


class _ContextoDoble:
    """Apunta lo que se le pide y en qué orden. No arranca nada."""

    def __init__(self):
        self.llamadas: list[str] = []
        self.guiones: list[str] = []
        self.rutas: list[str] = []

    async def add_init_script(self, guion):
        self.llamadas.append("add_init_script")
        self.guiones.append(guion)

    async def route(self, patron, manejador):
        self.llamadas.append("route")
        self.rutas.append(patron)
        self.manejador = manejador


async def test_el_submit_se_neutraliza_ANTES_de_instalar_la_red(destino):
    """**Criterio 3 del bloque, la mitad que es de orden.** Al revés el navegador
    formaría envíos que mueren abortados, y un envío que muere se observa como «no
    hubo validación» — la observación falsa que el agente no puede producir. Es la
    misma razón por la que teclear está fuera de v1."""
    contexto = _ContextoDoble()
    await preparar_contexto(contexto, destino)
    assert contexto.llamadas == ["add_init_script", "route"]
    assert contexto.guiones == [GUION_NEUTRALIZAR_SUBMIT]
    assert contexto.rutas == ["**/*"]


class _PeticionDoble:
    def __init__(self, metodo, url, navegacion):
        self.method = metodo
        self.url = url
        self._navegacion = navegacion

    def is_navigation_request(self):
        return self._navegacion


class _RutaDoble:
    def __init__(self):
        self.acciones: list[str] = []

    async def continue_(self):
        self.acciones.append("continue")

    async def abort(self):
        self.acciones.append("abort")


@pytest.mark.parametrize(
    "metodo, url, navegacion, esperado",
    [
        ("GET", URL_BASE, True, "continue"),
        ("HEAD", URL_BASE, False, "continue"),
        ("POST", URL_BASE, False, "abort"),
        ("POST", f"https://{HOST}/api/guias", True, "abort"),
        ("GET", "https://portal.externo.pe/", True, "abort"),
        ("GET", "https://cdn.externo.pe/app.js", False, "continue"),
    ],
)
async def test_el_manejador_obedece_al_veredicto(
    destino, metodo, url, navegacion, esperado
):
    """El manejador no decide: pregunta. Si tuviera criterio propio serían dos
    reglas que divergen, y la divergencia se descubre siempre por el lado malo."""
    contexto = _ContextoDoble()
    await preparar_contexto(contexto, destino)
    ruta = _RutaDoble()
    await contexto.manejador(ruta, _PeticionDoble(metodo, url, navegacion))
    assert ruta.acciones == [esperado]
