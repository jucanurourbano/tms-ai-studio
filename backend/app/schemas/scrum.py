"""Esquemas de request/response de la API del Agente Scrum."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreatePlanRequest(BaseModel):
    """Cuerpo para generar un plan ágil a partir de un job EF listo."""

    ef_job_id: str = Field(description="Id del job EF de origen (agent_jobs.id).")
    capacity_points: Optional[int] = Field(
        default=None, ge=1, description="Capacidad por sprint (D4: default 20)."
    )


class ScrumValidationPatchRequest(BaseModel):
    """Registro de una validación del PO (v1: solo ``question``)."""

    target_type: Literal["question"] = "question"
    target_id: str
    status: Literal["pendiente", "confirmado", "corregido"]
    respuesta: Optional[str] = None
