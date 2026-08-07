"""Tests de ASSEMBLE + PERSIST (API8), sobre el pipeline completo con mocks.

Aquí el estado del grafo se convierte en un `ApiArtifact` validado contra el
contrato de API1. Lo que se comprueba es que **nada se pierda por el camino**: ni
una corrección aplicada sobre el modelo, ni una pieza descartada, ni el hecho de
que el job terminó con avisos.
"""

import pytest
from pydantic import ValidationError

from ai.agents.api.assemble import assemble_artifact, validate_artifact
from ai.agents.api.schemas import ApiArtifact
from ai.agents.arquitectura.schemas.examples import (
    example_artifact as arquitectura_example,
)
from ai.agents.bd.schemas.examples import example_artifact as bd_example
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from ai.orchestrator import build_api_graph
from ai.orchestrator.checkpointer import build_memory_checkpointer
from tests.mocks import ApiMapLLM


def _base_state():
    return {
        "job_id": "API-1",
        "bd_job_id": "BD-1",
        "bd_artifact": bd_example().model_dump(mode="json"),
        "bd_artifact_hash": "bd123",
        "bd_ready": True,
        "architecture_job_id": "AR-1",
        "architecture_artifact": arquitectura_example().model_dump(mode="json"),
        "architecture_artifact_hash": "ar123",
        "scrum_job_id": "SC-1",
        "scrum_artifact": scrum_example().model_dump(mode="json"),
        "scrum_artifact_hash": "sc123",
        "ef_job_id": "EF-1",
        "ef_artifact": ef_example().model_dump(mode="json"),
        "ef_artifact_hash": "ef123",
    }


async def _noop_persist(job_id, artifact, status, metrics):
    """PERSIST sin base de datos: los tests del grafo no escriben en Postgres."""
    return None


async def _correr(persist=None):
    graph = build_api_graph(build_memory_checkpointer())
    config = {
        "configurable": {
            "thread_id": "API-1",
            "llm": ApiMapLLM(),
            "persist": persist or _noop_persist,
        }
    }
    return await graph.ainvoke(_base_state(), config)


# --- El artefacto ---------------------------------------------------------------


async def test_el_pipeline_completo_produce_un_artefacto_valido():
    """La prueba de que las nueve piezas encajan en el contrato de API1."""
    final = await _correr()
    artifact = validate_artifact(final["artifact"])

    assert artifact.schema_version == "1.0.0"
    assert artifact.resources and artifact.endpoints and artifact.schemas
    assert artifact.authorization_matrix and artifact.error_catalog
    assert artifact.rule_mappings and artifact.questions_for_tech_lead
    assert artifact.openapi.content.startswith("openapi: 3.1.0")
    assert artifact.validation.spec_valid is True


async def test_la_cadena_de_origen_queda_completa_y_reproducible():
    final = await _correr()
    source = final["artifact"]["source"]
    assert source["bd_job_id"] == "BD-1"
    assert source["architecture_job_id"] == "AR-1"
    assert source["scrum_job_id"] == "SC-1"
    assert source["ef_job_id"] == "EF-1"
    # El hash que trae el estado gana; la herencia desde el `source` del BD es el
    # fallback, y se prueba en test_load_resource_map.
    assert source["ef_artifact_hash"] == "ef123"
    assert source["bd_artifact_hash"] == "bd123"
    assert source["ready_snapshot"] is True


async def test_ninguna_correccion_del_pipeline_se_pierde_en_el_ensamblado():
    """Las observaciones son el registro de todo lo que se corrigió al modelo.

    Si se quedaran en el estado y no llegaran al artefacto, el usuario vería un
    contrato limpio sin saber que tres acciones propuestas se descartaron.
    """
    final = await _correr()
    observaciones = final["artifact"]["analysis"]["observations"]
    motivos = " ".join(o["reason"] for o in observaciones)

    assert "no aparece literalmente" in motivos  # la acción sin evidencia real
    assert "no existen en el EF" in motivos  # la que citó un proceso inventado
    assert "ya está ocupada" in motivos  # la ruta duplicada
    assert "no se puede pedir el detalle" in motivos  # la PK que quiso ocultarse
    assert all(o["id"].startswith("OBS-") for o in observaciones)


