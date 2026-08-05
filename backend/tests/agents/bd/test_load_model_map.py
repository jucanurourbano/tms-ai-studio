"""Tests del grafo BD con stubs, del gate, del motor y del andamio (BD2).

Los insumos son los artefactos de ejemplo **reales** de EF y Arquitectura, no
fixtures inventados: así los tests comprueban que el agente sabe leer lo que la
cadena produce de verdad.
"""

import pytest

from ai.agents.arquitectura.schemas.examples import (
    example_artifact as arquitectura_example,
)
from ai.agents.bd.load_sources import (
    assert_architecture_ready,
    extract_sources,
    resolve_engine,
    resolve_hashes,
)
from ai.agents.bd.model_map import (
    build_model_map,
    build_relation_plan,
    build_table_candidates,
    resolve_audit_columns,
)
from ai.agents.bd.schemas.enums import TableKind
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from ai.errors import GateError
from ai.orchestrator import build_bd_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer


def _ef_dict():
    return ef_example().model_dump(mode="json")


def _arq_dict():
    return arquitectura_example().model_dump(mode="json")


def _scrum_dict():
    return scrum_example().model_dump(mode="json")


def _sources(**overrides):
    sources = extract_sources(_ef_dict(), _arq_dict(), _scrum_dict())
    for key, value in overrides.items():
        sources[key] = value
    return sources


async def _noop_persist(job_id, artifact, status, metrics):
    return None


def _base_config():
    return {"configurable": {"thread_id": "BD-1", "persist": _noop_persist}}


def _base_state(architecture_ready: bool = True, **extra):
    state = {
        "job_id": "BD-1",
        "architecture_job_id": "AR-1",
        "architecture_artifact": _arq_dict(),
        "architecture_artifact_hash": "ar123",
        "architecture_ready": architecture_ready,
        "scrum_job_id": "SC-1",
        "scrum_artifact": _scrum_dict(),
        "scrum_artifact_hash": "sc123",
        "ef_job_id": "EF-1",
        "ef_artifact": _ef_dict(),
        "ef_artifact_hash": "ef123",
    }
    state.update(extra)
    return state


# --- Gate de entrada --------------------------------------------------------


def test_assert_architecture_ready_explica_como_desbloquear():
    with pytest.raises(GateError) as exc:
        assert_architecture_ready(False, "AR-9")
    mensaje = str(exc.value)
    assert "AR-9" in mensaje
    assert "refine" in mensaje  # el mensaje dice qué hacer, no solo que falló


async def test_gate_bloquea_arquitectura_no_lista():
    graph = build_bd_graph(build_memory_checkpointer())
    with pytest.raises(GateError):
        await graph.ainvoke(_base_state(architecture_ready=False), _base_config())


# --- Contexto consolidado ---------------------------------------------------


def test_extract_sources_expone_la_materia_prima_del_EF():
    sources = _sources()
    ef = sources["ef"]
    # Lo que el modelo físico necesita de verdad.
    assert [e["id"] for e in ef["entities"]] == ["ENT-001", "ENT-002"]
    assert [r["id"] for r in ef["relationships"]] == ["REL-001"]
    assert [f["id"] for f in ef["fields"]] == ["FLD-001", "FLD-002"]
    assert ef["validations"] and ef["business_rules"]
    assert ef["crud"] and ef["apis"]


def test_extract_sources_expone_lo_util_de_la_arquitectura():
    arq = _sources()["architecture"]
    assert arq["stack"]
    assert arq["components"]
    assert arq["cross_cutting"]
    assert arq["style"] == "modular_monolith"


def test_el_scrum_solo_aporta_trazabilidad():
    """El plan ágil no alimenta el modelo de datos: se carga por la cadena."""
    sources = _sources()
    assert set(sources["scrum"]) == {"epics"}


def test_extract_sources_tolera_arquitectura_o_scrum_vacios():
    sources = extract_sources(_ef_dict(), {}, None)
    assert sources["architecture"]["stack"] == []
    assert sources["scrum"]["epics"] == []


# --- Resolución del motor ---------------------------------------------------


