"""Tests del contrato DatabaseArtifact v1.0.0 (BD1): validación + round-trip.

Más allá del round-trip, estos tests fijan las **invariantes de diseño** que el
contrato debe sostener: el doble nivel de tipo (DB2), la trazabilidad al EF y que
ninguna regla del EF pueda desaparecer sin dejar rastro.
"""

import pytest
from pydantic import ValidationError

from ai.agents.bd.schemas import (
    SCHEMA_VERSION,
    DatabaseArtifact,
    DbEngine,
    LogicalType,
    PrimaryKeyStrategy,
    RuleEnforcement,
    TableKind,
)
from ai.agents.bd.schemas.examples import example_artifact
from ai.knowledge import DB_ENGINES, engine_type_map, load_db_conventions


def test_ejemplo_valido_y_version():
    art = example_artifact()
    assert art.schema_version == SCHEMA_VERSION == "1.0.0"
    assert art.source.ready_snapshot is True
    # Enlace a los TRES jobs de la cadena (Arquitectura directo; Scrum y EF
    # transitivos), para poder reproducir la corrida.
    assert art.source.architecture_job_id
    assert art.source.scrum_job_id
    assert art.source.ef_job_id
    assert art.target.engine is DbEngine.POSTGRESQL
    assert len(art.tables) >= 1


def test_round_trip_json_estable():
    art = example_artifact()
    dumped = art.model_dump(mode="json")
    reloaded = DatabaseArtifact.model_validate(dumped)
    assert reloaded.model_dump(mode="json") == dumped


def test_extra_forbid_en_artifact():
    data = example_artifact().model_dump(mode="json")
    data["campo_desconocido"] = "x"
    with pytest.raises(ValidationError):
        DatabaseArtifact.model_validate(data)


def test_extra_forbid_en_columna():
    """El structured output de TABLES es cerrado hasta el nivel de columna."""
    data = example_artifact().model_dump(mode="json")
    data["tables"][0]["columns"][0]["inventado"] = True
    with pytest.raises(ValidationError):
        DatabaseArtifact.model_validate(data)


# --- Doble nivel de tipo (DB2) ----------------------------------------------


def test_logical_type_cerrado():
    """El tipo lógico es un enum: el LLM no puede colar un tipo SQL arbitrario."""
    data = example_artifact().model_dump(mode="json")
    data["tables"][0]["columns"][0]["logical_type"] = "NVARCHAR(MAX)"
    with pytest.raises(ValidationError):
        DatabaseArtifact.model_validate(data)


@pytest.mark.parametrize("engine", DB_ENGINES)
def test_todo_logical_type_del_enum_se_traduce_en_cada_motor(engine: str):
    """El enum y el mapa de tipos del YAML van a la par, en ambos sentidos.

    Es la invariante que sostiene DB2: si alguien añade un ``LogicalType`` sin
    extender ``db_conventions.yaml`` (o al revés), el renderizador de DDL se
    quedaría sin traducción y esto lo detecta antes de generar nada.
    """
    del_enum = {t.value for t in LogicalType}
    del_yaml = set(load_db_conventions()["types"].keys())
    assert del_enum == del_yaml
    assert set(engine_type_map(engine)) == del_enum


def test_engine_cerrado_a_los_cuatro_motores():
    assert {e.value for e in DbEngine} == set(DB_ENGINES)
    data = example_artifact().model_dump(mode="json")
    data["target"]["engine"] = "sqlite"  # no está en el allow-list de la casa
    with pytest.raises(ValidationError):
        DatabaseArtifact.model_validate(data)


def test_type_fisico_es_opcional_hasta_que_lo_rellena_el_renderizador():
    """``type`` lo escribe DDL_GEN: antes de ese nodo la columna es válida sin él."""
    data = example_artifact().model_dump(mode="json")
    data["tables"][0]["columns"][0]["type"] = None
    art = DatabaseArtifact.model_validate(data)
    assert art.tables[0].columns[0].type is None
    # Pero el tipo lógico nunca falta.
    assert art.tables[0].columns[0].logical_type in set(LogicalType)


def test_logical_type_es_obligatorio():
    data = example_artifact().model_dump(mode="json")
    del data["tables"][0]["columns"][0]["logical_type"]
    with pytest.raises(ValidationError):
        DatabaseArtifact.model_validate(data)


# --- Trazabilidad y anti-invención ------------------------------------------


def test_toda_tabla_de_entidad_cita_su_entidad_del_EF():
    """`kind=entity` sin `entity_ref` sería una tabla inventada."""
    art = example_artifact()
    for table in art.tables:
        if table.kind is TableKind.ENTITY:
            assert table.entity_ref, f"{table.name} no cita entidad del EF"
        assert table.source_refs, f"{table.name} sin source_refs"


def test_catalogo_no_finge_ser_entidad_del_EF():
    """Un catálogo derivado declara su naturaleza en vez de inventar un ENT-."""
    art = example_artifact()
    catalogos = [t for t in art.tables if t.kind is TableKind.CATALOG]
    assert catalogos
    for table in catalogos:
        assert table.entity_ref is None


def test_toda_columna_tiene_trazabilidad_o_es_derivada():
    """Una columna sin `field_ref` debe declararse `derived` (nunca `stated`)."""
    from ai.agents.bd.schemas import Origin

    for table in example_artifact().tables:
        for col in table.columns:
            if col.field_ref is None:
                assert (
                    col.origin is not Origin.STATED
                ), f"{table.name}.{col.name} dice venir del EF sin citar campo"