async def test_las_metricas_reflejan_el_contrato_y_lo_que_falta():
    final = await _correr()
    metrics = final["artifact"]["metrics"]
    artifact = final["artifact"]

    assert metrics["resources_total"] == len(artifact["resources"])
    assert metrics["endpoints_total"] == len(artifact["endpoints"])
    assert metrics["schemas_total"] == len(artifact["schemas"])
    assert metrics["auth_rules_total"] == len(artifact["authorization_matrix"])
    assert metrics["tokens"]["total"] > 0
    assert metrics["cost"] > 0
    assert metrics["duration"] >= 0
    # Dos endpoints que nadie puede llamar: el semáforo lo va a usar.
    assert metrics["endpoints_unauthorized"] == 2
    assert metrics["spec_valid"] is True
    assert metrics["coverage"] == final["critique"]["coverage_ratio"]


async def test_la_cuarentena_del_map_llega_a_las_metricas():
    """El recurso que el modelo no supo describir queda contado, no escondido."""
    final = await _correr()
    skipped = final["artifact"]["metrics"]["skipped"]
    assert [s["stage"] for s in skipped] == ["resources"]


# --- Descartes del propio ensamblado -------------------------------------------


def test_un_item_que_viola_el_contrato_se_descarta_con_su_motivo():
    """No tumba el job: entrega el resto señalando la pieza rota.

    Suena permisivo y no lo es: las invariantes que importan viven en el contrato,
    así que un ítem que cae aquí violaba una de ellas, y la observación lo dice con
    el error de validación completo.
    """
    estado = {
        "job_id": "API-1",
        "bd_job_id": "BD-1",
        "bd_artifact_hash": "h",
        "ef_job_id": "EF-1",
        "ef_artifact_hash": "h",
        "schemas": [
            {
                "id": "SCH-001",
                "name": "Roto",
                "kind": "read",
                # Campo sin columna y sin ser calculado: el contrato lo rechaza.
                "fields": [{"id": "SF-001", "name": "x", "logical_type": "string"}],
            }
        ],
    }
    artifact, avisos = assemble_artifact(estado)
    assert artifact.schemas == []
    assert avisos is True
    descarte = next(
        o for o in artifact.analysis.observations if o.id.startswith("OBS-D-")
    )
    assert "schemas" in descarte.description
    assert "columna de origen" in descarte.reason


def test_validate_artifact_rechaza_un_artefacto_corrupto():
    data = ApiArtifact.model_validate(
        assemble_artifact(
            {
                "bd_job_id": "B",
                "bd_artifact_hash": "h",
                "ef_job_id": "E",
                "ef_artifact_hash": "h",
            }
        )[0].model_dump(mode="json")
    ).model_dump(mode="json")
    data["endpoints"] = [{"id": "EP-001"}]  # sin los campos obligatorios
    with pytest.raises(ValidationError):
        validate_artifact(data)


# --- PERSIST --------------------------------------------------------------------


async def test_persist_recibe_el_artefacto_y_marca_avisos():
    """Hubo cuarentena en RESOURCES: el job no puede cerrar COMPLETED limpio."""
    guardado = {}

    async def fake_persist(job_id, artifact, status, metrics):
        guardado.update(
            {
                "job_id": job_id,
                "artifact": artifact,
                "status": status,
                "metrics": metrics,
            }
        )

    final = await _correr(persist=fake_persist)

    assert guardado["job_id"] == "API-1"
    assert guardado["status"] == "COMPLETED_WITH_WARNINGS"
    assert guardado["artifact"]["schema_version"] == "1.0.0"
    assert guardado["metrics"]["endpoints_total"] == len(final["endpoints"])
    assert final["status"] == "COMPLETED_WITH_WARNINGS"


async def test_sin_avisos_el_job_cierra_limpio():
    """Sin cuarentena ni errores de validación, el estado es COMPLETED."""
    estado = {
        "job_id": "API-2",
        "bd_job_id": "BD-1",
        "bd_artifact_hash": "h",
        "ef_job_id": "EF-1",
        "ef_artifact_hash": "h",
        "endpoints": [],
        "metrics": {"tokens": {"input": 1, "output": 1, "total": 2}, "skipped": []},
        "validation": {"spec_valid": True, "errors": []},
    }
    artifact, avisos = assemble_artifact(estado)
    assert avisos is False
    assert artifact.metrics.skipped == []
