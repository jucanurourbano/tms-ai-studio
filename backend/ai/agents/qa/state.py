"""Estado del grafo LangGraph del Agente QA.

Todas las estructuras complejas se guardan como ``dict``/``list`` serializables
para ser compatibles con el checkpointer (Redis, ``thread_id=job_id``).
"""

from typing import Optional, TypedDict


class QaState(TypedDict, total=False):
    """Estado que fluye por el pipeline del Agente QA."""

    # --- Entrada (la provee el servicio al encolar) ---
    job_id: str
    scrum_job_id: str
    scrum_artifact: dict  # ScrumArtifact v1.0.0: historias y criterios
    scrum_artifact_hash: str
    scrum_ready: bool  # snapshot del gate (plan listo)
    ef_job_id: str
    ef_artifact: dict  # EFArtifact v1.2.0: reglas BR-, validaciones VAL-, campos
    ef_artifact_hash: str
    #: Contrato de API **opcional** (QA-D1). No se descubre: se indica, porque no
    #: está en la cadena hacia atrás sino hacia delante. Sin él no hay casos de
    #: autorización y el motivo queda escrito en el artefacto.
    api_job_id: Optional[str]
    api_artifact: dict
    api_artifact_hash: Optional[str]
    authoritative_context: Optional[str]  # ciclo de afinamiento (refine)
    started_at: float

    # --- Derivado por los nodos ---
    sources: dict  # contexto consolidado Scrum + EF (+ API si lo hay)
    target: dict  # umbrales y política efectivos de la corrida
    #: Veredicto de LOAD_SOURCES sobre la dependencia opcional. Un contrato
    #: indicado pero sin artefacto o sin hash cuenta como ausente **con motivo**:
    #: seguir como si estuviera disponible produciría casos de autorización sin
    #: matriz detrás.
    api_available: bool
    api_absent_reason: Optional[str]
    hashes: dict  # hashes de la cadena para el bloque `source`
    #: Andamio determinista: los pares (historia, criterio) que EXISTEN. Es el
    #: cortafuegos anti-invención: ningún caso puede citar un criterio que no
    #: esté aquí.
    criterion_map: dict
    test_cases: list[dict]
    datasets: list[dict]
    trace_matrix: dict
    execution_plan: dict
    #: Correcciones aplicadas sobre las propuestas del LLM (casos con criterio
    #: inexistente, bordes sin evidencia, casos podados por el techo) y omisiones
    #: deliberadas (autorizaciones ambiguas). Acaban como Observation: ningún
    #: descarte es silencioso.
    map_observations: list[dict]
    #: Reglas de autorización ambiguas del contrato de API: no producen caso,
    #: producen pregunta bloqueante.
    ambiguous_auth_refs: list[str]
    #: Criterios declarados no verificables, con el motivo. Van a QUESTION_GEN.
    not_testable: list[dict]
    risks: list[dict]
    observations: list[dict]
    questions: list[dict]
    artifact: dict
    metrics: dict
