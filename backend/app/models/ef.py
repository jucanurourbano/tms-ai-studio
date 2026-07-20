"""Compatibilidad EF sobre los modelos multi-agente.

Las tablas ``ef_*`` se generalizaron a ``agent_*`` (D1 del diseño). Este módulo
re-exporta los modelos generalizados con los nombres históricos del EF para no
romper el código y los tests existentes. La única tabla que sigue siendo propia
de la familia EF es ``ef_source_docs`` (``EFSourceDoc``).
"""

from .agent import AgentArtifactRow as EFArtifactRow
from .agent import AgentJob as EFJob
from .agent import (
    AgentType,
)
from .agent import AgentValidation as EFValidation
from .agent import (
    EFSourceDoc,
    EFSourceDocType,
    JobStatus,
    ValidationStatus,
    ValidationTargetType,
)

__all__ = [
    "AgentType",
    "EFArtifactRow",
    "EFJob",
    "EFSourceDoc",
    "EFSourceDocType",
    "EFValidation",
    "JobStatus",
    "ValidationStatus",
    "ValidationTargetType",
]
