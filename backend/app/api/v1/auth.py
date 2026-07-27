"""Endpoints de autenticación y gestión de usuarios (API v1).

Toda respuesta usa ``ApiResponse``. Rutas públicas: ``/auth/login`` y
``/auth/register`` (esta última con la excepción de bootstrap). El resto exige
autenticación; el panel de usuarios exige rol ``admin``.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.permissions import (
    MODULE_LABELS,
    ROLE_LABELS,
    ROLE_MATRIX,
    AccessLevel,
    Module,
)
from app.dependencies.current_user import get_current_user, get_optional_user
from app.dependencies.database import get_session
from app.dependencies.permissions import require_admin_role, require_module
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResult,
    RegisterRequest,
    ResetPasswordRequest,
    SetActiveRequest,
    SetGrantsRequest,
    SetRoleRequest,
    UpdateProfileRequest,
    UserOut,
)
from app.services.auth_service import AuthService
from shared.responses.api_response import ApiResponse

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# El panel de usuarios/configuración se valida contra la matriz de permisos
# (módulo ``config``), igual que los módulos de agentes.
_CONFIG_READ = Depends(require_module(Module.CONFIG, AccessLevel.READ))
_CONFIG_WRITE = Depends(require_module(Module.CONFIG, AccessLevel.FULL))


@router.get(
    "/bootstrap-status",
    summary="¿La plataforma necesita crear el primer administrador?",
)
async def bootstrap_status(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Chequeo ligero y público: ``needs_bootstrap=true`` cuando no hay usuarios.

    Lo usa la pantalla de login para ofrecer, solo entonces, la creación de la
    primera cuenta de administrador.
    """
    needs = await AuthService(session).needs_bootstrap()
    return ApiResponse.ok(data={"needs_bootstrap": needs})