def test_motor_lo_decide_la_arquitectura():
    """STK-002 del ejemplo dice «SQL Server»: se traduce y se cita la fuente."""
    info = resolve_engine(_sources())
    assert info["engine"] == "sqlserver"
    assert info["decided"] is True
    assert info["source_ref"] == "STK-002"


def test_override_de_la_peticion_manda():
    info = resolve_engine(_sources(), override="PostgreSQL")
    assert info["engine"] == "postgresql"
    assert info["decided"] is True


def test_override_fuera_del_allow_list_se_rechaza():
    """Nadie mete SQLite por la puerta de atrás del request."""
    with pytest.raises(GateError):
        resolve_engine(_sources(), override="sqlite")


def test_sin_motor_en_la_arquitectura_hay_fallback_declarado():
    """El pipeline corre, pero `decided=False` deja el vacío visible."""
    sources = _sources()
    sources["architecture"]["stack"] = [
        {"id": "STK-001", "layer": "framework_backend", "technology": "Spring Boot"}
    ]
    info = resolve_engine(sources)
    assert info["decided"] is False
    assert info["engine"] in ("sqlserver", "postgresql", "oracle", "mysql")
    assert "no decidió motor" in info["reason"]


def test_motor_exotico_en_la_arquitectura_no_se_acepta_en_silencio():
    """Un motor fuera del allow-list degrada a fallback + pregunta, no se usa."""
    sources = _sources()
    sources["architecture"]["stack"] = [
        {"id": "STK-002", "layer": "database_relational", "technology": "MongoDB"}
    ]
    info = resolve_engine(sources)
    assert info["decided"] is False
    assert info["source_ref"] == "STK-002"
    assert "MongoDB" in info["reason"]


@pytest.mark.parametrize(
    "declarado,esperado",
    [
        ("SQL Server", "sqlserver"),
        ("sqlserver", "sqlserver"),
        ("MSSQL", "sqlserver"),
        ("PostgreSQL", "postgresql"),
        ("Postgres", "postgresql"),
        ("Oracle Database", "oracle"),
        ("MariaDB", "mysql"),
    ],
)
def test_alias_de_motor_se_normalizan(declarado: str, esperado: str):
    sources = _sources()
    sources["architecture"]["stack"] = [
        {"id": "STK-002", "layer": "database_relational", "technology": declarado}
    ]
    assert resolve_engine(sources)["engine"] == esperado


def test_resolve_hashes_cae_al_source_del_artefacto_de_arriba():
    """Si el estado no trae el hash del EF, se toma del artefacto de Arquitectura."""
    arq = _arq_dict()
    arch_hash, ef_hash = resolve_hashes("ar1", "", arq, _ef_dict())
    assert arch_hash == "ar1"
    assert ef_hash == arq["source"]["ef_artifact_hash"]


# --- Columnas de auditoría --------------------------------------------------


def test_auditoria_solo_si_la_arquitectura_la_declaro():
    """XC-001 del ejemplo es `audit`: procede añadir columnas de auditoría."""
    columnas = resolve_audit_columns(_sources())
    assert columnas is not None
    assert {c["name"] for c in columnas} >= {"created_at", "created_by"}


def test_sin_transversal_de_auditoria_no_se_inventan_columnas():
    """No se hereda la convención de TMS AI Studio al sistema diseñado."""
    sources = _sources()
    sources["architecture"]["cross_cutting"] = [
        {"id": "XC-002", "concern": "auth", "requirement": "…", "approach": "…"}
    ]
    assert resolve_audit_columns(sources) is None


# --- MODEL_MAP: el andamio determinista -------------------------------------


def test_una_tabla_por_entidad_del_EF():
    candidatas = build_table_candidates(_sources(), "postgresql")
    assert [c["entity_ref"] for c in candidatas] == ["ENT-001", "ENT-002"]
    assert [c["name"] for c in candidatas] == ["siniestros", "guias"]
    assert all(c["kind"] == TableKind.ENTITY.value for c in candidatas)
    assert [c["id"] for c in candidatas] == ["TBL-001", "TBL-002"]


