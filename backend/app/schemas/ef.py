"""Esquemas de request/response de la API del Agente EF."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AnalyzeTextRequest(BaseModel):
    """Cuerpo JSON para analizar texto libre."""

    content: str = Field(min_length=100, description="Texto a analizar (mín. 100).")
    title: Optional[str] = Field(default=None, description="Título opcional.")


class ValidationPatchRequest(BaseModel):
    """Registro de una validación del ciclo de afinamiento."""

    target_type: Literal["question", "assumption"]
    target_id: str
    status: Literal["pendiente", "confirmado", "corregido"]
    respuesta: Optional[str] = None
