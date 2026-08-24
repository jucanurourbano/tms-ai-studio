"""Tests de la fábrica de clientes LLM (LLM0).

La fábrica es el punto por el que pasan las 15 construcciones del cliente que
antes estaban repartidas. Lo que se fija aquí no es cómo resuelve, sino que
**falla hacia el lado seguro**: sin configuración usa Anthropic, con un nombre
desconocido no adivina, y sin `data_class` no arranca.
"""

import pytest

from ai.llm import (
    DEFAULT_PROVIDER,
    PROVIDERS,
    ProviderConfigError,
    get_llm,
    resolve_model,
    resolve_provider,
)
from app.config.settings import settings


def test_el_default_es_anthropic_sin_configuracion():
    """Criterio irrenunciable: sin nada en el entorno, el sistema usa Anthropic."""
    assert DEFAULT_PROVIDER == "anthropic"
    assert settings.LLM_PROVIDER == "anthropic"
    assert settings.LLM_ROLE_OVERRIDES == {}
    assert resolve_provider("ef") == "anthropic"
    assert resolve_provider("inventory_doc") == "anthropic"


def test_el_default_sobrevive_a_un_global_vacio(monkeypatch):
    """Un ``LLM_PROVIDER=`` vacío en el ``.env`` no deja al sistema sin proveedor."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "")
    assert resolve_provider("qa") == DEFAULT_PROVIDER


def test_el_override_por_rol_gana_al_global(monkeypatch):
    """Precedencia: rol > global. Es el caso real del banco de pruebas."""
    monkeypatch.setattr(settings, "LLM_ROLE_OVERRIDES", {"qa": "anthropic"})
    monkeypatch.setattr(settings, "LLM_PROVIDER", "inexistente")
    assert resolve_provider("qa") == "anthropic"
    # El rol SIN override sigue cayendo en el global — que aquí no existe.
    with pytest.raises(ProviderConfigError):
        resolve_provider("ef")


def test_un_proveedor_desconocido_falla_en_vez_de_caer_al_default(monkeypatch):
    """No adivina: un `.env` mal escrito que resolviera a Anthropic mentiría."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    with pytest.raises(ProviderConfigError, match="Proveedor de LLM desconocido"):
        resolve_provider("bd")


def test_get_llm_exige_data_class():
    """Omitir `data_class` es un TypeError ruidoso, no una fuga silenciosa."""
    with pytest.raises(TypeError):
        get_llm("ef")  # type: ignore[call-arg]


def test_get_llm_rechaza_una_data_class_inventada():
    with pytest.raises(ProviderConfigError, match="data_class inválida"):
        get_llm("ef", data_class="publico")  # type: ignore[arg-type]


def test_get_llm_devuelve_un_llmclient_completo():
    """Devuelve el cliente del protocolo, no el chat crudo del SDK.

    Es exactamente el fallo que tenía la ingesta de documentos del inventario:
    recibía un ``ChatAnthropic`` —sin ``complete_json``— donde se esperaba un
    ``LLMClient``.
    """
    llm = get_llm("inventory_doc", data_class="real")
    assert hasattr(llm, "complete_json")
    assert llm.provider == "anthropic"
    assert llm.data_class == "real"


def test_el_modelo_sale_del_proveedor_y_admite_override(monkeypatch):
    assert resolve_model("anthropic") == settings.CLAUDE_MODEL
    monkeypatch.setattr(settings, "LLM_MODEL_OVERRIDES", {"anthropic": "claude-otro"})
    assert resolve_model("anthropic") == "claude-otro"
    assert get_llm("bd", data_class="real").model == "claude-otro"


def test_el_registro_tiene_un_solo_proveedor_en_llm0():
    """Candado del bloque: LLM0 no añade proveedores, solo la puerta."""
    assert list(PROVIDERS) == ["anthropic"]
