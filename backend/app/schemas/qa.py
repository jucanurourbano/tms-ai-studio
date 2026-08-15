"""Esquemas de request/response de la API del Agente QA."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateTestPlanRequest(BaseModel):
    """Cuerpo para generar un plan de pruebas desde un plan Scrum listo."""

    scrum_job_id: str = Field(
        description="Id del job de Scrum de origen (agent_jobs.id)."
    )
    api_job_id: Optional[str] = Field(
        default=None,
        description=(
            "Contrato de API contra el que diseñar los casos de autorización. Es "
            "**opcional y explícito**: el contrato no está en la cadena hacia atrás "
            "del plan Scrum sino hacia delante, así que no se descubre. Si se indica, "
            "se verifica que pertenezca a esta misma cadena; si no se indica, el plan "
            "se genera sin casos de autorización y lo declara."
        ),
    )
    coverage_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Cobertura exigida de los criterios de historias must/should. Por "
            "defecto, la de `settings` (1.0)."
        ),
    )
    max_cases_per_criterion: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Techo de casos por criterio. Lo que se pode queda registrado con su id: "
            "un tope silencioso se leería como cobertura completa."
        ),
    )
    manual_capacity_minutes: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Minutos disponibles por sesión de QA. Si se informa, el plan estima "
            "cuántas sesiones necesita la ejecución manual."
        ),
    )


class QaLeadValidationPatchRequest(BaseModel):
    """Registro de una validación del QA lead (v1: solo ``question``)."""

    target_type: Literal["question"] = "question"
    target_id: str
    status: Literal["pendiente", "confirmado", "corregido"]
    respuesta: Optional[str] = None
