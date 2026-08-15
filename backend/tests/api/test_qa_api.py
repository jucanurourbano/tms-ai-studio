"""Tests de la API del Agente QA (QA6) con pipeline mockeado.

Cubren el gate de entrada (409), el semáforo, el ciclo de afinamiento y —el eje de
este agente— la **validación de que el contrato de API indicado pertenezca a la
cadena del plan**. Sin esa comprobación, un plan de pruebas diseñaría casos de
autorización contra el contrato de otro proyecto: casos perfectamente formados,
citando reglas reales, probando otro sistema.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.services.qa_service as qa_service
from ai.agents.api.schemas.examples import example_artifact as api_example
from ai.agents.arquitectura.schemas.examples import example_artifact as arch_example
from ai.agents.bd.schemas.examples import example_artifact as bd_example
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.qa.schemas.examples import example_artifact as qa_example
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


async def _seed_chain(
    factory, *, marca: str = "ok", blocking_scrum: bool = False
) -> dict:
    """Siembra EF → Scrum → Arquitectura → BD → API y devuelve los ids."""
    async with factory() as session:
        ef_repo = EFRepository(session)
        doc = await ef_repo.get_or_create_source_doc(
            f"qa-ef-hash-{marca}", EFSourceDocType.TEXT
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
        # El ejemplo de Scrum nace con preguntas al PO: el caso "listo" las resuelve
        # explícitamente en vez de dar por hecho que el ejemplo está en verde.
        for question in scrum_art["questions_for_po"]:
            question["blocking"] = blocking_scrum
        await repo.save_artifact(scrum_job.id, scrum_art, scrum_art["schema_version"])
        await repo.update_job_metrics(scrum_job.id, scrum_art["metrics"])
        await repo.update_job_status(scrum_job.id, JobStatus.COMPLETED)

        arch_job = await repo.create_job(
            AgentType.ARQUITECTURA,
            input_job_id=scrum_job.id,
            title="Siniestros",
            source_type="text",
        )
        arch_art = arch_example().model_dump(mode="json")
        await repo.save_artifact(arch_job.id, arch_art, arch_art["schema_version"])
        await repo.update_job_status(arch_job.id, JobStatus.COMPLETED)

        bd_job = await repo.create_job(
            AgentType.BD,
            input_job_id=arch_job.id,
            title="Siniestros",
            source_type="text",
        )
        bd_art = bd_example().model_dump(mode="json")
        await repo.save_artifact(bd_job.id, bd_art, bd_art["schema_version"])
        await repo.update_job_status(bd_job.id, JobStatus.COMPLETED)

        api_job = await repo.create_job(
            AgentType.API,
            input_job_id=bd_job.id,
            title="Siniestros",
            source_type="text",
        )
        api_art = api_example().model_dump(mode="json")
        await repo.save_artifact(api_job.id, api_art, api_art["schema_version"])
        await repo.update_job_status(api_job.id, JobStatus.COMPLETED)

        await session.commit()
        return {"scrum": scrum_job.id, "api": api_job.id, "ef": ef_job.id}


@pytest_asyncio.fixture
async def ctx(engine, monkeypatch):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_current_user] = _fake_user

    ids = await _seed_chain(factory)
    llamadas: list[dict] = []

    async def fake_pipeline(
        job_id,
        scrum_job_id,
        scrum_artifact,
        scrum_artifact_hash,
        ef_job_id,
        ef_artifact,
        ef_artifact_hash,
        scrum_ready,
        api_job_id=None,
        api_artifact=None,
        api_artifact_hash=None,
        target_overrides=None,
        authoritative_context=None,
    ):
        llamadas.append(
            {
                "job_id": job_id,
                "scrum_job_id": scrum_job_id,
                "ef_job_id": ef_job_id,
                "api_job_id": api_job_id,
                "target_overrides": target_overrides,
                "authoritative_context": authoritative_context,
            }
        )
        async with factory() as session:
            repo = AgentJobRepository(session)
            art = qa_example().model_dump(mode="json")
            # El artefacto guardado apunta a los ids REALES que recibió el pipeline,
            # como haría el de verdad. Dejar los sintéticos del fixture haría que el
            # refine buscara un contrato que no existe y el fallo se leería como un
            # bug del refine en vez de como lo que sería: datos inconsistentes.
            art["source"] |= {
                "scrum_job_id": scrum_job_id,
                "ef_job_id": ef_job_id,
                "api_job_id": api_job_id,
                "api_available": bool(api_job_id),
                "api_artifact_hash": api_artifact_hash if api_job_id else None,
                "api_absent_reason": None if api_job_id else "Sin contrato indicado.",
            }
            await repo.save_artifact(job_id, art, art["schema_version"])
            await repo.update_job_metrics(job_id, art["metrics"])
            await repo.update_job_status(job_id, JobStatus.COMPLETED)
            await session.commit()

    monkeypatch.setattr(qa_service, "run_qa_pipeline", fake_pipeline)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, ids, factory, llamadas

    app.dependency_overrides.clear()


async def _crear_plan(client, scrum_job_id, **body) -> str:
    r = await client.post(
        "/api/v1/qa/plans", json={"scrum_job_id": scrum_job_id, **body}
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["job_id"]


# --- Gate de entrada -----------------------------------------------------------


async def test_el_gate_rechaza_un_plan_scrum_que_no_esta_listo(engine, monkeypatch):
    """409 con un mensaje que dice qué hacer, no solo que falló."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_current_user] = _fake_user
    ids = await _seed_chain(factory, marca="block", blocking_scrum=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/qa/plans", json={"scrum_job_id": ids["scrum"]})
    assert r.status_code == 409
    cuerpo = r.json()
    assert cuerpo["success"] is False
    assert "refine" in cuerpo["message"]
    app.dependency_overrides.clear()


async def test_un_plan_scrum_inexistente_da_error_claro(ctx):
    client, _ids, _factory, _ = ctx
    r = await client.post("/api/v1/qa/plans", json={"scrum_job_id": "no-existe"})
    assert r.status_code in (400, 404, 422)
    assert "no existe" in r.json()["message"].lower()


# --- El contrato de API: la excepción estructural ------------------------------


async def test_se_puede_generar_sin_contrato_de_api(ctx):
    """La dependencia es opcional: sin ella el plan se genera igual."""
    client, ids, _factory, llamadas = ctx
    await _crear_plan(client, ids["scrum"])
    assert llamadas[0]["api_job_id"] is None


async def test_el_contrato_de_la_misma_cadena_se_acepta(ctx):
    client, ids, _factory, llamadas = ctx
    await _crear_plan(client, ids["scrum"], api_job_id=ids["api"])
    assert llamadas[0]["api_job_id"] == ids["api"]


async def test_un_contrato_de_OTRA_cadena_se_rechaza(ctx):
    """El corazón de QA-D1: el vínculo se verifica, no se supone."""
    client, ids, factory, _ = ctx
    otros = await _seed_chain(factory, marca="otra-cadena")
    r = await client.post(
        "/api/v1/qa/plans",
        json={"scrum_job_id": ids["scrum"], "api_job_id": otros["api"]},
    )
    assert r.status_code == 409
    mensaje = r.json()["message"]
    assert "no pertenece a la cadena" in mensaje
    assert "otro sistema" in mensaje


async def test_un_contrato_inexistente_da_error_claro(ctx):
    client, ids, _factory, _ = ctx
    r = await client.post(
        "/api/v1/qa/plans",
        json={"scrum_job_id": ids["scrum"], "api_job_id": "no-existe"},
    )
    assert r.status_code in (400, 404, 422)
    assert "contrato de api" in r.json()["message"].lower()


async def test_los_contratos_compatibles_se_pueden_listar(ctx):
    """El descubrimiento existe como ayuda; la elección es del QA lead."""
    client, ids, factory, _ = ctx
    otros = await _seed_chain(factory, marca="otra-cadena-2")
    r = await client.get(
        "/api/v1/qa/compatible-api-jobs", params={"scrum_job_id": ids["scrum"]}
    )
    assert r.status_code == 200
    devueltos = {i["job_id"] for i in r.json()["data"]["items"]}
    assert ids["api"] in devueltos
    assert otros["api"] not in devueltos


# --- Umbrales ------------------------------------------------------------------


async def test_los_umbrales_de_la_peticion_llegan_al_pipeline(ctx):
    client, ids, _factory, llamadas = ctx
    await _crear_plan(
        client,
        ids["scrum"],
        coverage_threshold=0.9,
        max_cases_per_criterion=3,
        manual_capacity_minutes=480,
    )
    assert llamadas[0]["target_overrides"] == {
        "coverage_threshold": 0.9,
        "max_cases_per_criterion": 3,
        "manual_capacity_minutes": 480,
    }


async def test_sin_umbrales_no_se_inventan_overrides(ctx):
    client, ids, _factory, llamadas = ctx
    await _crear_plan(client, ids["scrum"])
    assert llamadas[0]["target_overrides"] is None


# --- Lectura y semáforo --------------------------------------------------------


async def test_el_artefacto_se_devuelve_completo(ctx):
    client, ids, _factory, _ = ctx
    job_id = await _crear_plan(client, ids["scrum"])
    r = await client.get(f"/api/v1/qa/jobs/{job_id}/artifact")
    assert r.status_code == 200
    datos = r.json()["data"]
    assert datos["schema_version"] == "1.0.0"
    assert datos["test_cases"]
    assert datos["trace_matrix"]["rows"]


async def test_el_semaforo_bloquea_con_preguntas_pendientes(ctx):
    """El fixture trae una bloqueante (AUTH-002 ambigua): no está listo."""
    client, ids, _factory, _ = ctx
    job_id = await _crear_plan(client, ids["scrum"])
    r = await client.get(f"/api/v1/qa/jobs/{job_id}/validations")
    datos = r.json()["data"]
    assert datos["blocking_total"] == 1
    assert datos["blocking_pending"] == ["QQ-001"]
    assert datos["ready_for_next_stage"] is False


async def test_al_responder_la_bloqueante_el_plan_queda_listo(ctx):
    client, ids, _factory, _ = ctx
    job_id = await _crear_plan(client, ids["scrum"])
    r = await client.patch(
        f"/api/v1/qa/jobs/{job_id}/validations",
        json={
            "target_id": "QQ-001",
            "status": "corregido",
            "respuesta": "La columna es siniestros.equipo_id, se añade en el modelo.",
        },
    )
    assert r.status_code == 200
    datos = (await client.get(f"/api/v1/qa/jobs/{job_id}/validations")).json()["data"]
    assert datos["blocking_pending"] == []
    assert datos["checks"]["no_blocking_questions"] is True
    assert datos["checks"]["has_test_cases"] is True
    assert datos["checks"]["all_cases_anchored"] is True
    assert datos["checks"]["blocking_coverage_met"] is True
    assert datos["ready_for_next_stage"] is True


async def test_el_semaforo_detecta_un_caso_sin_criterio_en_la_matriz(ctx):
    """Un caso cuyo criterio no está en la matriz vendría de la nada."""
    client, ids, factory, _ = ctx
    job_id = await _crear_plan(client, ids["scrum"])
    async with factory() as session:
        repo = AgentJobRepository(session)
        art = qa_example().model_dump(mode="json")
        art["test_cases"][0]["criterion_ref"] = "AC-999"
        await repo.save_artifact(job_id, art, art["schema_version"])
        await session.commit()
    datos = (await client.get(f"/api/v1/qa/jobs/{job_id}/validations")).json()["data"]
    assert datos["checks"]["all_cases_anchored"] is False
    assert datos["ready_for_next_stage"] is False


async def test_el_listado_pagina_y_cuenta(ctx):
    client, ids, _factory, _ = ctx
    await _crear_plan(client, ids["scrum"])
    r = await client.get("/api/v1/qa/jobs", params={"limit": 10})
    datos = r.json()["data"]
    assert datos["total"] >= 1
    assert datos["items"][0]["input_job_id"] == ids["scrum"]
    assert "status_counts" in datos


async def test_los_planes_scrum_disponibles_se_marcan(ctx):
    client, ids, _factory, _ = ctx
    r = await client.get("/api/v1/qa/available-scrum-jobs")
    items = {i["job_id"]: i for i in r.json()["data"]["items"]}
    assert items[ids["scrum"]]["ready_for_next_stage"] is True


# --- Refine --------------------------------------------------------------------


async def test_el_refine_reinyecta_las_respuestas(ctx):
    client, ids, _factory, llamadas = ctx
    job_id = await _crear_plan(client, ids["scrum"], api_job_id=ids["api"])
    await client.patch(
        f"/api/v1/qa/jobs/{job_id}/validations",
        json={
            "target_id": "QQ-001",
            "status": "corregido",
            "respuesta": "La columna es siniestros.equipo_id.",
        },
    )
    r = await client.post(f"/api/v1/qa/jobs/{job_id}/refine")
    assert r.status_code == 200, r.text
    datos = r.json()["data"]
    assert datos["parent_job_id"] == job_id
    assert datos["version"] == 2
    ultima = llamadas[-1]
    assert "equipo_id" in ultima["authoritative_context"]
    # El contrato de API del job original se conserva: afinar el plan no cambia
    # contra qué contrato se probó.
    assert ultima["api_job_id"] == ids["api"]


async def test_el_refine_no_degrada_si_el_contrato_ya_no_esta(ctx):
    """Perder una clase entera de casos entre versiones, y en silencio, es peor.

    Si el contrato con el que se generó el plan desapareció, afinar sin él dejaría
    la versión 2 sin casos de autorización sin que nadie lo hubiera pedido, y la
    comparación entre versiones mostraría una caída de cobertura inexplicable.
    """
    client, ids, factory, _ = ctx
    job_id = await _crear_plan(client, ids["scrum"], api_job_id=ids["api"])
    await client.patch(
        f"/api/v1/qa/jobs/{job_id}/validations",
        json={"target_id": "QQ-001", "status": "confirmado", "respuesta": "ok"},
    )
    # El artefacto apunta a un contrato que ya no existe.
    async with factory() as session:
        repo = AgentJobRepository(session)
        art = (await repo.get_artifact(job_id)).data
        art["source"]["api_job_id"] = "01APDESAPARECIDO0000000000"
        await repo.save_artifact(job_id, art, art["schema_version"])
        await session.commit()

    r = await client.post(f"/api/v1/qa/jobs/{job_id}/refine")
    assert r.status_code == 409
    mensaje = r.json()["message"]
    assert "ya no está disponible" in mensaje
    assert "sin casos de autorización" in mensaje


async def test_el_refine_sin_respuestas_se_rechaza(ctx):
    client, ids, _factory, _ = ctx
    job_id = await _crear_plan(client, ids["scrum"])
    r = await client.post(f"/api/v1/qa/jobs/{job_id}/refine")
    assert r.status_code in (400, 404, 422)
    assert "no hay validaciones" in r.json()["message"].lower()