def test_columnas_candidatas_vienen_de_los_campos_del_EF():
    candidatas = build_table_candidates(_sources(), "postgresql")
    siniestros = next(c for c in candidatas if c["name"] == "siniestros")
    por_nombre = {col["name"]: col for col in siniestros["columns"]}
    assert set(por_nombre) == {"numero_guia", "fecha_siniestro"}
    # Tipos ya normalizados desde el `data_type` del EF.
    assert por_nombre["fecha_siniestro"]["logical_type"] == "date"
    assert por_nombre["numero_guia"]["logical_type"] == "string"
    # `required=True` en el EF ⇒ NOT NULL en el modelo.
    assert por_nombre["numero_guia"]["nullable"] is False
    # Trazabilidad al campo de origen.
    assert por_nombre["numero_guia"]["field_ref"] == "FLD-001"


def test_pk_subrogada_se_nombra_por_convencion():
    candidatas = build_table_candidates(_sources(), "postgresql")
    assert {c["name"]: c["pk_column"] for c in candidatas} == {
        "siniestros": "siniestro_id",
        "guias": "guia_id",
    }


def test_relacion_1_a_N_pone_la_FK_en_el_lado_N():
    """REL-001: «una guía puede tener varios siniestros» ⇒ FK en siniestros."""
    sources = _sources()
    candidatas = build_table_candidates(sources, "postgresql")
    plan = build_relation_plan(sources, candidatas, "postgresql")

    assert len(plan["foreign_keys"]) == 1
    fk = plan["foreign_keys"][0]
    assert fk["table"] == "siniestros"
    assert fk["column"] == "guia_id"
    assert fk["references_table"] == "guias"
    assert fk["references_column"] == "guia_id"
    assert fk["relationship_ref"] == "REL-001"


def test_relacion_N_a_M_genera_tabla_puente_con_pk_compuesta():
    sources = _sources()
    sources["ef"]["relationships"] = [
        {
            "id": "REL-002",
            "source_entity_ref": "ENT-001",
            "target_entity_ref": "ENT-002",
            "cardinality": "N:M",
        }
    ]
    candidatas = build_table_candidates(sources, "postgresql")
    plan = build_relation_plan(sources, candidatas, "postgresql")

    assert plan["foreign_keys"] == []
    assert len(plan["junction_tables"]) == 1
    puente = plan["junction_tables"][0]
    assert puente["kind"] == TableKind.JUNCTION.value
    assert puente["name"] == "guias_siniestros"
    assert puente["entity_ref"] is None
    assert [c["name"] for c in puente["columns"]] == ["guia_id", "siniestro_id"]
    assert all(c["is_primary_key"] for c in puente["columns"])


def test_la_misma_relacion_N_a_M_declarada_dos_veces_no_duplica_la_tabla():
    sources = _sources()
    sources["ef"]["relationships"] = [
        {
            "id": "REL-002",
            "source_entity_ref": "ENT-001",
            "target_entity_ref": "ENT-002",
            "cardinality": "N:M",
        },
        {
            "id": "REL-003",
            "source_entity_ref": "ENT-002",
            "target_entity_ref": "ENT-001",
            "cardinality": "N:M",
        },
    ]
    candidatas = build_table_candidates(sources, "postgresql")
    plan = build_relation_plan(sources, candidatas, "postgresql")
    assert len(plan["junction_tables"]) == 1


def test_relacion_1_a_1_no_se_decide_en_python():
    """Quién es dueño de la FK depende del negocio: lo resuelve RELATIONS (LLM)."""
    sources = _sources()
    sources["ef"]["relationships"] = [
        {
            "id": "REL-004",
            "source_entity_ref": "ENT-001",
            "target_entity_ref": "ENT-002",
            "cardinality": "1:1",
        }
    ]
    candidatas = build_table_candidates(sources, "postgresql")
    plan = build_relation_plan(sources, candidatas, "postgresql")

    assert plan["foreign_keys"] == []
    assert len(plan["needs_owner_decision"]) == 1
    assert plan["needs_owner_decision"][0]["relationship_ref"] == "REL-004"


