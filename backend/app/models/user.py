"""Modelo ORM de usuarios y autenticación de la plataforma.

Autenticación por ``email`` + contraseña (hash bcrypt) y rol
(``admin`` | ``member``). El ``password_hash`` NUNCA se expone en la API ni se
registra en logs (ver ``app/schemas/auth.py`` y ``app/core/security.py``).
"""

from enum import Enum

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from .agent import pg_enum
from .base import Base, IdMixin, TimestampMixin


class UserRole(str, Enum):
    """Rol del usuario en la plataforma."""

    ADMIN = "admin"
    MEMBER = "member"


class User(Base, IdMixin, TimestampMixin):
    """Usuario de TMS AI Studio (identidad + credenciales + rol)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"),
        nullable=False,
        default=UserRole.MEMBER,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
