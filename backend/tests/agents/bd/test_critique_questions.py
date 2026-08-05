"""Tests de CRITIQUE y QUESTION_GEN (BD6).

Dos cosas se prueban aquí por encima del resto: que **la cobertura no oculta
huecos** (siempre enumera lo que falta) y que **las preguntas se agrupan** — cuarenta
columnas sin tipo no pueden convertirse en cuarenta preguntas, porque entonces nadie
responde la que importa.
"""

import pytest

from ai.agents.arquitectura.schemas.examples import (
    example_artifact as arquitectura_example,
)
from ai.agents.bd.catalogs import run_catalogs
from ai.agents.bd.constraints import run_constraints
from ai.agents.bd.critique import (
    compute_coverage,
    detect_pii,
    run_critique,
    run_deterministic_checks,
)
from ai.agents.bd.ddl.render import build_ddl_scripts, render_type
from ai.agents.bd.ddl.validate import validate_ddl
from ai.agents.bd.indexes import run_indexes
from ai.agents.bd.load_sources import extract_sources
from ai.agents.bd.model_map import build_model_map
from ai.agents.bd.question_gen import generate_questions
from ai.agents.bd.relations import run_relations
from ai.agents.bd.schemas.artifact import DbaQuestion, Risk
from ai.agents.bd.schemas.enums import RuleEnforcement
from ai.agents.bd.tables import run_tables
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.orchestrator import build_bd_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from tests.mocks import BdMapLLM

ENGINE = "postgresql"


def _sources():
    return extract_sources(
        ef_example().model_dump(mode="json"),
        arquitectura_example().model_dump(mode="json"),
        None,
    )


async def _modelo(sources=None):
    """Modelo completo tras BD3-BD5 (la entrada real de CRITIQUE)."""
    sources = sources or _sources()
    mapa = build_model_map(sources, ENGINE)
    tables, _, _, _ = await run_tables(BdMapLLM(), mapa, sources, ENGINE)
    tables, _, _, _ = await run_relations(BdMapLLM(), tables, mapa, sources, ENGINE)
    tables, mappings, _, _, _ = await run_constraints(
        BdMapLLM(), tables, sources, ENGINE
    )
    tables, _, _, _ = await run_indexes(BdMapLLM(), tables, sources, ENGINE)
    tables, seeds, _, _, _ = await run_catalogs(BdMapLLM(), tables, sources, ENGINE)
    for table in tables:
        for column in table["columns"]:
            column["type"] = render_type(column, ENGINE)
    scripts, ciclos = build_ddl_scripts(tables, seeds, ENGINE)
    validation = validate_ddl(tables, seeds, scripts, ENGINE, cycles=ciclos)
    return {
        "tables": tables,
        "rule_mappings": mappings,
        "seed_data": seeds,
        "validation": validation,
        "sources": sources,
        "model_map": mapa,
        "target": {"engine": ENGINE, "engine_decided": True},
    }


async def _critica(modelo=None, **overrides):
    modelo = modelo or await _modelo()
    modelo.update(overrides)
    critique, _ = await run_critique(
        modelo["tables"],
        modelo["rule_mappings"],
        modelo["validation"],
        modelo["sources"],
        modelo["model_map"],
        modelo["seed_data"],
        modelo["target"],
        llm=BdMapLLM(),
        engine=ENGINE,
    )
    return critique


# --- Cobertura --------------------------------------------------------------


async def test_la_cobertura_cuenta_entidades_campos_validaciones_y_reglas():
    modelo = await _modelo()
    coverage = compute_coverage(
        modelo["tables"], modelo["rule_mappings"], modelo["sources"]
    )
    assert coverage["entities_total"] == 2
    assert coverage["entities_mapped"] == 2
    assert coverage["uncovered_entity_refs"] == []
    assert coverage["fields_total"] == 2
    assert coverage["rules_total"] == 1
    assert coverage["validations_total"] == 1


async def test_una_regla_de_aplicacion_no_cuenta_como_aplicada_en_el_esquema():
    """VAL-001 quedó en la capa de aplicación: la cobertura no puede maquillarlo."""
    modelo = await _modelo()
    coverage = compute_coverage(
        modelo["tables"], modelo["rule_mappings"], modelo["sources"]
    )
    assert "VAL-001" in coverage["unenforced_validation_refs"]
    assert coverage["validations_enforced"] == 0


def test_la_cobertura_enumera_siempre_lo_que_falta():
    """Un porcentaje sin la lista de lo que falta tranquiliza sin informar."""
    sources = _sources()
    coverage = compute_coverage([], [], sources)
    assert coverage["entities_mapped"] == 0
    assert coverage["uncovered_entity_refs"] == ["ENT-001", "ENT-002"]
    assert coverage["unmapped_field_refs"] == ["FLD-001", "FLD-002"]
    assert coverage["unenforced_rule_refs"] == ["BR-001"]


