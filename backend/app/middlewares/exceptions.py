"""Manejo de excepciones de dominio -> ApiResponse de error controlado."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ai.errors import AgentError
from app.errors import AppError
from shared.responses.api_response import ApiResponse


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los handlers de errores de dominio (``ApiResponse`` uniforme)."""

    @app.exception_handler(AgentError)
    async def _handle_agent_error(request: Request, exc: AgentError) -> JSONResponse:
        payload = ApiResponse.fail(message=exc.message, data={"code": exc.code})
        return JSONResponse(
            status_code=exc.http_status,
            content=payload.model_dump(),
        )

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        payload = ApiResponse.fail(message=exc.message, data={"code": exc.code})
        return JSONResponse(
            status_code=exc.http_status,
            content=payload.model_dump(),
        )
