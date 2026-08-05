"""Esquemas de request/response de la API del Agente BD."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateModelRequest(BaseModel):
    """Cuerpo para generar un modelo de datos desde un diseño de arquitectura listo."""

    architecture_job_id: str = Field(
        description="Id del job de Arquitectura de origen (agent_jobs.id)."
    )
    engine_override: Optional[Literal["postgresql", "sqlserver", "oracle", "mysql"]] = (
        Field(
            default=None,
            description=(
                "Motor destino, si se quiere forzar uno distinto al que decidió la "
                "arquitectura. Útil cuando el diseño técnico aún no fijó el motor y no "
                "se quiere esperar a corregirlo."
            ),
        )
    )


class DbaValidationPatchRequest(BaseModel):
    """Registro de una validación del DBA (v1: solo ``question``)."""

    target_type: Literal["question"] = "question"
    target_id: str
    status: Literal["pendiente", "confirmado", "corregido"]
    respuesta: Optional[str] = None
