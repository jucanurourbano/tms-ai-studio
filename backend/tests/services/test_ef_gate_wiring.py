"""Gate compuesto del EF (#6) y cableado de critique_llm en el pipeline (#3)."""

import app.services.ef_service as ef_service
from ai.agents.ef.schemas.examples import example_artifact
from app.models.ef import EFSourceDocType
from app.repositories.ef_repository import EFRepository
from app.services.ef_service import EFAnalysisService


async def _job_con_artifact(session, artifact: dict) -> str:
    """Crea un job EF y le persiste el artifact dado; devuelve el job_id."""
    repo = EFRepository(session)
    doc = await repo.get_or_create_source_doc("hash-gate", EFSourceDocType.TEXT)
    job = await repo.create_job(doc.id)
    await repo.save_artifact(job.id, artifact, artifact["schema_version"])
    await session.commit()
    return job.id


# --- #6: gate compuesto (Y, no O) -------------------------------------------


async def test_gate_verde_requiere_las_tres_condiciones(session):
    """Sin preguntas blocking + RF funcionales + cobertura => verde."""
    art = example_artifact().model_dump(mode="json")
    art["questions_for_analyst"] = []  # sin blocking pendientes
    # example ya trae functional>=1 y coverage=1.0
    job_id = await _job_con_artifact(session, art)

    summary = await EFAnalysisService(session).validation_summary(job_id)
    assert summary["ready_for_next_stage"] is True
    assert summary["gate_checks"] == {
        "no_blocking_pending": True,
        "min_functional": True,
        "coverage": True,
    }


async def test_gate_rojo_con_cero_requisitos_funcionales(session):
    """REGRESIÓN (#6): 0 RF funcionales NO puede quedar verde aunque no haya
    preguntas blocking (antes la condición era O y salía verde)."""
    art = example_artifact().model_dump(mode="json")
    art["questions_for_analyst"] = []
    art["requirements"]["functional"] = []  # 0 RF funcionales
    job_id = await _job_con_artifact(session, art)

    summary = await EFAnalysisService(session).validation_summary(job_id)
    assert summary["ready_for_next_stage"] is False
    assert summary["gate_checks"]["min_functional"] is False
    assert summary["gate_checks"]["no_blocking_pending"] is True


async def test_gate_rojo_con_cobertura_insuficiente(session):
    art = example_artifact().model_dump(mode="json")
    art["questions_for_analyst"] = []
    art["metrics"]["coverage"] = 0.83  # una dimensión en cuarentena
    job_id = await _job_con_artifact(session, art)

    summary = await EFAnalysisService(session).validation_summary(job_id)
    assert summary["ready_for_next_stage"] is False
    assert summary["gate_checks"]["coverage"] is False


# --- #3: el pipeline EF cablea critique_llm ---------------------------------


async def test_run_ef_pipeline_cablea_critique_llm(monkeypatch):
    """REGRESIÓN (#3): run_ef_pipeline debe pasar extra_config con critique_llm,
    o QUESTION_GEN se queda sin insumos semánticos (0 preguntas)."""
    captured: dict = {}

    async def fake_run_agent_pipeline(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "ai.agents.base.pipeline.run_agent_pipeline", fake_run_agent_pipeline
    )

    await ef_service.run_ef_pipeline(
        "01JOBIDGATE0000000000000000", {"filename": "vacaciones.txt"}
    )

    extra = captured.get("extra_config") or {}
    assert "critique_llm" in extra
    assert extra["critique_llm"] is not None
