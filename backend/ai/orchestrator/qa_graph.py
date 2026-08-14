"""Construcción del grafo LangGraph del Agente QA.

Pipeline lineal (mismo patrón EF/Scrum/Arquitectura/BD/API, vía la base
compartida):

    LOAD_SOURCES -> CRITERION_MAP -> TEST_DESIGN -> EDGE_CASES -> AUTH_CASES
                 -> DATASET -> TRACE_MATRIX -> EXEC_PLAN
                 -> CRITIQUE -> QUESTION_GEN -> ASSEMBLE -> PERSIST

Solo cinco nodos llaman al LLM (TEST_DESIGN, EDGE_CASES, los valores de DATASET,
CRITIQUE y QUESTION_GEN). El resto es determinista: mismo plan ⇒ misma salida, y
por tanto testeable sin gastar tokens.

Dos posiciones que no son casuales:

- ``CRITERION_MAP`` va **antes** de TEST_DESIGN porque es el cortafuegos
  anti-invención: fija en Python qué pares (historia, criterio) existen. Validar
  eso después significaría descartar trabajo ya pagado al modelo.
- ``AUTH_CASES`` va **después** de EDGE_CASES y **no llama al LLM**: los casos de
  autorización se derivan de la matriz del contrato de API, donde ya están el
  efecto, el alcance y las columnas que lo materializan. La superficie de
  autorización no se redacta a ojo, y una regla marcada ambigua no produce caso
  sino pregunta bloqueante.
"""

from ai.agents.base.graph import build_linear_graph
from ai.agents.qa.state import QaState

from . import qa_nodes as nodes

_NODES = [
    ("load_sources", nodes.node_load_sources),
    ("criterion_map", nodes.node_criterion_map),
    ("test_design", nodes.node_test_design),
    ("edge_cases", nodes.node_edge_cases),
    ("auth_cases", nodes.node_auth_cases),
    ("dataset", nodes.node_dataset),
    ("trace_matrix", nodes.node_trace_matrix),
    ("exec_plan", nodes.node_exec_plan),
    ("critique", nodes.node_critique),
    ("question_gen", nodes.node_question_gen),
    ("assemble", nodes.node_assemble),
    ("persist", nodes.node_persist),
]


def build_qa_graph(checkpointer=None):
    """Compila el grafo del Agente QA (helper lineal compartido de la base)."""
    return build_linear_graph(QaState, _NODES, checkpointer)
