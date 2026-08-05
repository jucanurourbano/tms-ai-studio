"""Tests de CONSTRAINTS, INDEXES y CATALOGS (BD4), con LLM mockeado.

El mock propone a propósito lo que **no** debe pasar el filtro: un CHECK con
``CURRENT_DATE`` (no determinista), un índice sin justificación, uno sobre una tabla
inexistente y un catálogo sin evidencia. Cada test comprueba que el agente lo
rechaza *y* deja constancia.
"""

import pytest

from ai.agents.arquitectura.schemas.examples import (
    example_artifact as arquitectura_example,
)
from ai.agents.bd.catalogs import (
    apply_catalogs,
    detect_catalog_candidates,
    run_catalogs,
)
from ai.agents.bd.constraints import (
    add_missing_rule_mappings,
    apply_constraints,
    rules_for_table,
    run_constraints,
)
from ai.agents.bd.expressions import (
    REASON_FUNCTION,
    REASON_MULTIPLE_STATEMENTS,
    REASON_NO_COLUMN,
    REASON_NON_DETERMINISTIC,
    REASON_SUBQUERY,
    REASON_UNKNOWN_COLUMN,
    validate_check_expression,
)
from ai.agents.bd.indexes import build_fk_indexes, run_indexes, valid_access_refs
from ai.agents.bd.load_sources import extract_sources
from ai.agents.bd.model_map import build_model_map
from ai.agents.bd.relations import run_relations
from ai.agents.bd.schemas.artifact import SeedData, Table
from ai.agents.bd.schemas.enums import RuleEnforcement, TableKind
from ai.agents.bd.tables import run_tables
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


async def _modelo(sources=None):
    """Tablas tras TABLES + RELATIONS (la entrada real de BD4)."""
    sources = sources or _sources()
    mapa = build_model_map(sources, ENGINE)
    tables, _, _, _ = await run_tables(BdMapLLM(), mapa, sources, ENGINE)
    tables, _, _, _ = await run_relations(BdMapLLM(), tables, mapa, sources, ENGINE)
    return tables, sources


# --- Validación de expresiones CHECK ----------------------------------------

_COLUMNAS = {"monto", "fecha_siniestro", "estado", "nombre"}


@pytest.mark.parametrize(
    "expresion",
    [
        "monto >= 0",
        "monto > 0 AND monto < 1000000",
        "estado IN ('REGISTRADO', 'CERRADO')",
        "monto BETWEEN 0 AND 500",
        "nombre IS NOT NULL",
        "NOT (monto < 0)",
        "nombre LIKE 'URB-%'",
    ],
)
def test_expresiones_validas_se_aceptan(expresion: str):
    verdict = validate_check_expression(expresion, _COLUMNAS, ENGINE)
    assert verdict.ok, f"{expresion} debería aceptarse ({verdict.reason})"


@pytest.mark.parametrize(
    "expresion,motivo",
    [
        # El caso realista del dominio: «la fecha no puede ser futura».
        ("fecha_siniestro <= CURRENT_DATE", REASON_NON_DETERMINISTIC),
        ("fecha_siniestro < NOW()", REASON_NON_DETERMINISTIC),
        ("fecha_siniestro <= GETDATE()", REASON_FUNCTION),
        ("monto > (SELECT AVG(monto) FROM siniestros)", REASON_SUBQUERY),
        ("UPPER(nombre) = 'X'", REASON_FUNCTION),
        ("LENGTH(nombre) > 3", REASON_FUNCTION),
        ("monto >= 0; DROP TABLE siniestros", REASON_MULTIPLE_STATEMENTS),
        ("monto >= columna_inexistente", REASON_UNKNOWN_COLUMN),
        ("1 = 1", REASON_NO_COLUMN),
    ],
)
def test_expresiones_invalidas_se_rechazan_con_motivo(expresion: str, motivo: str):
    verdict = validate_check_expression(expresion, _COLUMNAS, ENGINE)
    assert not verdict.ok
    assert verdict.reason == motivo, f"{expresion}: {verdict.reason} != {motivo}"


