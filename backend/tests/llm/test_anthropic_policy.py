"""Candado: la política de Anthropic es la de siempre, byte a byte (LLM0).

Este bloque movió la política (reintentos, ``retry-after``, tarifa) de
``app/dependencies/claude.py`` a ``ai/llm/providers/anthropic.py``. Un refactor
de una política de reintentos falla **en silencio**: deja de reintentar y nadie
lo nota hasta que un job cae contra un 429. De ahí que se fije aquí.
"""

from anthropic import APIConnectionError, InternalServerError, RateLimitError

from ai.llm.providers.anthropic import SPEC, is_retryable, price_per_mtok
from ai.llm.retry import call_with_retry, wait_strategy
from app.config.settings import settings
from app.dependencies.claude import _RETRYABLE, estimate_cost, retry_after_seconds


def test_la_tupla_de_reintentables_no_cambio():
    assert _RETRYABLE == (RateLimitError, InternalServerError, APIConnectionError)


def test_is_retryable_responde_lo_mismo_que_la_tupla():
    for tipo in _RETRYABLE:
        # Instancia sin __init__: solo interesa el isinstance, no el mensaje.
        assert is_retryable(tipo.__new__(tipo)) is True
    assert is_retryable(ValueError("x")) is False


def test_el_spec_usa_la_lectura_de_retry_after_de_siempre():
    class _Resp:
        headers = {"retry-after": "2.5"}

    class _Exc(Exception):
        response = _Resp()

    assert SPEC.wait_hint(_Exc()) == 2.5
    assert SPEC.wait_hint(ValueError("x")) is None
    assert retry_after_seconds(_Exc()) == 2.5


def test_la_espera_respeta_retry_after_y_si_no_hace_backoff():
    class _Outcome:
        def __init__(self, exc):
            self._exc = exc

        def exception(self):
            return self._exc

    class _State:
        def __init__(self, exc, attempt):
            self.outcome = _Outcome(exc)
            self.attempt_number = attempt

    class _Resp:
        headers = {"retry-after": "7"}

    class _Exc(Exception):
        response = _Resp()

    espera = wait_strategy(SPEC)
    assert espera(_State(_Exc(), 1)) == 7.0
    # Sin cabecera: exponencial con tope de 30s, idéntico al de antes.
    assert espera(_State(ValueError("x"), 3)) == 8.0
    assert espera(_State(ValueError("x"), 10)) == 30.0


async def test_call_with_retry_reintenta_lo_reintentable():
    intentos = {"n": 0}

    async def _falla_una_vez():
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise InternalServerError.__new__(InternalServerError)
        return "ok"

    # `wait_hint` devuelve 0 en esta excepción sintética (no trae cabecera), así
    # que el backoff sería exponencial; se recorta el spec para no dormir.
    rapido = type(SPEC)(
        name=SPEC.name,
        default_model=SPEC.default_model,
        build_client=SPEC.build_client,
        is_retryable=SPEC.is_retryable,
        wait_hint=lambda _exc: 0.0,
        price_per_mtok=SPEC.price_per_mtok,
    )
    assert await call_with_retry(_falla_una_vez, spec=rapido) == "ok"
    assert intentos["n"] == 2


async def test_call_with_retry_no_reintenta_lo_no_reintentable():
    intentos = {"n": 0}

    async def _falla():
        intentos["n"] += 1
        raise ValueError("no reintentable")

    try:
        await call_with_retry(_falla, spec=SPEC)
    except ValueError:
        pass
    assert intentos["n"] == 1


def test_la_tarifa_sale_de_las_mismas_variables_de_entorno():
    assert price_per_mtok(settings.CLAUDE_MODEL) == (
        settings.CLAUDE_PRICE_INPUT_PER_MTOK,
        settings.CLAUDE_PRICE_OUTPUT_PER_MTOK,
    )


def test_el_costo_estimado_da_el_mismo_numero_que_antes():
    """1M input + 1M output => 3 + 15 = 18 USD, con el mismo redondeo."""
    assert estimate_cost(1_000_000, 1_000_000) == 18.0
    assert estimate_cost(0, 0) == 0.0
    assert estimate_cost(1234, 567) == 0.012207

    from ai.llm import get_llm

    # El cliente que devuelve la fábrica lleva la tarifa dentro: mismo número.
    llm = get_llm("ef", data_class="real")
    assert llm.estimate_cost(1234, 567) == estimate_cost(1234, 567)
