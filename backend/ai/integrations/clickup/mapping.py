"""Mapeo ScrumArtifact -> filas compatibles con ClickUp (D7).

Mapeo elegido: **Sprint → Lista, Historia → Tarea, Épica → tag/custom field**.
Las historias sin asignar van a la lista ``Backlog`` (siempre visibles).
"""

from typing import Any

# Prioridad ClickUp: must→urgent, should→high, could→normal, wont→low.
CLICKUP_PRIORITY = {
    "must": "urgent",
    "should": "high",
    "could": "normal",
    "wont": "low",
}

_BACKLOG_LIST = "Backlog"


def _sprint_of(artifact: dict) -> dict[str, str]:
    """Mapea story_id -> nombre de lista (sprint) o Backlog si no está asignada."""
    mapping: dict[str, str] = {}
    for sprint in artifact.get("sprints", []):
        for sid in sprint.get("story_ids", []):
            mapping[sid] = sprint["id"]
    for sid in artifact.get("unassigned_story_ids", []):
        mapping[sid] = _BACKLOG_LIST
    return mapping


def _criteria_markdown(story: dict) -> str:
    """Renderiza los criterios de aceptación como checklist markdown."""
    lines: list[str] = []
    for ac in story.get("acceptance_criteria", []):
        if ac.get("format") == "gherkin" and ac.get("given"):
            text = (
                f"Dado {ac.get('given')}, cuando {ac.get('when') or '—'}, "
                f"entonces {ac.get('then')}"
            )
        else:
            text = ac.get("text") or "(criterio)"
        lines.append(f"- [ ] {text}")
    return "\n".join(lines)


def _description(story: dict) -> str:
    parts = [story.get("statement", "")]
    criteria = _criteria_markdown(story)
    if criteria:
        parts.append("## Criterios de aceptación\n" + criteria)
    return "\n\n".join(p for p in parts if p)


def story_rows(artifact: dict[str, Any]) -> list[dict]:
    """Convierte las historias del artefacto en filas de tarea ClickUp."""
    sprint_of = _sprint_of(artifact)
    epic_title = {e["id"]: e.get("title") for e in artifact.get("epics", [])}
    rows: list[dict] = []
    for story in artifact.get("stories", []):
        sid = story["id"]
        rows.append(
            {
                "list": sprint_of.get(sid, _BACKLOG_LIST),
                "task_name": story.get("goal") or story.get("statement") or sid,
                "description": _description(story),
                "status": "to do",
                "priority": CLICKUP_PRIORITY.get(
                    story.get("priority") or "could", "normal"
                ),
                "points": story.get("story_points"),
                "epic": epic_title.get(story.get("epic_ref")) or story.get("epic_ref"),
                "tags": list(story.get("tags", [])),
                "external_key": story.get("external_key") or sid,
            }
        )
    return rows
