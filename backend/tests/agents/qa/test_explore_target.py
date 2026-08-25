"""El guard del Modo C: capas 1, 2 y 4, más las dos decisiones nuevas (A1, A2).

Los tests que importan aquí no son los del camino feliz sino los del guard: esto
conduce un navegador **autenticado** contra una aplicación desplegada, y el destino
nunca lo elige quien llama a la API.
"""

import pytest

from ai.agents.qa.explore.target import (
    HOSTS_LOCALES,
    ExploreTarget,
    alcance_para_prompt,
    assert_target_authorized,
    available_targets,
    data_class_de_exploracion,
    origin_ref_for,
    redact_url,
)
from ai.errors import GateError
from app.config.settings import settings
from app.errors import ForbiddenError, NotFoundError
from tests.agents.qa.explore_helpers import HOST, URL_BASE, configurar

# --- capa 1: el cliente NUNCA envía una URL ----------------------------------


def test_desactivado_por_defecto_no_explora_nada(monkeypatch):
    """Nace apagado, igual que la introspección de BD: activarlo es una decisión."""
    configurar(monkeypatch, habilitado=False)
    with pytest.raises(ForbiddenError, match="desactivada"):
        assert_target_authorized("tms-qa")
    assert available_targets() == []


def test_un_alias_inexistente_no_se_puede_inventar(monkeypatch):
    configurar(monkeypatch)
    with pytest.raises(NotFoundError, match="no acepta URLs"):
        assert_target_authorized("el-que-no-existe")


def test_una_url_en_el_lugar_del_alias_se_rechaza(monkeypatch):
    """La afordancia del SSRF no existe: una URL no es un alias, es un 404.

    Aunque un endpoint futuro pasara una cadena del cliente sin filtrar, aquí
    muere: el alias tiene forma cerrada y una URL no la cumple.
    """
    configurar(monkeypatch)
    for intento in (
        "https://evil.com/",
        "http://tms.interno/",
        "//evil.com",
        "tms.interno",
    ):
        with pytest.raises(NotFoundError):
            assert_target_authorized(intento)


# --- capa 2: allowlist de hosts ----------------------------------------------


def test_sin_allowlist_no_hay_nada_autorizado(monkeypatch):
    """Lista vacía significa "nada", NUNCA "todo"."""
    configurar(monkeypatch, hosts=[])
    with pytest.raises(ForbiddenError, match="allowlist"):
        assert_target_authorized("tms-qa")
    assert available_targets() == []


def test_un_host_fuera_de_la_allowlist_se_rechaza(monkeypatch):
    configurar(monkeypatch, hosts=["otra.cosa"])
    with pytest.raises(ForbiddenError, match="allowlist"):
        assert_target_authorized("tms-qa")


# --- QA-D21 §4.2: precondición de solo lectura -------------------------------


def test_sin_readonly_verified_no_se_explora(monkeypatch):
    """409: sin cuenta de solo lectura, nuestras capas serían el único control."""
    configurar(
        monkeypatch, destinos={"tms-qa": {"url": URL_BASE, "readonly_verified": False}}
    )
    with pytest.raises(GateError, match="SOLO LECTURA"):
        assert_target_authorized("tms-qa")


def test_el_default_de_readonly_verified_es_no(monkeypatch):
    """Omitirlo no es afirmarlo: ausencia significa no autorizado."""
    configurar(monkeypatch, destinos={"tms-qa": {"url": URL_BASE}})
    with pytest.raises(GateError):
        assert_target_authorized("tms-qa")


def test_una_clave_mal_escrita_no_pasa_por_default(monkeypatch):
    """``readonly_verifed`` (sin la i) fallaría luego con un mensaje que no explica
    nada. ``extra="forbid"`` lo convierte en un error de declaración."""
    configurar(
        monkeypatch,
        destinos={"tms-qa": {"url": URL_BASE, "readonly_verifed": True}},
    )
    with pytest.raises(ForbiddenError, match="mal declarado"):
        assert_target_authorized("tms-qa")


# --- A1: el alias no puede ser una coordenada --------------------------------


@pytest.mark.parametrize(
    "alias",
    [
        "tms.interno",
        "https://tms.interno",
        "10.0.0.5",
        "tms_qa",
        "TMS-QA",
        "q",
        "",
    ],
)
def test_un_alias_con_forma_de_coordenada_no_es_explorable(monkeypatch, alias):
    """El alias se lee en el plan y en el PDF: el host no debe viajar ahí."""
    configurar(
        monkeypatch, destinos={alias: {"url": URL_BASE, "readonly_verified": True}}
    )
    with pytest.raises(ForbiddenError, match="mal declarado"):
        assert_target_authorized(alias)
    assert available_targets() == []


def test_un_alias_bien_formado_si_pasa(monkeypatch):
    configurar(monkeypatch)
    destino = assert_target_authorized("tms-qa")
    assert destino.alias == "tms-qa"
    assert destino.host == HOST


# --- A2: el alias sintético, y su candado de host local ----------------------


def test_un_host_no_local_no_puede_declararse_sintetico(monkeypatch):
    """La dirección segura del error: una app desplegada muestra datos reales."""
    configurar(
        monkeypatch,
        destinos={
            "tms-qa": {
                "url": URL_BASE,
                "readonly_verified": True,
                "data_class": "sintetico",
            }
        },
    )
    with pytest.raises(ForbiddenError, match="no es local"):
        assert_target_authorized("tms-qa")


