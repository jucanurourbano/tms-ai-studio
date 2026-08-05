"""Tests de la API del Agente BD (BD7) con pipeline mockeado.

Cubren el gate de entrada (409), el semáforo compuesto que habilita al Agente API,
el ciclo de afinamiento y el export del DDL —incluido el re-render a otro motor,
que es coste cero por el diseño de doble nivel de tipo (DB2)—.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.services.bd_service as bd_service
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


async def _seed_chain(factory, *, blocking_arch: bool = False) -> str:
    """Siembra la cadena EF → Scrum → Arquitectura y devuelve el job de Arquitectura."""
    marca = "block" if blocking_arch else "ok"
    async with factory() as session:
        ef_repo = EFRepository(session)
        doc = await ef_repo.get_or_create_source_doc(
            f"ef-hash-{marca}", EFSourceDocType.TEXT
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
        # El ejemplo de Arquitectura nace CON una pregunta bloqueante (el contrato
        # de la integración de Planillas), así que el caso "listo" la resuelve
        # explícitamente en vez de dar por hecho que el ejemplo está en verde.
        for question in arch_art["questions_for_architect"]:
            question["blocking"] = blocking_arch
        await repo.save_artifact(arch_job.id, arch_art, arch_art["schema_version"])
        await repo.update_job_metrics(arch_job.id, arch_art["metrics"])
        await repo.update_job_status(arch_job.id, JobStatus.COMPLETED)
        await session.commit()
        return arch_job.id


@pytest_asyncio.fixture
async def ctx(engine, monkeypatch):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_current_user] = _fake_user

    arch_job_id = await _seed_chain(factory)
    llamadas: list[dict] = []

    async def fake_pipeline(
        job_id,
        architecture_job_id,
        architecture_artifact,
        architecture_artifact_hash,
        scrum_job_id,
        scrum_artifact,
        scrum_artifact_hash,
        ef_job_id,
        ef_artifact,
        ef_artifact_hash,
        architecture_ready,
        engine_override=None,
        authoritative_context=None,
    ):
        llamadas.append(
            {
                "job_id": job_id,
                "architecture_job_id": architecture_job_id,
                "scrum_job_id": scrum_job_id,
                "ef_job_id": ef_job_id,
                "engine_override": engine_override,
                "authoritative_context": authoritative_context,
            }
        )
        async with factory() as session:
            repo = AgentJobRepository(session)
            art = bd_example().model_dump(mode="json")
            await repo.save_artifact(job_id, art, art["schema_version"])
            await repo.update_job_metrics(job_id, art["metrics"])
            await repo.update_job_status(job_id, JobStatus.COMPLETED)
            await session.commit()

    monkeypatch.setattr(bd_service, "run_bd_pipeline", fake_pipeline)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, arch_job_id, factory, llamadas

    app.dependency_overrides.clear()


async def _crear_modelo(client, arch_job_id, **body) -> str:
    r = await client.post(
        "/api/v1/bd/models", json={"architecture_job_id": arch_job_id, **body}
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["job_id"]


# --- Gate de entrada --------------------------------------------------------


async def test_modelo_rechazado_si_la_arquitectura_no_esta_lista(ctx):
    client, _, factory, _ = ctx
    not_ready = await _seed_chain(factory, blocking_arch=True)
    r = await client.post("/api/v1/bd/models", json={"architecture_job_id": not_ready})
    assert r.status_code == 409
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "GateError"
    assert "no está listo" in body["message"]
    # El mensaje dice cómo desbloquear, no solo que falló.
    assert "refine" in body["message"]


async def test_arquitectura_inexistente_400(ctx):
    client, _, _, _ = ctx
    r = await client.post("/api/v1/bd/models", json={"architecture_job_id": "NOPE"})
    assert r.status_code == 400
    assert r.json()["data"]["code"] == "IngestError"


async def test_motor_fuera_del_allow_list_se_rechaza_en_el_request(ctx):
    """La validación del enum ocurre antes de tocar nada: 422 de FastAPI."""
    client, arch_job_id, _, _ = ctx
    r = await client.post(
        "/api/v1/bd/models",
        json={"architecture_job_id": arch_job_id, "engine_override": "sqlite"},
    )
    assert r.status_code == 422


# --- Creación y linaje ------------------------------------------------------


async def test_modelo_ok_y_artefacto(ctx):
    client, arch_job_id, _, _ = ctx
    job_id = await _crear_modelo(client, arch_job_id)

    r = await client.get(f"/api/v1/bd/jobs/{job_id}")
    data = r.json()["data"]
    assert data["status"] == "COMPLETED"
    assert data["input_job_id"] == arch_job_id

    r = await client.get(f"/api/v1/bd/jobs/{job_id}/artifact")
    art = r.json()["data"]
    assert art["schema_version"] == "1.0.0"
    assert art["tables"]


async def test_el_pipeline_recibe_la_cadena_completa(ctx):
    """El EF (dos saltos arriba) llega resuelto, no hay que pedirlo aparte."""
    client, arch_job_id, _, llamadas = ctx
    await _crear_modelo(client, arch_job_id)

    llamada = llamadas[-1]
    assert llamada["architecture_job_id"] == arch_job_id
    assert llamada["scrum_job_id"]
    assert llamada["ef_job_id"]
    assert llamada["scrum_job_id"] != llamada["ef_job_id"]


async def test_el_override_de_motor_llega_al_pipeline(ctx):
    client, arch_job_id, _, llamadas = ctx
    await _crear_modelo(client, arch_job_id, engine_override="postgresql")
    assert llamadas[-1]["engine_override"] == "postgresql"


async def test_listado_de_arquitecturas_marca_cuales_estan_listas(ctx):
    client, arch_job_id, factory, _ = ctx
    bloqueada = await _seed_chain(factory, blocking_arch=True)

    r = await client.get("/api/v1/bd/available-architecture-jobs")
    items = {i["job_id"]: i for i in r.json()["data"]["items"]}
    assert items[arch_job_id]["ready_for_next_stage"] is True
    assert items[bloqueada]["ready_for_next_stage"] is False
    assert items[bloqueada]["blocking_pending"]


async def test_listado_de_jobs_con_contadores(ctx):
    client, arch_job_id, _, _ = ctx
    await _crear_modelo(client, arch_job_id)

    r = await client.get("/api/v1/bd/jobs")
    data = r.json()["data"]
    assert data["total"] >= 1
    assert data["status_counts"]
    assert data["items"][0]["input_job_id"] == arch_job_id


# --- Semáforo compuesto -----------------------------------------------------


async def test_el_semaforo_verde_habilita_al_agente_API(ctx):
    client, arch_job_id, _, _ = ctx
    job_id = await _crear_modelo(client, arch_job_id)

    r = await client.get(f"/api/v1/bd/jobs/{job_id}/validations")
    data = r.json()["data"]
    assert data["ready_for_next_stage"] is True
    assert data["checks"] == {
        "no_blocking_questions": True,
        "has_tables": True,
        "all_tables_have_pk": True,
        "coverage_met": True,
        "ddl_valid": True,
    }


async def test_una_tabla_sin_pk_deja_el_semaforo_en_rojo(ctx):
    """Aunque nadie haya dejado preguntas sin responder: el modelo no sirve."""
    client, arch_job_id, factory, _ = ctx
    job_id = await _crear_modelo(client, arch_job_id)

    async with factory() as session:
        repo = AgentJobRepository(session)
        art = (await repo.get_artifact(job_id)).data
        art["tables"][0]["primary_key"] = None
        await repo.save_artifact(job_id, art, art["schema_version"])
        await session.commit()

    r = await client.get(f"/api/v1/bd/jobs/{job_id}/validations")
    data = r.json()["data"]
    assert data["checks"]["all_tables_have_pk"] is False
    assert data["ready_for_next_stage"] is False


async def test_un_ddl_invalido_deja_el_semaforo_en_rojo(ctx):
    client, arch_job_id, factory, _ = ctx
    job_id = await _crear_modelo(client, arch_job_id)

    async with factory() as session:
        repo = AgentJobRepository(session)
        art = (await repo.get_artifact(job_id)).data
        art["validation"]["syntax_ok"] = False
        art["validation"]["errors"] = [
            {"code": "fk_target_missing", "message": "…", "ref": "FK-001"}
        ]
        await repo.save_artifact(job_id, art, art["schema_version"])
        await session.commit()

    r = await client.get(f"/api/v1/bd/jobs/{job_id}/validations")
    assert r.json()["data"]["checks"]["ddl_valid"] is False
    assert r.json()["data"]["ready_for_next_stage"] is False


async def test_una_pregunta_bloqueante_pendiente_frena_el_semaforo(ctx):
    client, arch_job_id, factory, _ = ctx
    job_id = await _crear_modelo(client, arch_job_id)

    async with factory() as session:
        repo = AgentJobRepository(session)
        art = (await repo.get_artifact(job_id)).data
        art["questions_for_dba"][0]["blocking"] = True
        await repo.save_artifact(job_id, art, art["schema_version"])
        await session.commit()

    r = await client.get(f"/api/v1/bd/jobs/{job_id}/validations")
    assert r.json()["data"]["ready_for_next_stage"] is False
    assert r.json()["data"]["blocking_pending"] == ["Q-001"]

    # Responderla la desbloquea.
    r = await client.patch(
        f"/api/v1/bd/jobs/{job_id}/validations",
        json={
            "target_id": "Q-001",
            "status": "confirmado",
            "respuesta": "NUMERIC(12,2)",
        },
    )
    assert r.status_code == 200
    r = await client.get(f"/api/v1/bd/jobs/{job_id}/validations")
    assert r.json()["data"]["ready_for_next_stage"] is True


# --- Export del DDL ---------------------------------------------------------


async def test_el_ddl_se_devuelve_en_json(ctx):
    client, arch_job_id, _, _ = ctx
    job_id = await _crear_modelo(client, arch_job_id)

    r = await client.get(f"/api/v1/bd/jobs/{job_id}/ddl")
    data = r.json()["data"]
    assert data["engine"] == "postgresql"
    assert data["regenerated"] is False
    assert data["scripts"]
    assert "CREATE TABLE" in data["sql"]


async def test_el_ddl_se_descarga_como_archivo_sql(ctx):
    client, arch_job_id, _, _ = ctx
    job_id = await _crear_modelo(client, arch_job_id)

    r = await client.get(f"/api/v1/bd/jobs/{job_id}/ddl?formato=sql")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/sql")
    assert ".sql" in r.headers["content-disposition"]
    assert "CREATE TABLE" in r.text


async def test_cambiar_de_motor_re_renderiza_sin_tocar_el_artefacto(ctx):
    """La ventaja de DB2: otro dialecto cuesta cero llamadas al modelo."""
    client, arch_job_id, _, _ = ctx
    job_id = await _crear_modelo(client, arch_job_id)

    r = await client.get(f"/api/v1/bd/jobs/{job_id}/ddl?engine=oracle")
    data = r.json()["data"]
    assert data["engine"] == "oracle"
    assert data["engine_of_record"] == "postgresql"
    assert data["regenerated"] is True
    # Tipos traducidos al dialecto pedido.
    assert "VARCHAR2" in data["sql"]
    assert "public." not in data["sql"]  # Oracle no prefija esquema

    # Y el artefacto sigue diciendo lo que decidió la arquitectura.
    r = await client.get(f"/api/v1/bd/jobs/{job_id}/artifact")
    assert r.json()["data"]["target"]["engine"] == "postgresql"


async def test_motor_desconocido_en_el_export_se_rechaza(ctx):
    client, arch_job_id, _, _ = ctx
    job_id = await _crear_modelo(client, arch_job_id)
    r = await client.get(f"/api/v1/bd/jobs/{job_id}/ddl?engine=mongodb")
    assert r.status_code == 422


async def test_ddl_de_un_job_sin_artefacto(ctx):
    client, _, _, _ = ctx
    r = await client.get("/api/v1/bd/jobs/NOPE/ddl")
    assert r.json()["success"] is False


# --- Refine -----------------------------------------------------------------


async def test_refine_crea_job_hijo_con_contexto_autoritativo(ctx):
    client, arch_job_id, _, llamadas = ctx
    job_id = await _crear_modelo(client, arch_job_id)

    await client.patch(
        f"/api/v1/bd/jobs/{job_id}/validations",
        json={
            "target_id": "Q-001",
            "status": "corregido",
            "respuesta": "El monto usa NUMERIC(14,2).",
        },
    )
    r = await client.post(f"/api/v1/bd/jobs/{job_id}/refine")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["parent_job_id"] == job_id

    llamada = llamadas[-1]
    assert llamada["job_id"] == data["job_id"]
    assert "NUMERIC(14,2)" in llamada["authoritative_context"]
    # El refine conserva el motor del job original: afina el modelo, no cambia
    # la plataforma sobre la que se construye.
    assert llamada["engine_override"] == "postgresql"
    # Y sigue colgando del mismo diseño de arquitectura.
    assert llamada["architecture_job_id"] == arch_job_id


async def test_refine_sin_respuestas_no_procede(ctx):
    client, arch_job_id, _, _ = ctx
    job_id = await _crear_modelo(client, arch_job_id)
    r = await client.post(f"/api/v1/bd/jobs/{job_id}/refine")
    assert r.status_code == 400
    assert "validaciones respondidas" in r.json()["message"]


async def test_refine_de_un_job_que_no_es_de_BD(ctx):
    client, arch_job_id, _, _ = ctx
    r = await client.post(f"/api/v1/bd/jobs/{arch_job_id}/refine")
    assert r.status_code == 400
    assert r.json()["data"]["code"] == "IngestError"
