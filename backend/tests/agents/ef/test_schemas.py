"""Tests del contrato EFArtifact v1.2.0 (Bloque 1)."""

import pytest
from pydantic import ValidationError

from ai.agents.ef.schemas import (
    SCHEMA_VERSION,
    Assumption,
    Cardinality,
    EFArtifact,
    Entity,
    Origin,
    Question,
    Relationship,
)
from ai.agents.ef.schemas.examples import example_artifact


def test_example_artifact_es_valido():
    """La fixture de ejemplo debe construir un EFArtifact válido."""
    art = example_artifact()
    assert isinstance(art, EFArtifact)
    assert art.schema_version == SCHEMA_VERSION == "1.2.0"
    assert art.entities[0].name == "Siniestro"


def test_round_trip_dump_y_validate():
    """model_dump -> model_validate debe reconstruir un artefacto idéntico."""
    art = example_artifact()
    dumped = art.model_dump(mode="json")
    reconstruido = EFArtifact.model_validate(dumped)
    assert reconstruido == art
    # el segundo dump debe ser byte-idéntico al primero
    assert reconstruido.model_dump(mode="json") == dumped


def test_round_trip_json_string():
    """Serialización a JSON string y de vuelta."""
    art = example_artifact()
    raw = art.model_dump_json()
    reconstruido = EFArtifact.model_validate_json(raw)
    assert reconstruido == art


def test_claves_en_ingles_valores_en_espanol():
    """Las claves del JSON son inglés; los valores de negocio, español."""
    dumped = example_artifact().model_dump(mode="json")
    assert "systems_interpretation" in dumped
    assert "questions_for_analyst" in dumped
    assert "siniestro" in dumped["summary"].lower()


def test_extra_keys_prohibidas():
    """extra='forbid': una clave desconocida invalida el artefacto."""
    dumped = example_artifact().model_dump(mode="json")
    dumped["clave_desconocida"] = 123
    with pytest.raises(ValidationError):
        EFArtifact.model_validate(dumped)


def test_confidence_fuera_de_rango():
    """confidence debe estar en [0, 1]."""
    with pytest.raises(ValidationError):
        Entity(id="ENT-X", name="X", origin=Origin.STATED, confidence=1.5)


def test_cardinality_enum_cerrado():
    """cardinality solo admite valores del enum."""
    rel = Relationship(
        id="REL-X",
        source_entity_ref="A",
        target_entity_ref="B",
        cardinality="1:N",
    )
    assert rel.cardinality is Cardinality.ONE_TO_MANY
    with pytest.raises(ValidationError):
        Relationship(
            id="REL-Y",
            source_entity_ref="A",
            target_entity_ref="B",
            cardinality="muchos",
        )


def test_assumption_id_formato_sup():
    """El id de un supuesto debe seguir el formato SUP-###."""
    ok = Assumption(id="SUP-001", assumption="algo")
    assert ok.id == "SUP-001"
    with pytest.raises(ValidationError):
        Assumption(id="A-1", assumption="algo")


def test_question_status_default_pendiente():
    """El estado por defecto de una pregunta es 'pendiente'."""
    q = Question(
        id="Q-X",
        question="¿?",
        reason="motivo",
        audience="negocio",
    )
    assert q.status.value == "pendiente"
    assert q.blocking is False
