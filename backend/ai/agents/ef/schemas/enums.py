"""Enumeraciones de valores cerrados del EFArtifact.

Todas las claves/valores viajan en inglés donde son parte del contrato de datos;
las descripciones y textos de negocio van en español (ver CLAUDE.md).
"""

from enum import Enum


class SourceType(str, Enum):
    """Tipo de fuente analizada."""

    DOCUMENT = "document"  # archivo .docx / .pdf
    TEXT = "text"  # texto libre


class SourceFidelity(str, Enum):
    """Fidelidad de la extracción de la fuente.

    full: se extrajo la estructura completa (p. ej. .docx).
    partial: se extrajo parte (p. ej. PDF con estructura parcial).
    degraded: extracción degradada (p. ej. PDF solo texto sin topología).
    """

    FULL = "full"
    PARTIAL = "partial"
    DEGRADED = "degraded"


class Origin(str, Enum):
    """Procedencia de un ítem: declarado explícitamente o derivado por inferencia."""

    STATED = "stated"
    DERIVED = "derived"


class Cardinality(str, Enum):
    """Cardinalidad de una relación entre entidades."""

    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_MANY = "N:M"


class Audience(str, Enum):
    """Audiencia destinataria de una pregunta al analista."""

    NEGOCIO = "negocio"
    TECNICO = "tecnico"


class QuestionStatus(str, Enum):
    """Estado de una pregunta / supuesto en el ciclo de afinamiento."""

    PENDIENTE = "pendiente"
    CONFIRMADO = "confirmado"
    CORREGIDO = "corregido"


class Priority(str, Enum):
    """Prioridad de un requisito."""

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class HttpMethod(str, Enum):
    """Método HTTP de un endpoint inferido."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
