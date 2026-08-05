"""Tests de TABLES y RELATIONS (BD3), con LLM mockeado.

El mock (``BdMapLLM``) responde **mal a propósito**: inventa una columna, cambia
tipos que el EF declara y propone un ``cascade`` sin base. Los tests comprueban
que el agente lo corrige y deja rastro, que es lo que distingue una salvaguarda
real de una intención escrita en el prompt.
"""

import pytest

from ai.agents.arquitectura.schemas.examples import (
    example_artifact as arquitectura_example,
)
from ai.agents.bd.load_sources import extract_sources
from ai.agents.bd.model_map import build_model_map
from ai.agents.bd.relations import apply_relations, run_relations
from ai.agents.bd.schemas.artifact import Table
from ai.agents.bd.schemas.enums import (
    LogicalType,
    PrimaryKeyStrategy,
    ReferentialAction,
    TableKind,
)
from ai.agents.bd.tables import build_table, build_tables_user, run_tables
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.orchestrator import build_bd_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from tests.mocks import BdMapLLM

ENGINE = "postgresql"


def _sources(**overrides):
    sources = extract_sources(
        ef_example().model_dump(mode="json"),
        arquitectura_example().model_dump(mode="json"),
        None,
    )
    for key, value in overrides.items():
        sources[key] = value
    return sources


def _mapa(sources=None):
    return build_model_map(sources or _sources(), ENGINE)


async def _corre_tables(sources=None):
    sources = sources or _sources()
    return await run_tables(BdMapLLM(), _mapa(sources), sources, ENGINE)


# --- TABLES -----------------------------------------------------------------


async def test_una_tabla_por_entidad_con_pk_subrogada():
    tables, _, skipped, tokens = await _corre_tables()
    assert skipped == []
    assert [t["name"] for t in tables] == ["siniestros", "guias"]
    for table in tables:
        pk = table["primary_key"]
        assert pk["strategy"] == PrimaryKeyStrategy.SURROGATE.value
        assert pk["name"] == f"pk_{table['name']}"
        # La columna de PK existe, es la primera y la genera el motor.
        primera = table["columns"][0]
        assert primera["is_primary_key"] is True
        assert primera["is_generated"] is True
        assert primera["nullable"] is False
        assert primera["ordinal"] == 1
    assert tokens["total"] > 0


async def test_columna_inventada_por_el_LLM_se_descarta_con_observacion():
    """`campo_fantasma` no está en el EF: no entra al esquema, pero se reporta."""
    tables, observations, _, _ = await _corre_tables()
    todas = {c["name"] for t in tables for c in t["columns"]}
    assert "campo_fantasma" not in todas

    descartes = [o for o in observations if "campo_fantasma" in o["description"]]
    assert descartes, "el descarte no puede ser silencioso"
    assert "anti-invención" in descartes[0]["reason"]


async def test_el_tipo_declarado_en_el_EF_gana_al_del_modelo():
    """El mock pide `text` para todo; `fecha_siniestro` es `date` declarado en el EF."""
    tables, observations, _, _ = await _corre_tables()
    siniestros = next(t for t in tables if t["name"] == "siniestros")
    por_nombre = {c["name"]: c for c in siniestros["columns"]}

    assert por_nombre["fecha_siniestro"]["logical_type"] == LogicalType.DATE.value
    assert por_nombre["numero_guia"]["logical_type"] == LogicalType.STRING.value
    # Y la corrección queda registrada.
    correcciones = [o for o in observations if "tipo declarado" in o["description"]]
    assert correcciones


async def test_el_modelo_completa_descripcion_y_ejemplo():
    """Lo que sí es su trabajo: la prosa que alimenta el diccionario de datos."""
    tables, _, _, _ = await _corre_tables()
    siniestros = next(t for t in tables if t["name"] == "siniestros")
    assert siniestros["description"]
    del_ef = [c for c in siniestros["columns"] if c["field_ref"]]
    assert all(c["description"] for c in del_ef)
    assert all(c["example"] for c in del_ef)


