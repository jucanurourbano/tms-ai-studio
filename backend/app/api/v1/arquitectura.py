"""Endpoints del Agente Arquitectura (API v1). Toda respuesta usa ApiResponse."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.current_user import get_current_user
from app.dependencies.database import get_session
from app.schemas.arquitectura import (
    ArchitectValidationPatchRequest,
    CreateDesignRequest,
)
from app.services.arquitectura_service import ArquitecturaService
from shared.responses.api_response import ApiResponse

# Todas las rutas del Agente Arquitectura exigen autenticación (401 sin token).
router = APIRouter(
    prefix="/arquitectura",
    tags=["Agente Arquitectura"],
    dependencies=[Depends(get_current_user)],
)


def _service(session: AsyncSession) -> ArquitecturaService:
    return ArquitecturaService(session)


@router.post("/designs", summary="Generar un diseño desde un plan Scrum listo")
async def create_design(
    body: CreateDesignRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un diseño de arquitectura.

    Verifica el **gate de entrada**: el plan Scrum debe estar listo
    (``ready_for_next_stage=true``). Si no lo está, responde ``409`` con un
    mensaje claro. Enlaza al job Scrum (``input_job_id``); el EF se resuelve
    transitivamente.
    """
    job = await _service(session).create_design(
        body.scrum_job_id, background_tasks=background_tasks
    )
    return ApiResponse.ok(
        data={
            "job_id": job.id,
            "status": job.status.value,
            "input_job_id": job.input_job_id,
        },
        message="Diseño de arquitectura en curso",
    )


@router.get(
    "/available-scrum-jobs",
    summary="Jobs Scrum y si están listos para diseñar arquitectura",
)
async def available_scrum_jobs(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ApiResponse:
    """Lista jobs Scrum marcando ``ready_for_next_stage`` (para elegir el origen)."""
    items = await _service(session).list_ready_scrum_jobs(limit=limit, offset=offset)
    return ApiResponse.ok(data={"items": items})


@router.get("/jobs/{job_id}", summary="Estado y métricas de un job de Arquitectura")
async def get_job(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve estado, métricas y enlaces del job de Arquitectura."""
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


@router.get("/jobs/{job_id}/artifact", summary="ArchitectureArtifact de un job")
async def get_artifact(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve el ArchitectureArtifact v1.0.0 persistido del job."""
    artifact = await _service(session).get_artifact(job_id)
    if artifact is None:
        return ApiResponse.fail(
            message="Artefacto no disponible", data={"job_id": job_id}
        )
    return ApiResponse.ok(data=artifact)


@router.get("/jobs", summary="Listado paginado de jobs de Arquitectura")
async def list_jobs(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ApiResponse:
    """Lista los jobs de Arquitectura (más recientes primero) con total."""
    jobs, total = await _service(session).list_jobs(limit=limit, offset=offset)
    return ApiResponse.ok(
        data={
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [
                {
                    "job_id": j.id,
                    "title": j.title,
                    "source_type": j.source_type,
                    "status": j.status.value,
                    "version": j.version,
                    "parent_job_id": j.parent_job_id,
                    "input_job_id": j.input_job_id,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                    "completed_at": (
                        j.completed_at.isoformat() if j.completed_at else None
                    ),
                }
                for j in jobs
            ],
        }
    )


@router.patch(
    "/jobs/{job_id}/validations", summary="Registrar validación del Arquitecto"
)
async def patch_validation(
    job_id: str,
    body: ArchitectValidationPatchRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Registra/actualiza una validación del Arquitecto, sin mutar el artefacto."""
    val = await _service(session).register_validation(
        job_id=job_id,
        target_id=body.target_id,
        status=body.status,
        respuesta=body.respuesta,
        target_type=body.target_type,
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
    """Resumen de validaciones con el ``ready_for_next_stage`` compuesto.

    Habilita a los Agentes **BD** y **API** cuando está en verde.
    """
    summary = await _service(session).validation_summary(job_id)
    return ApiResponse.ok(data=summary)


@router.post("/jobs/{job_id}/refine", summary="Crear job hijo de afinamiento")
async def refine(
    job_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un job hijo reinyectando las respuestas confirmadas del Arquitecto."""
    child = await _service(session).create_refine(
        job_id, background_tasks=background_tasks
    )
    return ApiResponse.ok(
        data={"job_id": child.id, "parent_job_id": child.parent_job_id},
        message="Refine en curso",
    )
