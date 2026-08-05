"""Tests de los selectores de job de origen (los tres agentes encadenados).

Regla común: un selector **solo puede ofrecer lo que se puede consumir**. Un job
fallido o en curso no tiene artefacto, así que aparecer en la lista solo produciría
un rechazo del gate y la sensación de que la aplicación se contradice. Los que sí
terminaron pero no están listos se devuelven **marcados**, para que el selector
pueda mostrarlos como "casi listos" con lo que les falta.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from ai.agents.arquitectura.schemas.examples import example_artifact as arch_example
from ai.agents.ef.schemas.examples import example_artifact as ef_example
from ai.agents.scrum.schemas.examples import example_artifact as scrum_example
from app.models.agent import USABLE_JOB_STATUSES, AgentType, JobStatus
from app.repositories.agent_job_repository import AgentJobRepository
from app.services.arquitectura_service import ArquitecturaService
from app.services.bd_service import BdModelingService
from app.services.scrum_service import ScrumPlanningService


def test_los_estados_utilizables_son_los_dos_terminados_con_exito():
    """Los avisos cuentan: una cuarentena no invalida el artefacto."""
    assert set(USABLE_JOB_STATUSES) == {
        JobStatus.COMPLETED,
        JobStatus.COMPLETED_WITH_WARNINGS,
    }
    assert JobStatus.FAILED not in USABLE_JOB_STATUSES
    assert JobStatus.RUNNING not in USABLE_JOB_STATUSES


async def _job(repo, agent_type, artifact, status, *, titulo="Siniestros", **kw):
    job = await repo.create_job(agent_type, title=titulo, source_type="text", **kw)
    if artifact is not None:
        await repo.save_artifact(job.id, artifact, artifact["schema_version"])
    await repo.update_job_status(job.id, status)
    return job


@pytest.fixture
def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_el_selector_de_scrum_ignora_los_EF_fallidos_y_en_curso(factory):
    async with factory() as session:
        repo = AgentJobRepository(session)
        art = ef_example().model_dump(mode="json")
        listo = await _job(repo, AgentType.EF, art, JobStatus.COMPLETED)
        con_avisos = await _job(
            repo, AgentType.EF, art, JobStatus.COMPLETED_WITH_WARNINGS
        )
        fallido = await _job(repo, AgentType.EF, None, JobStatus.FAILED)
        en_curso = await _job(repo, AgentType.EF, None, JobStatus.RUNNING)
        await session.commit()

        items = await ScrumPlanningService(session).list_ready_ef_jobs(
            limit=50, offset=0
        )

    ids = {i["job_id"] for i in items}
    assert listo.id in ids
    # Un job con avisos sigue siendo utilizable: su artefacto existe.
    assert con_avisos.id in ids
    assert fallido.id not in ids
    assert en_curso.id not in ids


async def test_el_selector_marca_lo_que_esta_listo_y_lo_que_no(factory):
    """Listo vs. casi listo, que es la distinción que el selector tiene que pintar.

    El EF de ejemplo nace **con** una pregunta bloqueante, así que el caso "listo"
    la resuelve explícitamente en vez de dar por hecho que el ejemplo está verde.
    """
    async with factory() as session:
        repo = AgentJobRepository(session)
        listo_art = ef_example().model_dump(mode="json")
        for q in listo_art["questions_for_analyst"]:
            q["blocking"] = False
        listo = await _job(repo, AgentType.EF, listo_art, JobStatus.COMPLETED)

        bloqueado_art = ef_example().model_dump(mode="json")
        bloqueado_art["questions_for_analyst"][0]["blocking"] = True
        bloqueado = await _job(
            repo, AgentType.EF, bloqueado_art, JobStatus.COMPLETED, titulo="Con dudas"
        )
        await session.commit()

        items = {
            i["job_id"]: i
            for i in await ScrumPlanningService(session).list_ready_ef_jobs(
                limit=50, offset=0
            )
        }

    assert items[listo.id]["ready_for_next_stage"] is True
    assert items[listo.id]["blocking_pending"] == []
    assert items[bloqueado.id]["ready_for_next_stage"] is False
    # El selector necesita el conteo para decir cuántas faltan.
    assert len(items[bloqueado.id]["blocking_pending"]) >= 1
    # Y el título, para no obligar a leer un ULID.
    assert items[bloqueado.id]["title"] == "Con dudas"


async def test_el_selector_de_arquitectura_ignora_los_scrum_no_utilizables(factory):
    async with factory() as session:
        repo = AgentJobRepository(session)
        art = scrum_example().model_dump(mode="json")
        listo = await _job(repo, AgentType.SCRUM, art, JobStatus.COMPLETED)
        fallido = await _job(repo, AgentType.SCRUM, None, JobStatus.FAILED)
        await session.commit()

        items = await ArquitecturaService(session).list_ready_scrum_jobs(
            limit=50, offset=0
        )

    ids = {i["job_id"] for i in items}
    assert listo.id in ids and fallido.id not in ids
    assert all("title" in i for i in items)


async def test_el_selector_de_BD_ignora_las_arquitecturas_no_utilizables(factory):
    async with factory() as session:
        repo = AgentJobRepository(session)
        art = arch_example().model_dump(mode="json")
        completa = await _job(repo, AgentType.ARQUITECTURA, art, JobStatus.COMPLETED)
        fallida = await _job(repo, AgentType.ARQUITECTURA, None, JobStatus.FAILED)
        pendiente = await _job(repo, AgentType.ARQUITECTURA, None, JobStatus.PENDING)
        await session.commit()

        items = await BdModelingService(session).list_ready_architecture_jobs(
            limit=50, offset=0
        )

    ids = {i["job_id"] for i in items}
    assert ids == {completa.id}
    assert fallida.id not in ids and pendiente.id not in ids
    # El ejemplo de Arquitectura trae una pregunta bloqueante: casi listo, no listo.
    assert items[0]["ready_for_next_stage"] is False
    assert items[0]["blocking_pending"]


async def test_un_selector_vacio_devuelve_lista_vacia_sin_romper(factory):
    async with factory() as session:
        items = await BdModelingService(session).list_ready_architecture_jobs(
            limit=50, offset=0
        )
    assert items == []
