"""Tests del conocimiento inyectable: glosario (EF), stack de la casa (A0) y
convenciones de base de datos (BD0)."""

import re

import pytest

from ai.knowledge import (
    DB_ENGINES,
    db_conventions_block,
    default_schema,
    engine_type_map,
    glossary_block,
    identity_clause,
    load_db_conventions,
    load_glossary,
    load_tech_stack,
    max_identifier_length,
    tech_stack_block,
    type_synonyms,
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


# --- Convenciones de base de datos (BD0) ------------------------------------


def test_db_conventions_carga_y_marca_pendiente_de_validacion():
    """Nace explícitamente pendiente de validación, igual que el tech stack."""
    data = load_db_conventions()
    assert data.get("status") == "pendiente_de_validacion"
    assert data.get("version") == 0
    for bloque in ("naming", "keys", "audit", "catalogs", "defaults", "types"):
        assert data.get(bloque), f"falta el bloque {bloque}"


def test_los_motores_del_mapa_de_tipos_son_los_del_tech_stack():
    """El mapa de tipos cubre exactamente los motores del allow-list de A5.

    Si alguien añade un motor a `tech_stack.yaml` sin extender el mapa de tipos,
    el renderizador de DDL no sabría traducir y este test lo delata.
    """
    permitidos = load_tech_stack()["layers"]["database_relational"]["allowed"]
    # El allow-list usa nombres de producto ("SQL Server"); el mapa, claves.
    normalizados = {p.lower().replace(" ", "") for p in permitidos}
    esperados = {"sqlserver", "oracle", "postgresql", "mysql"}
    assert normalizados == esperados
    assert set(DB_ENGINES) == esperados


@pytest.mark.parametrize("engine", DB_ENGINES)
def test_todo_logical_type_se_traduce_en_todos_los_motores(engine: str):
    """Ningún `logical_type` puede quedarse sin tipo físico en un motor.

    Es la invariante que sostiene el diseño DB2 (el LLM elige un tipo lógico y
    Python lo traduce): un hueco aquí sería un DDL imposible de generar.
    """
    logicos = set(load_db_conventions()["types"].keys())
    mapa = engine_type_map(engine)
    assert set(mapa) == logicos
    assert all(valor for valor in mapa.values())


@pytest.mark.parametrize("engine", DB_ENGINES)
def test_cada_motor_tiene_identidad_y_limite_de_identificador(engine: str):
    """Datos que el renderizador necesita SIEMPRE (PK autoincremental, truncado)."""
    assert identity_clause(engine)
    assert max_identifier_length(engine) >= 30


def test_esquema_por_defecto_solo_donde_aplica():
    """Postgres/SQL Server tienen esquema; Oracle y MySQL no lo prefijan."""
    assert default_schema("postgresql") == "public"
    assert default_schema("sqlserver") == "dbo"
    assert default_schema("oracle") == ""
    assert default_schema("mysql") == ""


def test_placeholders_de_tipo_solo_usan_claves_conocidas():
    """Los tipos parametrizados solo admiten {length}/{precision}/{scale}."""
    permitidos = {"length", "precision", "scale"}
    for logical, per_engine in load_db_conventions()["types"].items():
        for engine, plantilla in per_engine.items():
            usados = set(re.findall(r"\{(\w+)\}", plantilla))
            assert usados <= permitidos, f"{logical}/{engine} usa {usados - permitidos}"


def test_sinonimos_de_tipo_apuntan_a_logical_types_reales():
    """Un sinónimo que apunte a un tipo inexistente rompería MODEL_MAP."""
    logicos = set(load_db_conventions()["types"].keys())
    assert set(type_synonyms()) <= logicos
    # Y los términos del EF que sí sabemos que aparecen están cubiertos.
    todos = {palabra for palabras in type_synonyms().values() for palabra in palabras}
    for termino in ("texto", "fecha", "monto", "booleano", "entero"):
        assert termino in todos


def test_db_conventions_block_no_filtra_tipos_sql_al_prompt():
    """El prompt recibe tipos LÓGICOS; jamás sintaxis SQL de un motor.

    Es la salvaguarda de DB2: si el bloque inyectara `NVARCHAR(MAX)`, el modelo
    podría copiarlo y colar sintaxis de SQL Server en un script de Postgres.
    """
    block = db_conventions_block("postgresql")
    assert "postgresql" in block
    assert "TIPOS LÓGICOS ADMITIDOS" in block
    assert "string" in block and "timestamp" in block
    for sintaxis in ("NVARCHAR", "VARCHAR2", "JSONB", "IDENTITY(1,1)", "BYTEA"):
        assert sintaxis not in block
    # Comunica la regla dura de no adivinar tipos.
    assert "PROHIBIDO adivinar" in block
