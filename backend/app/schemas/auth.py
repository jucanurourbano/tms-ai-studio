"""Esquemas de request/response de la API de autenticación."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import User


class RegisterRequest(BaseModel):
    """Cuerpo para registrar un usuario.

    El ``role`` solo lo respeta un admin autenticado; en el bootstrap (primer
    usuario) se fuerza ``admin`` y este campo se ignora.
    """

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "member"] = "member"


class LoginRequest(BaseModel):
    """Credenciales de acceso."""

    email: EmailStr
    password: str = Field(min_length=1)


class SetActiveRequest(BaseModel):
    """Activa/desactiva un usuario (panel de administración)."""

    is_active: bool


class UserOut(BaseModel):
    """Representación pública de un usuario (NUNCA incluye el hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: Literal["admin", "member"]
    is_active: bool
    created_at: Optional[datetime] = None

    @classmethod
    def of(cls, user: User) -> "UserOut":
        """Construye la vista pública desde el modelo ORM."""
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at,
        )


class LoginResult(BaseModel):
    """Respuesta de un login exitoso."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Vigencia del token en segundos.")
    user: UserOut