async def test_coherencia_entre_tipo_y_parametros():
    """Un DATE no lleva longitud; un STRING sí; un DECIMAL lleva precisión."""
    tables, _, _, _ = await _corre_tables()
    for table in tables:
        for col in table["columns"]:
            if col["logical_type"] == LogicalType.DATE.value:
                assert col["length"] is None and col["precision"] is None
            if col["logical_type"] == LogicalType.STRING.value:
                assert col["length"]
            if col["logical_type"] == LogicalType.DECIMAL.value:
                assert col["precision"] and col["scale"] is not None


async def test_las_tablas_resultantes_validan_contra_el_contrato():
    """Lo que produce el nodo debe ser un `Table` v1.0.0 válido, no un dict libre."""
    tables, _, _, _ = await _corre_tables()
    for table in tables:
        Table.model_validate(table)


def test_una_tabla_sin_respuesta_del_LLM_se_construye_igual():
    """Perder una entidad del EF por un fallo del modelo sería peor que no tener prosa."""
    candidate = _mapa()["tables"][0]
    table, notas = build_table(candidate, None, ENGINE)
    assert table["name"] == candidate["name"]
    assert table["primary_key"]["strategy"] == PrimaryKeyStrategy.SURROGATE.value
    # Las columnas del EF siguen ahí, con su tipo pre-normalizado.
    assert {c["name"] for c in table["columns"]} == {candidate["pk_column"]} | {
        c["name"] for c in candidate["columns"]
    }
    assert notas == []


def test_pk_natural_propuesta_reemplaza_la_subrogada():
    """Si el modelo elige una clave natural, la subrogada desaparece (no sobran ids)."""
    candidate = _mapa()["tables"][0]
    natural = candidate["columns"][0]["name"]
    table, _ = build_table(
        candidate,
        {
            "description": "…",
            "primary_key": {
                "columns": [natural],
                "strategy": "natural",
                "rationale": "Clave de negocio estable.",
            },
            "columns": [],
        },
        ENGINE,
    )
    assert table["primary_key"]["columns"] == [natural]
    assert table["primary_key"]["strategy"] == PrimaryKeyStrategy.NATURAL.value
    assert candidate["pk_column"] not in {c["name"] for c in table["columns"]}
    # La columna de la PK natural queda NOT NULL y marcada.
    col = next(c for c in table["columns"] if c["name"] == natural)
    assert col["is_primary_key"] is True and col["nullable"] is False
    # Los ordinales se renumeran sin huecos.
    assert [c["ordinal"] for c in table["columns"]] == list(
        range(1, len(table["columns"]) + 1)
    )


def test_pk_que_cita_columnas_inexistentes_se_ignora():
    candidate = _mapa()["tables"][0]
    table, notas = build_table(
        candidate,
        {
            "primary_key": {"columns": ["no_existe"], "strategy": "natural"},
            "columns": [],
        },
        ENGINE,
    )
    assert table["primary_key"]["columns"] == [candidate["pk_column"]]
    assert any("clave primaria propuesta" in n["description"] for n in notas)


def test_el_prompt_de_una_tabla_no_filtra_otras():
    """Cada llamada del map ve SOLO su tabla: prompts pequeños y sin contaminación."""
    mapa = _mapa()
    user = build_tables_user(mapa["tables"][0], _sources())
    assert "siniestros" in user
    assert "guias" not in user


def test_el_prompt_lleva_el_contexto_del_EF_de_esa_tabla():
    user = build_tables_user(_mapa()["tables"][0], _sources())
    assert "FLD-001" in user  # campos de la entidad
    assert "BR-001" in user  # reglas que ayudan a tipar


async def test_tabla_puente_no_pasa_por_el_LLM():
    """Su forma la dicta la relación: PK compuesta por las dos FK."""
    sources = _sources()
    sources["ef"]["relationships"] = [
        {
            "id": "REL-002",
            "source_entity_ref": "ENT-001",
            "target_entity_ref": "ENT-002",
            "cardinality": "N:M",
        }
    ]
    tables, _, _, _ = await run_tables(BdMapLLM(), _mapa(sources), sources, ENGINE)
    puente = next(t for t in tables if t["kind"] == TableKind.JUNCTION.value)
    assert puente["name"] == "guias_siniestros"
    assert puente["primary_key"]["strategy"] == PrimaryKeyStrategy.COMPOSITE.value
    assert puente["primary_key"]["columns"] == ["guia_id", "siniestro_id"]
    assert all(c["is_primary_key"] for c in puente["columns"])
    Table.model_validate(puente)


