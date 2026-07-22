"""Tests del contrato ArchitectureArtifact v1.0.0 (A1): validación + round-trip."""

import pytest
from pydantic import ValidationError

from ai.agents.arquitectura.schemas import (
    SCHEMA_VERSION,
    ArchitectureArtifact,
    ArchitectureStyle,
    ComponentType,
    DiagramFormat,
    SizeClass,
)
from ai.agents.arquitectura.schemas.examples import example_artifact


def test_ejemplo_valido_y_version():
    art = example_artifact()
    assert art.schema_version == SCHEMA_VERSION == "1.0.0"
    assert art.source.ready_snapshot is True
    # Enlace a AMBOS jobs de origen (Scrum directo + EF transitivo).
    assert art.source.scrum_job_id
    assert art.source.ef_job_id
    assert art.architecture_style is not None
    assert art.architecture_style.chosen == ArchitectureStyle.MODULAR_MONOLITH
    assert len(art.components) >= 1


def test_round_trip_json_estable():
    art = example_artifact()
    dumped = art.model_dump(mode="json")
    reloaded = ArchitectureArtifact.model_validate(dumped)
    assert reloaded.model_dump(mode="json") == dumped


def test_extra_forbid_en_artifact():
    data = example_artifact().model_dump(mode="json")
    data["campo_desconocido"] = "x"
    with pytest.raises(ValidationError):
        ArchitectureArtifact.model_validate(data)


def test_architecture_style_cerrado():
    data = example_artifact().model_dump(mode="json")
    data["architecture_style"]["chosen"] = "layered"  # no es un estilo válido
    with pytest.raises(ValidationError):
        ArchitectureArtifact.model_validate(data)


def test_component_type_cerrado():
    data = example_artifact().model_dump(mode="json")
    data["components"][0]["type"] = "microfrontend"  # no es un tipo válido
    with pytest.raises(ValidationError):
        ArchitectureArtifact.model_validate(data)


def test_confidence_fuera_de_rango_falla():
    data = example_artifact().model_dump(mode="json")
    data["components"][0]["confidence"] = 1.5  # > 1.0
    with pytest.raises(ValidationError):
        ArchitectureArtifact.model_validate(data)


def test_minimal_defaults():
    # Un artefacto mínimo (solo source) valida con sus defaults.
    minimal = ArchitectureArtifact.model_validate(
        {
            "source": {
                "scrum_job_id": "S1",
                "scrum_artifact_hash": "sh",
                "ef_job_id": "E1",
                "ef_artifact_hash": "eh",
            }
        }
    )
    assert minimal.context.size_class == SizeClass.M
    assert minimal.architecture_style is None
    assert minimal.components == []
    assert minimal.metrics.coverage == 0.0


def test_diagramas_mermaid_deterministas():
    art = example_artifact()
    assert art.diagrams.component is not None
    assert art.diagrams.component.format == DiagramFormat.MERMAID
    assert "flowchart" in art.diagrams.component.code


def test_pregunta_al_arquitecto_bloqueante():
    art = example_artifact()
    q = art.questions_for_architect[0]
    assert q.blocking is True
    assert q.audience.value == "tecnico"
    assert q.linked_to_ref == "INT-001"


def test_integracion_sin_contrato_conocido():
    art = example_artifact()
    assert art.integrations[0].contract_known is False
    # Toda inferencia lleva origin=derived + confidence.
    assert art.integrations[0].origin.value == "derived"
    assert art.integrations[0].confidence is not None
