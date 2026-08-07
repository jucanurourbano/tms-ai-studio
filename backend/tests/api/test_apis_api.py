"""Tests de la API del Agente API (API8) con pipeline mockeado.

Cubren el gate de entrada (409), el semáforo compuesto que habilita a los Agentes
Backend y Frontend, el ciclo de afinamiento y la descarga del documento OpenAPI
—incluido el JSON, que se re-serializa desde el YAML canónico sin llamar al
modelo—.
"""

import json

import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.services.api_service as api_service
from ai.agents.api.schemas.examples import example_artifact as api_example
from ai.agents.arquitectura.schemas.examples import example_artifact as arch_example
from ai.agents.bd.schemas.examples import example_artifact as bd_example
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from app.dependencies.current_user import get_current_user
from app.dependencies.database import get_session
from app.models.agent import AgentType, EFSourceDocType, JobStatus
from app.models.user import User, UserRole
from app.repositories.agent_job_repository import AgentJobRepository
from app.repositories.ef_repository import EFRepository
from main import app


def _fake_user() -> User:
    return User(
        id="test-user",
        email="qa@urbano.com.pe",
        full_name="QA",
        password_hash="x",
        role=UserRole.ADMIN,
        is_active=True,
    )


async def _seed_chain(factory, *, blocking_bd: bool = False) -> str:
    """Siembra EF → Scrum → Arquitectura → BD y devuelve el job de BD."""
    marca = "block" if blocking_bd else "ok"
    async with factory() as session:
        ef_repo = EFRepository(session)
        doc = await ef_repo.get_or_create_source_doc(
            f"api-ef-hash-{marca}", EFSourceDocType.TEXT
        )
        ef_job = await ef_repo.create_job(
            doc.id, title="Siniestros", source_type="text"
        )
        ef_art = ef_example().model_dump(mode="json")
        await ef_repo.save_artifact(ef_job.id, ef_art, ef_art["schema_version"])
        await ef_repo.update_job_status(ef_job.id, JobStatus.COMPLETED)

        repo = AgentJobRepository(session)
        scrum_job = await repo.create_job(
            AgentType.SCRUM,
            input_job_id=ef_job.id,
            title="Siniestros",
            source_type="text",
        )
        scrum_art = scrum_example().model_dump(mode="json")
        await repo.save_artifact(scrum_job.id, scrum_art, scrum_art["schema_version"])
        await repo.update_job_status(scrum_job.id, JobStatus.COMPLETED)

        arch_job = await repo.create_job(
            AgentType.ARQUITECTURA,
            input_job_id=scrum_job.id,
            title="Siniestros",
            source_type="text",
        )
        arch_art = arch_example().model_dump(mode="json")
        for question in arch_art["questions_for_architect"]:
            question["blocking"] = False
        await repo.save_artifact(arch_job.id, arch_art, arch_art["schema_version"])
        await repo.update_job_status(arch_job.id, JobStatus.COMPLETED)

        bd_job = await repo.create_job(
            AgentType.BD,
            input_job_id=arch_job.id,
            title="Siniestros",
            source_type="text",
        )
        bd_art = bd_example().model_dump(mode="json")
        # El ejemplo de BD nace con preguntas al DBA: el caso "listo" las resuelve
        # explícitamente en vez de dar por hecho que el ejemplo está en verde.
        for question in bd_art["questions_for_dba"]:
            question["blocking"] = blocking_bd
        await repo.save_artifact(bd_job.id, bd_art, bd_art["schema_version"])
        await repo.update_job_metrics(bd_job.id, bd_art["metrics"])
        await repo.update_job_status(bd_job.id, JobStatus.COMPLETED)
        await session.commit()
        return bd_job.id


@pytest_asyncio.fixture
async def ctx(engine, monkeypatch):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_current_user] = _fake_user

    bd_job_id = await _seed_chain(factory)
    llamadas: list[dict] = []

    async def fake_pipeline(
        job_id,
        bd_job_id_,
        bd_artifact,
        bd_artifact_hash,
        architecture_job_id,
        architecture_artifact,
        architecture_artifact_hash,
        scrum_job_id,
        scrum_artifact,
        scrum_artifact_hash,
        ef_job_id,
        ef_artifact,
        ef_artifact_hash,
        bd_ready,
        style_override=None,
        authoritative_context=None,
    ):
        llamadas.append(
            {
                "job_id": job_id,
                "bd_job_id": bd_job_id_,
                "architecture_job_id": architecture_job_id,
                "scrum_job_id": scrum_job_id,
                "ef_job_id": ef_job_id,
                "style_override": style_override,
                "authoritative_context": authoritative_context,
            }
        )
        async with factory() as session:
            repo = AgentJobRepository(session)
            art = api_example().model_dump(mode="json")
            await repo.save_artifact(job_id, art, art["schema_version"])
            await repo.update_job_metrics(job_id, art["metrics"])
            await repo.update_job_status(job_id, JobStatus.COMPLETED)
            await session.commit()

    monkeypatch.setattr(api_service, "run_api_pipeline", fake_pipeline)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, bd_job_id, factory, llamadas

    app.dependency_overrides.clear()


