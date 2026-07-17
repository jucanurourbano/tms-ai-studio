"""Nodos del grafo LangGraph del Agente EF.

INGEST / PARSE / SEGMENT usan el pipeline real del Bloque 3. El resto son stubs
que se completan en los Bloques 5-7, pero ya producen estructuras válidas para
que el grafo corra de extremo a extremo.
"""

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


# --- Stubs (Bloques 5-7) ----------------------------------------------------


async def node_extract(state: EFState) -> dict:
    """STUB: extracción por dimensiones (Bloque 5)."""
    return {"raw_extractions": []}


async def node_consolidate(state: EFState) -> dict:
    """STUB: consolidación (Bloque 5)."""
    return {"consolidated_model": {}}


async def node_infer(state: EFState) -> dict:
    """STUB: inferencia del modelo de datos (Bloque 5)."""
    return {"inferred_model": {}}


async def node_interpret(state: EFState) -> dict:
    """STUB: interpretación de Sistemas (Bloque 6)."""
    return {
        "systems_interpretation": {
            "what_process_requests": "(pendiente)",
            "scope_for_systems": [],
            "apparent_out_of_scope": [],
            "interpretation_assumptions": [],
        }
    }


async def node_critique(state: EFState) -> dict:
    """STUB: crítica (Bloque 6)."""
    return {"critique": {}}


async def node_question_gen(state: EFState) -> dict:
    """STUB: generación de preguntas (Bloque 6)."""
    return {"questions": []}


async def node_assemble(state: EFState) -> dict:
    """STUB: ensambla un EFArtifact mínimo válido (Bloque 7 lo completa)."""
    from ai.agents.ef.schemas import EFArtifact

    source = state["source"]
    artifact = EFArtifact(
        source={
            "type": source["source_type"],
            "hash": source["content_hash"],
            "fidelity": (state.get("cir") or {}).get("fidelity") or "full",
            "filename": source.get("filename"),
        },
        summary="(pendiente de análisis)",
        systems_interpretation=state.get("systems_interpretation")
        or {"what_process_requests": "(pendiente)"},
        metrics=state.get("metrics") or {},
    )
    return {"artifact": artifact.model_dump(mode="json")}


async def node_persist(state: EFState) -> dict:
    """STUB: marca el job como completado (persistencia real en Bloques 7-8)."""
    return {"status": "COMPLETED"}
