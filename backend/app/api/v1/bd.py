"""Endpoints del Agente BD (API v1). Toda respuesta usa ApiResponse."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import AccessLevel, Module
from app.dependencies.database import get_session
from app.dependencies.permissions import require_module
from app.models.agent import JobStatusGroup
from app.models.user import User
from app.schemas.bd import CreateModelRequest, DbaValidationPatchRequest
from app.services.bd_service import BdModelingService
from shared.responses.api_response import ApiResponse

# Autenticación (401 sin token) + acceso de LECTURA al módulo BD en todas las
# rutas; las de escritura añaden su exigencia de nivel FULL.
_READ = Depends(require_module(Module.BD, AccessLevel.READ))
_WRITE = Depends(require_module(Module.BD, AccessLevel.FULL))

router = APIRouter(
    prefix="/bd",
    tags=["Agente BD"],
    dependencies=[_READ],
)


def _service(session: AsyncSession) -> BdModelingService:
    return BdModelingService(session)


@router.post(
    "/models",
    summary="Generar un modelo de datos desde un diseño de arquitectura listo",
)
async def create_model(
    body: CreateModelRequest,
    background_tasks: BackgroundTasks,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un modelo de datos físico.

    Verifica el **gate de entrada**: el diseño de arquitectura debe estar listo
    (``ready_for_next_stage=true``). Si no lo está, responde ``409`` con un mensaje
    claro. Enlaza al job de Arquitectura (``input_job_id``); Scrum y EF se
    resuelven transitivamente.
    """
    job = await _service(session).create_model(
        body.architecture_job_id,
        engine_override=body.engine_override,
        background_tasks=background_tasks,
        actor_id=actor.id,
    )
    return ApiResponse.ok(
        data={
            "job_id": job.id,
            "status": job.status.value,
            "input_job_id": job.input_job_id,
        },
        message="Modelo de datos en curso",
    )


@router.get(
    "/available-architecture-jobs",
    summary="Diseños de arquitectura y si están listos para modelar datos",
)
async def available_architecture_jobs(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ApiResponse:
    """Lista diseños marcando ``ready_for_next_stage`` (para elegir el origen)."""
    items = await _service(session).list_ready_architecture_jobs(
        limit=limit, offset=offset
    )
    return ApiResponse.ok(data={"items": items})


@router.get("/jobs/{job_id}", summary="Estado y métricas de un job de BD")
async def get_job(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve estado, métricas y enlaces del job de BD."""
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


@router.get("/jobs/{job_id}/artifact", summary="DatabaseArtifact de un job")
async def get_artifact(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve el DatabaseArtifact v1.0.0 persistido del job."""
    artifact = await _service(session).get_artifact(job_id)
    if artifact is None:
        return ApiResponse.fail(
            message="Artefacto no disponible", data={"job_id": job_id}
        )
    return ApiResponse.ok(data=artifact)


@router.get(
    "/jobs/{job_id}/ddl",
    summary="DDL del modelo, opcionalmente re-renderizado a otro motor",
    # Devuelve envelope o archivo según `formato`: FastAPI no puede derivar un
    # response_model de esa unión, y aquí el tipo lo decide el cliente.
    response_model=None,
)
async def get_ddl(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    engine: str | None = Query(
        None,
        pattern="^(postgresql|sqlserver|oracle|mysql)$",
        description=(
            "Motor destino. Si difiere del que decidió la arquitectura, el DDL se "
            "vuelve a renderizar SIN llamar al modelo (el artefacto guarda el tipo "
            "lógico de cada columna). No modifica el artefacto."
        ),
    ),
    formato: str = Query(
        "json",
        pattern="^(json|sql)$",
        description="`json` devuelve los scripts por separado; `sql`, un archivo.",
    ),
) -> ApiResponse | PlainTextResponse:
    """Devuelve el DDL del modelo, en JSON o como archivo `.sql` descargable."""
    data = await _service(session).render_ddl(job_id, engine=engine)
    if data is None:
        return ApiResponse.fail(
            message="Artefacto no disponible", data={"job_id": job_id}
        )
    if formato == "sql":
        return PlainTextResponse(
            data["sql"],
            media_type="application/sql; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="modelo_{job_id}_{data["engine"]}.sql"'
                )
            },
        )
    return ApiResponse.ok(data=data)


@router.get("/jobs", summary="Listado paginado de jobs de BD")
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
    """Lista los jobs de BD (más recientes primero) con total y contadores."""
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
    summary="Registrar validación del DBA",
)
async def patch_validation(
    job_id: str,
    body: DbaValidationPatchRequest,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Registra/actualiza una validación del DBA, sin mutar el artefacto."""
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

    Habilita al **Agente API** cuando está en verde.
    """
    summary = await _service(session).validation_summary(job_id)
    return ApiResponse.ok(data=summary)


@router.post(
    "/jobs/{job_id}/refine",
    summary="Crear job hijo de afinamiento",
)
async def refine(
    job_id: str,
    background_tasks: BackgroundTasks,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un job hijo reinyectando las respuestas confirmadas del DBA."""
    child = await _service(session).create_refine(
        job_id, background_tasks=background_tasks, actor_id=actor.id
    )
    return ApiResponse.ok(
        data={"job_id": child.id, "parent_job_id": child.parent_job_id},
        message="Refine en curso",
    )
