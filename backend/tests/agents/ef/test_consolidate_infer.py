"""Tests de CONSOLIDATE e INFER (Bloque 5)."""

from ai.agents.ef.consolidate import consolidate
from ai.agents.ef.critique import find_orphan_refs
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


def test_consolidate_enlaza_field_ref_a_fld_id():
    """REGRESIÓN (#5): field_ref en texto libre del LLM se enlaza al FLD-ID real,
    evitando referencias huérfanas espurias en CRITIQUE."""
    raw = [
        {
            "chunk_id": "c0",
            "dimension": "fields",
            "data": {
                "fields": [
                    {"name": "saldo_dias_disponibles", "origin": "stated"},
                    {"name": "fecha_inicio", "origin": "stated"},
                ]
            },
        },
        {
            "chunk_id": "c0",
            "dimension": "rules_validations",
            "data": {
                "business_rules": [],
                "validations": [
                    {
                        "rule": "No exceder el saldo.",
                        "field_ref": "saldo de días disponibles",  # texto libre
                        "origin": "stated",
                    },
                    {
                        "rule": "Fecha válida.",
                        "field_ref": "fecha de inicio",  # texto libre
                        "origin": "stated",
                    },
                ],
            },
        },
    ]
    result = consolidate(raw)
    by_name = {f["name"]: f["id"] for f in result["fields"]}
    refs = [v["field_ref"] for v in result["validations"]]
    assert by_name["saldo_dias_disponibles"] in refs
    assert by_name["fecha_inicio"] in refs
    # Ya no quedan referencias huérfanas de field_ref.
    orphans = find_orphan_refs(result, {"entities": []})
    assert orphans == []


def _consolidado_con_campos():
    return {
        "actors": [{"id": "ACT-001", "name": "Operador"}],
        "fields": [
            {"id": "FLD-001", "name": "numero_guia", "entity_ref": "Siniestro"},
            {"id": "FLD-002", "name": "guia_id", "entity_ref": "Siniestro"},
            {"id": "FLD-003", "name": "codigo", "entity_ref": "Guia"},
        ],
    }


def test_infer_relationship_fk_prefijo_y_tipo_referencia():
    """REGRESIÓN (#4): deriva la relación Solicitud N:1 Trabajador desde una FK,
    reconociendo prefijo 'id_' y data_type 'reference' (antes solo sufijo '_id')."""
    cons = {
        "actors": [],
        "fields": [
            {"name": "dias_solicitados", "entity_ref": "Solicitud de vacaciones"},
            {"name": "saldo", "entity_ref": "Trabajador"},
            {
                "name": "trabajador_id",
                "entity_ref": "Solicitud de vacaciones",
                "data_type": "reference",
            },
        ],
    }
    inferred = infer(cons)
    ent = {e["name"]: e["id"] for e in inferred["entities"]}
    assert set(ent) == {"Solicitud de vacaciones", "Trabajador"}
    rels = inferred["relationships"]
    assert len(rels) == 1
    rel = rels[0]
    # Un Trabajador tiene muchas Solicitudes (Solicitud N:1 Trabajador).
    assert rel["source_entity_ref"] == ent["Trabajador"]
    assert rel["target_entity_ref"] == ent["Solicitud de vacaciones"]
    assert rel["cardinality"] == "1:N"


def test_infer_relationship_prefijo_id():
    """El patrón 'id_<entidad>' (común en español) también deriva la relación."""
    cons = {
        "actors": [],
        "fields": [
            {"name": "monto", "entity_ref": "Pedido"},
            {"name": "nombre", "entity_ref": "Cliente"},
            {"name": "id_cliente", "entity_ref": "Pedido"},
        ],
    }
    inferred = infer(cons)
    assert len(inferred["relationships"]) == 1


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
