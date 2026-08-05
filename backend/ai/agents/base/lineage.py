"""Resolución del **linaje** de un job a través de la cadena ISDF.

Cada job apunta a su predecesor directo con ``agent_jobs.input_job_id``; los
antecesores más lejanos se resuelven **transitivamente**, sin columnas nuevas
(decisión A1, extendida en DB1):

```
bd_job.input_job_id -> arquitectura_job.input_job_id -> scrum_job.input_job_id -> ef_job
```

El Agente Arquitectura daba **un** salto y lo hacía a mano en su servicio. El
Agente BD da **dos** y el Agente API dará **tres**: en vez de repetir la escalera
en cada servicio, se recorre aquí una sola vez.

La función no conoce la cadena ISDF de antemano: sube por ``input_job_id`` hasta
la raíz y devuelve lo encontrado indexado por ``agent_type``. Así un cambio en el
orden de la cadena no obliga a tocar este módulo.
"""

from typing import Optional, Protocol

from app.models.agent import AgentJob, AgentType

#: Tope de saltos al subir la cadena. La cadena ISDF más larga tiene 9 eslabones;
#: 12 deja margen y, sobre todo, garantiza que un ciclo de datos corrupto no
#: cuelgue el pipeline en un bucle infinito.
MAX_DEPTH = 12


class _JobReader(Protocol):
    """Lo mínimo que se necesita del repositorio para subir la cadena."""

    async def get_job(self, job_id: str) -> Optional[AgentJob]: ...


async def resolve_lineage(
    repo: _JobReader, job: AgentJob, *, max_depth: int = MAX_DEPTH
) -> dict[AgentType, AgentJob]:
    """Devuelve ``{agent_type: job}`` con ``job`` y todos sus antecesores.

    Sube por ``input_job_id`` hasta la raíz de la cadena. Si dos antecesores
    comparten ``agent_type`` (posible si alguien encadenara dos veces el mismo
    agente), gana el **más cercano** al job de partida, que es el que produjo la
    entrada efectiva.

    Se detiene ante un ciclo (job ya visto) o al alcanzar ``max_depth``, sin
    lanzar: la ausencia de un eslabón la reporta quien la necesita, con un mensaje
    de dominio (``GateError``), no esta utilidad.
    """
    chain: dict[AgentType, AgentJob] = {}
    seen: set[str] = set()
    current: Optional[AgentJob] = job

    for _ in range(max_depth):
        if current is None or current.id in seen:
            break
        seen.add(current.id)
        chain.setdefault(current.agent_type, current)
        if not current.input_job_id:
            break
        current = await repo.get_job(current.input_job_id)

    return chain


async def resolve_ancestor(
    repo: _JobReader,
    job: AgentJob,
    agent_type: AgentType,
    *,
    max_depth: int = MAX_DEPTH,
) -> Optional[AgentJob]:
    """Antecesor de ``job`` producido por ``agent_type``, o ``None`` si no está."""
    chain = await resolve_lineage(repo, job, max_depth=max_depth)
    found = chain.get(agent_type)
    return None if found is not None and found.id == job.id else found
