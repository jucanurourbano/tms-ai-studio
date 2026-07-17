"""Construcción del grafo LangGraph del Agente EF.

Pipeline lineal:
    INGEST -> PARSE -> SEGMENT -> EXTRACT -> CONSOLIDATE -> INFER -> INTERPRET
    -> CRITIQUE -> QUESTION_GEN -> ASSEMBLE -> PERSIST
"""

from langgraph.graph import END, START, StateGraph

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
    """Compila el grafo EF. Si no se pasa checkpointer, usa uno en memoria."""
    if checkpointer is None:
        from .checkpointer import build_memory_checkpointer

        checkpointer = build_memory_checkpointer()

    graph = StateGraph(EFState)
    for name, fn in _NODES:
        graph.add_node(name, fn)

    graph.add_edge(START, _NODES[0][0])
    for (prev, _), (nxt, _) in zip(_NODES, _NODES[1:]):
        graph.add_edge(prev, nxt)
    graph.add_edge(_NODES[-1][0], END)

    return graph.compile(checkpointer=checkpointer)
