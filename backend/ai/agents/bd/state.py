"""Estado del grafo LangGraph del Agente BD.

Todas las estructuras complejas se guardan como ``dict``/``list`` serializables
para ser compatibles con el checkpointer (Redis, ``thread_id=job_id``).
"""

from typing import Optional, TypedDict


class DatabaseState(TypedDict, total=False):
    """Estado que fluye por el pipeline del Agente BD."""

    # --- Entrada (la provee el servicio al encolar) ---
    job_id: str
    architecture_job_id: str
    architecture_artifact: dict  # ArchitectureArtifact v1.0.0 consumido
    architecture_artifact_hash: str
    architecture_ready: bool  # snapshot del gate (sin blocking pendientes)
    scrum_job_id: str  # eslabón intermedio (solo trazabilidad)
    scrum_artifact: dict
    scrum_artifact_hash: str
    ef_job_id: str  # EF resuelto transitivamente (2 saltos)
    ef_artifact: dict  # EFArtifact v1.2.0: materia prima principal
    ef_artifact_hash: str
    #: Motor forzado en la petición (permite modelar sin esperar a la arquitectura).
    engine_override: Optional[str]
    authoritative_context: Optional[str]  # ciclo de afinamiento (refine del DBA)
    started_at: float

    # --- Derivado por los nodos ---
    sources: dict  # contexto consolidado EF + Arquitectura
    target: dict  # motor + convenciones efectivas
    model_map: dict  # andamio determinista (tablas/columnas/relaciones candidatas)
    tables: list[dict]
    rule_mappings: list[dict]  # destino de cada BR-/VAL- del EF
    seed_data: list[dict]
    ddl_scripts: list[dict]
    validation: dict  # resultado determinista de la validación del DDL
    data_dictionary: list[dict]
    er_diagram: dict
    design_decisions: list[dict]
    critique: dict
    questions: list[dict]
    artifact: dict  # DatabaseArtifact
    metrics: dict
    errors: list[str]
    status: str
