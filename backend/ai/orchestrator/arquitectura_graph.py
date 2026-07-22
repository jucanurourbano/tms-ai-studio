"""Construcción del grafo LangGraph del Agente Arquitectura.

Pipeline lineal (mismo patrón EF/Scrum, vía la base compartida):
    LOAD_SOURCES -> CONTEXT -> COMPONENTS -> STACK -> ADRS -> CONTRACTS
                 -> DIAGRAMS -> CRITIQUE -> QUESTION_GEN -> ASSEMBLE -> PERSIST
"""

from ai.agents.arquitectura.state import ArchitectureState
from ai.agents.base.graph import build_linear_graph

from . import arquitectura_nodes as nodes

_NODES = [
    ("load_sources", nodes.node_load_sources),
    ("context", nodes.node_context),
    ("components", nodes.node_components),
    ("stack", nodes.node_stack),
    ("adrs", nodes.node_adrs),
    ("contracts", nodes.node_contracts),
    ("diagrams", nodes.node_diagrams),
    ("critique", nodes.node_critique),
    ("question_gen", nodes.node_question_gen),
    ("assemble", nodes.node_assemble),
    ("persist", nodes.node_persist),
]


def build_arquitectura_graph(checkpointer=None):
    """Compila el grafo de Arquitectura lineal (helper compartido de la base)."""
    return build_linear_graph(ArchitectureState, _NODES, checkpointer)
