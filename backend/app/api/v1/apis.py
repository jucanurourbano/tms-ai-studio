"""Endpoints del Agente API (API v1). Toda respuesta usa ApiResponse.

El router vive bajo ``/apis`` y no bajo ``/api``: el prefijo global ya es
``/api/v1``, así que ``/api/v1/api/...`` se leería mal en cada log y en cada
llamada. El módulo se llama ``apis.py`` por lo mismo, y para no colisionar con el
paquete ``ai/agents/api``.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import AccessLevel, Module
from app.dependencies.database import get_session
from app.dependencies.permissions import require_module
from app.models.agent import JobStatusGroup
from app.models.user import User
from app.schemas.api import CreateSpecRequest, TechLeadValidationPatchRequest
from app.services.api_service import ApiSpecService
from shared.responses.api_response import ApiResponse

# Autenticación (401 sin token) + acceso de LECTURA al módulo API en todas las
# rutas; las de escritura añaden su exigencia de nivel FULL.
_READ = Depends(require_module(Module.API, AccessLevel.READ))
_WRITE = Depends(require_module(Module.API, AccessLevel.FULL))

router = APIRouter(
    prefix="/apis",
    tags=["Agente API"],
    dependencies=[_READ],
)


def _service(session: AsyncSession) -> ApiSpecService:
    return ApiSpecService(session)


@router.post(
    "/specs",
    summary="Generar una especificación de API desde un modelo de datos listo",
)
async def create_spec(
    body: CreateSpecRequest,
    background_tasks: BackgroundTasks,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea una especificación de API.

    Verifica el **gate de entrada**: el modelo de datos debe estar listo
    (``ready_for_next_stage=true``). Si no lo está, responde ``409`` con un mensaje
    claro. Enlaza al job de BD (``input_job_id``); Arquitectura, Scrum y EF se
    resuelven transitivamente.
    """
    job = await _service(session).create_spec(
        body.bd_job_id,
        style_override=body.style_override,
        background_tasks=background_tasks,
        actor_id=actor.id,
    )
    return ApiResponse.ok(
        data={
            "job_id": job.id,
            "status": job.status.value,
            "input_job_id": job.input_job_id,
        },
        message="Especificación de API en curso",
    )


@router.get(
    "/available-bd-jobs",
    summary="Modelos de datos y si están listos para especificar la API",
)
async def available_bd_jobs(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ApiResponse:
    """Lista modelos marcando ``ready_for_next_stage`` (para elegir el origen)."""
    items = await _service(session).list_ready_bd_jobs(limit=limit, offset=offset)
    return ApiResponse.ok(data={"items": items})


@router.get("/jobs/{job_id}", summary="Estado y métricas de un job de API")
async def get_job(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve estado, métricas y enlaces del job de API."""
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


@router.get("/jobs/{job_id}/artifact", summary="ApiArtifact de un job")
async def get_artifact(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve el ApiArtifact v1.0.0 persistido del job."""
    artifact = await _service(session).get_artifact(job_id)
    if artifact is None:
        return ApiResponse.fail(
            message="Artefacto no disponible", data={"job_id": job_id}
        )
    return ApiResponse.ok(data=artifact)


@router.get(
    "/jobs/{job_id}/openapi",
    summary="Documento OpenAPI del contrato, en YAML o JSON",
    # Devuelve envelope o archivo según `descargar`: FastAPI no puede derivar un
    # response_model de esa unión, y aquí el tipo lo decide el cliente.
    response_model=None,
)
async def get_openapi(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    formato: str = Query(
        "yaml",
        pattern="^(yaml|json)$",
        description=(
            "`yaml` devuelve el documento canónico (el que se validó); `json`, la "
            "misma especificación re-serializada, sin llamar al modelo."
        ),
    ),
    descargar: bool = Query(
        False, description="Si es `true`, responde como archivo adjunto."
    ),
) -> ApiResponse | PlainTextResponse:
    """Devuelve el documento OpenAPI 3.1 del contrato, como envelope o archivo."""
    data = await _service(session).render_openapi(job_id, formato=formato)
    if data is None:
        return ApiResponse.fail(
            message="Artefacto no disponible", data={"job_id": job_id}
        )
    if descargar:
        media = (
            "application/json; charset=utf-8"
            if formato == "json"
            else "application/yaml; charset=utf-8"
        )
        return PlainTextResponse(
            data["content"],
            media_type=media,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="openapi_{job_id}.{formato}"'
                )
            },
        )
    return ApiResponse.ok(data=data)


@router.get("/jobs", summary="Listado paginado de jobs de API")
async def list_jobs(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    estado: JobStatusGroup = Query(
        JobStatusGroup.TODOS,
        description=(
            "Grupo de estado: completados | avisos | en_proceso | fallidos | todos."
        ),
    ),
) -> ApiResponse:
    """Lista los jobs de API (más recientes primero) con total y contadores."""
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
    summary="Registrar validación del líder técnico",
)
async def patch_validation(
    job_id: str,
    body: TechLeadValidationPatchRequest,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Registra/actualiza una validación, sin mutar el artefacto."""
    val = await _service(session).register_validation(
        job_id=job_id,
        target_id=body.target_id,
        status=body.status,
        respuesta=body.respuesta,
        target_type=body.target_type,
        actor_id=actor.id,
    )
    return ApiResponse.ok(
        data={
            "job_id": job_id,
            "target_id": val.target_id,
            "status": val.status.value,
        },
        message="Validación registrada",
    )


@router.get(
    "/jobs/{job_id}/validations",
    summary="Resumen de validaciones y semáforo del contrato",
)
async def get_validations(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve las validaciones y si el contrato habilita a Backend y Frontend."""
    return ApiResponse.ok(data=await _service(session).validation_summary(job_id))


@router.post(
    "/jobs/{job_id}/refine",
    summary="Generar una especificación afinada con las respuestas del líder técnico",
)
async def refine(
    job_id: str,
    background_tasks: BackgroundTasks,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un job hijo reinyectando las respuestas como contexto autoritativo."""
    child = await _service(session).create_refine(
        job_id, background_tasks=background_tasks, actor_id=actor.id
    )
    return ApiResponse.ok(
        data={
            "job_id": child.id,
            "parent_job_id": child.parent_job_id,
            "version": child.version,
            "status": child.status.value,
        },
        message="Especificación afinada en curso",
    )
