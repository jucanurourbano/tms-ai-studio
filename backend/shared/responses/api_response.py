"""Envelope estándar de respuesta de la API.

Toda respuesta de la API expone la misma estructura: ``{success, message, data}``.
Es una convención obligatoria del proyecto (ver CLAUDE.md).
"""

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Envoltorio uniforme para toda respuesta de la API.

    Atributos:
        success: Indica si la operación fue exitosa.
        message: Mensaje legible (en español) describiendo el resultado.
        data: Carga útil de la respuesta (puede ser ``None``).
    """

    success: bool
    message: str
    data: Optional[T] = None

    @classmethod
    def ok(cls, data: Optional[T] = None, message: str = "OK") -> "ApiResponse[T]":
        """Construye una respuesta exitosa."""
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str, data: Optional[T] = None) -> "ApiResponse[T]":
        """Construye una respuesta de error."""
        return cls(success=False, message=message, data=data)
