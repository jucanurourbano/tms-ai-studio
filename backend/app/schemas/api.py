"""Esquemas de request/response de la API del Agente API."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateSpecRequest(BaseModel):
    """Cuerpo para generar una especificación desde un modelo de datos listo."""

    bd_job_id: str = Field(description="Id del job de BD de origen (agent_jobs.id).")
    style_override: Optional[Literal["rest", "graphql", "grpc", "soap"]] = Field(
        default=None,
        description=(
            "Estilo de API, si se quiere forzar uno distinto al que decidió la "
            "arquitectura. v1 solo sabe especificar REST: cualquier otro se "
            "registra y genera una pregunta bloqueante."
        ),
    )


class TechLeadValidationPatchRequest(BaseModel):
    """Registro de una validación del líder técnico (v1: solo ``question``)."""

    target_type: Literal["question"] = "question"
    target_id: str
    status: Literal["pendiente", "confirmado", "corregido"]
    respuesta: Optional[str] = None
