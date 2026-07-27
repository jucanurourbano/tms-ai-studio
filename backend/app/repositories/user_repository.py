"""Repositorio de usuarios (capa repositories).

Operaciones de persistencia sobre la tabla ``users``. No conoce contraseñas en
claro ni JWT: recibe/devuelve el modelo ``User`` con el hash ya calculado.
"""

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import AccessLevel, Module, satisfies
from app.models.agent import AgentJob, AgentValidation
from app.models.user import User, UserModuleGrant, UserRole


class UserRepository:
    """Operaciones de persistencia de usuarios."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self, user_id: str, *, include_deleted: bool = False
    ) -> Optional[User]:
        """Recupera un usuario por id. Los dados de baja se omiten por defecto."""
        user = await self.session.get(User, user_id)
        if user is None:
            return None
        if user.deleted_at is not None and not include_deleted:
            return None
        return user

    async def get_by_email(
        self, email: str, *, include_deleted: bool = False
    ) -> Optional[User]:
        """Recupera un usuario por email (exacto, normalizado).

        Con ``include_deleted`` se usa para comprobar que el correo no está
        ocupado NI por una baja lógica: la restricción única de la tabla sigue
        cubriendo esas filas, así que reutilizar el correo exige reactivar.
        """
        stmt = select(User).where(User.email == email)
        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))
        return await self.session.scalar(stmt)

    async def count(self) -> int:
        """Usuarios vigentes (para el bootstrap del primer admin)."""
        return int(
            await self.session.scalar(
                select(func.count()).select_from(User).where(User.deleted_at.is_(None))
            )
            or 0
        )

    async def count_active_admins(self, *, excluding: Optional[str] = None) -> int:
        """Admins activos y vigentes. Evita dejar la plataforma sin administrador."""
        stmt = (
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        if excluding is not None:
            stmt = stmt.where(User.id != excluding)
        return int(await self.session.scalar(stmt) or 0)

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
        """Listado paginado de usuarios VIGENTES (más recientes primero) + total."""
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(User).where(User.deleted_at.is_(None))
            )
            or 0
        )
        rows = await self.session.scalars(
            select(User)
            .where(User.deleted_at.is_(None))
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

    async def update_profile(
        self,
        user: User,
        *,
        full_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> User:
        """Actualiza los datos de identidad. Solo toca lo que llega informado."""
        if full_name is not None:
            user.full_name = full_name
        if email is not None:
            user.email = email
        await self.session.flush()
        return user

    async def set_password_hash(self, user: User, password_hash: str) -> User:
        """Reemplaza el hash de la contraseña (restablecimiento por un admin)."""
        user.password_hash = password_hash
        await self.session.flush()
        return user

    async def soft_delete(self, user: User, *, when: datetime) -> User:
        """Da de baja lógicamente: se conserva la fila y se desactiva la cuenta."""
        user.deleted_at = when
        user.is_active = False
        await self.session.flush()
        return user

    async def activity_counts(self, user_id: str) -> dict[str, int]:
        """Actividad atribuida al usuario (para decidir baja vs. desactivación).

        Cuenta jobs creados y validaciones respondidas por él. Los registros
        anteriores a la migración 0007 no tienen autor, así que no se cuentan:
        el resumen mide la huella CONOCIDA, nunca la inventa.
        """
        jobs = int(
            await self.session.scalar(
                select(func.count())
                .select_from(AgentJob)
                .where(AgentJob.created_by == user_id)
            )
            or 0
        )
        validations = int(
            await self.session.scalar(
                select(func.count())
                .select_from(AgentValidation)
                .where(AgentValidation.answered_by == user_id)
            )
            or 0
        )
        return {"jobs": jobs, "validations": validations}

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