async def _crear_spec(client, bd_job_id, **body) -> str:
    r = await client.post("/api/v1/apis/specs", json={"bd_job_id": bd_job_id, **body})
    assert r.status_code == 200, r.text
    return r.json()["data"]["job_id"]


# --- Gate de entrada -----------------------------------------------------------


async def test_el_gate_rechaza_un_modelo_de_datos_que_no_esta_listo(
    engine, monkeypatch
):
    """409 con un mensaje que dice qué hacer, no solo que falló."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_current_user] = _fake_user
    bd_job_id = await _seed_chain(factory, blocking_bd=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v1/apis/specs", json={"bd_job_id": bd_job_id})

    assert r.status_code == 409
    mensaje = r.json()["message"]
    assert bd_job_id in mensaje
    assert "refine" in mensaje
    app.dependency_overrides.clear()


async def test_un_job_de_otro_agente_no_sirve_de_origen(ctx):
    client, bd_job_id, factory, _ = ctx
    async with factory() as session:
        repo = AgentJobRepository(session)
        ajeno = await repo.create_job(AgentType.SCRUM, title="x", source_type="text")
        await session.commit()
    r = await client.post("/api/v1/apis/specs", json={"bd_job_id": ajeno.id})
    assert r.status_code >= 400


# --- Creación ------------------------------------------------------------------


async def test_crear_una_especificacion_enlaza_la_cadena_completa(ctx):
    client, bd_job_id, _, llamadas = ctx
    job_id = await _crear_spec(client, bd_job_id)

    r = await client.get(f"/api/v1/apis/jobs/{job_id}")
    datos = r.json()["data"]
    assert datos["input_job_id"] == bd_job_id  # el predecesor directo

    # Y el pipeline recibió los cuatro eslabones, resueltos transitivamente.
    llamada = llamadas[0]
    assert llamada["bd_job_id"] == bd_job_id
    assert llamada["architecture_job_id"]
    assert llamada["scrum_job_id"]
    assert llamada["ef_job_id"]


async def test_el_estilo_forzado_llega_al_pipeline(ctx):
    client, bd_job_id, _, llamadas = ctx
    await _crear_spec(client, bd_job_id, style_override="rest")
    assert llamadas[0]["style_override"] == "rest"


async def test_los_modelos_disponibles_marcan_cuales_estan_listos(ctx):
    client, bd_job_id, _, _ = ctx
    r = await client.get("/api/v1/apis/available-bd-jobs")
    items = r.json()["data"]["items"]
    nuestro = next(i for i in items if i["job_id"] == bd_job_id)
    assert nuestro["ready_for_next_stage"] is True
    assert nuestro["blocking_pending"] == []


# --- Artefacto y documento ------------------------------------------------------


async def test_el_artefacto_se_devuelve_completo(ctx):
    client, bd_job_id, _, _ = ctx
    job_id = await _crear_spec(client, bd_job_id)
    r = await client.get(f"/api/v1/apis/jobs/{job_id}/artifact")
    artifact = r.json()["data"]
    assert artifact["schema_version"] == "1.0.0"
    assert artifact["endpoints"] and artifact["authorization_matrix"]


async def test_el_openapi_se_sirve_en_yaml_canonico(ctx):
    client, bd_job_id, _, _ = ctx
    job_id = await _crear_spec(client, bd_job_id)
    r = await client.get(f"/api/v1/apis/jobs/{job_id}/openapi")
    datos = r.json()["data"]
    assert datos["format"] == "yaml"
    assert datos["spec_version"] == "3.1.0"
    assert datos["valid"] is True
    assert datos["content"].startswith("openapi: 3.1.0")
    assert datos["checksum"].startswith("sha256:")


async def test_el_json_es_la_misma_especificacion_sin_llamar_al_modelo(ctx):
    """Mismo dividendo que el DDL por motor del Agente BD: re-serializar es gratis."""
    client, bd_job_id, _, _ = ctx
    job_id = await _crear_spec(client, bd_job_id)

    yaml_resp = await client.get(f"/api/v1/apis/jobs/{job_id}/openapi")
    json_resp = await client.get(
        f"/api/v1/apis/jobs/{job_id}/openapi", params={"formato": "json"}
    )
    del_yaml = yaml.safe_load(yaml_resp.json()["data"]["content"])
    del_json = json.loads(json_resp.json()["data"]["content"])
    assert del_yaml == del_json


async def test_el_documento_se_puede_descargar_como_archivo(ctx):
    client, bd_job_id, _, _ = ctx
    job_id = await _crear_spec(client, bd_job_id)
    r = await client.get(
        f"/api/v1/apis/jobs/{job_id}/openapi", params={"descargar": True}
    )
    assert r.headers["content-type"].startswith("application/yaml")
    assert f'filename="openapi_{job_id}.yaml"' in r.headers["content-disposition"]
    assert r.text.startswith("openapi: 3.1.0")


async def test_un_job_sin_artefacto_no_finge_un_documento(ctx):
    client, _, factory, _ = ctx
    async with factory() as session:
        repo = AgentJobRepository(session)
        vacio = await repo.create_job(AgentType.API, title="x", source_type="text")
        await session.commit()
    r = await client.get(f"/api/v1/apis/jobs/{vacio.id}/openapi")
    assert r.json()["success"] is False


# --- Semáforo compuesto ---------------------------------------------------------


async def test_una_pregunta_bloqueante_sin_responder_deja_el_semaforo_en_rojo(ctx):
    client, bd_job_id, _, _ = ctx
    job_id = await _crear_spec(client, bd_job_id)

    r = await client.get(f"/api/v1/apis/jobs/{job_id}/validations")
    datos = r.json()["data"]
    assert datos["ready_for_next_stage"] is False
    assert datos["blocking_pending"] == ["Q-001"]
    # El resto del contenido mínimo sí se cumple: el hueco está localizado.
    assert datos["checks"]["has_endpoints"] is True
    assert datos["checks"]["spec_valid"] is True
    assert datos["checks"]["no_blocking_questions"] is False


async def test_al_responder_la_bloqueante_el_contrato_habilita_a_backend_y_frontend(
    ctx,
):
    client, bd_job_id, _, _ = ctx
    job_id = await _crear_spec(client, bd_job_id)

    r = await client.patch(
        f"/api/v1/apis/jobs/{job_id}/validations",
        json={
            "target_id": "Q-001",
            "status": "corregido",
            "respuesta": "El jefe ve solo los de su equipo; se añade equipo_id.",
        },
    )
    assert r.status_code == 200

    datos = (await client.get(f"/api/v1/apis/jobs/{job_id}/validations")).json()["data"]
    assert datos["blocking_pending"] == []
    assert datos["ready_for_next_stage"] is True
    assert all(datos["checks"].values())


async def test_un_endpoint_sin_autorizar_deja_el_semaforo_en_rojo(ctx):
    """Aunque el documento sea válido y no queden preguntas.

    Un contrato con una operación que nadie puede llamar no habilita a construir:
    el Agente Backend generaría código muerto.
    """
    client, bd_job_id, factory, _ = ctx
    job_id = await _crear_spec(client, bd_job_id)

    async with factory() as session:
        repo = AgentJobRepository(session)
        art = api_example().model_dump(mode="json")
        art["questions_for_tech_lead"] = []
        art["metrics"]["endpoints_unauthorized"] = 1
        await repo.save_artifact(job_id, art, art["schema_version"])
        await session.commit()

    datos = (await client.get(f"/api/v1/apis/jobs/{job_id}/validations")).json()["data"]
    assert datos["blocking_pending"] == []
    assert datos["checks"]["all_endpoints_authorized"] is False
    assert datos["ready_for_next_stage"] is False


async def test_una_especificacion_invalida_deja_el_semaforo_en_rojo(ctx):
    client, bd_job_id, factory, _ = ctx
    job_id = await _crear_spec(client, bd_job_id)

    async with factory() as session:
        repo = AgentJobRepository(session)
        art = api_example().model_dump(mode="json")
        art["questions_for_tech_lead"] = []
        art["validation"]["spec_valid"] = False
        await repo.save_artifact(job_id, art, art["schema_version"])
        await session.commit()

    datos = (await client.get(f"/api/v1/apis/jobs/{job_id}/validations")).json()["data"]
    assert datos["checks"]["spec_valid"] is False
    assert datos["ready_for_next_stage"] is False


# --- Refine ---------------------------------------------------------------------


async def test_no_hay_refine_sin_respuestas_que_reinyectar(ctx):
    client, bd_job_id, _, _ = ctx
    job_id = await _crear_spec(client, bd_job_id)
    r = await client.post(f"/api/v1/apis/jobs/{job_id}/refine")
    assert r.status_code >= 400


async def test_el_refine_reinyecta_las_respuestas_y_conserva_el_estilo(ctx):
    client, bd_job_id, _, llamadas = ctx
    job_id = await _crear_spec(client, bd_job_id)
    await client.patch(
        f"/api/v1/apis/jobs/{job_id}/validations",
        json={
            "target_id": "Q-001",
            "status": "corregido",
            "respuesta": "Solo los de su equipo.",
        },
    )

    r = await client.post(f"/api/v1/apis/jobs/{job_id}/refine")
    assert r.status_code == 200
    hijo = r.json()["data"]
    assert hijo["parent_job_id"] == job_id
    assert hijo["version"] == 2

    llamada = llamadas[-1]
    assert llamada["job_id"] == hijo["job_id"]
    assert "Solo los de su equipo." in llamada["authoritative_context"]
    # Afinar el contrato no cambia la clase de API que se está diseñando.
    assert llamada["style_override"] == "rest"


# --- Listado --------------------------------------------------------------------


async def test_el_listado_pagina_y_cuenta_por_estado(ctx):
    client, bd_job_id, _, _ = ctx
    await _crear_spec(client, bd_job_id)
    await _crear_spec(client, bd_job_id)

    r = await client.get("/api/v1/apis/jobs", params={"limit": 1})
    datos = r.json()["data"]
    assert datos["total"] == 2
    assert len(datos["items"]) == 1
    assert datos["status_counts"]
    assert datos["items"][0]["input_job_id"] == bd_job_id
