"""Checkpointer del grafo EF.

En runtime se usa Redis (thread_id = job_id) para que los reintentos NO
re-facturen fases ya completadas. En tests se usa un checkpointer en memoria.
"""

from typing import Optional


def build_redis_checkpointer(redis_url: Optional[str] = None):
    """Crea un checkpointer Redis async a partir de la URL (import perezoso)."""
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver

    from app.config.settings import settings

    url = redis_url or settings.REDIS_URL
    return AsyncRedisSaver(redis_url=url)


def build_memory_checkpointer():
    """Checkpointer en memoria (tests / desarrollo sin Redis)."""
    try:
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver()
    except ImportError:  # pragma: no cover
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
