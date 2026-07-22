"""Estado del grafo LangGraph del Agente Arquitectura.

Todas las estructuras complejas se guardan como ``dict`` serializables para ser
compatibles con el checkpointer (Redis, ``thread_id=job_id``).
"""

from typing import Optional, TypedDict


class ArchitectureState(TypedDict, total=False):
    """Estado que fluye por el pipeline de Arquitectura."""

    # --- Entrada (la provee el servicio al encolar) ---
    job_id: str
    scrum_job_id: str
    scrum_artifact: dict  # ScrumArtifact v1.0.0 consumido
    scrum_artifact_hash: str
    scrum_ready: bool  # snapshot del gate del Scrum (sin blocking pendientes)
    ef_job_id: str  # EF resuelto transitivamente (scrum.input_job_id)
    ef_artifact: dict  # EFArtifact v1.2.0 consumido
    ef_artifact_hash: str
    authoritative_context: Optional[str]  # ciclo de afinamiento (refine Arquitecto)
    started_at: float

    # --- Derivado por los nodos ---
    sources: dict  # contexto consolidado EF + Scrum
    scope_profile: dict  # conteos deterministas (CONTEXT)
    size_class: str  # S | M | L (CONTEXT)
    bounded_contexts: list[dict]
    style: Optional[dict]  # decisión de estilo arquitectónico
    components: list[dict]
    stack: list[dict]
    adrs: list[dict]
    integrations: list[dict]
    contracts: list[dict]
    cross_cutting: list[dict]
    diagrams: dict
    critique: dict
    questions: list[dict]
    artifact: dict  # ArchitectureArtifact
    metrics: dict
    errors: list[str]
    status: str