def test_expresion_vacia_se_rechaza():
    assert not validate_check_expression("", _COLUMNAS, ENGINE).ok
    assert not validate_check_expression("   ", _COLUMNAS, ENGINE).ok


@pytest.mark.parametrize("engine", ["postgresql", "sqlserver", "oracle", "mysql"])
def test_la_validacion_funciona_en_los_cuatro_dialectos(engine: str):
    assert validate_check_expression("monto >= 0", _COLUMNAS, engine).ok
    assert not validate_check_expression("monto > (SELECT 1)", _COLUMNAS, engine).ok


# --- CONSTRAINTS ------------------------------------------------------------


async def test_check_temporal_se_rechaza_y_la_regla_pasa_a_aplicacion():
    """VAL-001 («fecha no futura») no cabe en el esquema: se reclasifica, no se pierde."""
    tables, sources = await _modelo()
    tables, mappings, observations, skipped, _ = await run_constraints(
        BdMapLLM(), tables, sources, ENGINE
    )
    assert skipped == []

    siniestros = next(t for t in tables if t["name"] == "siniestros")
    expresiones = [ck["expression"] for ck in siniestros["check_constraints"]]
    assert not any("CURRENT_DATE" in e for e in expresiones)

    # El rechazo queda registrado con su motivo real.
    rechazos = [o for o in observations if "rechazado" in o["description"]]
    assert rechazos
    assert "no es determinista" in rechazos[0]["reason"]

    # Y la regla acaba como `application`, no desaparecida.
    val = next(m for m in mappings if m["rule_ref"] == "VAL-001")
    assert val["enforcement"] == RuleEnforcement.APPLICATION.value
    assert "Reclasificada" in val["note"]


async def test_check_valido_entra_con_nombre_de_la_casa():
    """Con una columna numérica de negocio, el CHECK legítimo sí se crea."""
    sources = _sources()
    sources["ef"]["fields"] = sources["ef"]["fields"] + [
        {
            "id": "FLD-020",
            "name": "monto",
            "entity_ref": "ENT-001",
            "data_type": "decimal",
            "required": False,
        }
    ]
    tables, sources = await _modelo(sources)
    tables, _, _, _, _ = await run_constraints(BdMapLLM(), tables, sources, ENGINE)
    checks = [ck for t in tables for ck in t["check_constraints"]]
    assert checks
    assert any("monto" in ck["expression"] for ck in checks)
    for ck in checks:
        assert ck["name"].startswith("ck_")
        assert ck["id"].startswith("CK-")
        assert ck["source_refs"]


async def test_unique_de_clave_natural_se_crea():
    tables, sources = await _modelo()
    tables, _, _, _, _ = await run_constraints(BdMapLLM(), tables, sources, ENGINE)
    uniques = [uq for t in tables for uq in t["unique_constraints"]]
    assert uniques
    for uq in uniques:
        assert uq["name"].startswith("uq_")
        assert uq["id"].startswith("UQ-")


def test_unique_redundante_con_la_pk_se_descarta():
    table = {
        "id": "TBL-001",
        "name": "guias",
        "columns": [{"name": "guia_id", "nullable": False, "is_primary_key": True}],
        "primary_key": {"columns": ["guia_id"]},
        "unique_constraints": [],
        "check_constraints": [],
        "foreign_keys": [],
    }
    _, notas = apply_constraints(
        table,
        {"unique_constraints": [{"columns": ["guia_id"]}]},
        ENGINE,
    )
    assert table["unique_constraints"] == []
    assert any("redundante" in n["description"] for n in notas)


def test_unique_sobre_columna_inexistente_se_descarta():
    table = {
        "id": "TBL-001",
        "name": "guias",
        "columns": [{"name": "guia_id", "nullable": False}],
        "primary_key": {"columns": ["guia_id"]},
        "unique_constraints": [],
        "check_constraints": [],
        "foreign_keys": [],
    }
    _, notas = apply_constraints(
        table, {"unique_constraints": [{"columns": ["fantasma"]}]}, ENGINE
    )
    assert table["unique_constraints"] == []
    assert any("no existen" in n["reason"] for n in notas)