# --- Datos personales -------------------------------------------------------


def test_se_marcan_las_columnas_candidatas_a_dato_personal():
    tables = [
        {
            "name": "colaboradores",
            "columns": [
                {"id": "COL-1", "name": "colaborador_id"},
                {"id": "COL-2", "name": "nombre_completo"},
                {"id": "COL-3", "name": "numero_documento"},
                {"id": "COL-4", "name": "correo_institucional"},
                {"id": "COL-5", "name": "cuenta_bancaria"},
                {"id": "COL-6", "name": "cantidad_bultos"},
            ],
        }
    ]
    encontradas = detect_pii(tables)
    nombres = {c["column"] for c in encontradas}
    assert nombres == {
        "nombre_completo",
        "numero_documento",
        "correo_institucional",
        "cuenta_bancaria",
    }
    # Se marca en la propia columna, para que la vista pueda pintarlo.
    assert tables[0]["columns"][1]["pii"] is True
    assert "pii" not in tables[0]["columns"][5]


async def test_el_pii_genera_observacion_y_pregunta_no_bloqueante():
    """Señalar sin bloquear: el tratamiento lo decide el DBA, pero se menciona."""
    modelo = await _modelo()
    modelo["tables"][0]["columns"].append(
        {
            "id": "COL-9999",
            "name": "nombre_denunciante",
            "logical_type": "string",
            "nullable": True,
        }
    )
    critique = await _critica(modelo)
    assert any("dato personal" in o["description"] for o in critique["observations"])

    preguntas = generate_questions(critique)
    pii = next(p for p in preguntas if "datos personales" in p["question"])
    assert pii["blocking"] is False
    assert "nombre_denunciante" in pii["reason"]


# --- Hallazgos deterministas ------------------------------------------------


async def test_una_tabla_aislada_se_detecta():
    modelo = await _modelo()
    modelo["tables"].append(
        {
            "id": "TBL-099",
            "name": "parametros",
            "kind": "entity",
            "columns": [{"id": "COL-99", "name": "parametro_id"}],
            "foreign_keys": [],
            "unique_constraints": [],
            "indexes": [],
        }
    )
    critique = await _critica(modelo)
    assert "parametros" in critique["findings"]["orphan_tables"]
    assert any("no participa" in o["description"] for o in critique["observations"])


async def test_un_catalogo_no_cuenta_como_tabla_aislada():
    """Un catálogo referenciado por nadie todavía es normal, no un hallazgo."""
    modelo = await _modelo()
    modelo["tables"].append(
        {
            "id": "TBL-098",
            "name": "motivos",
            "kind": "catalog",
            "columns": [{"id": "COL-98", "name": "motivo_id"}],
            "foreign_keys": [],
            "unique_constraints": [],
            "indexes": [],
        }
    )
    critique = await _critica(modelo)
    assert "motivos" not in critique["findings"]["orphan_tables"]


async def test_un_ddl_invalido_se_convierte_en_riesgo_alto():
    modelo = await _modelo()
    modelo["validation"] = {
        "errors": [{"code": "fk_target_missing", "message": "…", "ref": "FK-001"}]
    }
    critique = await _critica(modelo)
    riesgo = next(
        r for r in critique["risks"] if "DDL generado no es válido" in r["description"]
    )
    assert riesgo["severity"] == "alta"
    assert riesgo["source_ref"] == "FK-001"
    Risk.model_validate(riesgo)


async def test_el_pase_LLM_aporta_riesgos_sin_tocar_el_modelo():
    modelo = await _modelo()
    antes = [dict(t) for t in modelo["tables"]]
    critique = await _critica(modelo)
    assert any("volumetría" in r["description"] for r in critique["risks"])
    assert [t["name"] for t in modelo["tables"]] == [t["name"] for t in antes]
    for risk in critique["risks"]:
        Risk.model_validate(risk)


async def test_sin_LLM_la_critica_sigue_funcionando():
    """Los hallazgos deterministas no dependen del modelo."""
    modelo = await _modelo()
    critique, tokens = await run_critique(
        modelo["tables"],
        modelo["rule_mappings"],
        modelo["validation"],
        modelo["sources"],
        modelo["model_map"],
        modelo["seed_data"],
        modelo["target"],
        llm=None,
        engine=ENGINE,
    )
    assert tokens["total"] == 0
    assert critique["coverage"]["entities_total"] == 2


