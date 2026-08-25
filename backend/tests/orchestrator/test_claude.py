"""Tests del cliente Claude y utilidades (Bloque 4).

Los dos tests del constructor piden ``sdk_construible``: la capa 2 del
cortafuegos (LLM1) bloquea la construcción directa del SDK, y el objeto de estos
dos tests **es** el constructor. Construir no es llamar —no abre conexión ni
consume tokens— y las capas 1, 3 y 4 siguen en pie.

Hasta LLM1 estos dos tests construían un ``ChatAnthropic`` real sin que ninguna
capa lo viera: importan ``get_claude_client`` por su nombre al cargar el módulo,
así que el ``monkeypatch`` del conftest sobre el atributo del módulo nunca les
alcanzaba. Era exactamente el hueco que la capa 2 viene a cerrar; ahora la
excepción es visible y está pedida por su nombre.
"""

from app.dependencies.claude import (
    estimate_cost,
    get_claude_client,
    retry_after_seconds,
)


def test_estimate_cost_usa_precios_de_settings():
    # 1M input + 1M output => 3 + 15 = 18 USD
    assert estimate_cost(1_000_000, 1_000_000) == 18.0
    assert estimate_cost(0, 0) == 0.0


def test_retry_after_seconds_lee_header():
    class _Resp:
        headers = {"retry-after": "2.5"}

    class _Exc(Exception):
        response = _Resp()

    assert retry_after_seconds(_Exc()) == 2.5


def test_retry_after_seconds_sin_header():
    assert retry_after_seconds(ValueError("x")) is None


def test_get_claude_client_construye(sdk_construible):
    client = get_claude_client()
    model = getattr(client, "model", None) or getattr(client, "model_name", None)
    assert model == "claude-sonnet-5"


def test_get_claude_client_fija_max_tokens(sdk_construible):
    """El cliente fija max_tokens explícito (no el default 4096) para que la
    dimensión más grande de EXTRACT no se trunque a mitad del JSON."""
    from app.config.settings import settings

    client = get_claude_client()
    assert client.max_tokens == settings.CLAUDE_MAX_TOKENS
    assert settings.CLAUDE_MAX_TOKENS >= 8192
