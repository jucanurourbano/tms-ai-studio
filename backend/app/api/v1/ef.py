"""Endpoints del Agente EF (API v1). Toda respuesta usa ApiResponse."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ai.errors import IngestError
from app.dependencies.database import get_session
from app.schemas.ef import AnalyzeTextRequest, ValidationPatchRequest
from app.services.ef_service import EFAnalysisService
from shared.responses.api_response import ApiResponse

router = APIRouter(prefix="/ef", tags=["Agente EF"])

_MIN_TEXT = 100


def _service(session: AsyncSession) -> EFAnalysisService:
    return EFAnalysisService(session)


@router.post("/analyze", summary="Analizar un documento o texto libre")
async def analyze(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un análisis EF.

    Acepta **multipart** (campo ``file``) o **JSON** ``{content, title}``
    (``content`` con mínimo 100 caracteres). Idempotente por hash: si ya existe
    un análisis completado para el mismo contenido, lo devuelve con ``cached=true``.
    """
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("application/json"):
        try:
            body = AnalyzeTextRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise IngestError("El texto debe tener al menos 100 caracteres.") from exc
        filename = f"{(body.title or 'texto')}.txt"
        content = body.content.encode("utf-8")
    elif content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise IngestError("Falta el archivo 'file' en el multipart.")
        filename = upload.filename or "archivo"
        content = await upload.read()
    else:
        raise IngestError(
            "Content-Type no soportado. Use application/json o multipart/form-data."
        )

    service = _service(session)
    job, cached = await service.create_analysis(
        filename, content, background_tasks=background_tasks
    )
    return ApiResponse.ok(
        data={"job_id": job.id, "status": job.status.value, "cached": cached},
        message="Análisis en curso" if not cached else "Resultado cacheado",
    )


@router.get("/jobs/{job_id}", summary="Estado, métricas y fuente de un job")
async def get_job(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve estado, métricas y datos de la fuente del job."""
    job = await _service(session).get_job(job_id)
    if job is None:
        return ApiResponse.fail(message="Job no encontrado", data={"job_id": job_id})
    return ApiResponse.ok(
        data={
            "job_id": job.id,
            "status": job.status.value,
            "parent_job_id": job.parent_job_id,
            "error": job.error,
            "metrics": job.metrics,
            "source_doc_id": job.source_doc_id,
        }
    )


@router.get("/jobs/{job_id}/artifact", summary="EFArtifact de un job")
async def get_artifact(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve el EFArtifact v1.2.0 persistido del job."""
    artifact = await _service(session).get_artifact(job_id)
    if artifact is None:
        return ApiResponse.fail(
            message="Artefacto no disponible", data={"job_id": job_id}
        )
    return ApiResponse.ok(data=artifact)


@router.get("/jobs", summary="Listado paginado de jobs")
async def list_jobs(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ApiResponse:
    """Lista los jobs (más recientes primero) con total."""
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
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                    "completed_at": (
                        j.completed_at.isoformat() if j.completed_at else None
                    ),
                }
                for j in jobs
            ],
        }
    )


@router.patch("/jobs/{job_id}/validations", summary="Registrar validación")
async def patch_validation(
    job_id: str,
    body: ValidationPatchRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Registra/actualiza una validación (pregunta o supuesto), sin mutar el artefacto."""
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


@router.get("/jobs/{job_id}/validations", summary="Resumen de validaciones")
async def get_validation_summary(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Resumen de validaciones con ``ready_for_next_stage`` (gate del Agente Scrum)."""
    summary = await _service(session).validation_summary(job_id)
    return ApiResponse.ok(data=summary)


@router.post("/jobs/{job_id}/refine", summary="Crear job hijo de afinamiento")
async def refine(
    job_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un job hijo (``parent_job_id``) reinyectando las respuestas confirmadas."""
    child = await _service(session).create_refine(
        job_id, background_tasks=background_tasks
    )
    return ApiResponse.ok(
        data={"job_id": child.id, "parent_job_id": child.parent_job_id},
        message="Refine en curso",
    )
