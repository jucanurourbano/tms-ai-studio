"""Tests de la base compartida de agentes (B0): structured / refine / graph."""

from pydantic import BaseModel

from ai.agents.base.refine import answered_validations, build_authoritative_context
from ai.agents.base.structured import complete_structured, run_structured_map


class _Item(BaseModel):
    name: str


class ScriptedLLM:
    """Devuelve respuestas en orden (independiente del prompt)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def complete_json(self, *, system, user):
        resp = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return resp


class DimLLM:
    """Devuelve válido salvo para el ítem cuyo user contenga ``bad``."""

    async def complete_json(self, *, system, user):
        if "bad" in user:
            return "{ roto"
        return '{"name":"ok"}'


async def test_complete_structured_repara():
    llm = ScriptedLLM(["{ roto", '{"name":"ok"}'])
    model, err = await complete_structured(
        llm, system="s", user="u", schema=_Item, max_repairs=2
    )
    assert model is not None and model.name == "ok"
    assert err == ""
    assert llm.calls == 2


async def test_complete_structured_irreparable():
    llm = ScriptedLLM(["x", "y", "z"])
    model, err = await complete_structured(
        llm, system="s", user="u", schema=_Item, max_repairs=1
    )
    assert model is None
    assert err  # último error reportado
    assert llm.calls == 2  # intento + 1 reparación


async def test_run_structured_map_cuarentena():
    items = [{"id": "a", "text": "good"}, {"id": "b", "text": "bad"}]
    results, skipped, tokens = await run_structured_map(
        DimLLM(),
        items,
        build_system=lambda it: "SYS",
        build_user=lambda it: it["text"],
        schema=_Item,
        ref_of=lambda it: it["id"],
        stage="TEST",
        estimate_tokens=len,
        concurrency=2,
        max_repairs=1,
    )
    assert {r["ref"] for r in results} == {"a"}
    assert len(skipped) == 1
    assert skipped[0]["ref"] == "b"
    assert skipped[0]["stage"] == "TEST"
    assert tokens["total"] > 0


def test_build_authoritative_context():
    summary = {
        "validations": [
            {
                "target_type": "question",
                "target_id": "Q-001",
                "status": "confirmado",
                "respuesta": "Sí",
            },
            {
                "target_type": "question",
                "target_id": "Q-002",
                "status": "pendiente",
                "respuesta": None,
            },
        ]
    }
    assert len(answered_validations(summary)) == 1
    ctx = build_authoritative_context(summary)
    assert "Q-001" in ctx and "Sí" in ctx
    assert "Q-002" not in ctx


def test_build_authoritative_context_vacio():
    assert build_authoritative_context({"validations": []}) is None