def test_un_modelo_vacio_lo_dice():
    findings = run_deterministic_checks([], [], {}, {"ef": {}}, {})
    assert findings["tables_total"] == 0


# --- QUESTION_GEN: qué bloquea ----------------------------------------------


async def test_las_preguntas_validan_contra_el_contrato():
    critique = await _critica()
    preguntas = generate_questions(critique)
    for pregunta in preguntas:
        DbaQuestion.model_validate(pregunta)
        assert pregunta["audience"] == "tecnico"
        assert pregunta["status"] == "pendiente"
    ids = [p["id"] for p in preguntas]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_una_entidad_sin_tabla_es_bloqueante():
    critique = {
        "findings": {"coverage": {"uncovered_entity_refs": ["ENT-003", "ENT-004"]}}
    }
    pregunta = generate_questions(critique)[0]
    assert pregunta["blocking"] is True
    assert "ENT-003" in pregunta["reason"] and "ENT-004" in pregunta["reason"]
    assert pregunta["linked_to_ref"] == "ENT-003"


def test_el_motor_sin_decidir_es_bloqueante():
    """Todo el DDL depende del motor: no puede quedar en verde sin confirmarlo."""
    preguntas = generate_questions({"findings": {"engine_undecided": True}})
    assert preguntas[0]["blocking"] is True
    assert "motor relacional" in preguntas[0]["question"]


def test_un_ddl_invalido_es_bloqueante():
    critique = {
        "findings": {
            "ddl_errors": [
                {"code": "fk_target_missing", "ref": "FK-001"},
                {"code": "table_without_pk", "ref": "TBL-002"},
            ]
        }
    }
    pregunta = generate_questions(critique)[0]
    assert pregunta["blocking"] is True
    assert "fk_target_missing" in pregunta["question"]
    assert "table_without_pk" in pregunta["question"]


def test_una_relacion_1_a_1_sin_dueño_es_bloqueante():
    critique = {
        "findings": {
            "unresolved_one_to_one": [
                {"relationship_ref": "REL-004", "candidates": ["guias", "detalles"]}
            ]
        }
    }
    pregunta = generate_questions(critique)[0]
    assert pregunta["blocking"] is True
    assert "guias o detalles" in pregunta["question"]


def test_un_tipo_ambiguo_bloquea_solo_si_la_columna_es_obligatoria():
    """Una columna opcional con tipo por defecto no puede frenar el flujo."""
    critique = {
        "findings": {
            "ambiguous_type_columns": [
                {
                    "table": "t",
                    "column": "obligatoria",
                    "ref": "COL-1",
                    "required": True,
                },
                {"table": "t", "column": "opcional", "ref": "COL-2", "required": False},
            ]
        }
    }
    preguntas = generate_questions(critique)
    bloqueantes = [p for p in preguntas if p["blocking"]]
    no_bloqueantes = [p for p in preguntas if not p["blocking"]]
    assert len(bloqueantes) == 1 and "obligatoria" in bloqueantes[0]["reason"]
    assert len(no_bloqueantes) == 1 and "opcional" in no_bloqueantes[0]["reason"]


@pytest.mark.parametrize(
    "findings,esperado_bloqueante",
    [
        ({"catalogs_without_seed": ["estados"]}, False),
        ({"pii_columns": [{"table": "t", "column": "dni", "ref": "C1"}]}, False),
        ({"orphan_tables": ["parametros"]}, False),
        ({"coverage": {"unenforced_rule_refs": ["BR-009"]}}, False),
        ({"coverage": {"unmapped_field_refs": ["FLD-033"]}}, False),
        ({"low_confidence_tables": [{"table": "t", "ref": "TBL-1"}]}, False),
    ],
)
def test_lo_mejorable_no_bloquea(findings, esperado_bloqueante):
    """Si todo bloqueara, el semáforo no distinguiría nada."""
    preguntas = generate_questions({"findings": findings})
    assert preguntas
    assert all(p["blocking"] is esperado_bloqueante for p in preguntas)


# --- QUESTION_GEN: agrupación -----------------------------------------------


def test_cuarenta_columnas_sin_tipo_son_una_sola_pregunta():
    """La regla que hace usable el panel de afinamiento."""
    columnas = [
        {"table": "t", "column": f"c{i}", "ref": f"COL-{i:04d}", "required": False}
        for i in range(40)
    ]
    preguntas = generate_questions({"findings": {"ambiguous_type_columns": columnas}})
    assert len(preguntas) == 1
    assert "40 columna(s)" in preguntas[0]["question"]


