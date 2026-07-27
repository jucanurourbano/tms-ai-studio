"""Servicio de autenticación y gestión de usuarios (capa services).

Orquesta el repositorio de usuarios y las utilidades de seguridad. Reglas:

- **Registro**: solo un ``admin`` autenticado puede registrar usuarios. Excepción
  de *bootstrap*: si no existe **ningún** usuario, el primer registro se permite
  sin autenticación y nace ``admin``.
- **Login**: valida email + contraseña; emite un JWT de acceso.
- **Token**: resuelve el usuario actual a partir del ``sub`` del JWT.

Las contraseñas en claro NUNCA se registran en logs ni se devuelven.
"""

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import DEFAULT_ROLE, AccessLevel, Module, can
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.errors import AuthError, ConflictError, ForbiddenError, NotFoundError
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository


class AuthService:
    """Casos de uso de autenticación y administración de usuarios."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    async def needs_bootstrap(self) -> bool:
        """``True`` si no existe ningún usuario (habilita crear el primer admin)."""
        return await self.repo.count() == 0

    async def register(
        self,
        *,
        email: str,
        full_name: str,
        password: str,
        role: UserRole = DEFAULT_ROLE,
        actor: Optional[User] = None,
    ) -> User:
        """Registra un usuario aplicando la regla de autorización + bootstrap.

        - Si la tabla de usuarios está vacía: registro de bootstrap sin auth; el
          usuario nace ``admin`` (se ignora ``role``/``actor``).
        - En caso contrario: ``actor`` debe ser un ``admin`` autenticado.
        """
        is_bootstrap = await self.repo.count() == 0
        if is_bootstrap:
            role = UserRole.ADMIN
        elif actor is None or not can(
            actor.role, actor.grant_pairs(), Module.CONFIG, AccessLevel.FULL
        ):
            raise ForbiddenError(
                "Solo un administrador puede registrar nuevos usuarios."
            )
        elif role is UserRole.ADMIN and actor.role is not UserRole.ADMIN:
            # Crear un admin es escalada de privilegios: exige rol admin real,
            # no un grant de `config` (ver ``require_admin_role``).
            raise ForbiddenError(
                "Solo un Administrador puede crear otra cuenta de Administrador."
            )

        normalized = self._normalize_email(email)
        if await self.repo.get_by_email(normalized) is not None:
            raise ConflictError("Ya existe un usuario con ese correo.")

        user = await self.repo.create(
            email=normalized,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            role=role,
        )
        await self.session.commit()
        return user

    async def login(self, email: str, password: str) -> tuple[User, str]:
        """Valida credenciales y devuelve ``(usuario, access_token)``.

        Usa un mensaje genérico ante email inexistente o contraseña incorrecta
        para no revelar qué correos están registrados.
        """
        user = await self.repo.get_by_email(self._normalize_email(email))
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Correo o contraseña incorrectos.")
        if not user.is_active:
            raise AuthError("La cuenta está desactivada. Contacte a un administrador.")
        token = create_access_token(user.id)
        return user, token

    async def authenticate_token(self, user_id: Optional[str]) -> User:
        """Resuelve el usuario actual desde el ``sub`` (id) de un JWT válido."""
        if not user_id:
            raise AuthError("No autenticado: token inválido o ausente.")
        user = await self.repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthError("No autenticado: la sesión ya no es válida.")
        return user

    async def list_users(
        self, limit: int = 50, offset: int = 0
    ) -> tuple[list[User], int]:
        """Listado paginado de usuarios (panel de administración)."""
        return await self.repo.list(limit=limit, offset=offset)

    async def set_active(self, *, user_id: str, is_active: bool, actor: User) -> User:
        """Activa/desactiva un usuario (solo admin; no puede desactivarse a sí mismo)."""
        if user_id == actor.id and not is_active:
            raise ForbiddenError("Un administrador no puede desactivarse a sí mismo.")
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado.")
        if not is_active and user.role is UserRole.ADMIN:
            # Este endpoint solo exige `config` FULL, que es concedible por grant:
            # sin esta guarda, alguien sin rol admin podría desactivar a TODOS los
            # administradores y dejar la plataforma sin nadie que pueda promover a
            # otro (cambiar roles exige rol admin estricto).
            restantes = await self.repo.count_active_admins(excluding=user.id)
            if restantes == 0:
                raise ForbiddenError(
                    "No puedes desactivar al último administrador activo. "
                    "Asigna el rol de Administrador a otra cuenta primero."
                )
        await self.repo.set_active(user, is_active)
        await self.session.commit()
        return user

    async def update_profile(
        self,
        *,
        user_id: str,
        actor: User,
        full_name: Optional[str] = None,
        email: Optional[str] = None,
        institutional_email: Optional[str] = None,
        position: Optional[str] = None,
        available_for_assignment: Optional[bool] = None,
    ) -> User:
        """Edita identidad y perfil de equipo de un usuario (requiere `config` FULL)."""
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado.")

        normalized: Optional[str] = None
        if email is not None:
            normalized = self._normalize_email(email)
            if normalized != user.email:
                # ``include_deleted``: la única de la tabla también cubre las bajas
                # lógicas, así que un correo "libre" en apariencia puede no estarlo.
                otro = await self.repo.get_by_email(normalized, include_deleted=True)
                if otro is not None and otro.id != user.id:
                    raise ConflictError("Ya existe un usuario con ese correo.")

        await self.repo.update_profile(
            user,
            full_name=full_name,
            email=normalized,
            institutional_email=institutional_email,
            position=position,
            available_for_assignment=available_for_assignment,
        )
        await self.session.commit()
        return user

    async def reset_password(
        self, *, user_id: str, new_password: str, actor: User
    ) -> User:
        """Restablece la contraseña de un usuario (la define un administrador).

        No se exige la contraseña anterior: es una operación administrativa, no un
        cambio hecho por el propio usuario. La contraseña en claro no se registra
        en ningún log; solo se persiste su hash.
        """
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado.")
        await self.repo.set_password_hash(user, hash_password(new_password))
        await self.session.commit()
        return user

    async def activity_summary(self, *, user_id: str) -> dict:
        """Huella del usuario + recomendación de baja vs. desactivación."""
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado.")
        counts = await self.repo.activity_counts(user_id)
        total = sum(counts.values())
        return {
            **counts,
            "total": total,
            # Con actividad registrada se recomienda desactivar: la cuenta deja de
            # servir para entrar, pero el historial sigue leyéndose con su nombre.
            "recommend_deactivate": total > 0,
        }

    async def delete_user(self, *, user_id: str, actor: User) -> User:
        """Da de **baja lógica** a un usuario, con salvaguardas.

        - No puedes eliminarte a ti mismo.
        - No se permite dejar la plataforma sin ningún administrador activo.

        Es baja lógica (``deleted_at``), nunca borrado físico: los jobs y las
        validaciones referencian al autor y el historial debe seguir respondiendo
        "¿quién hizo esto?". La cuenta queda inutilizable (no inicia sesión ni
        aparece en los listados) y la baja es reversible.
        """
        if user_id == actor.id:
            raise ForbiddenError("No puedes eliminar tu propia cuenta.")
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado.")
        if user.role is UserRole.ADMIN:
            restantes = await self.repo.count_active_admins(excluding=user.id)
            if restantes == 0:
                raise ForbiddenError(
                    "No puedes eliminar al último administrador activo. "
                    "Asigna el rol de Administrador a otra cuenta primero."
                )
        await self.repo.soft_delete(user, when=datetime.now(timezone.utc))
        await self.session.commit()
        return user

    async def set_role(self, *, user_id: str, role: UserRole, actor: User) -> User:
        """Cambia el rol funcional de un usuario (solo admin).

        Un admin **no puede cambiar su propio rol**: sería la vía directa a
        quedarse sin administradores (o sin acceso al propio panel). Mismo
        criterio que la guarda de auto-desactivación.
        """
        if user_id == actor.id:
            raise ForbiddenError(
                "Un administrador no puede cambiar su propio rol. "
                "Pide a otro administrador que lo haga."
            )
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado.")
        await self.repo.set_role(user, role)
        await self.session.commit()
        return user

    async def replace_grants(
        self,
        *,
        user_id: str,
        grants: Iterable[tuple[Module, AccessLevel]],
        actor: User,
    ) -> User:
        """Reemplaza los accesos adicionales de un usuario (solo admin).

        Un admin no edita sus propios grants: no le aportan nada (su rol ya da
        FULL en todo) y evita que se toque su propio nivel de acceso por error.
        """
        if user_id == actor.id:
            raise ForbiddenError(
                "Un administrador no edita sus propios accesos adicionales."
            )
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado.")
        await self.repo.replace_grants(user, grants)
        await self.session.commit()
        return user