def test_relacion_huerfana_se_reporta_en_vez_de_descartarse():
    """Una relación que cita una entidad inexistente no desaparece en silencio."""
    sources = _sources()
    sources["ef"]["relationships"] = [
        {
            "id": "REL-009",
            "source_entity_ref": "ENT-404",
            "target_entity_ref": "ENT-001",
            "cardinality": "1:N",
        }
    ]
    candidatas = build_table_candidates(sources, "postgresql")
    plan = build_relation_plan(sources, candidatas, "postgresql")
    assert plan["foreign_keys"] == []
    assert len(plan["orphan_relationships"]) == 1
    assert "ENT-404" in plan["orphan_relationships"][0]["reason"]


def test_summary_del_model_map_alimenta_cobertura_y_preguntas():
    mapa = build_model_map(_sources(), "postgresql")
    resumen = mapa["summary"]
    assert resumen["entities_total"] == 2
    assert resumen["tables_planned"] == 2
    assert resumen["fields_total"] == 2
    assert resumen["fields_mapped"] == 2
    assert resumen["unmapped_field_refs"] == []
    assert resumen["orphan_relationships"] == 0


def test_campo_sin_entidad_se_reporta_como_no_mapeado():
    """Un campo del EF sin `entity_ref` no cabe en ninguna tabla: se declara."""
    sources = _sources()
    sources["ef"]["fields"] = sources["ef"]["fields"] + [
        {"id": "FLD-099", "name": "campo_suelto", "data_type": "texto"}
    ]
    resumen = build_model_map(sources, "postgresql")["summary"]
    assert resumen["unmapped_field_refs"] == ["FLD-099"]


def test_columnas_con_tipo_ambiguo_quedan_listadas():
    sources = _sources()
    sources["ef"]["fields"] = [
        {"id": "FLD-010", "name": "zzz", "entity_ref": "ENT-001", "required": True}
    ]
    resumen = build_model_map(sources, "postgresql")["summary"]
    assert resumen["ambiguous_type_columns"] == ["siniestros.zzz"]


def test_model_map_es_reproducible():
    """Mismo EF ⇒ mismo andamio, byte a byte (base de los tests del DDL)."""
    primera = build_model_map(_sources(), "postgresql")
    segunda = build_model_map(_sources(), "postgresql")
    assert primera == segunda


# --- Grafo end-to-end con stubs ---------------------------------------------


async def test_grafo_end_to_end_con_stubs():
    """El pipeline completo corre y produce un DatabaseArtifact válido y vacío."""
    graph = build_bd_graph(build_memory_checkpointer())
    result = await graph.ainvoke(_base_state(), _base_config())

    assert result["status"] == "COMPLETED"
    art = result["artifact"]
    assert art["schema_version"] == "1.0.0"
    # Cadena completa en `source` (Arquitectura directo, Scrum y EF transitivos).
    assert art["source"]["architecture_job_id"] == "AR-1"
    assert art["source"]["scrum_job_id"] == "SC-1"
    assert art["source"]["ef_job_id"] == "EF-1"
    assert art["source"]["ready_snapshot"] is True
    # Motor resuelto desde la arquitectura y convenciones persistidas.
    assert art["target"]["engine"] == "sqlserver"
    assert art["target"]["engine_source_ref"] == "STK-002"
    assert art["target"]["conventions"]["schema_name"] == "dbo"
    assert art["target"]["conventions"]["audit_columns"] is True
    assert art["target"]["conventions_source"].endswith("db_conventions.yaml@v0")
    # Con los stubs todavía no hay tablas: el semáforo del DDL sigue en rojo.
    assert art["tables"] == []
    assert art["metrics"]["ddl_valid"] is False


async def test_el_andamio_esta_disponible_para_los_nodos_siguientes():
    """MODEL_MAP deja el andamio en el estado, listo para TABLES (BD3)."""
    graph = build_bd_graph(build_memory_checkpointer())
    result = await graph.ainvoke(_base_state(), _base_config())
    mapa = result["model_map"]
    assert [t["name"] for t in mapa["tables"]] == ["siniestros", "guias"]
    assert len(mapa["relations"]["foreign_keys"]) == 1


async def test_override_de_motor_llega_al_artefacto():
    graph = build_bd_graph(build_memory_checkpointer())
    result = await graph.ainvoke(
        _base_state(engine_override="postgresql"), _base_config()
    )
    target = result["artifact"]["target"]
    assert target["engine"] == "postgresql"
    assert target["conventions"]["schema_name"] == "public"
