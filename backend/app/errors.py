"""Errores de dominio a nivel de aplicación (fuera del dominio de agentes).

``AppError`` es la base que el middleware de excepciones traduce a un
``ApiResponse`` de error con el código HTTP adecuado. Comparte forma con
``ai.errors.AgentError`` pero cubre las preocupaciones transversales de la app
(p. ej. autenticación y autorización).
"""

from typing import Optional


class AppError(Exception):
    """Error base de la aplicación (envelope controlado)."""

    #: código HTTP sugerido para el middleware de la API.
    http_status: int = 400

    def __init__(self, message: str, *, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__


class AuthError(AppError):
    """Credenciales ausentes o inválidas (no autenticado)."""

    http_status = 401


class ForbiddenError(AppError):
    """Autenticado pero sin permisos suficientes para la operación."""

    http_status = 403


class NotFoundError(AppError):
    """Recurso solicitado inexistente."""

    http_status = 404


class ConflictError(AppError):
    """Conflicto con el estado actual (p. ej. email ya registrado)."""

    http_status = 409
