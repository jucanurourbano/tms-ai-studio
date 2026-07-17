"""Jerarquía de errores del dominio de agentes de IA.

``AgentError`` es la base que el middleware de excepciones de la API captura
(ver Bloque 8) para devolver un ``ApiResponse`` de error controlado.
"""

from typing import Optional


class AgentError(Exception):
    """Error base del dominio de agentes."""

    #: código HTTP sugerido para el middleware de la API.
    http_status: int = 400

    def __init__(self, message: str, *, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__


class IngestError(AgentError):
    """Error durante la ingesta de una fuente."""


class UnsupportedFileError(IngestError):
    """Tipo/extensión de archivo no soportado."""


class FileTooLargeError(IngestError):
    """El archivo supera el tamaño máximo permitido."""

    http_status = 413


class ParserError(AgentError):
    """Error al parsear una fuente."""


class ScannedPDFError(ParserError):
    """PDF sin texto extraíble (escaneado). OCR se difiere a v1.1."""


class PipelineError(AgentError):
    """Error genérico durante la ejecución del pipeline."""

    http_status = 500
