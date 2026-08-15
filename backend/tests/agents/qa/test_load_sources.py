"""Tests del grafo QA con stubs, del gate y de la carga de fuentes (QA2).

Los insumos son los artefactos de ejemplo **reales** de Scrum, EF y API, no
fixtures inventados: así los tests comprueban que el agente sabe leer lo que la
cadena produce de verdad.

El eje de este bloque es la **dependencia opcional**. Un contrato de API indicado
pero inutilizable (sin artefacto, sin hash) no puede tratarse como presente: si se
tratara así, los nodos posteriores derivarían casos de autorización de una fuente a
medias, que es exactamente lo que el contrato del artefacto prohíbe.
"""

import pytest

from ai.agents.api.schemas.examples import example_artifact as api_example
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.qa.load_sources import (
    NO_API_REASON,
    assert_scrum_ready,
    extract_sources,
    resolve_api_availability,
    resolve_hashes,
    resolve_target,
)
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from ai.errors import GateError
from ai.orchestrator import build_qa_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from tests.mocks import QaMapLLM


def _scrum_dict():
    return scrum_example().model_dump(mode="json")


def _ef_dict():
    return ef_example().model_dump(mode="json")


def _api_dict():
    return api_example().model_dump(mode="json")


# --- Gate ---------------------------------------------------------------------


def test_gate_bloquea_un_plan_no_listo():
    with pytest.raises(GateError) as exc:
        assert_scrum_ready(False, "01SC")
    mensaje = str(exc.value)
    # El mensaje dice qué hacer, no solo que no se puede.
    assert "01SC" in mensaje
    assert "refine" in mensaje


def test_gate_pasa_con_plan_listo():
    assert_scrum_ready(True, "01SC") is None


# --- Contexto consolidado -----------------------------------------------------


def test_sources_trae_historias_y_criterios_del_scrum():
    sources = extract_sources(_scrum_dict(), _ef_dict())
    historias = sources["scrum"]["stories"]
    assert [h["id"] for h in historias] == ["US-001", "US-002"]
    criterios = [ac["id"] for h in historias for ac in h["acceptance_criteria"]]
    assert criterios == ["AC-001", "AC-002"]
    assert sources["scrum"]["epics"][0]["id"] == "EPIC-001"


def test_sources_trae_reglas_validaciones_y_campos_del_ef():
    sources = extract_sources(_scrum_dict(), _ef_dict())
    ef = sources["ef"]
    assert [r["id"] for r in ef["business_rules"]] == ["BR-001"]
    assert [v["id"] for v in ef["validations"]] == ["VAL-001"]
    assert {c["id"] for c in ef["fields"]} == {"FLD-001", "FLD-002"}
    assert [r["id"] for r in ef["functional"]] == ["REQ-F-001"]


def test_las_validaciones_se_agrupan_por_campo():
    """Agrupar por campo es lo que permite armar bordes campo a campo."""
    sources = extract_sources(_scrum_dict(), _ef_dict())
    por_campo = sources["ef"]["validations_by_field"]
    assert [v["id"] for v in por_campo["FLD-002"]] == ["VAL-001"]


def test_una_validacion_sin_campo_no_se_pierde():
    """Descartarla sería perder en silencio una frontera que alguien escribió."""
    ef = _ef_dict()
    ef["validations"].append(
        {"id": "VAL-099", "rule": "El proceso exige aprobación previa."}
    )
    por_campo = extract_sources(_scrum_dict(), ef)["ef"]["validations_by_field"]
    assert [v["id"] for v in por_campo[""]] == ["VAL-099"]


def test_sin_api_el_bloque_api_queda_vacio_y_marcado():
    sources = extract_sources(_scrum_dict(), _ef_dict())
    assert sources["api"]["available"] is False
    assert sources["api"]["endpoints"] == []
    assert sources["api"]["authorization_matrix"] == []


def test_con_api_llegan_matriz_endpoints_y_campos():
    sources = extract_sources(_scrum_dict(), _ef_dict(), _api_dict())
    api = sources["api"]
    assert api["available"] is True
    assert [r["id"] for r in api["authorization_matrix"]] == [
        "AUTH-001",
        "AUTH-002",
        "AUTH-003",
        "AUTH-004",
    ]
    assert api["endpoints"]
    # Los campos de todos los esquemas, cada uno sabiendo de qué esquema viene:
    # es lo que permite anclar un borde en `SF-005` y citar el esquema.
    campos = {c["id"] for c in api["fields"]}
    assert "SF-005" in campos
    assert all(c["schema_ref"] for c in api["fields"])


def test_la_regla_ambigua_llega_intacta():
    """AUTH-002 es la que NO debe convertirse en caso; tiene que llegar marcada."""
    sources = extract_sources(_scrum_dict(), _ef_dict(), _api_dict())
    ambigua = [
        r for r in sources["api"]["authorization_matrix"] if r["id"] == "AUTH-002"
    ][0]
    assert ambigua["ambiguous"] is True
    assert ambigua["scope"] == "own_team"
    assert ambigua["scope_column_refs"] == []


# --- Dependencia opcional -----------------------------------------------------


def test_sin_api_job_id_se_declara_la_ausencia_con_motivo():
    veredicto = resolve_api_availability(None, None, None)
    assert veredicto["available"] is False
    assert veredicto["reason"] == NO_API_REASON


