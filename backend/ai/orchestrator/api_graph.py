"""Construcción del grafo LangGraph del Agente API.

Pipeline lineal (mismo patrón EF/Scrum/Arquitectura/BD, vía la base compartida):

    LOAD_SOURCES -> RESOURCE_MAP -> RESOURCES -> ENDPOINTS -> SCHEMAS
                 -> AUTHORIZATION -> RULE_MAPPING -> ERRORS
                 -> OPENAPI_GEN -> VALIDATE -> CRITIQUE -> QUESTION_GEN
                 -> ASSEMBLE -> PERSIST

Solo seis nodos llaman al LLM (RESOURCES, ENDPOINTS, SCHEMAS, AUTHORIZATION,
RULE_MAPPING y el pase de riesgos de CRITIQUE). El andamio de recursos, el
catálogo de errores, el documento OpenAPI y su validación son **deterministas**:
mismo modelo de datos ⇒ misma salida, y por tanto testeables sin gastar tokens.

``ERRORS`` va **después** de ``AUTHORIZATION`` a propósito: el ``403`` solo se
estampa donde existe una regla que pueda denegar.
"""

from ai.agents.api.state import ApiState
from ai.agents.base.graph import build_linear_graph

from . import api_nodes as nodes

_NODES = [
    ("load_sources", nodes.node_load_sources),
    ("resource_map", nodes.node_resource_map),
    ("resources", nodes.node_resources),
    ("endpoints", nodes.node_endpoints),
    ("schemas", nodes.node_schemas),
    ("authorization", nodes.node_authorization),
    ("rule_mapping", nodes.node_rule_mapping),
    ("errors", nodes.node_errors),
    ("openapi_gen", nodes.node_openapi_gen),
    ("validate", nodes.node_validate),
    ("critique", nodes.node_critique),
    ("question_gen", nodes.node_question_gen),
    ("assemble", nodes.node_assemble),
    ("persist", nodes.node_persist),
]


def build_api_graph(checkpointer=None):
    """Compila el grafo del Agente API (helper lineal compartido de la base)."""
    return build_linear_graph(ApiState, _NODES, checkpointer)