def test_una_pregunta_agrupada_declara_lo_que_no_enumera():
    """Nunca un recorte mudo: el texto dice cuántos casos quedan fuera."""
    columnas = [
        {"table": "t", "column": f"c{i}", "ref": f"COL-{i:04d}", "required": True}
        for i in range(20)
    ]
    pregunta = generate_questions({"findings": {"ambiguous_type_columns": columnas}})[0]
    assert "y 8 más" in pregunta["reason"]  # 20 - 12 visibles
    assert pregunta["reason"].count("t.c") == 12


def test_las_relaciones_1_a_1_no_se_agrupan():
    """Cada una exige una decisión distinta: agruparlas impediría responderlas."""
    critique = {
        "findings": {
            "unresolved_one_to_one": [
                {"relationship_ref": "REL-001", "candidates": ["a", "b"]},
                {"relationship_ref": "REL-002", "candidates": ["c", "d"]},
            ]
        }
    }
    preguntas = generate_questions(critique)
    assert len(preguntas) == 2
    assert {p["linked_to_ref"] for p in preguntas} == {"REL-001", "REL-002"}


def test_sin_hallazgos_no_hay_preguntas():
    """Un modelo limpio deja el semáforo en verde: cero preguntas es correcto."""
    assert generate_questions({"findings": {}}) == []


# --- Integración en el grafo ------------------------------------------------


async def _noop_persist(job_id, artifact, status, metrics):
    return None


async def test_grafo_completo_hasta_BD6():
    graph = build_bd_graph(build_memory_checkpointer())
    result = await graph.ainvoke(
        {
            "job_id": "BD-7",
            "architecture_job_id": "AR-1",
            "architecture_artifact": arquitectura_example().model_dump(mode="json"),
            "architecture_artifact_hash": "ar123",
            "architecture_ready": True,
            "ef_job_id": "EF-1",
            "ef_artifact": ef_example().model_dump(mode="json"),
            "ef_artifact_hash": "ef123",
            "engine_override": "postgresql",
        },
        {
            "configurable": {
                "thread_id": "BD-7",
                "llm": BdMapLLM(),
                "persist": _noop_persist,
            }
        },
    )
    art = result["artifact"]

    # Cobertura completa del EF, con los huecos declarados.
    coverage = art["analysis"]["coverage"]
    assert coverage["entities_total"] == 2 and coverage["entities_mapped"] == 2
    assert coverage["unenforced_validation_refs"] == ["VAL-001"]
    assert 0 < art["metrics"]["coverage"] <= 1.0

    # Riesgos y observaciones presentes y bien formados.
    assert art["analysis"]["risks"]
    assert art["analysis"]["observations"]
    assert all(o["id"] for o in art["analysis"]["observations"])

    # Las correcciones de los nodos anteriores siguen publicadas (no se perdieron
    # al pasar CRITIQUE a ser quien las agrupa).
    descripciones = " ".join(o["description"] for o in art["analysis"]["observations"])
    assert "campo_fantasma" in descripciones

    # Preguntas al DBA: agrupadas, sin duplicados y con las bloqueantes bien puestas.
    preguntas = art["questions_for_dba"]
    assert preguntas
    assert len({p["id"] for p in preguntas}) == len(preguntas)
    # El modelo de ejemplo es sano: nada debería bloquear.
    assert [p["question"] for p in preguntas if p["blocking"]] == []

    assert result["status"] == "COMPLETED"


async def test_un_modelo_con_hueco_produce_pregunta_bloqueante():
    """Si el EF trae una entidad sin campos ni relaciones, el semáforo debe frenar."""
    ef = ef_example().model_dump(mode="json")
    # Una entidad que el andamio no podrá mapear: sin nombre utilizable.
    ef["relationships"] = [
        {
            "id": "REL-404",
            "source_entity_ref": "ENT-999",
            "target_entity_ref": "ENT-001",
            "cardinality": "1:N",
        }
    ]
    graph = build_bd_graph(build_memory_checkpointer())
    result = await graph.ainvoke(
        {
            "job_id": "BD-8",
            "architecture_job_id": "AR-1",
            "architecture_artifact": arquitectura_example().model_dump(mode="json"),
            "architecture_artifact_hash": "ar123",
            "architecture_ready": True,
            "ef_job_id": "EF-1",
            "ef_artifact": ef,
            "ef_artifact_hash": "ef123",
            "engine_override": "postgresql",
        },
        {
            "configurable": {
                "thread_id": "BD-8",
                "llm": BdMapLLM(),
                "persist": _noop_persist,
            }
        },
    )
    preguntas = result["artifact"]["questions_for_dba"]
    bloqueantes = [p for p in preguntas if p["blocking"]]
    assert bloqueantes
    assert any("no existen" in p["question"] for p in bloqueantes)