def test_not_null_de_una_regla_endurece_la_columna():
    table = {
        "id": "TBL-001",
        "name": "siniestros",
        "columns": [
            {"name": "guia_id", "nullable": True, "source_refs": []},
        ],
        "primary_key": {"columns": []},
        "unique_constraints": [],
        "check_constraints": [],
        "foreign_keys": [],
    }
    apply_constraints(
        table,
        {"not_null_columns": [{"column": "guia_id", "source_refs": ["BR-001"]}]},
        ENGINE,
    )
    columna = table["columns"][0]
    assert columna["nullable"] is False
    assert "BR-001" in columna["source_refs"]


async def test_toda_regla_del_EF_acaba_con_un_destino():
    """La invariante central: ninguna BR-/VAL- del EF desaparece del artefacto."""
    tables, sources = await _modelo()
    _, mappings, _, _, _ = await run_constraints(BdMapLLM(), tables, sources, ENGINE)

    del_ef = {r["id"] for r in sources["ef"]["business_rules"]} | {
        v["id"] for v in sources["ef"]["validations"]
    }
    clasificadas = {m["rule_ref"] for m in mappings}
    assert del_ef <= clasificadas
    assert all(m["id"].startswith("RM-") for m in mappings)


def test_regla_que_nadie_clasifico_queda_pendiente_y_visible():
    sources = _sources()
    mappings, notas = add_missing_rule_mappings([], sources)
    refs = {m["rule_ref"] for m in mappings}
    assert "BR-001" in refs and "VAL-001" in refs
    for mapping in mappings:
        assert mapping["enforcement"] == RuleEnforcement.APPLICATION.value
        assert "Sin clasificar" in mapping["note"]
    assert len(notas) == len(mappings)


def test_reglas_de_una_tabla_se_ligan_por_field_ref():
    """A cada llamada solo le llegan las validaciones de SUS columnas."""
    sources = _sources()
    table = {
        "id": "TBL-001",
        "name": "siniestros",
        "columns": [
            {"name": "fecha_siniestro", "field_ref": "FLD-002"},
        ],
    }
    rules, validations = rules_for_table(table, sources)
    assert [v["id"] for v in validations] == ["VAL-001"]
    assert validations[0]["column"] == "fecha_siniestro"
    assert [r["id"] for r in rules] == ["BR-001"]


async def test_regla_declarativa_se_enlaza_con_su_constraint():
    tables, sources = await _modelo()
    _, mappings, _, _, _ = await run_constraints(BdMapLLM(), tables, sources, ENGINE)
    declarativas = [
        m for m in mappings if m["enforcement"] == RuleEnforcement.DECLARATIVE.value
    ]
    assert declarativas
    # Al menos una queda enlazada a la constraint concreta que la implementa.
    assert any(m["constraint_ref"] for m in declarativas)


# --- INDEXES ----------------------------------------------------------------


async def test_cada_fk_recibe_su_indice():
    tables, sources = await _modelo()
    creados = build_fk_indexes(tables, ENGINE)
    assert creados >= 1
    siniestros = next(t for t in tables if t["name"] == "siniestros")
    assert any(idx["columns"] == ["guia_id"] for idx in siniestros["indexes"])
    # Un índice estructural no necesita patrón de acceso, pero sí justificación.
    for idx in siniestros["indexes"]:
        assert idx["rationale"]


async def test_indice_sin_patron_de_acceso_se_descarta():
    tables, sources = await _modelo()
    tables, observations, skipped, _ = await run_indexes(
        BdMapLLM(), tables, sources, ENGINE
    )
    assert skipped == []
    descartes = [o for o in observations if "por si acaso" in (o["reason"] or "")]
    assert descartes, "un índice sin justificación no puede entrar en silencio"


