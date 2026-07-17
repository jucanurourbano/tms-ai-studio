"""Estado del grafo LangGraph del Agente EF."""

from typing import Optional, TypedDict


class EFState(TypedDict, total=False):
    """Estado que fluye por el pipeline EF.

    Todas las estructuras complejas se guardan como ``dict`` serializables para
    ser compatibles con el checkpointer (Redis).
    """

    job_id: str
    filename: str
    content: bytes  # bytes crudos de la fuente (entrada)
    text: Optional[str]  # texto libre (entrada alternativa)
    summary: Optional[str]
    started_at: float
    authoritative_context: Optional[str]

    source: dict  # IngestResult
    cir: dict  # CIR
    chunks: dict  # ChunkingResult
    raw_extractions: list[dict]
    consolidated_model: dict
    inferred_model: dict
    systems_interpretation: dict
    critique: dict
    questions: list[dict]
    artifact: dict  # EFArtifact
    errors: list[str]
    metrics: dict
    status: str
