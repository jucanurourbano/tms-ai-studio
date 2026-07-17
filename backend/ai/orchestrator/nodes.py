"""Nodos del grafo LangGraph del Agente EF.

INGEST / PARSE / SEGMENT usan el pipeline real del Bloque 3. El resto son stubs
que se completan en los Bloques 5-7, pero ya producen estructuras válidas para
que el grafo corra de extremo a extremo.
"""

import time

from langchain_core.runnables import RunnableConfig

from ai.tools.chunker import chunk_cir
from ai.tools.cir import CIR
from ai.tools.ingest import LocalStorage, ingest
from ai.tools.parsers import DocxParser, PdfParser, TextToCIRAdapter
from app.config.settings import settings

from .state import EFState


def _storage() -> LocalStorage:
    return LocalStorage(settings.STORAGE_DIR)


async def node_ingest(state: EFState) -> dict:
    """Valida, calcula hash y almacena la fuente (real)."""
    filename = state["filename"]
    content = state.get("content")
    if content is None and state.get("text") is not None:
        content = state["text"].encode("utf-8")
    result = ingest(
        filename=filename,
        content=content,
        storage=_storage(),
        max_upload_mb=settings.MAX_UPLOAD_MB,
    )
    return {
        "source": result.model_dump(),
        "status": "RUNNING",
        "metrics": {},
        "errors": [],
        "started_at": time.time(),
    }


async def node_parse(state: EFState) -> dict:
    """Parsea la fuente a CIR según su tipo (real)."""
    source = state["source"]
    ext = source["extension"]
    uri = source["storage_uri"]
    if ext == ".docx":
        cir = DocxParser.parse(uri)
    elif ext == ".pdf":
        cir = PdfParser.parse(uri)
    else:  # .txt / .md
        raw = _storage().read(uri).decode("utf-8", errors="replace")
        cir = TextToCIRAdapter.adapt(raw, title=source.get("filename"))
    return {"cir": cir.model_dump()}


async def node_segment(state: EFState) -> dict:
    """Divide el CIR en chunks (real)."""
    cir = CIR.model_validate(state["cir"])
    result = chunk_cir(cir, token_threshold=settings.SINGLE_SHOT_TOKEN_THRESHOLD)
    metrics = dict(state.get("metrics") or {})
    metrics["chunks_total"] = result.chunks_total
    return {"chunks": result.model_dump(), "metrics": metrics}


# --- EXTRACT / CONSOLIDATE / INFER (Bloque 5) -------------------------------


async def node_extract(state: EFState, config: RunnableConfig) -> dict:
    """EXTRACT: map por dimensiones sobre los chunks (LLM inyectable por config)."""
    from ai.agents.ef.extract import ClaudeLLMClient, run_extract

    llm = (config or {}).get("configurable", {}).get("llm")
    if llm is None:
        llm = ClaudeLLMClient()

    chunks = (state.get("chunks") or {}).get("chunks", [])
    results, skipped, tokens = await run_extract(
        llm, chunks, concurrency=settings.EXTRACT_CONCURRENCY
    )

    metrics = dict(state.get("metrics") or {})
    acc_skipped = list(metrics.get("skipped") or []) + skipped
    metrics["skipped"] = acc_skipped
    metrics["chunks_skipped"] = len(acc_skipped)
    metrics["tokens"] = tokens
    attempts = len(results) + len(skipped)
    metrics["coverage"] = round(len(results) / attempts, 4) if attempts else 1.0
    return {"raw_extractions": results, "metrics": metrics}


async def node_consolidate(state: EFState) -> dict:
    """CONSOLIDATE: dedupe + renumeración estable."""
    from ai.agents.ef.consolidate import consolidate

    return {"consolidated_model": consolidate(state.get("raw_extractions") or [])}


async def node_infer(state: EFState) -> dict:
    """INFER: deriva entities/fields/relationships/CRUD/APIs."""
    from ai.agents.ef.infer import infer

    return {"inferred_model": infer(state.get("consolidated_model") or {})}


async def node_interpret(state: EFState) -> dict:
    """INTERPRET: genera systems_interpretation (determinístico)."""
    from ai.agents.ef.interpret import interpret

    return {
        "systems_interpretation": interpret(
            state.get("consolidated_model") or {},
            state.get("inferred_model") or {},
            summary=state.get("summary"),
        )
    }


async def node_critique(state: EFState, config: RunnableConfig) -> dict:
    """CRITIQUE: refs huérfanas (determinístico) + pase LLM opcional."""
    from ai.agents.ef.critique import critique

    llm = (config or {}).get("configurable", {}).get("critique_llm")
    result = await critique(
        state.get("consolidated_model") or {},
        state.get("inferred_model") or {},
        llm=llm,
    )
    return {"critique": result}


async def node_question_gen(state: EFState) -> dict:
    """QUESTION_GEN: dudas de Sistemas hacia Procesos; técnicas -> observaciones."""
    from ai.agents.ef.question_gen import generate_questions

    critique_result = dict(state.get("critique") or {})
    questions, obs_extra = generate_questions(
        critique_result, state.get("consolidated_model") or {}
    )

    # Las observaciones extra (refs huérfanas) se anexan al análisis crítico.
    observations = list(critique_result.get("observations") or [])
    start = len(observations)
    for i, obs in enumerate(obs_extra, start=start + 1):
        obs["id"] = f"OBS-{i:03d}"
        observations.append(obs)
    critique_result["observations"] = observations

    return {"questions": questions, "critique": critique_result}


async def node_assemble(state: EFState) -> dict:
    """ASSEMBLE + VALIDATE: construye el EFArtifact y calcula métricas reales."""
    from ai.agents.ef.assemble import assemble_artifact, validate_artifact

    artifact, _ = assemble_artifact(state)
    dumped = artifact.model_dump(mode="json")
    validate_artifact(dumped)  # VALIDATE contra el esquema v1.2.0
    return {"artifact": dumped}


async def node_persist(state: EFState, config: RunnableConfig) -> dict:
    """PERSIST: guarda el artefacto y marca el job COMPLETED[_WITH_WARNINGS].

    La persistencia es inyectable por config (tests sin Postgres); si no se
    inyecta, usa la BD real vía session_scope.
    """
    artifact = state["artifact"]
    metrics = artifact.get("metrics") or {}
    has_warnings = bool(metrics.get("skipped"))
    status = "COMPLETED_WITH_WARNINGS" if has_warnings else "COMPLETED"

    persist = (config or {}).get("configurable", {}).get("persist")
    if persist is not None:
        await persist(state["job_id"], artifact, status, metrics)
    else:  # pragma: no cover - ruta runtime con Postgres real
        from app.dependencies.database import session_scope
        from app.models.ef import JobStatus
        from app.repositories.ef_repository import EFRepository

        async with session_scope() as session:
            repo = EFRepository(session)
            await repo.save_artifact(
                state["job_id"], artifact, artifact["schema_version"]
            )
            await repo.update_job_metrics(state["job_id"], metrics)
            await repo.update_job_status(state["job_id"], JobStatus[status])

    return {"status": status}
