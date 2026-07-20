"""Construcción del grafo LangGraph del Agente EF.

Pipeline lineal:
    INGEST -> PARSE -> SEGMENT -> EXTRACT -> CONSOLIDATE -> INFER -> INTERPRET
    -> CRITIQUE -> QUESTION_GEN -> ASSEMBLE -> PERSIST
"""

from ai.agents.base.graph import build_linear_graph

from . import nodes
from .state import EFState

_NODES = [
    ("ingest", nodes.node_ingest),
    ("parse", nodes.node_parse),
    ("segment", nodes.node_segment),
    ("extract", nodes.node_extract),
    ("consolidate", nodes.node_consolidate),
    ("infer", nodes.node_infer),
    ("interpret", nodes.node_interpret),
    ("critique", nodes.node_critique),
    ("question_gen", nodes.node_question_gen),
    ("assemble", nodes.node_assemble),
    ("persist", nodes.node_persist),
]


def build_ef_graph(checkpointer=None):
    """Compila el grafo EF lineal (usa el helper compartido de la base)."""
    return build_linear_graph(EFState, _NODES, checkpointer)