def test_indice_sin_rationale_no_valida():
    """La regla «no hay índices por si acaso» está en el contrato, no solo en el prompt."""
    data = example_artifact().model_dump(mode="json")
    del data["tables"][1]["indexes"][0]["rationale"]
    with pytest.raises(ValidationError):
        DatabaseArtifact.model_validate(data)


def test_regla_no_declarativa_queda_registrada_con_su_destino():
    """VAL-001 no es expresable como CHECK: aparece en rule_mappings, no desaparece."""
    art = example_artifact()
    mapping = {m.rule_ref: m for m in art.rule_mappings}
    assert "VAL-001" in mapping
    assert mapping["VAL-001"].enforcement is RuleEnforcement.APPLICATION
    assert mapping["VAL-001"].note
    # Y la cobertura la reporta como no aplicada en el esquema (nunca la oculta).
    assert "VAL-001" in art.analysis.coverage.unenforced_validation_refs
    # Con su observación correspondiente (descartes nunca silenciosos).
    assert any("VAL-001" in o.description for o in art.analysis.observations)


# --- Claves, constraints e índices ------------------------------------------


def test_columnas_de_clave_no_pueden_estar_vacias():
    """Una PK/FK/índice sin columnas es un objeto imposible de renderizar."""
    data = example_artifact().model_dump(mode="json")
    data["tables"][0]["primary_key"]["columns"] = []
    with pytest.raises(ValidationError):
        DatabaseArtifact.model_validate(data)


def test_fk_declara_tabla_y_columnas_destino():
    art = example_artifact()
    fks = [fk for t in art.tables for fk in t.foreign_keys]
    assert fks
    for fk in fks:
        assert fk.references_table and fk.references_columns
        assert fk.rationale, f"{fk.name} sin justificación"


def test_clave_natural_se_preserva_como_unique():
    """La PK subrogada no puede perder la regla de negocio: queda como UNIQUE."""
    guias = next(t for t in example_artifact().tables if t.name == "guias")
    assert guias.primary_key is not None
    assert guias.primary_key.strategy is PrimaryKeyStrategy.SURROGATE
    assert any("numero" in uq.columns for uq in guias.unique_constraints)


def test_confidence_fuera_de_rango_falla():
    data = example_artifact().model_dump(mode="json")
    data["tables"][0]["confidence"] = 1.5
    with pytest.raises(ValidationError):
        DatabaseArtifact.model_validate(data)


def test_longitudes_negativas_no_validan():
    data = example_artifact().model_dump(mode="json")
    data["tables"][0]["columns"][1]["length"] = 0
    with pytest.raises(ValidationError):
        DatabaseArtifact.model_validate(data)


def test_escala_cero_es_valida_pero_precision_cero_no():
    """`DECIMAL(10,0)` es legítimo; precisión 0 no existe."""
    data = example_artifact().model_dump(mode="json")
    col = next(c for c in data["tables"][1]["columns"] if c["name"] == "monto")
    col["scale"] = 0
    DatabaseArtifact.model_validate(data)  # no lanza
    col["precision"] = 0
    with pytest.raises(ValidationError):
        DatabaseArtifact.model_validate(data)


# --- Validación del DDL y semáforo ------------------------------------------


def test_validacion_distingue_parseado_de_ejecutado():
    """`executed=False` con `syntax_ok=True`: parseado no es certificado."""
    art = example_artifact()
    assert art.validation.syntax_ok is True
    assert art.validation.executed is False
    assert art.validation.validator
    assert art.validation.checks
    assert art.validation.errors == []


def test_ddl_valid_por_defecto_es_falso():
    """El semáforo nace en rojo: hay que demostrar que el DDL es válido."""
    from ai.agents.bd.schemas import DatabaseMetrics, DdlValidation

    assert DatabaseMetrics().ddl_valid is False
    assert DdlValidation().syntax_ok is False


def test_motor_no_decidido_se_declara_en_el_artefacto():
    """Un fallback de motor queda visible (`engine_decided=False`), no camuflado."""
    data = example_artifact().model_dump(mode="json")
    data["target"]["engine_decided"] = False
    data["target"]["engine_source_ref"] = None
    art = DatabaseArtifact.model_validate(data)
    assert art.target.engine_decided is False


def test_ddl_scripts_ordenados_y_con_dialecto():
    art = example_artifact()
    assert [s.order for s in art.ddl_scripts] == sorted(
        s.order for s in art.ddl_scripts
    )
    for script in art.ddl_scripts:
        assert script.engine is art.target.engine
        assert script.statements and script.sql


def test_semilla_solo_con_evidencia_del_EF():
    """Los valores de un catálogo se citan; no se inventan."""
    for seed in example_artifact().seed_data:
        assert seed.rows
        assert seed.source_refs
        assert seed.evidence, f"{seed.table} trae filas sin evidencia del EF"


def test_diccionario_es_derivable_de_las_tablas():
    """Cada fila del diccionario apunta a una columna que existe de verdad."""
    art = example_artifact()
    reales = {(t.name, c.name) for t in art.tables for c in t.columns}
    for entry in art.data_dictionary:
        assert (entry.table, entry.column) in reales


def test_er_diagram_es_mermaid():
    art = example_artifact()
    assert art.er_diagram.format.value == "mermaid"
    assert art.er_diagram.code.startswith("erDiagram")


def test_desnormalizacion_por_defecto_desactivada():
    """Nadie desnormaliza por accidente: hay que declararlo explícitamente."""
    for table in example_artifact().tables:
        assert table.normalization.denormalized is False
