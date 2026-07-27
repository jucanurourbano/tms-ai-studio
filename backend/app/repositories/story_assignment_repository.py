"""Repositorio de asignaciones de historias (capa repositories).

Las asignaciones viven **fuera del artefacto** (misma filosofía que las
validaciones): el ``ScrumArtifact`` no se muta nunca.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import StoryAssignment
from app.models.user import User


class StoryAssignmentRepository:
    """Operaciones de persistencia de las asignaciones de historias."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_job(self, job_id: str) -> list[StoryAssignment]:
        """Asignaciones de un plan, en orden estable por historia."""
        rows = await self.session.scalars(
            select(StoryAssignment)
            .where(StoryAssignment.job_id == job_id)
            .order_by(StoryAssignment.story_id.asc())
        )
        return list(rows)

    async def get(self, job_id: str, story_id: str) -> Optional[StoryAssignment]:
        """Asignación de una historia concreta, si existe."""
        return await self.session.scalar(
            select(StoryAssignment).where(
                StoryAssignment.job_id == job_id,
                StoryAssignment.story_id == story_id,
            )
        )

    async def assign(
        self,
        *,
        job_id: str,
        story_id: str,
        user_id: str,
        assigned_by: Optional[str],
        when: datetime,
    ) -> StoryAssignment:
        """Asigna (o **reasigna**) la historia. Única por ``(job_id, story_id)``."""
        existing = await self.get(job_id, story_id)
        if existing is not None:
            existing.user_id = user_id
            existing.assigned_by = assigned_by
            existing.assigned_at = when
            await self.session.flush()
            return existing

        row = StoryAssignment(
            job_id=job_id,
            story_id=story_id,
            user_id=user_id,
            assigned_by=assigned_by,
            assigned_at=when,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def unassign(self, *, job_id: str, story_id: str) -> bool:
        """Quita la asignación. ``True`` si había algo que quitar."""
        existing = await self.get(job_id, story_id)
        if existing is None:
            return False
        await self.session.delete(existing)
        await self.session.flush()
        return True

    async def assignable_users(self) -> list[User]:
        """Colaboradores que pueden recibir historias.

        Activos, no dados de baja y marcados como disponibles. Se ordena por
        nombre para que el selector del plan sea predecible.
        """
        rows = await self.session.scalars(
            select(User)
            .where(
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.available_for_assignment.is_(True),
            )
            .order_by(User.full_name.asc())
        )
        return list(rows)

    async def users_by_ids(self, user_ids: list[str]) -> dict[str, User]:
        """Usuarios por id (incluye bajas: un histórico debe seguir legible)."""
        if not user_ids:
            return {}
        rows = await self.session.scalars(select(User).where(User.id.in_(user_ids)))
        return {u.id: u for u in rows}