def test_api_job_id_sin_artefacto_cuenta_como_ausente():
    """ "No hay contrato" y "el contrato no está disponible" no se leen igual."""
    veredicto = resolve_api_availability("01AP", None, "h")
    assert veredicto["available"] is False
    assert "01AP" in veredicto["reason"]
    assert "no tiene artefacto" in veredicto["reason"]


def test_api_sin_hash_cuenta_como_ausente():
    """Sin hash la corrida no sería reproducible, así que no se usa."""
    veredicto = resolve_api_availability("01AP", _api_dict(), "  ")
    assert veredicto["available"] is False
    assert "hash" in veredicto["reason"]


def test_api_completo_se_usa():
    veredicto = resolve_api_availability("01AP", _api_dict(), "9f8e7d6c5b4a")
    assert veredicto == {"available": True, "reason": None}


def test_los_hashes_del_api_solo_viajan_si_se_uso():
    usado = resolve_hashes("h-scrum", "h-ef", "h-api", True)
    assert usado["api_artifact_hash"] == "h-api"
    no_usado = resolve_hashes("h-scrum", "h-ef", "h-api", False)
    assert no_usado["api_artifact_hash"] is None


# --- Umbrales efectivos -------------------------------------------------------


def test_target_por_defecto_exige_cobertura_total():
    target = resolve_target()
    assert target["coverage_threshold"] == 1.0
    assert target["max_cases_per_criterion"] == 6
    assert target["minutes_by_type"]["functional"] == 10


def test_target_solo_pisa_lo_informado():
    target = resolve_target(coverage_threshold=0.9, manual_capacity_minutes=480)
    assert target["coverage_threshold"] == 0.9
    assert target["manual_capacity_minutes"] == 480
    # Lo no informado conserva el default.
    assert target["max_cases_per_criterion"] == 6


# --- Grafo de extremo a extremo (con stubs) -----------------------------------


async def _sin_persistir(job_id, artifact, status, metrics):
    """PERSIST inocuo: sin él el nodo cae a la BD real y el fallo llega como
    violación de clave ajena, ocultando lo que el test comprobaba."""


async def _corre(estado: dict) -> dict:
    graph = build_qa_graph(build_memory_checkpointer())
    # El LLM va mockeado siempre (REGLA DE PRESUPUESTO). Estos tests miran
    # LOAD_SOURCES, pero el grafo atraviesa los nodos generativos para llegar al
    # final, y el cortafuegos autouse de `conftest` corta si alguno cayera en el
    # cliente real.
    return await graph.ainvoke(
        estado,
        config={
            "configurable": {
                "thread_id": estado["job_id"],
                "llm": QaMapLLM(),
                "today": "2026-08-14",
                "persist": _sin_persistir,
            }
        },
    )


async def test_el_grafo_corre_de_extremo_a_extremo_con_stubs():
    salida = await _corre(
        {
            "job_id": "01QA00000000000000000000QA",
            "scrum_job_id": "01SC",
            "scrum_artifact": _scrum_dict(),
            "scrum_artifact_hash": "f6e5d4c3b2a1",
            "scrum_ready": True,
            "ef_job_id": "01EF",
            "ef_artifact": _ef_dict(),
            "ef_artifact_hash": "a1b2c3d4e5f6",
        }
    )
    assert salida["sources"]["scrum"]["stories"]
    assert salida["api_available"] is False
    # La ausencia del contrato deja Observation desde el primer nodo: el descarte
    # nunca es silencioso, ni siquiera cuando el pipeline todavía es un andamio.
    assert any("autorización" in o["description"] for o in salida["map_observations"])
    assert salida["target"]["coverage_threshold"] == 1.0


async def test_el_grafo_con_contrato_de_api_lo_marca_disponible():
    salida = await _corre(
        {
            "job_id": "01QA00000000000000000001QA",
            "scrum_job_id": "01SC",
            "scrum_artifact": _scrum_dict(),
            "scrum_artifact_hash": "f6e5d4c3b2a1",
            "scrum_ready": True,
            "ef_job_id": "01EF",
            "ef_artifact": _ef_dict(),
            "ef_artifact_hash": "a1b2c3d4e5f6",
            "api_job_id": "01AP",
            "api_artifact": _api_dict(),
            "api_artifact_hash": "9f8e7d6c5b4a",
        }
    )
    assert salida["api_available"] is True
    assert salida["api_absent_reason"] is None
    assert salida["hashes"]["api_artifact_hash"] == "9f8e7d6c5b4a"
    # Con contrato disponible, LOAD_SOURCES no anota la ausencia. Las demás
    # observaciones del pipeline (refs limpiadas, reglas ambiguas) sí pueden estar:
    # lo que este test fija es que no se declare ausente lo que sí llegó.
    assert not any(
        "No se diseñaron casos de autorización" in o["description"]
        for o in salida["map_observations"]
    )


async def test_el_grafo_corta_si_el_plan_no_esta_listo():
    with pytest.raises(GateError):
        await _corre(
            {
                "job_id": "01QA00000000000000000002QA",
                "scrum_job_id": "01SC",
                "scrum_artifact": _scrum_dict(),
                "scrum_artifact_hash": "h",
                "scrum_ready": False,
                "ef_job_id": "01EF",
                "ef_artifact": _ef_dict(),
                "ef_artifact_hash": "h",
            }
        )
