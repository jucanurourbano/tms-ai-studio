"""Enumeraciones de valores cerrados del ApiArtifact.

Claves/valores del contrato en inglés; textos de negocio en español (CLAUDE.md).
Se reutilizan ``Origin`` / ``Audience`` / ``QuestionStatus`` / ``HttpMethod`` del
EF, ``RiskSeverity`` de Arquitectura y ``LogicalType`` del Agente BD.

**No se redefine el sistema de tipos.** El tipo de un campo de la API es el
``logical_type`` que ya eligió el modelo de datos: el Agente API no vuelve a
decidirlo, solo lo traduce al esquema del documento con el mapa de
``api_conventions.yaml``. Un segundo enum de tipos sería una segunda verdad.
"""

from enum import Enum


class ApiStyle(str, Enum):
    """Estilo de la API expuesta.

    v1 implementa **solo REST**. El resto existe en el enum porque
    ``tech_stack.yaml`` los admite en su allow-list: si la arquitectura eligiera
    uno de ellos, el agente debe poder **decirlo y preguntar**, en vez de fingir
    que diseñó una API REST que nadie pidió.
    """

    REST = "rest"
    GRAPHQL = "graphql"
    GRPC = "grpc"
    SOAP = "soap"


class VersioningStrategy(str, Enum):
    """Dónde vive la versión de la API."""

    PATH = "path"  # /api/v1/...
    HEADER = "header"  # Accept-Version
    QUERY = "query"  # ?version=1


class AuthScheme(str, Enum):
    """Esquema de seguridad del documento (sale de la capa ``auth`` del stack)."""

    BEARER_JWT = "bearer_jwt"
    OAUTH2_OIDC = "oauth2_oidc"
    API_KEY = "api_key"
    NONE = "none"


class PaginationStyle(str, Enum):
    """Estrategia de paginación (v1: solo offset; cursor queda anotado)."""

    OFFSET = "offset"
    CURSOR = "cursor"


class ResourceExposure(str, Enum):
    """Cuánto se publica de un recurso.

    Todo lo que no sea ``CRUD`` obliga a escribir el motivo (lo verifica el
    contrato): una tabla que no se expone debe decir por qué, o la exclusión sería
    una omisión muda.
    """

    CRUD = "crud"
    READ_ONLY = "read_only"
    NESTED_ONLY = "nested_only"
    NONE = "none"


class EndpointKind(str, Enum):
    """Naturaleza de la operación, que fija su código de éxito y su forma.

    ``ACTION`` es la **única** que no nace del mapa determinista de recursos: la
    propone el LLM desde un proceso o una regla del EF, y por eso el contrato le
    exige ``source_refs``. Es el equivalente de los catálogos en el Agente BD.
    """

    LIST = "list"
    READ_ITEM = "read_item"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ACTION = "action"
    NESTED_LIST = "nested_list"
    NESTED_CREATE = "nested_create"


class SchemaKind(str, Enum):
    """Para qué sirve un esquema de datos."""

    CREATE = "create"
    UPDATE = "update"
    READ = "read"
    LIST_ITEM = "list_item"
    ACTION_INPUT = "action_input"
    ERROR = "error"
    ENVELOPE = "envelope"


class ParameterLocation(str, Enum):
    """Dónde viaja un parámetro de la operación."""

    PATH = "path"
    QUERY = "query"
    HEADER = "header"


class ResponseKind(str, Enum):
    """Forma del cuerpo de la respuesta exitosa."""

    ITEM = "item"
    PAGE = "page"
    NONE = "none"  # 204


class AuthEffect(str, Enum):
    """Efecto de una regla de autorización.

    No hay ausencia de regla: un endpoint que nadie autorizó lleva una regla
    ``DENY`` explícita con ``basis=default_deny``. Fail-closed **visible**, para
    que el hueco se vea en la matriz en vez de esconderse en una lista vacía.
    """

    ALLOW = "allow"
    DENY = "deny"


class AuthScope(str, Enum):
    """Alcance de las filas que el actor puede ver u operar.

    Cualquier valor distinto de ``ALL``/``NONE`` describe un filtro por fila y
    **exige la columna real** que lo materializa; si no la hay, la regla se marca
    ambigua y genera una pregunta bloqueante (lo verifica el contrato).
    """

    ALL = "all"
    OWN = "own"
    OWN_TEAM = "own_team"
    OWN_BRANCH = "own_branch"
    CUSTOM = "custom"
    NONE = "none"


class AuthBasis(str, Enum):
    """De dónde salió la regla de autorización. Es lo que la hace auditable."""

    #: Celda de la matriz CRUD del EF (base determinista).
    CRUD_MATRIX = "crud_matrix"
    #: Regla de negocio del EF que restringe la visibilidad.
    BUSINESS_RULE = "business_rule"
    #: Inferida por el modelo sin celda ni regla directa (siempre revisable).
    INFERRED = "inferred"
    #: Nadie la autorizó: se deniega por defecto y se pregunta.
    DEFAULT_DENY = "default_deny"


class ApiRuleEnforcement(str, Enum):
    """Dónde hace cumplir la API una regla/validación del EF.

    Se compara con el veredicto del Agente BD (``bd_enforcement``): una regla que
    el BD delegó en la aplicación y que aquí acaba en ``NOT_APPLICABLE`` es una
    regla que desaparecería del sistema, y por eso genera pregunta bloqueante.
    """

    #: La aplica la lógica del endpoint (queda para el Agente Backend).
    ENDPOINT = "endpoint"
    #: La expresa el esquema de datos (requerido, enum, longitud, formato).
    SCHEMA = "schema"
    #: La aplica el control de acceso (quién ve o toca qué).
    AUTHORIZATION = "authorization"
    #: Ya la garantiza el modelo de datos; la API no la duplica.
    DATABASE = "database"
    #: No corresponde a la API. **Exige motivo escrito** (lo verifica el contrato).
    NOT_APPLICABLE = "not_applicable"


class SpecFormat(str, Enum):
    """Formato de serialización del documento OpenAPI."""

    YAML = "yaml"
    JSON = "json"
