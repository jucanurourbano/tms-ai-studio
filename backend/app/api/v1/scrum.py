"""Endpoints del Agente Scrum (API v1). Toda respuesta usa ApiResponse."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import AccessLevel, Module
from app.dependencies.database import get_session
from app.dependencies.permissions import require_module
from app.models.agent import JobStatusGroup
from app.models.user import User
from app.schemas.scrum import (
    AssignSprintRequest,
    AssignStoryRequest,
    CreatePlanRequest,
    ScrumValidationPatchRequest,
)
from app.services.scrum_service import ScrumPlanningService
from shared.responses.api_response import ApiResponse

# Autenticación (401 sin token) + acceso de LECTURA al módulo Scrum en todas las
# rutas; los endpoints de escritura añaden su propia exigencia de nivel FULL.
_READ = Depends(require_module(Module.SCRUM, AccessLevel.READ))
_WRITE = Depends(require_module(Module.SCRUM, AccessLevel.FULL))

router = APIRouter(prefix="/scrum", tags=["Agente Scrum"], dependencies=[_READ])


def _service(session: AsyncSession) -> ScrumPlanningService:
    return ScrumPlanningService(session)


@router.post(
    "/plans",
    summary="Generar un plan ágil desde un job EF listo",
)
async def create_plan(
    body: CreatePlanRequest,
    background_tasks: BackgroundTasks,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un plan Scrum.

    Verifica el **gate de entrada**: el EF debe estar listo
    (``ready_for_next_stage=true``). Si no lo está, responde ``409`` con un mensaje
    claro (completar preguntas bloqueantes o generar EF afinada).
    """
    job = await _service(session).create_plan(
        body.ef_job_id,
        body.capacity_points,
        background_tasks=background_tasks,
        actor_id=actor.id,
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
    estado: JobStatusGroup = Query(
        JobStatusGroup.TODOS,
        description="Grupo de estado: completados | avisos | en_proceso | fallidos | todos.",
    ),
) -> ApiResponse:
    """Lista los jobs Scrum (más recientes primero) con total.

    ``estado`` filtra por grupo (el filtro se aplica en la consulta, no sobre la
    página, para que la paginación de cada pestaña sea real). ``total`` es el
    total DEL FILTRO; ``status_counts`` trae el recuento de los cinco grupos sobre
    todos los jobs del agente, que es lo que necesitan los tabs del historial.
    """
    service = _service(session)
    jobs, total = await service.list_jobs(
        limit=limit, offset=offset, status_group=estado
    )
    return ApiResponse.ok(
        data={
            "total": total,
            "limit": limit,
            "offset": offset,
            "estado": estado.value,
            "status_counts": await service.count_jobs_by_group(),
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
    "/jobs/{job_id}/validations",
    summary="Registrar validación del PO",
)
async def patch_validation(
    job_id: str,
    body: ScrumValidationPatchRequest,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Registra/actualiza una validación del PO, sin mutar el artefacto."""
    val = await _service(session).register_validation(
        job_id=job_id,
        target_type=body.target_type,
        target_id=body.target_id,
        status=body.status,
        respuesta=body.respuesta,
        actor_id=actor.id,
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


@router.get(
    "/team",
    summary="Colaboradores disponibles para asignar historias",
)
async def list_team(session: AsyncSession = Depends(get_session)) -> ApiResponse:
    """Lista los colaboradores asignables (activos, vigentes y disponibles).

    Vive bajo ``/scrum`` y no bajo ``/auth`` a propósito: lo necesita cualquiera
    que consulte un plan (nivel READ del módulo Scrum) y expone solo el perfil
    mínimo de equipo, sin abrir el panel de usuarios a quien no tiene
    Configuración.
    """
    return ApiResponse.ok(data={"items": await _service(session).list_team()})


@router.get(
    "/jobs/{job_id}/assignments",
    summary="Asignaciones de historias del plan",
)
async def list_assignments(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Asignaciones EFECTIVAS del plan, con la cascada del sprint ya resuelta.

    Viven **fuera del artefacto** (``story_assignments`` / ``sprint_assignments``),
    igual que las validaciones: el ``ScrumArtifact`` no se muta nunca. Cada
    historia indica en ``source`` si su responsable es explícito (``story``) o
    heredado del sprint (``sprint``).
    """
    return ApiResponse.ok(data=await _service(session).list_assignments(job_id))


@router.patch(
    "/jobs/{job_id}/assignments",
    summary="Asignar o desasignar una historia",
)
async def patch_assignment(
    job_id: str,
    body: AssignStoryRequest,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Asigna la historia a un colaborador; ``user_id: null`` la desasigna.

    Exige nivel FULL del módulo Scrum, que es lo que tienen `analista` y `admin`.
    """
    data = await _service(session).assign_story(
        job_id=job_id,
        story_id=body.story_id,
        user_id=body.user_id,
        actor_id=actor.id,
    )
    return ApiResponse.ok(
        data=data,
        message="Historia asignada" if body.user_id else "Asignación retirada",
    )


@router.patch(
    "/jobs/{job_id}/sprint-assignments",
    summary="Asignar o desasignar un sprint completo",
)
async def patch_sprint_assignment(
    job_id: str,
    body: AssignSprintRequest,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Asigna el sprint a un colaborador; ``user_id: null`` lo desasigna.

    Sus historias **sin responsable propio** pasan a mostrarse a nombre de esa
    persona (cascada derivada, no materializada: la asignación por historia
    prevalece). Exige nivel FULL del módulo Scrum (`analista` y `admin`).
    """
    data = await _service(session).assign_sprint(
        job_id=job_id,
        sprint_id=body.sprint_id,
        user_id=body.user_id,
        actor_id=actor.id,
    )
    return ApiResponse.ok(
        data=data,
        message="Sprint asignado" if body.user_id else "Asignación de sprint retirada",
    )


@router.get("/jobs/{job_id}/export", summary="Export compatible con ClickUp (CSV/JSON)")
async def export_clickup(
    job_id: str,
    format: str = Query("csv", pattern="^(csv|json)$"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Fase (a): export CSV/JSON compatible con la importación de ClickUp.

    Solo lectura del artefacto -> archivo (sin token, sin escritura en ClickUp).
    """
    payload = await _service(session).export_clickup(job_id, format)
    return ApiResponse.ok(data=payload, message="Export generado")


@router.post(
    "/jobs/{job_id}/refine",
    summary="Crear job hijo de afinamiento (PO)",
)
async def refine(
    job_id: str,
    background_tasks: BackgroundTasks,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un job hijo reinyectando las respuestas confirmadas del PO."""
    child = await _service(session).create_refine(
        job_id, background_tasks=background_tasks, actor_id=actor.id
    )
    return ApiResponse.ok(
        data={"job_id": child.id, "parent_job_id": child.parent_job_id},
        message="Refine en curso",
    )
