"""Repositorio de usuarios (capa repositories).

Operaciones de persistencia sobre la tabla ``users``. No conoce contraseñas en
claro ni JWT: recibe/devuelve el modelo ``User`` con el hash ya calculado.
"""

from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import AccessLevel, Module, satisfies
from app.models.user import User, UserModuleGrant, UserRole


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
        # ``grants=[]`` explícito: deja la colección ya "cargada" en memoria. Sin
        # esto, leer ``user.grants`` sobre el objeto recién creado dispara un
        # lazy load (IO) fuera del contexto greenlet -> ``MissingGreenlet``. La
        # estrategia ``selectin`` solo cubre los objetos que vienen de una query.
        user = User(
            email=email,
            full_name=full_name,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
            grants=[],
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

    async def set_role(self, user: User, role: UserRole) -> User:
        """Cambia el rol funcional de un usuario."""
        user.role = role
        await self.session.flush()
        return user

    async def replace_grants(
        self, user: User, grants: Iterable[tuple[Module, AccessLevel]]
    ) -> User:
        """Reemplaza el conjunto completo de accesos adicionales del usuario.

        Se sincroniza la colección **en sitio** (quitar / actualizar / añadir) en
        vez de reasignarla entera: al reasignar, SQLAlchemy emite los INSERT de
        las filas nuevas ANTES de los DELETE de las viejas y un módulo que se
        mantiene viola la restricción única ``(user_id, module)``.

        Si un módulo llega repetido en la entrada, gana el nivel mayor.
        """
        deseado: dict[Module, AccessLevel] = {}
        for module, level in grants:
            actual = deseado.get(module)
            if actual is None or satisfies(level, actual):
                deseado[module] = level

        existentes = {g.module: g for g in user.grants}

        for module, row in existentes.items():
            if module not in deseado:
                user.grants.remove(row)  # delete-orphan lo borra al hacer flush

        for module, level in deseado.items():
            row = existentes.get(module)
            if row is None:
                user.grants.append(UserModuleGrant(module=module, level=level))
            elif row.level is not level:
                row.level = level

        await self.session.flush()
        return user
