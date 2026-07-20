"""Construcción del grafo LangGraph del Agente Scrum.

Pipeline lineal (mismo patrón del EF, vía la base compartida):
    LOAD_EF -> EPICS -> STORIES -> CRITERIA -> ESTIMATE -> PRIORITIZE
            -> SPRINT_PLAN -> CRITIQUE -> QUESTION_GEN -> ASSEMBLE -> PERSIST
"""

from ai.agents.base.graph import build_linear_graph
from ai.agents.scrum.state import ScrumState

from . import scrum_nodes as nodes

_NODES = [
    ("load_ef", nodes.node_load_ef),
    ("epics", nodes.node_epics),
    ("stories", nodes.node_stories),
    ("criteria", nodes.node_criteria),
    ("estimate", nodes.node_estimate),
    ("prioritize", nodes.node_prioritize),
    ("sprint_plan", nodes.node_sprint_plan),
    ("critique", nodes.node_critique),
    ("question_gen", nodes.node_question_gen),
    ("assemble", nodes.node_assemble),
    ("persist", nodes.node_persist),
]


def build_scrum_graph(checkpointer=None):
    """Compila el grafo Scrum lineal (usa el helper compartido de la base)."""
    return build_linear_graph(ScrumState, _NODES, checkpointer)
