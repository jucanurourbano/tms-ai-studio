"""Repositorio del Agente EF (compat sobre ``AgentJobRepository``).

Tras la generalización multi-agente (D1), ``EFRepository`` es una fina
especialización que fija ``agent_type='ef'``, conservando la firma histórica que
usan el servicio, el seed y los tests del EF.
"""

from typing import Optional

from app.models.agent import AgentJob, AgentType
from app.repositories.agent_job_repository import AgentJobRepository


class EFRepository(AgentJobRepository):
    """Operaciones de persistencia del Agente EF (``agent_type`` fijo = ef)."""

    async def create_job(
        self,
        source_doc_id: str,
        parent_job_id: Optional[str] = None,
        *,
        title: Optional[str] = None,
        source_type: Optional[str] = None,
        version: int = 1,
    ) -> AgentJob:
        """Crea un job EF en estado PENDING."""
        return await super().create_job(
            AgentType.EF,
            source_doc_id=source_doc_id,
            parent_job_id=parent_job_id,
            title=title,
            source_type=source_type,
            version=version,
        )

    async def find_completed_job_by_hash(
        self, content_hash: str, agent_type: AgentType = AgentType.EF
    ) -> Optional[AgentJob]:
        """Último job EF completado para ese hash (idempotencia)."""
        return await super().find_completed_job_by_hash(content_hash, AgentType.EF)

    async def list_jobs(
        self, limit: int = 20, offset: int = 0
    ) -> tuple[list[AgentJob], int]:
        """Listado paginado de jobs EF (más recientes primero) + total."""
        return await super().list_jobs(
            agent_type=AgentType.EF, limit=limit, offset=offset
        )
