"""Repositorio de usuarios (capa repositories).

Operaciones de persistencia sobre la tabla ``users``. No conoce contraseñas en
claro ni JWT: recibe/devuelve el modelo ``User`` con el hash ya calculado.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole


class UserRepository:
    """Operaciones de persistencia de usuarios."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Recupera un usuario por id."""
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Recupera un usuario por email (búsqueda exacta, normalizado)."""
        return await self.session.scalar(select(User).where(User.email == email))

    async def count(self) -> int:
        """Número total de usuarios (para el bootstrap del primer admin)."""
        return int(
            await self.session.scalar(select(func.count()).select_from(User)) or 0
        )

    async def create(
        self,
        *,
        email: str,
        full_name: str,
        password_hash: str,
        role: UserRole,
        is_active: bool = True,
    ) -> User:
        """Crea un usuario. El ``email`` debe venir ya normalizado y validado."""
        user = User(
            email=email,
            full_name=full_name,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def list(self, limit: int = 50, offset: int = 0) -> tuple[list[User], int]:
        """Listado paginado de usuarios (más recientes primero) + total."""
        total = int(
            await self.session.scalar(select(func.count()).select_from(User)) or 0
        )
        rows = await self.session.scalars(
            select(User)
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), total

    async def set_active(self, user: User, is_active: bool) -> User:
        """Activa/desactiva un usuario."""
        user.is_active = is_active
        await self.session.flush()
        return user
