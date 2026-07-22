"""Modelos ORM. Importar aquí asegura el registro en ``Base.metadata``."""

from .agent import (
    AgentArtifactRow,
    AgentExternalLink,
    AgentJob,
    AgentType,
    AgentValidation,
    EFSourceDoc,
    EFSourceDocType,
    JobStatus,
    ValidationStatus,
    ValidationTargetType,
)
from .base import Base

# Alias históricos del Agente EF (compatibilidad).
from .ef import EFArtifactRow, EFJob, EFValidation
from .user import User, UserRole

__all__ = [
    "AgentArtifactRow",
    "AgentExternalLink",
    "AgentJob",
    "AgentType",
    "AgentValidation",
    "Base",
    "EFArtifactRow",
    "EFJob",
    "EFSourceDoc",
    "EFSourceDocType",
    "EFValidation",
    "JobStatus",
    "User",
    "UserRole",
    "ValidationStatus",
    "ValidationTargetType",
]
