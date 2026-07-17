"""Base declarativa y utilidades comunes de los modelos ORM."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from ulid import ULID

# JSONB en Postgres (producción), JSON en el resto (SQLite en tests).
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    """Genera un identificador ULID (26 chars, ordenable por tiempo)."""
    return str(ULID())


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos."""


class IdMixin:
    """Clave primaria ULID en formato string."""

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)


class TimestampMixin:
    """Marcas de tiempo de creación y actualización."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