# --- RELATIONS --------------------------------------------------------------


async def _corre_relations(sources=None):
    sources = sources or _sources()
    mapa = _mapa(sources)
    tables, _, _, _ = await run_tables(BdMapLLM(), mapa, sources, ENGINE)
    return await run_relations(BdMapLLM(), tables, mapa, sources, ENGINE)


async def test_fk_de_relacion_1_a_N_se_materializa_en_el_lado_N():
    tables, _, skipped, _ = await _corre_relations()
    assert skipped == []
    siniestros = next(t for t in tables if t["name"] == "siniestros")
    guias = next(t for t in tables if t["name"] == "guias")

    assert len(siniestros["foreign_keys"]) == 1
    assert guias["foreign_keys"] == []
    fk = siniestros["foreign_keys"][0]
    assert fk["id"] == "FK-001"
    assert fk["name"] == "fk_siniestros_guias"
    assert fk["columns"] == ["guia_id"]
    assert fk["references_table"] == "guias"
    assert fk["references_columns"] == ["guia_id"]
    assert fk["relationship_ref"] == "REL-001"
    assert "REL-001" in fk["source_refs"]


async def test_cascade_sin_regla_del_EF_se_degrada_a_restrict():
    """El mock pide `cascade` sin `source_refs`: el borrado en cascada no entra así."""
    tables, observations, _, _ = await _corre_relations()
    fk = next(t for t in tables if t["name"] == "siniestros")["foreign_keys"][0]
    assert fk["on_delete"] == ReferentialAction.RESTRICT.value
    rechazos = [o for o in observations if "CASCADE" in o["description"]]
    assert rechazos
    assert "destruye datos" in rechazos[0]["reason"]


def test_cascade_con_regla_citada_si_se_acepta():
    """Con base explícita en una regla del EF, la cascada es una decisión legítima."""
    sources = _sources()
    mapa = _mapa(sources)
    tables = [
        {
            "id": t["id"],
            "name": t["name"],
            "columns": [{"name": t["pk_column"], "is_primary_key": True, "ordinal": 1}],
            "foreign_keys": [],
        }
        for t in mapa["tables"]
    ]
    extracted = {
        "one_to_one": [],
        "referential_actions": [
            {
                "relationship_ref": "REL-001",
                "on_delete": "cascade",
                "rationale": "Un siniestro no existe sin su guía (BR-001).",
                "source_refs": ["BR-001"],
                "confidence": 0.8,
            }
        ],
    }
    tables, notas = apply_relations(tables, mapa, extracted, sources, ENGINE)
    fk = next(t for t in tables if t["name"] == "siniestros")["foreign_keys"][0]
    assert fk["on_delete"] == ReferentialAction.CASCADE.value
    assert "BR-001" in fk["source_refs"]
    assert notas == []


async def test_columna_de_FK_ya_declarada_en_el_EF_no_se_duplica():
    """Si el EF ya trae el campo de la FK, se reutiliza y se fuerza NOT NULL."""
    sources = _sources()
    sources["ef"]["fields"] = sources["ef"]["fields"] + [
        {
            "id": "FLD-050",
            "name": "guia_id",
            "entity_ref": "ENT-001",
            "data_type": "entero",
            "required": False,
        }
    ]
    tables, _, _, _ = await _corre_relations(sources)
    siniestros = next(t for t in tables if t["name"] == "siniestros")
    columnas = [c["name"] for c in siniestros["columns"]]
    assert columnas.count("guia_id") == 1
    # La FK exige obligatoriedad aunque el EF dijera que el campo era opcional.
    guia_id = next(c for c in siniestros["columns"] if c["name"] == "guia_id")
    assert guia_id["nullable"] is False


