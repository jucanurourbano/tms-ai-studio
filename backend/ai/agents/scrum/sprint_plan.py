"""Nodo SPRINT_PLAN: bin-packing determinista por capacidad (D4).

Voraz, reproducible y testeable: recorre el backlog en orden, respeta las
dependencias (una historia va en un sprint igual o posterior al de todas sus
dependencias) y la capacidad configurable. Lo que no cabe o no puede colocarse
(sin estimación, supera la capacidad, o depende de algo no asignado) queda en
``unassigned`` — **siempre visible, nunca oculto**.
"""

from typing import Any


def plan_sprints(
    stories: list[dict],
    ordered_story_ids: list[str],
    capacity: int,
) -> tuple[list[dict], list[str], list[dict]]:
    """Asigna historias a sprints. Devuelve (sprints, unassigned_ids, observations)."""
    by_id = {s["id"]: s for s in stories}
    assigned: dict[str, int] = {}  # story_id -> índice de sprint (0-based)
    sprints: list[dict] = []
    unassigned: list[str] = []
    observations: list[dict] = []

    def _unassign(sid: str, reason: str) -> None:
        unassigned.append(sid)
        observations.append(
            {
                "description": f"Historia {sid} sin asignar a un sprint.",
                "reason": reason,
            }
        )

    for sid in ordered_story_ids:
        story = by_id.get(sid)
        if story is None:
            continue
        points = story.get("story_points") or 0

        if points <= 0:
            _unassign(sid, "sin estimación de puntos (pendiente de PO).")
            continue
        if points > capacity:
            _unassign(
                sid,
                f"requiere {points} puntos, supera la capacidad del sprint ({capacity}).",
            )
            continue

        deps = story.get("dependencies", []) or []
        unresolved = [d for d in deps if d not in assigned]
        if unresolved:
            _unassign(
                sid, f"depende de historias no asignadas: {', '.join(unresolved)}."
            )
            continue

        min_start = max((assigned[d] for d in deps), default=0)
        placed = False
        for idx in range(min_start, len(sprints)):
            if sprints[idx]["total_points"] + points <= capacity:
                sprints[idx]["story_ids"].append(sid)
                sprints[idx]["total_points"] += points
                assigned[sid] = idx
                placed = True
                break
        if not placed:
            idx = len(sprints)
            sprints.append(
                {
                    "id": f"SPRINT-{idx + 1}",
                    "goal": None,
                    "capacity_points": capacity,
                    "total_points": points,
                    "story_ids": [sid],
                }
            )
            assigned[sid] = idx

    return sprints, unassigned, observations


def sprint_goal(sprint: dict, stories_by_id: dict[str, dict]) -> str:
    """Deriva un objetivo breve del sprint a partir de las metas de sus historias."""
    goals = [
        (stories_by_id.get(sid) or {}).get("goal")
        for sid in sprint.get("story_ids", [])
    ]
    goals = [g for g in goals if g]
    if not goals:
        return "Sprint sin historias asignadas."
    return "Entregar: " + "; ".join(goals[:3]) + ("…" if len(goals) > 3 else ".")


def annotate_goals(sprints: list[dict], stories: list[dict]) -> None:
    """Rellena ``goal`` de cada sprint de forma determinista."""
    by_id: dict[str, dict[str, Any]] = {s["id"]: s for s in stories}
    for sprint in sprints:
        sprint["goal"] = sprint_goal(sprint, by_id)
