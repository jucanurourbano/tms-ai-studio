"""Endpoints del Agente Scrum (API v1). Toda respuesta usa ApiResponse."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.database import get_session
from app.schemas.scrum import CreatePlanRequest, ScrumValidationPatchRequest
from app.services.scrum_service import ScrumPlanningService
from shared.responses.api_response import ApiResponse

router = APIRouter(prefix="/scrum", tags=["Agente Scrum"])


def _service(session: AsyncSession) -> ScrumPlanningService:
    return ScrumPlanningService(session)


@router.post("/plans", summary="Generar un plan ágil desde un job EF listo")
async def create_plan(
    body: CreatePlanRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un plan Scrum.

    Verifica el **gate de entrada**: el EF debe estar listo
    (``ready_for_next_stage=true``). Si no lo está, responde ``409`` con un mensaje
    claro (completar preguntas bloqueantes o generar EF afinada).
    """
    job = await _service(session).create_plan(
        body.ef_job_id, body.capacity_points, background_tasks=background_tasks
    )
    return ApiResponse.ok(
        data={
            "job_id": job.id,
            "status": job.status.value,
            "input_job_id": job.input_job_id,
        },
        message="Planificación en curso",
    )


@router.get("/available-ef-jobs", summary="Jobs EF y si están listos para planificar")
async def available_ef_jobs(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ApiResponse:
    """Lista jobs EF marcando ``ready_for_next_stage`` (para elegir el de origen)."""
    items = await _service(session).list_ready_ef_jobs(limit=limit, offset=offset)
    return ApiResponse.ok(data={"items": items})


@router.get("/jobs/{job_id}", summary="Estado y métricas de un job Scrum")
async def get_job(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve estado, métricas y enlaces del job Scrum."""
    job = await _service(session).get_job(job_id)
    if job is None:
        return ApiResponse.fail(message="Job no encontrado", data={"job_id": job_id})
    return ApiResponse.ok(
        data={
            "job_id": job.id,
            "status": job.status.value,
            "parent_job_id": job.parent_job_id,
            "input_job_id": job.input_job_id,
            "error": job.error,
            "metrics": job.metrics,
        }
    )


@router.get("/jobs/{job_id}/artifact", summary="ScrumArtifact de un job")
async def get_artifact(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve el ScrumArtifact v1.0.0 persistido del job."""
    artifact = await _service(session).get_artifact(job_id)
    if artifact is None:
        return ApiResponse.fail(
            message="Artefacto no disponible", data={"job_id": job_id}
        )
    return ApiResponse.ok(data=artifact)


@router.get("/jobs", summary="Listado paginado de jobs Scrum")
async def list_jobs(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ApiResponse:
    """Lista los jobs Scrum (más recientes primero) con total."""
    jobs, total = await _service(session).list_jobs(limit=limit, offset=offset)
    return ApiResponse.ok(
        data={
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [
                {
                    "job_id": j.id,
                    "status": j.status.value,
                    "parent_job_id": j.parent_job_id,
                    "input_job_id": j.input_job_id,
                }
                for j in jobs
            ],
        }
    )


@router.patch("/jobs/{job_id}/validations", summary="Registrar validación del PO")
async def patch_validation(
    job_id: str,
    body: ScrumValidationPatchRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Registra/actualiza una validación del PO, sin mutar el artefacto."""
    val = await _service(session).register_validation(
        job_id=job_id,
        target_type=body.target_type,
        target_id=body.target_id,
        status=body.status,
        respuesta=body.respuesta,
    )
    return ApiResponse.ok(
        data={
            "target_type": val.target_type.value,
            "target_id": val.target_id,
            "status": val.status.value,
        },
        message="Validación registrada",
    )


@router.get("/jobs/{job_id}/validations", summary="Resumen + semáforo compuesto")
async def get_validation_summary(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Resumen de validaciones con el ``ready_for_next_stage`` compuesto (D5)."""
    summary = await _service(session).validation_summary(job_id)
    return ApiResponse.ok(data=summary)


@router.post("/jobs/{job_id}/refine", summary="Crear job hijo de afinamiento (PO)")
async def refine(
    job_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un job hijo reinyectando las respuestas confirmadas del PO."""
    child = await _service(session).create_refine(
        job_id, background_tasks=background_tasks
    )
    return ApiResponse.ok(
        data={"job_id": child.id, "parent_job_id": child.parent_job_id},
        message="Refine en curso",
    )
