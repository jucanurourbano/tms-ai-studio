"""Estado del grafo LangGraph del Agente API.

Todas las estructuras complejas se guardan como ``dict``/``list`` serializables
para ser compatibles con el checkpointer (Redis, ``thread_id=job_id``).
"""

from typing import Optional, TypedDict


class ApiState(TypedDict, total=False):
    """Estado que fluye por el pipeline del Agente API."""

    # --- Entrada (la provee el servicio al encolar) ---
    job_id: str
    bd_job_id: str
    bd_artifact: dict  # DatabaseArtifact v1.0.0: materia prima principal
    bd_artifact_hash: str
    bd_ready: bool  # snapshot del gate (modelo de datos listo)
    architecture_job_id: Optional[str]
    architecture_artifact: dict
    architecture_artifact_hash: Optional[str]
    scrum_job_id: Optional[str]  # eslabón intermedio (solo trazabilidad)
    scrum_artifact: dict
    scrum_artifact_hash: Optional[str]
    ef_job_id: str
    ef_artifact: dict  # EFArtifact v1.2.0: actores, matriz CRUD, reglas
    ef_artifact_hash: str
    #: Estilo forzado en la petición (permite diseñar sin esperar a la arquitectura).
    style_override: Optional[str]
    authoritative_context: Optional[str]  # ciclo de afinamiento (refine)
    started_at: float

    # --- Derivado por los nodos ---
    sources: dict  # contexto consolidado BD + EF + Arquitectura
    target: dict  # estilo, seguridad y convenciones efectivas
    resource_map: dict  # andamio determinista (recursos y operaciones candidatas)
    resources: list[dict]
    schemas: list[dict]
    endpoints: list[dict]
    authorization_matrix: list[dict]
    error_catalog: list[dict]
    rule_mappings: list[dict]  # destino en la API de cada BR-/VAL- del EF
    #: Reglas que el Agente BD delegó en la aplicación y que la API tampoco hace
    #: cumplir. Cada una desaparecería del producto: acaban en pregunta bloqueante.
    unenforced_delegated_rules: list[str]
    #: Correcciones aplicadas sobre las propuestas del LLM (campos sin columna,
    #: endpoints fuera del mapa, alcances sin evidencia) y exclusiones del andamio.
    #: Acaban como Observation: ninguna corrección es silenciosa.
    map_observations: list[dict]
    openapi: dict  # bloque `openapi` del artefacto (YAML + metadatos)
    #: El documento como `dict`, antes de serializar. Solo viaja entre OPENAPI_GEN
    #: y VALIDATE: no entra al artefacto, que guarda el YAML canónico.
    openapi_document: dict
    validation: dict  # resultado determinista de la validación de la spec
    #: Sistema del inventario contra el que reconciliar (INV4). Sin él se
    #: resuelve el único sistema `destino`; con varios o ninguno, la fase se
    #: salta declarándolo (nunca se adivina el objetivo).
    target_system_id: Optional[str]
    #: Resumen de RECONCILE: conteos por estado y conflictos bloqueantes.
    reconciliation: dict
    critique: dict
    questions: list[dict]
    artifact: dict  # ApiArtifact
    metrics: dict
    errors: list[str]
    status: str
