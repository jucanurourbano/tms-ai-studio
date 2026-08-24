"""Base compartida de los agentes del ISDF.

Factoriza el patrón del Agente EF para que los siguientes agentes (Scrum,
Arquitectura, ...) lo reutilicen sin duplicar infraestructura:

- ``structured``: protocolo ``LLMClient``, el alias ``ClaudeLLMClient`` (el
  proveedor real vive en ``ai/llm/``) y el map genérico
  con reparación de esquema + cuarentena (``run_structured_map``).
- ``graph``: compilación lineal de grafos LangGraph con checkpointer.
- ``refine``: construcción del "contexto autoritativo" desde validaciones.
- ``pipeline``: runner genérico de ``BackgroundTasks`` parametrizado por agente.
- ``lineage``: recorrido transitivo de ``input_job_id`` para los agentes que
  consumen a varios predecesores (BD consume Arquitectura + EF).
"""

from .graph import build_linear_graph
from .lineage import resolve_ancestor, resolve_lineage
from .refine import build_authoritative_context
from .structured import (
    ClaudeLLMClient,
    LLMClient,
    complete_structured,
    run_structured_map,
)

__all__ = [
    "ClaudeLLMClient",
    "LLMClient",
    "build_authoritative_context",
    "build_linear_graph",
    "complete_structured",
    "resolve_ancestor",
    "resolve_lineage",
    "run_structured_map",
]
