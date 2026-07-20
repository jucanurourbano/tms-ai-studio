"""Tests de ESTIMATE/PRIORITIZE/SPRINT_PLAN (B4)."""

import json

from ai.agents.scrum.estimate import run_estimate
from ai.agents.scrum.prioritize import build_backlog, run_prioritize
from ai.agents.scrum.sprint_plan import annotate_goals, plan_sprints
from tests.mocks import ScrumMapLLM


class ScriptedLLM:
    def __init__(self, response):
        self.response = response

    async def complete_json(self, *, system, user):
        return self.response


def _stories():
    return [
        {
            "id": "US-001",
            "statement": "Como op quiero registrar para trazar.",
            "acceptance_criteria": [],
            "source_refs": {"requirement_refs": ["REQ-F-001"]},
            "dependencies": [],
        },
        {
            "id": "US-002",
            "statement": "Como op quiero cambiar estado para seguir.",
            "acceptance_criteria": [],
            "source_refs": {"requirement_refs": ["REQ-F-002"]},
            "dependencies": ["US-001"],
        },
    ]


async def test_estimate_fibonacci_y_confianza():
    stories, skipped, tokens = await run_estimate(ScrumMapLLM(), _stories())
    assert all(s["story_points"] == 5 for s in stories)
    assert all(s["estimation_confidence"] == 0.7 for s in stories)
    assert skipped == []
    assert tokens["total"] > 0


async def test_estimate_no_fibonacci_va_a_cuarentena():
    # 4 no es Fibonacci válido; tras reparación sigue igual -> cuarentena.
    bogus = ScriptedLLM(
        json.dumps({"story_points": 4, "rationale": "x", "confidence": 0.5})
    )
    stories, skipped, _ = await run_estimate(bogus, _stories(), max_repairs=1)
    assert all(s["story_points"] is None for s in stories)
    assert len(skipped) == 2


async def test_prioritize_y_backlog_ordenado():
    stories = _stories()
    stories, _, _ = await run_prioritize(ScrumMapLLM(), stories)
    assert all(s["priority"] == "must" for s in stories)
    backlog = build_backlog(stories)
    assert backlog["method"] == "moscow"
    assert set(backlog["ordered_story_ids"]) == {"US-001", "US-002"}


def test_backlog_respeta_buckets_moscow():
    stories = [
        {"id": "A", "priority": "could", "value": 5, "effort": 1},
        {"id": "B", "priority": "must", "value": 1, "effort": 5},
        {"id": "C", "priority": "should", "value": 3, "effort": 3},
    ]
    ordered = build_backlog(stories)["ordered_story_ids"]
    # must (B) antes que should (C) antes que could (A), pese al ratio de A.
    assert ordered == ["B", "C", "A"]


def test_sprint_plan_respeta_capacidad_y_dependencias():
    stories = [
        {"id": "US-001", "story_points": 13, "dependencies": []},
        {"id": "US-002", "story_points": 13, "dependencies": ["US-001"]},
        {"id": "US-003", "story_points": 5, "dependencies": []},
    ]
    sprints, unassigned, obs = plan_sprints(
        stories, ["US-001", "US-002", "US-003"], capacity=20
    )
    # US-001 (13) + US-003 (5) caben en SPRINT-1 (18<=20); US-002 (13) no cabe con
    # US-001 y además depende de él -> SPRINT-2.
    assert sprints[0]["story_ids"] == ["US-001", "US-003"]
    assert sprints[0]["total_points"] == 18
    assert sprints[1]["story_ids"] == ["US-002"]
    assert unassigned == []
    assert obs == []


def test_sprint_plan_unassigned_visible():
    stories = [
        {"id": "US-001", "story_points": 21, "dependencies": []},  # cabe justo (=cap)
        {"id": "US-002", "story_points": 8, "dependencies": ["US-009"]},  # dep ausente
        {"id": "US-003", "story_points": 0, "dependencies": []},  # sin estimar
    ]
    sprints, unassigned, obs = plan_sprints(
        stories, ["US-001", "US-002", "US-003"], capacity=21
    )
    assert sprints[0]["story_ids"] == ["US-001"]
    assert set(unassigned) == {"US-002", "US-003"}
    # Cada no-asignada deja observación (nunca oculto).
    assert len(obs) == 2


def test_sprint_plan_historia_supera_capacidad():
    stories = [{"id": "US-001", "story_points": 21, "dependencies": []}]
    sprints, unassigned, obs = plan_sprints(stories, ["US-001"], capacity=13)
    assert sprints == []
    assert unassigned == ["US-001"]
    assert "supera la capacidad" in obs[0]["reason"]


def test_annotate_goals():
    stories = [{"id": "US-001", "goal": "registrar siniestro"}]
    sprints = [{"id": "SPRINT-1", "goal": None, "story_ids": ["US-001"]}]
    annotate_goals(sprints, stories)
    assert "registrar siniestro" in sprints[0]["goal"]
