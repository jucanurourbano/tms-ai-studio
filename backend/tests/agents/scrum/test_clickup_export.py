"""Tests del export ClickUp (fase a), el guard fail-closed y la auditoría (B7)."""

import csv
import importlib.util
import io
from pathlib import Path

import pytest

from ai.agents.scrum.schemas.examples import example_artifact
from ai.errors import ClickUpForbiddenError
from ai.integrations.clickup import (
    assert_target_authorized,
    clickup_configured,
    story_rows,
    to_clickup_csv,
    to_clickup_rows,
)
from app.config.settings import settings
from app.models.agent import AgentType
from app.repositories.agent_job_repository import AgentJobRepository


def _artifact() -> dict:
    return example_artifact().model_dump(mode="json")


# --- Guard fail-closed ------------------------------------------------------


def test_guard_sin_allowlist_rechaza(monkeypatch):
    monkeypatch.setattr(settings, "CLICKUP_ALLOWED_LIST_IDS", [])
    assert clickup_configured() is False
    with pytest.raises(ClickUpForbiddenError):
        assert_target_authorized("list-123")


def test_guard_lista_fuera_de_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "CLICKUP_ALLOWED_LIST_IDS", ["list-ok"])
    with pytest.raises(ClickUpForbiddenError):
        assert_target_authorized("list-otra")


def test_guard_espacio_incorrecto(monkeypatch):
    monkeypatch.setattr(settings, "CLICKUP_ALLOWED_LIST_IDS", ["list-ok"])
    monkeypatch.setattr(settings, "CLICKUP_SPACE_ID", "space-sistemas")
    # Resolver que devuelve un espacio distinto -> rechazo.
    with pytest.raises(ClickUpForbiddenError):
        assert_target_authorized("list-ok", resolve_space=lambda _l: "space-otro")


def test_guard_autoriza_destino_valido(monkeypatch):
    monkeypatch.setattr(settings, "CLICKUP_ALLOWED_LIST_IDS", ["list-ok"])
    monkeypatch.setattr(settings, "CLICKUP_SPACE_ID", "space-sistemas")
    # No lanza: lista permitida y espacio correcto.
    assert_target_authorized("list-ok", resolve_space=lambda _l: "space-sistemas")


# --- Mapeo y export ---------------------------------------------------------


def test_story_rows_mapeo_prioridad_y_lista():
    rows = story_rows(_artifact())
    by_key = {r["external_key"]: r for r in rows}
    us1 = by_key["01EF00000000000000000000EF:US-001"]
    assert us1["priority"] == "urgent"  # must -> urgent
    assert us1["list"] == "SPRINT-1"
    assert us1["points"] == 5
    assert "## Criterios de aceptación" in us1["description"]


def test_export_json_rows():
    rows = to_clickup_rows(_artifact())
    assert len(rows) == 2
    assert all("task_name" in r for r in rows)


def test_export_csv_cabecera_y_filas():
    csv_text = to_clickup_csv(_artifact())
    reader = list(csv.reader(io.StringIO(csv_text)))
    assert reader[0] == [
        "List",
        "Task Name",
        "Description",
        "Status",
        "Priority",
        "Points",
        "Epic",
        "Tags",
        "External Key",
    ]
    assert len(reader) == 3  # cabecera + 2 historias


def test_unassigned_va_a_backlog():
    art = _artifact()
    # Mover US-002 a sin asignar.
    art["sprints"][0]["story_ids"] = ["US-001"]
    art["unassigned_story_ids"] = ["US-002"]
    rows = {r["external_key"].split(":")[1]: r for r in story_rows(art)}
    assert rows["US-002"]["list"] == "Backlog"


# --- Auditoría --------------------------------------------------------------


async def test_auditoria_external_link_idempotente(session):
    repo = AgentJobRepository(session)
    job = await repo.create_job(AgentType.SCRUM)
    link1 = await repo.record_external_link(
        job.id,
        external_key="JOB:US-001",
        action="planned",
        story_id="US-001",
        list_id="list-ok",
    )
    link2 = await repo.record_external_link(
        job.id,
        external_key="JOB:US-001",
        action="created",
        external_id="task-9",
        story_id="US-001",
        list_id="list-ok",
    )
    assert link1.id == link2.id  # idempotente por external_key
    assert link2.action == "created"
    links = await repo.list_external_links(job.id)
    assert len(links) == 1


def test_migracion_0003_importa():
    path = (
        Path(__file__).resolve().parents[3]
        / "alembic"
        / "versions"
        / "0003_agent_external_links.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0003", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0003_agent_external_links"
    assert mod.down_revision == "0002_generalizar_agentes"
