"""Enumeraciones de valores cerrados del DatabaseArtifact.

Claves/valores del contrato en inglés; textos de negocio en español (CLAUDE.md).
Se reutilizan ``Origin`` / ``Audience`` / ``QuestionStatus`` / ``RiskSeverity``
del EF y de Arquitectura.

``LogicalType`` es la pieza central del diseño (DB2): el LLM elige de este enum
**cerrado y neutro de motor**, y el renderizador de DDL traduce a la sintaxis del
motor con el mapa de ``db_conventions.yaml``. Así es imposible que el modelo cuele
un tipo de SQL Server en un script de PostgreSQL.
"""

from enum import Enum


class DbEngine(str, Enum):
    """Motor relacional destino (los cuatro del allow-list de ``tech_stack``)."""

    POSTGRESQL = "postgresql"
    SQLSERVER = "sqlserver"
    ORACLE = "oracle"
    MYSQL = "mysql"


class LogicalType(str, Enum):
    """Tipo de dato **lógico**, neutro de motor.

    Debe mantenerse a la par de las claves del bloque ``types`` de
    ``ai/knowledge/db_conventions.yaml`` (hay un test que lo verifica): un tipo
    lógico sin traducción sería un DDL imposible de generar.
    """

    STRING = "string"
    TEXT = "text"
    INTEGER = "integer"
    BIGINT = "bigint"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    TIME = "time"
    TIMESTAMP = "timestamp"
    TIMESTAMPTZ = "timestamptz"
    UUID = "uuid"
    JSON = "json"
    BINARY = "binary"


class TableKind(str, Enum):
    """Naturaleza de la tabla, que fija de dónde puede venir.

    ``entity`` exige ``entity_ref`` a una entidad del EF. ``junction`` la genera
    Python al resolver una relación N:M. ``catalog`` sale de la detección de
    catálogos. ``audit`` queda reservada para tablas de auditoría dedicadas.
    Ninguna otra procedencia es admisible: es el cortafuegos anti-invención.
    """

    ENTITY = "entity"
    JUNCTION = "junction"
    CATALOG = "catalog"
    AUDIT = "audit"


class PrimaryKeyStrategy(str, Enum):
    """Estrategia de clave primaria."""

    #: Autoincremental (identity/secuencia) generada por el motor.
    SURROGATE = "surrogate"
    #: UUID generado por la aplicación.
    SURROGATE_UUID = "surrogate_uuid"
    #: Clave natural del negocio (p. ej. número de guía).
    NATURAL = "natural"
    #: PK compuesta (típica de las tablas puente N:M).
    COMPOSITE = "composite"


class ReferentialAction(str, Enum):
    """Acción referencial de una FK (``ON DELETE`` / ``ON UPDATE``)."""

    CASCADE = "cascade"
    RESTRICT = "restrict"
    SET_NULL = "set_null"
    NO_ACTION = "no_action"


class RuleEnforcement(str, Enum):
    """Dónde se hace cumplir una regla/validación del EF.

    Nada se descarta en silencio: una regla que no sea expresable como constraint
    declarativa se clasifica aquí y genera una ``Observation`` con su destino.
    """

    #: Expresable en el esquema (unique / check / not null / FK).
    DECLARATIVE = "declarative"
    #: Requiere lógica de negocio (queda para el Agente Backend).
    APPLICATION = "application"
    #: Solo viable con un trigger (último recurso; exige confirmación del DBA).
    TRIGGER = "trigger"


class NormalizationForm(str, Enum):
    """Forma normal declarada de la tabla."""

    FIRST = "1NF"
    SECOND = "2NF"
    THIRD = "3NF"
    BCNF = "BCNF"


class VolumeEstimate(str, Enum):
    """Volumetría estimada de la tabla (informa índices; nunca particionado en v1)."""

    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    DESCONOCIDA = "desconocida"


class DdlScriptKind(str, Enum):
    """Tipo de script DDL, que además fija su orden de ejecución."""

    SCHEMA = "schema"
    TABLES = "tables"
    CONSTRAINTS = "constraints"
    INDEXES = "indexes"
    SEED = "seed"
    ROLLBACK = "rollback"


class DecisionScope(str, Enum):
    """Alcance de una decisión de diseño de datos."""

    GLOBAL = "global"
    TABLE = "table"


class DiagramFormat(str, Enum):
    """Formato del diagrama entidad-relación (v1: solo Mermaid)."""

    MERMAID = "mermaid"