@router.post("/register", summary="Registrar un usuario (admin; bootstrap del primero)")
async def register(
    body: RegisterRequest,
    actor: Optional[User] = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Crea un usuario.

    Solo un **administrador** autenticado puede registrar usuarios. Excepción de
    **bootstrap**: si aún no existe ningún usuario, el primer registro se permite
    sin autenticación y el usuario nace como ``admin``.
    """
    user = await AuthService(session).register(
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        role=body.role,
        actor=actor,
    )
    return ApiResponse.ok(
        data=UserOut.of(user).model_dump(mode="json"),
        message="Usuario registrado",
    )


@router.post("/login", summary="Iniciar sesión (email + contraseña -> JWT)")
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Valida las credenciales y devuelve un JWT de acceso."""
    user, token = await AuthService(session).login(body.email, body.password)
    result = LoginResult(
        access_token=token,
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        user=UserOut.of(user),
    )
    return ApiResponse.ok(
        data=result.model_dump(mode="json"), message="Sesión iniciada"
    )


@router.get("/me", summary="Usuario autenticado actual (rol + módulos efectivos)")
async def me(user: User = Depends(get_current_user)) -> ApiResponse:
    """Devuelve el usuario del token, su rol y sus **módulos efectivos**.

    ``modules`` trae los permisos ya resueltos (rol + accesos adicionales), de
    forma que el frontend decida navegación y acciones sin reimplementar la
    matriz de permisos.
    """
    return ApiResponse.ok(data=UserOut.of(user).model_dump(mode="json"))


@router.get(
    "/roles",
    summary="Catálogo de roles y módulos (para el panel de administración)",
    dependencies=[_CONFIG_READ],
)
async def list_roles() -> ApiResponse:
    """Expone la matriz de permisos y las etiquetas legibles.

    Permite que el panel de usuarios muestre qué concede cada rol sin
    codificarlo de nuevo en el cliente.
    """
    return ApiResponse.ok(
        data={
            "roles": [
                {
                    "value": role.value,
                    "label": ROLE_LABELS[role],
                    "modules": {
                        module.value: level.value for module, level in modules.items()
                    },
                }
                for role, modules in ROLE_MATRIX.items()
            ],
            "modules": [
                {"value": module.value, "label": MODULE_LABELS[module]}
                for module in Module
            ],
            "levels": [level.value for level in AccessLevel],
        }
    )


@router.get(
    "/users",
    summary="Listado de usuarios (requiere acceso a Configuración)",
    dependencies=[_CONFIG_READ],
)
async def list_users(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ApiResponse:
    """Lista los usuarios de la plataforma (panel de administración)."""
    users, total = await AuthService(session).list_users(limit=limit, offset=offset)
    return ApiResponse.ok(
        data={
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [UserOut.of(u).model_dump(mode="json") for u in users],
        }
    )


@router.patch(
    "/users/{user_id}",
    summary="Activar/desactivar un usuario (requiere Configuración)",
)
async def set_user_active(
    user_id: str,
    body: SetActiveRequest,
    actor: User = _CONFIG_WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Activa o desactiva la cuenta de un usuario."""
    user = await AuthService(session).set_active(
        user_id=user_id, is_active=body.is_active, actor=actor
    )
    return ApiResponse.ok(
        data=UserOut.of(user).model_dump(mode="json"),
        message="Usuario actualizado",
    )


@router.patch(
    "/users/{user_id}/profile",
    summary="Editar nombre y correo de un usuario (requiere Configuración)",
)
async def update_user_profile(
    user_id: str,
    body: UpdateProfileRequest,
    actor: User = _CONFIG_WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Actualiza los datos de identidad. Solo se aplica lo que llega informado."""
    user = await AuthService(session).update_profile(
        user_id=user_id,
        actor=actor,
        full_name=body.full_name,
        email=body.email,
        institutional_email=body.institutional_email,
        position=body.position,
        available_for_assignment=body.available_for_assignment,
    )
    return ApiResponse.ok(
        data=UserOut.of(user).model_dump(mode="json"),
        message="Usuario actualizado",
    )


@router.post(
    "/users/{user_id}/password",
    summary="Restablecer la contraseña de un usuario (requiere Configuración)",
)
async def reset_user_password(
    user_id: str,
    body: ResetPasswordRequest,
    actor: User = _CONFIG_WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Define una contraseña nueva para el usuario.

    Operación **administrativa**: no se pide la contraseña anterior. La contraseña
    en claro nunca se registra en logs ni se devuelve.
    """
    user = await AuthService(session).reset_password(
        user_id=user_id, new_password=body.password, actor=actor
    )
    return ApiResponse.ok(
        data=UserOut.of(user).model_dump(mode="json"),
        message="Contraseña restablecida",
    )


@router.get(
    "/users/{user_id}/activity",
    summary="Huella del usuario (jobs y validaciones) para decidir la baja",
    dependencies=[_CONFIG_READ],
)
async def user_activity(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Cuenta la actividad ATRIBUIDA al usuario y recomienda cómo darlo de baja.

    Con actividad registrada se recomienda **desactivar** en vez de eliminar: la
    cuenta deja de servir para entrar, pero el historial sigue leyéndose con su
    nombre. Los registros anteriores a la migración `0007` no tienen autor, así
    que el resumen mide la huella conocida y nunca la inventa.
    """
    data = await AuthService(session).activity_summary(user_id=user_id)
    return ApiResponse.ok(data=data)


@router.delete(
    "/users/{user_id}",
    summary="Dar de baja un usuario (baja lógica; requiere Configuración)",
)
async def delete_user(
    user_id: str,
    actor: User = _CONFIG_WRITE,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Da de **baja lógica** al usuario (no borrado físico).

    Se conserva la fila para no romper la trazabilidad (los jobs y validaciones
    referencian a su autor); la cuenta no puede iniciar sesión ni aparece en los
    listados. Salvaguardas: no puedes eliminarte a ti mismo ni dejar la
    plataforma sin ningún administrador activo.
    """
    user = await AuthService(session).delete_user(user_id=user_id, actor=actor)
    return ApiResponse.ok(
        data=UserOut.of(user).model_dump(mode="json"),
        message="Usuario dado de baja",
    )


@router.patch(
    "/users/{user_id}/role",
    summary="Cambiar el rol funcional de un usuario (solo rol admin)",
)
async def set_user_role(
    user_id: str,
    body: SetRoleRequest,
    admin: User = Depends(require_admin_role),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Cambia el rol de un usuario.

    Exige **rol** ``admin`` estricto (no basta un acceso adicional a
    ``config``): cambiar roles permite elevar privilegios.
    """
    user = await AuthService(session).set_role(
        user_id=user_id, role=body.role, actor=admin
    )
    return ApiResponse.ok(
        data=UserOut.of(user).model_dump(mode="json"),
        message="Rol actualizado",
    )


@router.put(
    "/users/{user_id}/grants",
    summary="Reemplazar los accesos adicionales de un usuario (solo rol admin)",
)
async def set_user_grants(
    user_id: str,
    body: SetGrantsRequest,
    admin: User = Depends(require_admin_role),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Reemplaza el conjunto completo de accesos adicionales del usuario.

    Los grants **suman** sobre el rol y nunca restan. Exige **rol** ``admin``
    estricto por el mismo motivo que el cambio de rol.
    """
    user = await AuthService(session).replace_grants(
        user_id=user_id,
        grants=[(g.module, g.level) for g in body.grants],
        actor=admin,
    )
    return ApiResponse.ok(
        data=UserOut.of(user).model_dump(mode="json"),
        message="Accesos adicionales actualizados",
    )
