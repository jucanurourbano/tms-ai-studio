"""Manejo de excepciones de dominio -> ApiResponse de error controlado."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ai.errors import AgentError
from shared.responses.api_response import ApiResponse


def register_exception_handlers(app: FastAPI) -> None:
    """Registra el handler de ``AgentError`` en la app."""

    @app.exception_handler(AgentError)
    async def _handle_agent_error(request: Request, exc: AgentError) -> JSONResponse:
        payload = ApiResponse.fail(message=exc.message, data={"code": exc.code})
        return JSONResponse(
            status_code=exc.http_status,
            content=payload.model_dump(),
        )
