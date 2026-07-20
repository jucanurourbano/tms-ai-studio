"""Tests del contrato ScrumArtifact v1.0.0 (B1): validación + round-trip."""

import pytest
from pydantic import ValidationError

from ai.agents.scrum.schemas import (
    SCHEMA_VERSION,
    AcceptanceFormat,
    BacklogMethod,
    MoscowPriority,
    ScrumArtifact,
    StoryPoints,
)
from ai.agents.scrum.schemas.examples import example_artifact


def test_ejemplo_valido_y_version():
    art = example_artifact()
    assert art.schema_version == SCHEMA_VERSION == "1.0.0"
    assert art.source.ready_snapshot is True
    assert art.stories[0].story_points == StoryPoints.SP_5
    assert art.stories[0].priority == MoscowPriority.MUST


def test_round_trip_json_estable():
    art = example_artifact()
    dumped = art.model_dump(mode="json")
    reloaded = ScrumArtifact.model_validate(dumped)
    assert reloaded.model_dump(mode="json") == dumped


def test_story_points_fibonacci_cerrado():
    art = example_artifact()
    data = art.model_dump(mode="json")
    # 4 no es Fibonacci válido -> debe fallar.
    data["stories"][0]["story_points"] = 4
    with pytest.raises(ValidationError):
        ScrumArtifact.model_validate(data)


def test_extra_forbid_en_artifact():
    data = example_artifact().model_dump(mode="json")
    data["campo_desconocido"] = "x"
    with pytest.raises(ValidationError):
        ScrumArtifact.model_validate(data)


def test_priority_moscow_cerrado():
    data = example_artifact().model_dump(mode="json")
    data["stories"][0]["priority"] = "high"  # no es MoSCoW
    with pytest.raises(ValidationError):
        ScrumArtifact.model_validate(data)


def test_backlog_y_criterios_por_defecto():
    # Un artefacto mínimo debe validar con sus defaults.
    minimal = ScrumArtifact.model_validate(
        {
            "source": {
                "ef_job_id": "J1",
                "ef_artifact_hash": "h",
            }
        }
    )
    assert minimal.product_backlog.method == BacklogMethod.MOSCOW
    assert minimal.stories == []
    assert minimal.metrics.coverage == 0.0


def test_acceptance_format_default_gherkin():
    art = example_artifact()
    assert art.stories[0].acceptance_criteria[0].format == AcceptanceFormat.GHERKIN
