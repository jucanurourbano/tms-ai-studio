"""Tests de la fase EXTRACT con LLM mockeado (Bloque 5)."""

from ai.agents.ef.extract import DIMENSIONS, extract_dimension, run_extract
from ai.agents.ef.schemas.extraction import ActorsExtract
from tests.mocks import DimAwareLLM

DIM_ACTORS = next(d for d in DIMENSIONS if d.name == "actors")

VALID_ACTORS = (
    '{"actors":[{"name":"Operador","source_ref":"c0","evidence":"e",'
    '"confidence":0.9,"origin":"stated"}]}'
)


class ScriptedLLM:
    """Devuelve respuestas en orden, sin importar el prompt."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def complete_json(self, *, system, user):
        resp = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return resp


async def test_extract_dimension_valido():
    llm = ScriptedLLM([VALID_ACTORS])
    result = await extract_dimension(llm, DIM_ACTORS, "ctx", "texto", "GLOS")
    assert isinstance(result, ActorsExtract)
    assert result.actors[0].name == "Operador"
    assert llm.calls == 1


async def test_extract_dimension_reparable():
    # primer intento JSON inválido, segundo válido
    llm = ScriptedLLM(["{ roto", VALID_ACTORS])
    result = await extract_dimension(llm, DIM_ACTORS, "ctx", "texto", "GLOS")
    assert result is not None
    assert llm.calls == 2  # una reparación


async def test_extract_dimension_irreparable():
    llm = ScriptedLLM(["roto1", "roto2", "roto3", "roto4"])
    result = await extract_dimension(
        llm, DIM_ACTORS, "ctx", "texto", "GLOS", max_repairs=2
    )
    assert result is None  # cuarentena
    assert llm.calls == 3  # intento + 2 reparaciones


async def test_run_extract_todas_las_dimensiones():
    chunk = {"chunk_id": "chunk-0000", "context": "Doc", "text": "..."}
    results, skipped = await run_extract(DimAwareLLM(), [chunk], concurrency=3)
    assert skipped == []
    dims = {r["dimension"] for r in results}
    assert dims == {d.name for d in DIMENSIONS}


async def test_run_extract_cuarentena_no_tumba_job():
    chunk = {"chunk_id": "chunk-0000", "context": "Doc", "text": "..."}
    # 'CAMPOS' siempre inválido -> se pone en cuarentena, el resto continúa
    results, skipped = await run_extract(
        DimAwareLLM(invalid_for="CAMPOS"), [chunk], concurrency=2, max_repairs=1
    )
    assert len(skipped) == 1
    assert skipped[0]["ref"].endswith(":fields")
    assert skipped[0]["stage"] == "EXTRACT"
    assert "fields" not in {r["dimension"] for r in results}
