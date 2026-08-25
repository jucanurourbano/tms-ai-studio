"""Los topes: enteros positivos validados. Un ``0`` es inválido, no infinito.

No es pedantería de validación: es uno de los cuatro impedimentos **en código**
para que el Modo C no se deslice hacia ser un ejecutor de pruebas (QA-D25.4). Un
ejecutor necesita corridas repetidas y sin techo; este agente no las puede pedir.
"""

import pytest

from ai.agents.qa.explore.limits import LimitesExploracion, limites_efectivos
from ai.errors import PipelineError
from app.config.settings import settings

CAMPOS = (
    "max_pages",
    "max_depth",
    "timeout_ms",
    "total_budget_s",
    "max_clicks_per_page",
)


def test_los_defaults_salen_de_settings():
    limites = limites_efectivos()
    assert limites.max_pages == settings.QA_EXPLORE_MAX_PAGES
    assert limites.max_depth == settings.QA_EXPLORE_MAX_DEPTH
    assert limites.timeout_ms == settings.QA_EXPLORE_TIMEOUT_MS
    assert limites.total_budget_s == settings.QA_EXPLORE_TOTAL_BUDGET_S
    assert limites.max_clicks_per_page == settings.QA_EXPLORE_MAX_CLICKS_PER_PAGE


def test_el_despliegue_nace_con_un_radio_de_accion_acotado():
    """Los valores por defecto no son "sin límite" ni un número enorme."""
    limites = limites_efectivos()
    assert 0 < limites.max_pages <= 200
    assert 0 < limites.max_depth <= 5
    assert 0 < limites.total_budget_s <= 900


@pytest.mark.parametrize("campo", CAMPOS)
def test_un_cero_es_invalido_y_no_significa_sin_limite(campo):
    with pytest.raises(PipelineError, match="mayor que 0"):
        limites_efectivos(**{campo: 0})


@pytest.mark.parametrize("campo", CAMPOS)
def test_un_negativo_es_invalido(campo):
    with pytest.raises(PipelineError, match="mayor que 0"):
        limites_efectivos(**{campo: -1})


@pytest.mark.parametrize("campo", CAMPOS)
def test_un_cero_en_el_env_rompe_el_arranque_del_job(campo, monkeypatch):
    """Y no abre una exploración infinita, que es el fallo que importa."""
    monkeypatch.setattr(settings, f"QA_EXPLORE_{campo.upper()}", 0)
    with pytest.raises(PipelineError):
        limites_efectivos()


@pytest.mark.parametrize("valor", ["50", 12.5, True])
def test_un_tope_que_no_es_entero_no_se_interpreta(valor):
    """``True`` incluido: en Python es un ``int`` de 1, y un tope de una página
    disfrazado de booleano sería un truncamiento silencioso."""
    with pytest.raises(PipelineError, match="entero positivo"):
        limites_efectivos(max_pages=valor)


def test_un_job_puede_bajar_los_topes():
    limites = limites_efectivos(max_pages=5, total_budget_s=30)
    assert limites.max_pages == 5
    assert limites.total_budget_s == 30


def test_los_topes_efectivos_se_reportan():
    """Van a ``target`` del artefacto: un tope que recorta en silencio se leería
    como cobertura completa."""
    assert set(limites_efectivos().como_dict()) == set(CAMPOS)


def test_los_topes_no_son_mutables():
    limites = limites_efectivos()
    with pytest.raises(Exception):
        limites.max_pages = 999
    assert isinstance(limites, LimitesExploracion)
