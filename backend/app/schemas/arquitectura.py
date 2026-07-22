"""Esquemas de request/response de la API del Agente Arquitectura."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateDesignRequest(BaseModel):
    """Cuerpo para generar un diseño de arquitectura desde un plan Scrum listo."""

    scrum_job_id: str = Field(description="Id del job Scrum de origen (agent_jobs.id).")


class ArchitectValidationPatchRequest(BaseModel):
    """Registro de una validación del Arquitecto (v1: solo ``question``)."""

    target_type: Literal["question"] = "question"
    target_id: str
    status: Literal["pendiente", "confirmado", "corregido"]
    respuesta: Optional[str] = None