async def test_relacion_1_a_1_usa_el_lado_que_decide_el_LLM():
    sources = _sources()
    sources["ef"]["relationships"] = [
        {
            "id": "REL-004",
            "source_entity_ref": "ENT-001",
            "target_entity_ref": "ENT-002",
            "cardinality": "1:1",
            "name": "un siniestro tiene una guía",
        }
    ]
    tables, _, _, _ = await _corre_relations(sources)
    # `candidates` conserva el orden source→target del EF (siniestros, guias) y el
    # mock elige el último: `guias` es el lado dueño, así que la FK vive ahí.
    guias = next(t for t in tables if t["name"] == "guias")
    siniestros = next(t for t in tables if t["name"] == "siniestros")
    assert [fk["references_table"] for fk in guias["foreign_keys"]] == ["siniestros"]
    assert siniestros["foreign_keys"] == []
    # La columna de la FK se añadió al lado dueño.
    assert "siniestro_id" in {c["name"] for c in guias["columns"]}


def test_relacion_1_a_1_sin_dueño_claro_no_se_materializa():
    """Modelar el lado equivocado es peor que dejarlo para el DBA."""
    sources = _sources()
    sources["ef"]["relationships"] = [
        {
            "id": "REL-004",
            "source_entity_ref": "ENT-001",
            "target_entity_ref": "ENT-002",
            "cardinality": "1:1",
        }
    ]
    mapa = _mapa(sources)
    tables = [
        {
            "id": t["id"],
            "name": t["name"],
            "columns": [{"name": t["pk_column"], "is_primary_key": True, "ordinal": 1}],
            "foreign_keys": [],
        }
        for t in mapa["tables"]
    ]
    # `owner: null` = el modelo reconoce que no hay un lado dependiente.
    extracted = {
        "one_to_one": [{"relationship_ref": "REL-004", "owner": None}],
        "referential_actions": [],
    }
    tables, notas = apply_relations(tables, mapa, extracted, sources, ENGINE)
    assert all(t["foreign_keys"] == [] for t in tables)
    assert any("sin materializar" in n["description"] for n in notas)


def test_dueño_inventado_en_una_1_a_1_se_rechaza():
    """Un `owner` que no es ninguno de los dos candidatos no crea nada."""
    sources = _sources()
    sources["ef"]["relationships"] = [
        {
            "id": "REL-004",
            "source_entity_ref": "ENT-001",
            "target_entity_ref": "ENT-002",
            "cardinality": "1:1",
        }
    ]
    mapa = _mapa(sources)
    tables = [
        {
            "id": t["id"],
            "name": t["name"],
            "columns": [{"name": t["pk_column"], "is_primary_key": True, "ordinal": 1}],
            "foreign_keys": [],
        }
        for t in mapa["tables"]
    ]
    extracted = {
        "one_to_one": [{"relationship_ref": "REL-004", "owner": "tabla_inexistente"}],
        "referential_actions": [],
    }
    tables, notas = apply_relations(tables, mapa, extracted, sources, ENGINE)
    assert all(t["foreign_keys"] == [] for t in tables)
    assert any("sin materializar" in n["description"] for n in notas)


async def test_tabla_puente_recibe_sus_dos_FK():
    sources = _sources()
    sources["ef"]["relationships"] = [
        {
            "id": "REL-002",
            "source_entity_ref": "ENT-001",
            "target_entity_ref": "ENT-002",
            "cardinality": "N:M",
        }
    ]
    tables, _, _, _ = await _corre_relations(sources)
    puente = next(t for t in tables if t["kind"] == TableKind.JUNCTION.value)
    assert len(puente["foreign_keys"]) == 2
    assert {fk["references_table"] for fk in puente["foreign_keys"]} == {
        "guias",
        "siniestros",
    }
    assert all(
        fk["on_delete"] == ReferentialAction.RESTRICT.value
        for fk in puente["foreign_keys"]
    )


