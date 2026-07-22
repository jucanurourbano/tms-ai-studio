"""Endpoints de autenticación y gestión de usuarios (API v1).

Toda respuesta usa ``ApiResponse``. Rutas públicas: ``/auth/login`` y
``/auth/register`` (esta última con la excepción de bootstrap). El resto exige
autenticación; el panel de usuarios exige rol ``admin``.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.dependencies.current_user import (
    get_current_user,
    get_optional_user,
    require_admin,
)
from app.dependencies.database import get_session
from app.models.user import User, UserRole
from app.schemas.auth import (
    LoginRequest,
    LoginResult,
    RegisterRequest,
    SetActiveRequest,
    UserOut,
)
from app.services.auth_service import AuthService
from shared.responses.api_response import ApiResponse

router = APIRouter(prefix="/auth", tags=["Autenticación"])


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
        role=UserRole(body.role),
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


@router.get("/me", summary="Usuario autenticado actual")
async def me(user: User = Depends(get_current_user)) -> ApiResponse:
    """Devuelve el usuario correspondiente al token presentado."""
    return ApiResponse.ok(data=UserOut.of(user).model_dump(mode="json"))


@router.get("/users", summary="Listado de usuarios (solo admin)")
async def list_users(
    _admin: User = Depends(require_admin),
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


@router.patch("/users/{user_id}", summary="Activar/desactivar un usuario (solo admin)")
async def set_user_active(
    user_id: str,
    body: SetActiveRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Activa o desactiva la cuenta de un usuario."""
    user = await AuthService(session).set_active(
        user_id=user_id, is_active=body.is_active, actor=admin
    )
    return ApiResponse.ok(
        data=UserOut.of(user).model_dump(mode="json"),
        message="Usuario actualizado",
    )
