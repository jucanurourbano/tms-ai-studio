"""Enumeraciones de valores cerrados del ScrumArtifact.

Claves/valores del contrato en inglés; textos de negocio en español (CLAUDE.md).
Se reutilizan ``Origin`` / ``Audience`` / ``QuestionStatus`` del Agente EF.
"""

from enum import Enum, IntEnum


class MoscowPriority(str, Enum):
    """Prioridad MoSCoW de una historia (D3: primario en la priorización)."""

    MUST = "must"
    SHOULD = "should"
    COULD = "could"
    WONT = "wont"


class StoryPoints(IntEnum):
    """Escala Fibonacci cerrada para la estimación de historias (D9)."""

    SP_1 = 1
    SP_2 = 2
    SP_3 = 3
    SP_5 = 5
    SP_8 = 8
    SP_13 = 13
    SP_21 = 21


class AcceptanceFormat(str, Enum):
    """Formato de un criterio de aceptación."""

    GHERKIN = "gherkin"
    TEXT = "text"


class RiskSeverity(str, Enum):
    """Severidad de un riesgo detectado en el plan."""

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class BacklogMethod(str, Enum):
    """Método de ordenamiento del backlog de producto."""

    MOSCOW = "moscow"
    VALUE_EFFORT = "value_effort"
