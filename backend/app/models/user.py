"""Modelo ORM de usuarios, roles funcionales y asignaciones adicionales.

Autenticación por ``email`` + contraseña (hash bcrypt) y **rol funcional** por
fase del ISDF (``admin`` | ``procesos`` | ``analista`` | ``arquitecto`` |
``developer`` | ``qa``). El ``password_hash`` NUNCA se expone en la API ni se
registra en logs (ver ``app/schemas/auth.py`` y ``app/core/security.py``).

El rol da el permiso base; ``user_module_grants`` añade accesos por usuario que
**suman** sobre el rol. La matriz que traduce rol → módulos vive en
``app/core/permissions.py`` (única fuente de verdad), no aquí.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.permissions import AccessLevel, Module, UserRole

from .agent import pg_enum
from .base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - solo para tipado
    pass

# Reexportado para que ``from app.models.user import UserRole`` siga funcionando.
__all__ = ["User", "UserModuleGrant", "UserRole"]


class User(Base, IdMixin, TimestampMixin):
    """Usuario de TMS AI Studio (identidad + credenciales + rol funcional)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"),
        nullable=False,
        default=UserRole.ANALISTA,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # --- Perfil de equipo (asignación de historias del Agente Scrum) ---------
    # Correo INSTITUCIONAL: puede coincidir con el de acceso o diferir (p. ej. si
    # se entra con un alias). Es el que se exporta a ClickUp como `assignee`, por
    # eso vive aparte del `email` de login, que puede cambiarse sin tocar el
    # destinatario de las tareas.
    institutional_email: Mapped[Optional[str]] = mapped_column(
        String(320), nullable=True
    )
    #: Cargo o especialidad libre (backend, frontend, QA, analista funcional…).
    position: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    #: Si aparece en el selector "Asignar a" del plan Scrum.
    available_for_assignment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # BAJA LÓGICA (soft delete). Se conserva la fila para no romper la trazabilidad:
    # los jobs (``created_by``), las validaciones (``answered_by``) y las
    # asignaciones de historias apuntan a este usuario, y anonimizar dejaría el
    # historial sin respuesta a "¿quién hizo esto?". Un usuario con
    # ``deleted_at`` no puede iniciar sesión ni aparece en los listados.
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ``lazy="selectin"``: los grants se cargan SIEMPRE con el usuario. Son pocos
    # por usuario y los necesita cada petición autenticada para resolver permisos,
    # así que se evita tanto el lazy-load prohibido en async como una consulta
    # extra en la dependencia ``require_module``.
    grants: Mapped[list["UserModuleGrant"]] = relationship(
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def grant_pairs(self) -> list[tuple[Module, AccessLevel]]:
        """Grants como pares ``(módulo, nivel)`` para ``core.permissions``."""
        return [(g.module, g.level) for g in self.grants]


class UserModuleGrant(Base, IdMixin, TimestampMixin):
    """Acceso adicional de un usuario a un módulo (SUMA sobre el rol).

    Un usuario tiene como máximo una fila por módulo (restricción única): el
    nivel de la fila es el acceso extra concedido. Nunca resta permisos — si el
    rol ya da más, gana el rol (ver ``core.permissions.effective_modules``).
    """

    __tablename__ = "user_module_grants"
    __table_args__ = (
        UniqueConstraint("user_id", "module", name="uq_user_module_grant"),
    )

    user_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module: Mapped[Module] = mapped_column(
        pg_enum(Module, "access_module"), nullable=False
    )
    level: Mapped[AccessLevel] = mapped_column(
        pg_enum(AccessLevel, "access_level"), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="grants")
