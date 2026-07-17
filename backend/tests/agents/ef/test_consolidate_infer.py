"""Tests de CONSOLIDATE e INFER (Bloque 5)."""

from ai.agents.ef.consolidate import consolidate
from ai.agents.ef.infer import infer


def test_consolidate_dedupe_semantico_y_provenance():
    raw = [
        {
            "chunk_id": "c0",
            "dimension": "actors",
            "data": {
                "actors": [
                    {
                        "name": "Operador",
                        "source_ref": "c0",
                        "confidence": 0.7,
                        "origin": "stated",
                    }
                ]
            },
        },
        {
            "chunk_id": "c1",
            "dimension": "actors",
            "data": {
                "actors": [
                    {
                        "name": "OPERÁDOR",  # mismo actor (acentos/mayúsculas)
                        "source_ref": "c1",
                        "confidence": 0.9,
                        "origin": "stated",
                    }
                ]
            },
        },
    ]
    result = consolidate(raw)
    actors = result["actors"]
    assert len(actors) == 1  # deduplicado
    assert actors[0]["id"] == "ACT-001"  # renumeración estable
    assert set(actors[0]["source_ref"].split(",")) == {"c0", "c1"}  # provenance
    assert actors[0]["confidence"] == 0.9  # confianza combinada (max)


def test_consolidate_requirements_por_categoria():
    raw = [
        {
            "chunk_id": "c0",
            "dimension": "requirements",
            "data": {
                "business": [{"text": "Registrar siniestro", "origin": "stated"}],
                "functional": [{"text": "Cambiar estado", "origin": "stated"}],
                "non_functional": [],
            },
        }
    ]
    result = consolidate(raw)
    assert result["requirements"]["business"][0]["id"] == "REQ-B-001"
    assert result["requirements"]["functional"][0]["id"] == "REQ-F-001"


def _consolidado_con_campos():
    return {
        "actors": [{"id": "ACT-001", "name": "Operador"}],
        "fields": [
            {"id": "FLD-001", "name": "numero_guia", "entity_ref": "Siniestro"},
            {"id": "FLD-002", "name": "guia_id", "entity_ref": "Siniestro"},
            {"id": "FLD-003", "name": "codigo", "entity_ref": "Guia"},
        ],
    }


def test_infer_deriva_modelo_de_datos():
    inferred = infer(_consolidado_con_campos())

    # Entidades derivadas a partir de entity_ref
    nombres = {e["name"] for e in inferred["entities"]}
    assert nombres == {"Siniestro", "Guia"}
    assert all(e["origin"] == "derived" for e in inferred["entities"])

    # Fields remapeados a ids de entidad
    assert all(f["entity_ref"].startswith("ENT-") for f in inferred["fields"])

    # Relationship inferida desde 'guia_id' (Siniestro -> Guia)
    assert len(inferred["relationships"]) == 1
    rel = inferred["relationships"][0]
    assert rel["cardinality"] == "1:N"
    assert rel["origin"] == "derived"

    # CRUD por entidad (2) y APIs GET/POST por entidad (4)
    assert len(inferred["crud"]) == 2
    assert len(inferred["apis"]) == 4
    assert all(a["origin"] == "derived" for a in inferred["apis"])