@pytest.mark.parametrize("host", sorted(HOSTS_LOCALES - {"::1"}))
def test_un_host_local_si_puede_declararse_sintetico(monkeypatch, host):
    """Sin esto el Modo C sería imposible de probar de punta a punta sin saldo."""
    configurar(
        monkeypatch,
        destinos={
            "dev-local": {
                "url": f"http://{host}:3000/",
                "readonly_verified": True,
                "data_class": "sintetico",
            }
        },
        hosts=[host],
    )
    destino = assert_target_authorized("dev-local")
    assert data_class_de_exploracion(destino) == "sintetico"


def test_un_destino_sin_declarar_data_class_es_real(monkeypatch):
    """``real`` es el default irrenunciable: el silencio no abarata nada."""
    configurar(monkeypatch)
    assert data_class_de_exploracion(assert_target_authorized("tms-qa")) == "real"


def test_un_host_local_sin_declarar_nada_sigue_siendo_real(monkeypatch):
    """Ser local **habilita** declararlo sintético; no lo declara por ti."""
    configurar(
        monkeypatch,
        destinos={
            "dev-local": {"url": "http://localhost:3000/", "readonly_verified": True}
        },
        hosts=["localhost"],
    )
    assert data_class_de_exploracion(assert_target_authorized("dev-local")) == "real"


def test_un_data_class_inventado_no_pasa(monkeypatch):
    configurar(
        monkeypatch,
        destinos={
            "tms-qa": {
                "url": URL_BASE,
                "readonly_verified": True,
                "data_class": "anonimizado",
            }
        },
    )
    with pytest.raises(ForbiddenError, match="mal declarado"):
        assert_target_authorized("tms-qa")


# --- capa 4: la credencial nunca sale ----------------------------------------

URL_CON_CREDENCIAL = "https://qa-explorer:s3cr3t0@tms.interno/inicio"


def test_la_credencial_no_aparece_en_ninguna_superficie_publica(monkeypatch):
    configurar(
        monkeypatch,
        destinos={"tms-qa": {"url": URL_CON_CREDENCIAL, "readonly_verified": True}},
    )
    destino = assert_target_authorized("tms-qa")
    superficies = [
        destino.url_publica,
        origin_ref_for(destino),
        redact_url(destino.url),
        str(available_targets()),
        str(alcance_para_prompt(destino, ["/inicio"])),
    ]
    for texto in superficies:
        assert "s3cr3t0" not in texto
        assert "qa-explorer" not in texto


def test_un_mensaje_de_error_no_filtra_la_credencial(monkeypatch):
    """El sitio más fácil de olvidar: el mensaje que se registra en el log."""
    configurar(
        monkeypatch,
        destinos={"tms-qa": {"url": URL_CON_CREDENCIAL}},
        hosts=["otra.cosa"],
    )
    with pytest.raises(ForbiddenError) as error:
        assert_target_authorized("tms-qa")
    assert "s3cr3t0" not in str(error.value)


def test_el_storage_state_no_se_lista(monkeypatch):
    """La ruta del estado de sesión vive en el servidor y no se publica."""
    configurar(
        monkeypatch,
        destinos={
            "tms-qa": {
                "url": URL_BASE,
                "readonly_verified": True,
                "storage_state": "/var/lib/tms/qa-explorer.json",
            }
        },
    )
    assert "qa-explorer.json" not in str(available_targets())


# --- el listado: lo que la pantalla puede ofrecer ----------------------------


def test_solo_se_listan_los_destinos_que_superan_todo_el_guard(monkeypatch):
    """Un botón que siempre va a fallar no se ofrece (precedente de INV2)."""
    configurar(
        monkeypatch,
        destinos={
            "tms-qa": {"url": URL_BASE, "readonly_verified": True},
            "sin-lectura": {"url": URL_BASE, "readonly_verified": False},
            "fuera": {"url": "https://otro.host/", "readonly_verified": True},
            "mal.declarado": {"url": URL_BASE, "readonly_verified": True},
        },
    )
    listados = available_targets()
    assert [d["alias"] for d in listados] == ["tms-qa"]
    assert listados[0] == {"alias": "tms-qa", "host": HOST, "data_class": "real"}


def test_la_url_base_debe_ser_http(monkeypatch):
    configurar(
        monkeypatch,
        destinos={"tms-qa": {"url": "file:///etc/passwd", "readonly_verified": True}},
    )
    with pytest.raises(ForbiddenError, match="mal declarado"):
        assert_target_authorized("tms-qa")


def test_el_origen_incluye_el_puerto(monkeypatch):
    """El mismo-origen de la capa 5 compara esquema, host **y** puerto."""
    destino = ExploreTarget(
        alias="tms-qa", url="https://tms.interno:8443/app", readonly_verified=True
    )
    assert destino.origin == "https://tms.interno:8443"
    assert (
        ExploreTarget(alias="tms-qa", url=URL_BASE, readonly_verified=True).origin
        == "https://tms.interno:443"
    )


def test_un_destino_no_es_mutable():
    """El destino resuelto no se retoca a mitad de una exploración."""
    destino = ExploreTarget(alias="tms-qa", url=URL_BASE, readonly_verified=True)
    with pytest.raises(Exception):
        destino.url = "https://evil.com/"


def test_los_destinos_no_se_guardan_en_la_base_de_datos():
    """Viven en el entorno del despliegue. Aquí solo se fija de dónde se leen."""
    assert isinstance(settings.QA_EXPLORE_TARGETS, dict)