async def test_indice_sobre_tabla_inexistente_se_descarta():
    tables, sources = await _modelo()
    _, observations, _, _ = await run_indexes(BdMapLLM(), tables, sources, ENGINE)
    assert any("no existe en el modelo" in (o["reason"] or "") for o in observations)


async def test_indice_justificado_conserva_su_trazabilidad():
    tables, sources = await _modelo()
    tables, _, _, _ = await run_indexes(BdMapLLM(), tables, sources, ENGINE)
    justificados = [
        idx for t in tables for idx in t["indexes"] if idx["access_pattern_refs"]
    ]
    assert justificados
    validos = valid_access_refs(sources)
    for idx in justificados:
        assert set(idx["access_pattern_refs"]) <= validos
        assert idx["id"].startswith("IDX-")


def test_indice_redundante_con_un_prefijo_existente_se_descarta():
    """`(estado_id)` sobra si ya hay `(estado_id, fecha)`: el motor usa el prefijo."""
    from ai.agents.bd.indexes import apply_proposed_indexes

    sources = _sources()
    tables = [
        {
            "id": "TBL-001",
            "name": "siniestros",
            "kind": TableKind.ENTITY.value,
            "columns": [{"name": "estado_id"}, {"name": "fecha"}],
            "primary_key": {"columns": []},
            "unique_constraints": [],
            "indexes": [
                {"columns": ["estado_id", "fecha"], "name": "ix_a", "id": "IDX-001"}
            ],
            "foreign_keys": [],
        }
    ]
    api = sources["ef"]["apis"][0]["id"]
    notas = apply_proposed_indexes(
        tables,
        {
            "indexes": [
                {
                    "table": "siniestros",
                    "columns": ["estado_id"],
                    "rationale": "…",
                    "access_pattern_refs": [api],
                }
            ]
        },
        sources,
        ENGINE,
        3,
    )
    assert len(tables[0]["indexes"]) == 1
    assert any("ya está cubierto" in n["reason"] for n in notas)


def test_el_tope_de_indices_no_es_un_recorte_silencioso():
    from ai.agents.bd.indexes import apply_proposed_indexes

    sources = _sources()
    api = sources["ef"]["apis"][0]["id"]
    tables = [
        {
            "id": "TBL-001",
            "name": "siniestros",
            "kind": TableKind.ENTITY.value,
            "columns": [{"name": f"c{i}"} for i in range(6)],
            "primary_key": {"columns": []},
            "unique_constraints": [],
            "indexes": [],
            "foreign_keys": [],
        }
    ]
    propuestas = {
        "indexes": [
            {
                "table": "siniestros",
                "columns": [f"c{i}"],
                "rationale": "…",
                "access_pattern_refs": [api],
            }
            for i in range(5)
        ]
    }
    notas = apply_proposed_indexes(tables, propuestas, sources, ENGINE, 2)
    assert len(tables[0]["indexes"]) == 2
    topes = [n for n in notas if "tope de 2" in (n["reason"] or "")]
    assert len(topes) == 3, "cada índice no creado debe quedar reportado"


def test_no_se_indexan_los_catalogos():
    from ai.agents.bd.indexes import apply_proposed_indexes

    sources = _sources()
    api = sources["ef"]["apis"][0]["id"]
    tables = [
        {
            "id": "TBL-003",
            "name": "siniestro_estados",
            "kind": TableKind.CATALOG.value,
            "columns": [{"name": "codigo"}],
            "primary_key": {"columns": []},
            "unique_constraints": [],
            "indexes": [],
            "foreign_keys": [],
        }
    ]
    notas = apply_proposed_indexes(
        tables,
        {
            "indexes": [
                {
                    "table": "siniestro_estados",
                    "columns": ["codigo"],
                    "rationale": "…",
                    "access_pattern_refs": [api],
                }
            ]
        },
        sources,
        ENGINE,
        3,
    )
    assert tables[0]["indexes"] == []
    assert any("pocas filas" in n["reason"] for n in notas)


# --- CATALOGS ---------------------------------------------------------------


