"""Endpoints del Inventario de Sistemas (API v1). Toda respuesta usa ApiResponse.

Lectura para todos los roles (el inventario es conocimiento transversal) y
escritura para ``admin``/``arquitecto``, que son quienes lo curan. Ver la
justificación de la excepción a la regla de forma en ``app/core/permissions.py``.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ai.inventory.ddl_import import DdlImportError, parse_ddl
from ai.inventory.doc_import import (
    build_assets,
    build_fragments,
    document_to_cir,
    extract_knowledge,
)
from ai.tools.ingest import LocalStorage, ingest
from app.config.settings import settings
from app.core.permissions import AccessLevel, Module
from app.dependencies.current_user import get_current_user
from app.dependencies.database import get_session
from app.dependencies.permissions import require_admin_role, require_module
from app.errors import ConflictError
from app.models.inventory import (
    InventoryAssetOrigin,
    InventoryAssetType,
    InventorySystemKind,
)
from app.models.user import User
from app.schemas.inventario import (
    CreateAssetRequest,
    CreateSystemRequest,
    IntrospectRequest,
    PromoteJobRequest,
    UpdateAssetStatusRequest,
    UpdateSystemRequest,
)
from app.services.introspection_service import (
    assert_source_authorized,
    available_sources,
    introspect_postgres,
    origin_ref_for,
)
from app.services.inventory_service import InventoryService
from shared.responses.api_response import ApiResponse

_READ = Depends(require_module(Module.INVENTARIO, AccessLevel.READ))
_WRITE = Depends(require_module(Module.INVENTARIO, AccessLevel.FULL))

router = APIRouter(
    prefix="/inventario",
    tags=["Inventario de Sistemas"],
    dependencies=[_READ],
)


def _service(session: AsyncSession) -> InventoryService:
    return InventoryService(session)


# --- sistemas ---------------------------------------------------------------


@router.get("/systems", summary="Sistemas inventariados")
async def list_systems(
    session: AsyncSession = Depends(get_session),
    kind: Optional[InventorySystemKind] = Query(
        None, description="Filtra por papel del sistema (destino/legado/externo)"
    ),
) -> ApiResponse:
    """Lista los sistemas con el conteo de sus activos vigentes por tipo."""
    items = await _service(session).list_systems(kind=kind)
    return ApiResponse.ok(data={"items": items})


@router.post("/systems", summary="Registrar un sistema en el inventario")
async def create_system(
    body: CreateSystemRequest,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Da de alta un sistema. El nombre es único (409 si ya existe)."""
    data = await _service(session).create_system(
        name=body.name,
        kind=body.kind,
        description=body.description,
        status=body.status,
        stack=[s.model_dump(mode="json") for s in body.stack] if body.stack else None,
        actor_id=actor.id,
    )
    return ApiResponse.ok(data=data, message="Sistema registrado en el inventario")


