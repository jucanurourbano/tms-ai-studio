"""Compilación lineal de grafos LangGraph (patrón compartido).

Factoriza el patrón ``_NODES -> compile(checkpointer)`` usado por el Agente EF
para que cualquier agente del ISDF construya su pipeline lineal con una llamada.
"""

from typing import Callable

from langgraph.graph import END, START, StateGraph


def build_linear_graph(
    state_type: type, nodes: list[tuple[str, Callable]], checkpointer=None
):
    """Compila un grafo lineal ``START -> n0 -> n1 -> ... -> END``.

    Si no se pasa checkpointer, usa uno en memoria (tests / desarrollo sin Redis).
    """
    if checkpointer is None:
        from ai.orchestrator.checkpointer import build_memory_checkpointer

        checkpointer = build_memory_checkpointer()

    graph = StateGraph(state_type)
    for name, fn in nodes:
        graph.add_node(name, fn)

    graph.add_edge(START, nodes[0][0])
    for (prev, _), (nxt, _) in zip(nodes, nodes[1:]):
        graph.add_edge(prev, nxt)
    graph.add_edge(nodes[-1][0], END)

    return graph.compile(checkpointer=checkpointer)
