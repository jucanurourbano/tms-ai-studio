"""Enumeraciones de valores cerrados del ArchitectureArtifact.

Claves/valores del contrato en inglés; textos de negocio en español (CLAUDE.md).
Se reutilizan ``Origin`` / ``Audience`` / ``QuestionStatus`` del Agente EF.
"""

from enum import Enum


class ArchitectureStyle(str, Enum):
    """Estilo arquitectónico elegido para la solución."""

    MODULAR_MONOLITH = "modular_monolith"
    MICROSERVICES = "microservices"
    SERVERLESS = "serverless"


class SizeClass(str, Enum):
    """Clasificación de tamaño del alcance (scope profile determinista)."""

    S = "S"
    M = "M"
    L = "L"


class ComponentType(str, Enum):
    """Tipo de componente lógico de la arquitectura."""

    UI = "ui"
    API = "api"
    SERVICE = "service"
    DOMAIN = "domain"
    INTEGRATION = "integration"
    DATASTORE = "datastore"
    WORKER = "worker"


class IntegrationDirection(str, Enum):
    """Sentido del flujo de una integración externa."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BIDIRECTIONAL = "bidirectional"


class IntegrationProtocol(str, Enum):
    """Protocolo de una integración externa (``unknown`` si el EF no lo indica)."""

    REST = "rest"
    SOAP = "soap"
    FILE = "file"
    DB = "db"
    QUEUE = "queue"
    UNKNOWN = "unknown"


class ContractKind(str, Enum):
    """Tipo de contrato entre componentes (los eventos van como ``event``)."""

    SYNC_API = "sync_api"
    EVENT = "event"
    SHARED_MODULE = "shared_module"
    FILE = "file"
    EXTERNAL = "external"


class CrossCuttingConcern(str, Enum):
    """Preocupación transversal derivada de RNF/reglas."""

    AUTH = "auth"
    AUTHORIZATION = "authorization"
    AUDIT = "audit"
    NOTIFICATIONS = "notifications"
    LOGGING = "logging"
    CONFIG = "config"
    ERROR_HANDLING = "error_handling"
    I18N = "i18n"


class AdrStatus(str, Enum):
    """Estado de una decisión de arquitectura (ADR)."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class DiagramFormat(str, Enum):
    """Formato de un diagrama (v1: solo Mermaid)."""

    MERMAID = "mermaid"


class RiskSeverity(str, Enum):
    """Severidad de un riesgo técnico detectado."""

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"