@router.get("/systems/{system_id}", summary="Ficha de un sistema y sus activos")
async def get_system(
    system_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve el sistema con sus activos vigentes (sin los contenidos)."""
    return ApiResponse.ok(data=await _service(session).get_system_detail(system_id))


@router.patch("/systems/{system_id}", summary="Editar un sistema")
async def update_system(
    system_id: str,
    body: UpdateSystemRequest,
    _actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Aplica **solo lo informado**; los campos ausentes no se tocan."""
    cambios = body.model_dump(exclude_unset=True)
    if body.stack is not None:
        cambios["stack"] = [s.model_dump(mode="json") for s in body.stack]
    data = await _service(session).update_system(system_id, cambios)
    return ApiResponse.ok(data=data, message="Sistema actualizado")


@router.delete("/systems/{system_id}", summary="Eliminar un sistema del inventario")
async def delete_system(
    system_id: str,
    _actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Elimina el sistema **con todos sus activos y versiones** (en cascada)."""
    await _service(session).delete_system(system_id)
    return ApiResponse.ok(
        data={"system_id": system_id}, message="Sistema eliminado del inventario"
    )


# --- activos ----------------------------------------------------------------


@router.get("/systems/{system_id}/assets", summary="Activos vigentes de un sistema")
async def list_assets(
    system_id: str,
    session: AsyncSession = Depends(get_session),
    asset_type: Optional[InventoryAssetType] = Query(
        None, description="Filtra por tipo (db_schema/module/api/document)"
    ),
) -> ApiResponse:
    """Lista los activos en su versión vigente, con un resumen de su contenido."""
    items = await _service(session).list_assets(system_id, asset_type=asset_type)
    return ApiResponse.ok(data={"items": items})


@router.post("/systems/{system_id}/assets", summary="Registrar un activo (o versión)")
async def create_asset(
    system_id: str,
    body: CreateAssetRequest,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Registra un activo. Si ya existe ese nombre, crea la **versión siguiente**.

    La versión anterior se conserva: el inventario no pierde memoria.
    """
    data = await _service(session).add_asset(
        system_id,
        asset_type=body.asset_type,
        name=body.name,
        content=body.content,
        origin=body.origin,
        origin_ref=body.origin_ref,
        description=body.description,
        actor_id=actor.id,
    )
    return ApiResponse.ok(
        data=data, message=f"Activo registrado (versión {data['version']})"
    )


# --- ingesta de esquemas de BD (INV2) ---------------------------------------


@router.post(
    "/systems/{system_id}/assets/ddl",
    summary="Cargar un esquema desde un dump DDL (.sql)",
)
async def upload_ddl(
    system_id: str,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
    file: UploadFile = File(..., description="Archivo .sql con el DDL del esquema"),
    name: str = Query("core", description="Nombre del activo db_schema"),
    engine: str = Query("postgresql", description="Motor del que salió el dump"),
) -> ApiResponse:
    """Lee el DDL con sqlglot (sin LLM) y registra el esquema como activo.

    Si alguna sentencia no se pudo interpretar, la respuesta lo dice con su
    **número de línea** y el activo se registra igualmente con lo que sí se leyó:
    perder un dump entero por una sentencia propietaria sería peor. Lo que no
    entró queda escrito, nunca se descarta en silencio.
    """
    if not (file.filename or "").lower().endswith(".sql"):
        raise ConflictError(
            f"«{file.filename}» no parece un archivo .sql. Sube el dump del "
            "esquema, no un export de datos."
        )
    crudo = await file.read()
    limite = settings.INVENTORY_MAX_DDL_MB * 1024 * 1024
    if len(crudo) > limite:
        raise ConflictError(
            f"El archivo supera el límite de {settings.INVENTORY_MAX_DDL_MB} MB."
        )
    try:
        texto = crudo.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConflictError(
            "El archivo no está en UTF-8. Vuelve a exportarlo con esa codificación."
        ) from exc

    try:
        resultado = parse_ddl(texto, engine=engine)
    except DdlImportError as exc:
        detalle = f" (línea {exc.line})" if exc.line else ""
        raise ConflictError(f"{exc.message}{detalle}") from exc

    if not resultado.tables:
        raise ConflictError(
            "No se encontró ninguna tabla legible en el archivo. "
            + "; ".join(e.message for e in resultado.errors[:3])
        )

    data = await InventoryService(session).add_asset(
        system_id,
        asset_type=InventoryAssetType.DB_SCHEMA,
        name=name,
        content=resultado.content,
        origin=InventoryAssetOrigin.DDL_DUMP,
        origin_ref=file.filename,
        actor_id=actor.id,
    )
    data["import_report"] = resultado.as_report()
    mensaje = f"Esquema cargado: {len(resultado.tables)} tablas"
    if resultado.errors:
        mensaje += f" ({len(resultado.errors)} sentencias no interpretadas)"
    return ApiResponse.ok(data=data, message=mensaje)


@router.post(
    "/systems/{system_id}/assets/document",
    summary="Extraer conocimiento de un documento (.docx/.pdf/.txt/.md)",
)
async def upload_document(
    system_id: str,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
    file: UploadFile = File(..., description="Documento que describe el sistema"),
) -> ApiResponse:
    """Lee el documento con el pipeline del EF y extrae su conocimiento con el LLM.

    Produce un activo ``document`` con la lectura completa y un activo ``module``
    por cada módulo identificado. Todo elemento arrastra su ``source_ref`` al
    párrafo del documento y su evidencia verbatim; lo que llega sin cita
    verificable se descarta y **se informa** en ``discarded``.
    """
    crudo = await file.read()
    resultado_ingesta = ingest(
        file.filename or "documento",
        crudo,
        LocalStorage(settings.STORAGE_DIR),
        max_upload_mb=settings.MAX_UPLOAD_MB,
    )

    cir = document_to_cir(
        resultado_ingesta.storage_uri,
        resultado_ingesta.extension,
        title=resultado_ingesta.filename,
    )
    fragmentos = build_fragments(
        cir, token_threshold=settings.SINGLE_SHOT_TOKEN_THRESHOLD
    )
    if not fragmentos:
        raise ConflictError(
            "El documento no tiene texto legible. Si es un PDF escaneado, esta "
            "versión no hace OCR."
        )

    from ai.llm import get_llm

    # Único punto que ingiere documentos reales de Urbano sin pasar por
    # ``run_agent_pipeline``. Antes construía el chat crudo (``get_claude_client``)
    # y se lo pasaba a ``extract_knowledge``, que espera un ``LLMClient``: además
    # de evadir la política del proveedor, el chat crudo NO tiene
    # ``complete_json``. Ahora entra por la misma puerta que todos los demás.
    conocimiento = await extract_knowledge(
        get_llm("inventory_doc", data_class="real"),
        fragmentos,
        concurrency=settings.INVENTORY_EXTRACT_CONCURRENCY,
    )
    activos = build_assets(conocimiento, document_name=resultado_ingesta.filename)

    creados = await InventoryService(session).add_assets_bulk(
        system_id,
        activos,
        origin=InventoryAssetOrigin.DOCUMENT,
        origin_ref=resultado_ingesta.filename,
        actor_id=actor.id,
    )
    return ApiResponse.ok(
        data={
            "assets": creados,
            "extraction_report": {
                "fragments": len(fragmentos),
                "modules": len(conocimiento["modules"]),
                "entities": len(conocimiento["entities"]),
                "functionalities": len(conocimiento["functionalities"]),
                "decisions": len(conocimiento["decisions"]),
                "discarded": conocimiento["discarded"],
                "skipped": conocimiento["skipped"],
            },
        },
        message=(
            f"Documento leído: {len(conocimiento['modules'])} módulos, "
            f"{len(conocimiento['entities'])} entidades"
        ),
    )


@router.get(
    "/introspection/sources",
    summary="Orígenes de introspección autorizados",
    dependencies=[Depends(require_admin_role)],
)
async def introspection_sources(
    _actor: User = Depends(get_current_user),
) -> ApiResponse:
    """Alias y host de los orígenes configurados **y** permitidos por la allowlist.

    Nunca devuelve cadenas de conexión. Un alias configurado pero no autorizado no
    aparece: el panel no debe ofrecer un botón que siempre fallará.
    """
    return ApiResponse.ok(data={"items": available_sources()})


@router.post(
    "/systems/{system_id}/assets/introspect",
    summary="Cargar un esquema introspeccionando una BD externa (solo admin)",
    dependencies=[Depends(require_admin_role)],
)
async def introspect(
    system_id: str,
    body: IntrospectRequest,
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Lee el catálogo de un PostgreSQL externo, **en solo lectura**, vía alias.

    Exige rol ``admin`` estricto, no basta con ``inventario`` FULL: esto se conecta
    a bases de datos de producción. El cliente manda un **alias** configurado en el
    despliegue, nunca una cadena de conexión — si mandara el DSN, quien pudiera
    escribir en el inventario podría apuntar el servidor a cualquier host.
    """
    dsn = assert_source_authorized(body.alias)
    contenido = await introspect_postgres(dsn, schema=body.schema_name)
    data = await InventoryService(session).add_asset(
        system_id,
        asset_type=InventoryAssetType.DB_SCHEMA,
        name=body.name,
        content=contenido,
        origin=InventoryAssetOrigin.INTROSPECTION,
        origin_ref=origin_ref_for(body.alias, dsn, body.schema_name),
        actor_id=actor.id,
    )
    return ApiResponse.ok(
        data=data,
        message=f"Esquema introspeccionado: {len(contenido['tables'])} tablas",
    )


# --- promoción al inventario (INV6) ------------------------------------------


@router.post(
    "/systems/{system_id}/promote",
    summary="Promover un artefacto terminado de BD o API al inventario",
)
async def promote_job(
    system_id: str,
    body: PromoteJobRequest,
    actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Registra las tablas o endpoints del artefacto como activos del sistema.

    Cierra el ciclo del módulo: los agentes leen el inventario para reconciliar y
    ahora también lo alimentan, así que cada proyecto entregado engorda la memoria
    de la organización.

    Se **mezcla** con la versión vigente, no la reemplaza: un diseño toca unas
    pocas tablas y el esquema tiene decenas. La respuesta detalla en ``changes``
    qué se añadió, qué se actualizó y qué se conservó.
    """
    data = await InventoryService(session).promote_job(
        system_id,
        body.job_id,
        asset_name=body.asset_name,
        actor_id=actor.id,
    )
    cambios = data["changes"]
    return ApiResponse.ok(
        data=data,
        message=(
            f"Promovido al inventario (versión {data['version']}): "
            f"{len(cambios['added'])} nuevos, {len(cambios['updated'])} "
            f"actualizados, {len(cambios['kept'])} conservados"
        ),
    )


@router.get("/assets/{asset_id}", summary="Contenido completo de un activo")
async def get_asset(
    asset_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Devuelve el activo con su ``content`` estructurado."""
    return ApiResponse.ok(data=await _service(session).get_asset(asset_id))


@router.get("/assets/{asset_id}/versions", summary="Historial de versiones del activo")
async def list_versions(
    asset_id: str, session: AsyncSession = Depends(get_session)
) -> ApiResponse:
    """Todas las versiones del activo, de la más reciente a la primera."""
    items = await _service(session).list_versions(asset_id)
    return ApiResponse.ok(data={"items": items})


@router.patch("/assets/{asset_id}/status", summary="Marcar un activo como validado")
async def set_asset_status(
    asset_id: str,
    body: UpdateAssetStatusRequest,
    _actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Pasa el activo de ``importado`` a ``validado`` (o lo revierte)."""
    data = await _service(session).set_validation_status(
        asset_id, body.validation_status
    )
    return ApiResponse.ok(data=data, message="Estado de validación actualizado")


@router.delete("/assets/{asset_id}", summary="Eliminar una versión de un activo")
async def delete_asset(
    asset_id: str,
    _actor: User = _WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Elimina **esa** versión; el resto del historial permanece."""
    await _service(session).delete_asset(asset_id)
    return ApiResponse.ok(data={"asset_id": asset_id}, message="Versión eliminada")
