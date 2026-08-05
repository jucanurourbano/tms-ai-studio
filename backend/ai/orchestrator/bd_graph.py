"""Construcción del grafo LangGraph del Agente BD.

Pipeline lineal (mismo patrón EF/Scrum/Arquitectura, vía la base compartida):

    LOAD_SOURCES -> MODEL_MAP -> TABLES -> RELATIONS -> CONSTRAINTS -> INDEXES
                 -> CATALOGS -> DDL_GEN -> VALIDATE -> DICTIONARY -> ER_DIAGRAM
                 -> CRITIQUE -> QUESTION_GEN -> ASSEMBLE -> PERSIST

Solo seis nodos llaman al LLM (TABLES, RELATIONS, CONSTRAINTS, INDEXES, CATALOGS
y el pase de riesgos de CRITIQUE). El andamio del modelo, el DDL, su validación,
el diccionario y el diagrama son **deterministas**: mismo EF ⇒ misma salida, y por
tanto testeables sin gastar tokens.
"""

from ai.agents.base.graph import build_linear_graph
from ai.agents.bd.state import DatabaseState

from . import bd_nodes as nodes

_NODES = [
    ("load_sources", nodes.node_load_sources),
    ("model_map", nodes.node_model_map),
    ("tables", nodes.node_tables),
    ("relations", nodes.node_relations),
    ("constraints", nodes.node_constraints),
    ("indexes", nodes.node_indexes),
    ("catalogs", nodes.node_catalogs),
    ("ddl_gen", nodes.node_ddl_gen),
    ("validate", nodes.node_validate),
    ("dictionary", nodes.node_dictionary),
    ("er_diagram", nodes.node_er_diagram),
    ("critique", nodes.node_critique),
    ("question_gen", nodes.node_question_gen),
    ("assemble", nodes.node_assemble),
    ("persist", nodes.node_persist),
]


def build_bd_graph(checkpointer=None):
    """Compila el grafo del Agente BD (helper lineal compartido de la base)."""
    return build_linear_graph(DatabaseState, _NODES, checkpointer)
