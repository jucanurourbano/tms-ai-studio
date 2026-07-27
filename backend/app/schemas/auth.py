"""Esquemas de request/response de la API de autenticación y permisos."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.permissions import (
    DEFAULT_ROLE,
    AccessLevel,
    Module,
    UserRole,
    effective_modules,
)
from app.models.user import Specialty, User


class RegisterRequest(BaseModel):
    """Cuerpo para registrar un usuario.

    El ``role`` solo lo respeta un admin autenticado; en el bootstrap (primer
    usuario) se fuerza ``admin`` y este campo se ignora.
    """

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    # Se tipa con el enum (no con un ``Literal`` duplicado) para que añadir un
    # rol en ``core.permissions`` no exija tocar este esquema.
    role: UserRole = DEFAULT_ROLE


class LoginRequest(BaseModel):
    """Credenciales de acceso."""

    email: EmailStr
    password: str = Field(min_length=1)


class SetActiveRequest(BaseModel):
    """Activa/desactiva un usuario (panel de administración)."""

    is_active: bool


class SetRoleRequest(BaseModel):
    """Cambia el rol funcional de un usuario (solo admin)."""

    role: UserRole


class UpdateProfileRequest(BaseModel):
    """Edita los datos de un usuario. Solo se aplica lo que llega informado.

    Incluye el **perfil de equipo** que consume la asignación de historias del
    Agente Scrum. ``institutional_email`` admite cadena vacía para borrarlo (y
    volver a usar el correo de acceso como destinatario en el export).
    """

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    institutional_email: Optional[str] = Field(default=None, max_length=320)
    specialty: Optional[Specialty] = None
    available_for_assignment: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    """Contraseña nueva definida por un administrador."""

    password: str = Field(min_length=8, max_length=128)


class ModuleGrantIn(BaseModel):
    """Acceso adicional a un módulo, tal como lo envía el panel."""

    module: Module
    level: AccessLevel


class SetGrantsRequest(BaseModel):
    """Reemplaza el conjunto COMPLETO de accesos adicionales de un usuario.

    Semántica de *replace*: lo que no venga en la lista se elimina. Enviar
    ``{"grants": []}`` deja al usuario solo con los permisos de su rol.
    """

    grants: list[ModuleGrantIn] = Field(default_factory=list)


class ModuleGrantOut(BaseModel):
    """Acceso adicional concedido a un usuario (fila de ``user_module_grants``)."""

    model_config = ConfigDict(from_attributes=True)

    module: Module
    level: AccessLevel


class UserOut(BaseModel):
    """Representación pública de un usuario (NUNCA incluye el hash).

    Incluye ``modules``: los permisos **efectivos** ya resueltos (rol + grants).
    El frontend los consume tal cual para decidir qué navegación y qué acciones
    muestra, sin reimplementar la matriz de ``core.permissions``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: Optional[datetime] = None
    # --- perfil de equipo (asignación de historias del Agente Scrum) ---
    institutional_email: Optional[str] = None
    specialty: Optional[Specialty] = None
    available_for_assignment: bool = True
    #: Accesos adicionales explícitos (para el editor del panel de usuarios).
    grants: list[ModuleGrantOut] = Field(default_factory=list)
    #: Módulos efectivos: ``{"ef": "full", "scrum": "read", ...}``.
    modules: dict[str, AccessLevel] = Field(default_factory=dict)

    @classmethod
    def of(cls, user: User) -> "UserOut":
        """Construye la vista pública desde el modelo ORM (con permisos resueltos)."""
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            institutional_email=user.institutional_email,
            specialty=user.specialty,
            available_for_assignment=user.available_for_assignment,
            grants=[
                ModuleGrantOut(module=g.module, level=g.level) for g in user.grants
            ],
            modules={
                module.value: level
                for module, level in effective_modules(
                    user.role, user.grant_pairs()
                ).items()
            },
        )


class LoginResult(BaseModel):
    """Respuesta de un login exitoso."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Vigencia del token en segundos.")
    user: UserOut
