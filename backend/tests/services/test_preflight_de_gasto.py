"""GAS1 — el preflight del techo del mes en los servicios.

Es **redundante** con el freno del cliente, y a propósito: sin él el usuario ve
un job que arranca, corre y muere; con él, ve el número antes de esperar. El que
GARANTIZA es el freno de ``MeteredLLMClient``, que corre antes de **cada**
llamada. Un freno que solo viviera aquí sería un freno que un nodo se salta —ya
nos pasó con la ingesta de documentos del inventario, que se saltaba incluso el
runner—.

Lo que estos tests fijan es esa jerarquía, no solo el 409: que el preflight
avise, que **no** sea quien garantiza, y que un libro mayor ilegible no rompa el
arranque por su cuenta (de eso se encarga el cliente, con su mensaje).
"""

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from ai.llm import budget
from app.config.settings import settings
from app.errors import ConflictError
from app.services.spend_sink import preflight_mensual

BACKEND = Path(__file__).resolve().parents[2]
SERVICIOS = ("ef", "scrum", "arquitectura", "bd", "api", "qa")


def _sumidero(mes: str):
    class Fijo:
        async def totales(self, **_kwargs):
            return budget.Totales(mes_usd=Decimal(mes), job_usd=Decimal("0"))

        async def anotar(self, fila):  # pragma: no cover
            pass

    return Fijo()


async def test_con_el_mes_agotado_el_preflight_devuelve_409(monkeypatch):
    monkeypatch.setattr("ai.llm.budget._SINK", _sumidero("99.9"))
    with pytest.raises(ConflictError) as exc:
        await preflight_mensual()
    assert exc.value.http_status == 409
    # Y dice lo mismo que diría el freno: cuánto llevaba y qué variable subir.
    assert "LLM_MONTHLY_CAP_USD" in str(exc.value)
    assert "99.9000" in str(exc.value)


async def test_con_margen_de_sobra_el_preflight_deja_pasar(monkeypatch):
    monkeypatch.setattr("ai.llm.budget._SINK", _sumidero("10.0"))
    await preflight_mensual()  # no lanza


async def test_el_objetivo_del_mes_no_frena_el_arranque(monkeypatch):
    """40 USD supera el objetivo de 30 y no llega al techo de 100: pasa.

    El objetivo se reporta, nunca bloquea. Si bloqueara, el tercer número dejaría
    de ser un objetivo y sería un segundo techo.
    """
    monkeypatch.setattr("ai.llm.budget._SINK", _sumidero("40.0"))
    assert settings.LLM_MONTHLY_TARGET_USD == 30.0
    await preflight_mensual()


async def test_un_libro_mayor_ilegible_NO_rompe_el_preflight(monkeypatch):
    """El fail-closed vive en el cliente, con su mensaje, y en un solo sitio.

    Duplicarlo aquí convertiría una cortesía en un segundo punto donde el
    arranque puede romperse por su cuenta, y con un mensaje peor: el usuario
    vería "no se puede leer el libro mayor" al pulsar Generar, en vez de verlo en
    el job, que es donde está el contexto.
    """
    monkeypatch.setattr("ai.llm.budget._SINK", budget.SumideroQueNiega())
    await preflight_mensual()  # no lanza: no es quien garantiza


@pytest.mark.parametrize("servicio", SERVICIOS)
def test_los_seis_servicios_llaman_al_preflight_antes_de_crear_el_job(servicio):
    """Candado estructural: se comprueba en TODOS los servicios, no en uno.

    Y se exige que sea la **primera** sentencia del método: después de crear el
    job, un 409 dejaría una fila ``PENDING`` que nunca va a correr.
    """
    ruta = BACKEND / "app" / "services" / f"{servicio}_service.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    fuente = ruta.read_text(encoding="utf-8")

    encolan = [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.AsyncFunctionDef)
        and "background_tasks.add_task" in (ast.get_source_segment(fuente, nodo) or "")
    ]
    assert encolan, f"{servicio}: no se encontró ningún método que encole un pipeline"

    for metodo in encolan:
        cuerpo = list(metodo.body)
        if (
            isinstance(cuerpo[0], ast.Expr)
            and isinstance(cuerpo[0].value, ast.Constant)
            and isinstance(cuerpo[0].value.value, str)
        ):
            cuerpo = cuerpo[1:]
        primera = ast.dump(cuerpo[0])
        assert "preflight_mensual" in primera, (
            f"{servicio}.{metodo.name} encola un pipeline sin llamar antes a "
            "preflight_mensual(), o lo llama después de crear el job."
        )
