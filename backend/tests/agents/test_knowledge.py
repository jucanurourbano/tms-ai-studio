"""Tests del conocimiento inyectable: glosario y stack de la casa (A0)."""

from ai.knowledge import (
    glossary_block,
    load_glossary,
    load_tech_stack,
    tech_stack_block,
)


def test_glossary_sigue_disponible():
    """El glosario logístico no se rompe al generalizar el loader."""
    terms = load_glossary()
    assert "checkpoint" in terms
    assert "GLOSARIO LOGÍSTICO" in glossary_block()


def test_tech_stack_carga_y_marca_pendiente_de_validacion():
    data = load_tech_stack()
    # Nace explícitamente pendiente de validación por el equipo de Urbano.
    assert data.get("status") == "pendiente_de_validacion"
    assert data.get("version") == 0
    layers = data.get("layers", {})
    # Capas críticas presentes con default + allow-list.
    for layer in ("language_backend", "database_relational", "auth"):
        assert layer in layers
        assert layers[layer].get("default")
        assert isinstance(layers[layer].get("allowed"), list)
        assert layers[layer]["allowed"]


def test_tech_stack_block_es_allow_list_para_el_prompt():
    block = tech_stack_block()
    # Debe comunicar que es una allow-list y arrastrar el estado.
    assert "allow-list" in block
    assert "pendiente_de_validacion" in block
    # Incluye al menos una capa con su default renderizado.
    assert "language_backend" in block
    assert "por defecto" in block