async def test_catalogo_se_crea_con_semilla_citada():
    tables, sources = await _modelo()
    tables, seeds, observations, skipped, _ = await run_catalogs(
        BdMapLLM(), tables, sources, ENGINE
    )
    assert skipped == []

    catalogo = next(t for t in tables if t["kind"] == TableKind.CATALOG.value)
    assert catalogo["entity_ref"] is None
    assert catalogo["source_refs"]  # cita el proceso del EF
    Table.model_validate(catalogo)

    seed = next(s for s in seeds if s["table_ref"] == catalogo["id"])
    assert seed["rows"]
    assert seed["evidence"]  # cita textual, no invención
    assert seed["id"].startswith("SEED-")
    SeedData.model_validate(seed)


async def test_catalogo_sin_evidencia_se_descarta_entero():
    """`motivos_inventados` no cita nada del EF: no se crea la tabla."""
    tables, sources = await _modelo()
    tables, seeds, observations, _, _ = await run_catalogs(
        BdMapLLM(), tables, sources, ENGINE
    )
    assert "motivos_inventados" not in {t["name"] for t in tables}
    assert any("anti-invención" in (o["reason"] or "") for o in observations)
    assert all("motivos_inventados" != s["table"] for s in seeds)


async def test_el_catalogo_queda_referenciado_por_su_tabla_padre():
    """Un catálogo que nadie referencia no sirve: se añade la columna + FK."""
    tables, sources = await _modelo()
    tables, _, _, _, _ = await run_catalogs(BdMapLLM(), tables, sources, ENGINE)

    catalogo = next(t for t in tables if t["kind"] == TableKind.CATALOG.value)
    padre = next(t for t in tables if t["name"] == "siniestros")
    fk = next(
        fk for fk in padre["foreign_keys"] if fk["references_table"] == catalogo["name"]
    )
    assert fk["columns"] == ["estado_id"]
    assert "estado_id" in {c["name"] for c in padre["columns"]}
    assert fk["on_delete"] == "restrict"


def test_catalogo_que_apunta_a_una_tabla_inexistente_se_descarta():
    sources = _sources()
    tables = [
        {
            "id": "TBL-001",
            "name": "siniestros",
            "kind": TableKind.ENTITY.value,
            "columns": [{"name": "siniestro_id", "is_primary_key": True}],
            "foreign_keys": [],
            "primary_key": {"columns": ["siniestro_id"]},
            "unique_constraints": [],
            "check_constraints": [],
            "indexes": [],
        }
    ]
    proceso = sources["ef"]["processes"][0]["id"]
    tables, seeds, notas = apply_catalogs(
        tables,
        {
            "catalogs": [
                {
                    "name": "estados",
                    "referenced_by": {"table": "tabla_fantasma", "column": "x_id"},
                    "rows": [{"codigo": "A", "nombre": "A"}],
                    "source_refs": [proceso],
                    "evidence": "…",
                }
            ]
        },
        sources,
        ENGINE,
    )
    assert len(tables) == 1
    assert any("no existe en el modelo" in n["reason"] for n in notas)


def test_catalogo_sin_valores_enumerados_se_crea_vacio_y_se_reporta():
    """«Hay estados pero el EF no dice cuáles» ⇒ tabla sin semilla + observación."""
    sources = _sources()
    tables = [
        {
            "id": "TBL-001",
            "name": "siniestros",
            "kind": TableKind.ENTITY.value,
            "columns": [{"name": "siniestro_id", "is_primary_key": True}],
            "foreign_keys": [],
            "primary_key": {"columns": ["siniestro_id"]},
            "unique_constraints": [],
            "check_constraints": [],
            "indexes": [],
        }
    ]
    proceso = sources["ef"]["processes"][0]["id"]
    tables, seeds, notas = apply_catalogs(
        tables,
        {
            "catalogs": [
                {
                    "name": "siniestro_estados",
                    "referenced_by": {"table": "siniestros", "column": "estado_id"},
                    "rows": [],
                    "source_refs": [proceso],
                    "evidence": "el siniestro tiene estados",
                }
            ]
        },
        sources,
        ENGINE,
    )
    assert "siniestro_estados" in {t["name"] for t in tables}
    assert seeds == []
    assert any("sin datos semilla" in n["description"] for n in notas)
    assert any("en vez de inventarlos" in n["reason"] for n in notas)


