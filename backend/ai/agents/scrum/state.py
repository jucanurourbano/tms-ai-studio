"""Estado del grafo LangGraph del Agente Scrum.

Todas las estructuras complejas se guardan como ``dict`` serializables para ser
compatibles con el checkpointer (Redis, ``thread_id=job_id``).
"""

from typing import Optional, TypedDict


class ScrumState(TypedDict, total=False):
    """Estado que fluye por el pipeline Scrum."""

    # --- Entrada (la provee el servicio al encolar) ---
    job_id: str
    ef_job_id: str
    ef_artifact: dict  # EFArtifact v1.2.0 consumido
    ef_artifact_hash: str
    ef_ready: bool  # snapshot del gate del EF (sin blocking pendientes)
    capacity_points: int  # D4: 20 por defecto
    coverage_threshold: float  # D5: 1.0 por defecto
    authoritative_context: Optional[str]  # ciclo de afinamiento (refine PO)
    started_at: float

    # --- Derivado por los nodos ---
    ef_context: dict  # RF/procesos/reglas/validaciones/entidades expuestos
    epics: list[dict]
    stories: list[dict]
    backlog: dict
    sprints: list[dict]
    unassigned_story_ids: list[str]
    critique: dict
    questions: list[dict]
    artifact: dict  # ScrumArtifact
    metrics: dict
    errors: list[str]
    status: str
