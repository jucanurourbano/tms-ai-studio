"""Servicio de autenticación y gestión de usuarios (capa services).

Orquesta el repositorio de usuarios y las utilidades de seguridad. Reglas:

- **Registro**: solo un ``admin`` autenticado puede registrar usuarios. Excepción
  de *bootstrap*: si no existe **ningún** usuario, el primer registro se permite
  sin autenticación y nace ``admin``.
- **Login**: valida email + contraseña; emite un JWT de acceso.
- **Token**: resuelve el usuario actual a partir del ``sub`` del JWT.

Las contraseñas en claro NUNCA se registran en logs ni se devuelven.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

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
        role: UserRole = UserRole.MEMBER,
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
        elif actor is None or actor.role != UserRole.ADMIN:
            raise ForbiddenError(
                "Solo un administrador puede registrar nuevos usuarios."
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
        await self.repo.set_active(user, is_active)
        await self.session.commit()
        return user