def test_filas_sin_evidencia_se_descartan_pero_la_tabla_queda():
    sources = _sources()
    tables = [
        {
            "id": "TBL-001",
            "name": "siniestros",
            "kind": TableKind.ENTITY.value,
            "columns": [{"name": "siniestro_id", "is_primary_key": True}],
            "foreign_keys": [],
            "primary_key": {"columns": ["siniestro_id"]},
            "unique_constraints": [],
            "check_constraints": [],
            "indexes": [],
        }
    ]
    proceso = sources["ef"]["processes"][0]["id"]
    tables, seeds, notas = apply_catalogs(
        tables,
        {
            "catalogs": [
                {
                    "name": "siniestro_estados",
                    "referenced_by": {"table": "siniestros", "column": "estado_id"},
                    "rows": [{"codigo": "X", "nombre": "Inventado"}],
                    "source_refs": [proceso],
                    "evidence": None,
                }
            ]
        },
        sources,
        ENGINE,
    )
    assert "siniestro_estados" in {t["name"] for t in tables}
    assert seeds == []
    assert any("peor error posible" in n["reason"] for n in notas)


def test_deteccion_determinista_reclasifica_una_entidad_pequeña():
    """Una entidad con nombre de catálogo y pocos campos se marca como catálogo."""
    tables = [
        {
            "id": "TBL-001",
            "name": "siniestro_tipos",
            "kind": TableKind.ENTITY.value,
            "columns": [
                {"name": "siniestro_tipo_id"},
                {"name": "nombre", "field_ref": "FLD-010"},
            ],
        },
        {
            "id": "TBL-002",
            "name": "siniestros",
            "kind": TableKind.ENTITY.value,
            "columns": [{"name": f"c{i}", "field_ref": f"FLD-{i}"} for i in range(8)],
        },
    ]
    reclasificadas = detect_catalog_candidates(tables)
    assert [t["name"] for t in reclasificadas] == ["siniestro_tipos"]
    assert tables[0]["kind"] == TableKind.CATALOG.value
    # Una entidad con muchos campos NO es un catálogo aunque el nombre confunda.
    assert tables[1]["kind"] == TableKind.ENTITY.value


# --- Integración en el grafo ------------------------------------------------


async def _noop_persist(job_id, artifact, status, metrics):
    return None


async def test_grafo_completo_hasta_BD4():
    graph = build_bd_graph(build_memory_checkpointer())
    state = {
        "job_id": "BD-4",
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
            "thread_id": "BD-4",
            "llm": BdMapLLM(),
            "persist": _noop_persist,
        }
    }
    result = await graph.ainvoke(state, config)
    art = result["artifact"]

    # Entidades + catálogo detectado.
    assert {"siniestros", "guias"} <= {t["name"] for t in art["tables"]}
    assert any(t["kind"] == TableKind.CATALOG.value for t in art["tables"])

    # Integridad, índices y semilla presentes y numerados.
    assert art["metrics"]["indexes_total"] >= 1
    assert art["metrics"]["constraints_total"] >= 4
    assert art["metrics"]["seed_rows_total"] >= 1
    assert art["rule_mappings"]
    assert art["seed_data"]

    # Toda regla del EF tiene destino declarado.
    del_ef = {"BR-001", "VAL-001"}
    assert del_ef <= {m["rule_ref"] for m in art["rule_mappings"]}

    # Y los rechazos de BD4 llegan como observaciones al artefacto.
    razones = " ".join(o["reason"] or "" for o in art["analysis"]["observations"])
    assert "no es determinista" in razones  # CHECK temporal
    assert "por si acaso" in razones  # índice sin justificación
    assert "anti-invención" in razones  # catálogo sin evidencia

    assert result["status"] == "COMPLETED"