async def test_sin_relaciones_no_se_llama_al_LLM():
    """Sin nada que decidir no se gasta un token."""

    class BoomLLM:
        async def complete_json(self, *, system, user):
            raise AssertionError("no debería llamarse al LLM sin relaciones")

    sources = _sources()
    sources["ef"]["relationships"] = []
    mapa = _mapa(sources)
    tables, _, _, _ = await run_tables(BdMapLLM(), mapa, sources, ENGINE)
    tables, notas, skipped, tokens = await run_relations(
        BoomLLM(), tables, mapa, sources, ENGINE
    )
    assert tokens["total"] == 0
    assert skipped == []


async def test_fk_irreparable_del_LLM_no_tumba_las_deterministas():
    """Si RELATIONS cae a cuarentena, las FK de 1:N se aplican igual."""

    class BrokenLLM:
        async def complete_json(self, *, system, user):
            return "{ no es json"

    sources = _sources()
    mapa = _mapa(sources)
    tables, _, _, _ = await run_tables(BdMapLLM(), mapa, sources, ENGINE)
    tables, _, skipped, _ = await run_relations(
        BrokenLLM(), tables, mapa, sources, ENGINE
    )
    assert skipped and skipped[0]["stage"] == "RELATIONS"
    siniestros = next(t for t in tables if t["name"] == "siniestros")
    assert len(siniestros["foreign_keys"]) == 1
    assert siniestros["foreign_keys"][0]["on_delete"] == (
        ReferentialAction.RESTRICT.value
    )


# --- Integración en el grafo ------------------------------------------------


async def _noop_persist(job_id, artifact, status, metrics):
    return None


async def test_grafo_produce_tablas_y_relaciones():
    graph = build_bd_graph(build_memory_checkpointer())
    state = {
        "job_id": "BD-1",
        "architecture_job_id": "AR-1",
        "architecture_artifact": arquitectura_example().model_dump(mode="json"),
        "architecture_artifact_hash": "ar123",
        "architecture_ready": True,
        "ef_job_id": "EF-1",
        "ef_artifact": ef_example().model_dump(mode="json"),
        "ef_artifact_hash": "ef123",
    }
    config = {
        "configurable": {
            "thread_id": "BD-1",
            "llm": BdMapLLM(),
            "persist": _noop_persist,
        }
    }
    result = await graph.ainvoke(state, config)

    art = result["artifact"]
    assert [t["name"] for t in art["tables"]] == ["siniestros", "guias"]
    assert art["metrics"]["tables_total"] == 2
    assert art["metrics"]["columns_total"] > 0
    # PK de cada tabla + la FK de REL-001.
    assert art["metrics"]["constraints_total"] == 3
    # Las correcciones sobre el LLM viajan como observaciones al artefacto.
    descripciones = " ".join(o["description"] for o in art["analysis"]["observations"])
    assert "campo_fantasma" in descripciones
    assert "CASCADE" in descripciones
    # El motor sigue siendo el que decidió la arquitectura.
    assert art["target"]["engine"] == "sqlserver"
    assert result["status"] == "COMPLETED"


@pytest.mark.parametrize("engine", ["postgresql", "sqlserver", "oracle", "mysql"])
async def test_los_nombres_respetan_el_limite_de_cada_motor(engine: str):
    """Con nombres de entidad largos, ningún identificador excede el límite."""
    from ai.knowledge import max_identifier_length

    sources = _sources()
    sources["ef"]["entities"] = [
        {
            "id": "ENT-001",
            "name": "Seguimiento Operativo Detallado de Siniestros Logisticos",
            "origin": "stated",
        },
        {
            "id": "ENT-002",
            "name": "Documento de Envio Consolidado Internacional",
            "origin": "stated",
        },
    ]
    sources["ef"]["relationships"] = [
        {
            "id": "REL-001",
            "source_entity_ref": "ENT-002",
            "target_entity_ref": "ENT-001",
            "cardinality": "1:N",
        }
    ]
    mapa = build_model_map(sources, engine)
    tables, _, _, _ = await run_tables(BdMapLLM(), mapa, sources, engine)
    tables, _, _, _ = await run_relations(BdMapLLM(), tables, mapa, sources, engine)

    limite = max_identifier_length(engine)
    for table in tables:
        assert len(table["primary_key"]["name"]) <= limite
        for fk in table["foreign_keys"]:
            assert len(fk["name"]) <= limite
