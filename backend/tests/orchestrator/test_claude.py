"""Tests del cliente Claude y utilidades (Bloque 4)."""

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


def test_get_claude_client_construye():
    client = get_claude_client()
    model = getattr(client, "model", None) or getattr(client, "model_name", None)
    assert model == "claude-sonnet-5"


def test_get_claude_client_fija_max_tokens():
    """El cliente fija max_tokens explícito (no el default 4096) para que la
    dimensión más grande de EXTRACT no se trunque a mitad del JSON."""
    from app.config.settings import settings

    client = get_claude_client()
    assert client.max_tokens == settings.CLAUDE_MAX_TOKENS
    assert settings.CLAUDE_MAX_TOKENS >= 8192
