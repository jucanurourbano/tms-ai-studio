"""Contrato de datos ApiArtifact v1.0.0 (Pydantic 2).

Artefacto que produce el Agente API a partir del ``DatabaseArtifact`` y, resueltos
transitivamente, los de Arquitectura, Scrum y EF: recursos, endpoints, esquemas de
datos, matriz de autorización, catálogo de errores, trazabilidad de reglas y el
documento OpenAPI 3.1 completo.

Claves en inglés, valores/descripciones en español. Todo ítem trazable lleva
``id`` y, donde aplique, ``source_refs``, ``confidence`` y ``origin``. Reusa
``TokenMetrics``/``SkippedItem``/``Observation`` del EF, ``RiskSeverity`` de
Arquitectura y ``LogicalType`` del Agente BD.

**Qué valida el contrato y qué no.** El contrato solo impide lo que sería
*invención* u *omisión muda*, no lo que sería un *defecto reportable*:

- Impide (lanza ``ValidationError``): un campo de esquema sin columna detrás, un
  recurso excluido sin motivo, un alcance de autorización sin la columna que lo
  materialice, una regla descartada sin explicación y un endpoint de acción sin
  evidencia. Nada de eso puede existir en un artefacto correcto **ni en uno
  defectuoso**: sería un dato falso con aspecto de verdad.
- No impide: un endpoint sin reglas de autorización, un documento inválido, una
  cobertura incompleta. Todo eso lo detecta la validación L1 y lo refleja el
  semáforo. Un contrato que se negara a representar un artefacto defectuoso
  impediría al agente **reportar** el defecto, que es justo lo que debe hacer
  (misma razón por la que ``Table.primary_key`` es opcional en el Agente BD).
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai.agents.arquitectura.schemas.enums import RiskSeverity
from ai.agents.bd.schemas.enums import LogicalType
from ai.agents.ef.schemas.artifact import Observation, SkippedItem, TokenMetrics
from ai.agents.ef.schemas.enums import Audience, HttpMethod, Origin, QuestionStatus
from ai.inventory.contract import ReconciliationRef, ReconciliationSummary

from .enums import (
    ApiRuleEnforcement,
    ApiStyle,
    AuthBasis,
    AuthEffect,
    AuthScheme,
    AuthScope,
    EndpointKind,
    PaginationStyle,
    ParameterLocation,
    ResourceExposure,
    ResponseKind,
    SchemaKind,
    SpecFormat,
    VersioningStrategy,
)

SCHEMA_VERSION = "1.0.0"

#: Versión de OpenAPI que renderiza el agente. 3.1 alinea el documento con JSON
#: Schema 2020-12; degradarlo a 3.0.3 es un re-render sin coste de modelo.
OPENAPI_VERSION = "3.1.0"


class _Strict(BaseModel):
    """Base estricta: prohíbe claves desconocidas (structured output cerrado)."""

    model_config = ConfigDict(extra="forbid")


class TracedItem(_Strict):
    """Ítem trazable con provenance y confianza.

    Atributos:
        id: Identificador estable del ítem (renumerable de forma determinística).
        confidence: Confianza [0, 1] donde aplique.
        origin: Declarado en un artefacto de origen (``stated``) o inferido
            (``derived``). Un endpoint que el EF ya declaraba como ``API-...`` es
            ``stated``; el resto, ``derived``.
    """

    id: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    origin: Optional[Origin] = None


# --- Fuente (enlace a los jobs BD + Arquitectura + Scrum + EF de origen) -----


class SourceRef(_Strict):
    """Referencia reproducible a la cadena consumida.

    El job de API se enlaza a BD por ``input_job_id`` (predecesor directo);
    Arquitectura, Scrum y EF se resuelven transitivamente (tres saltos). Se guardan
    los cuatro ids + hashes para poder reproducir la corrida.
    """

    bd_job_id: str
    bd_artifact_hash: str
    bd_schema_version: str = "1.0.0"
    architecture_job_id: Optional[str] = None
    architecture_artifact_hash: Optional[str] = None
    scrum_job_id: Optional[str] = None
    scrum_artifact_hash: Optional[str] = None
    ef_job_id: str
    ef_artifact_hash: str
    ef_schema_version: str = "1.2.0"
    ready_snapshot: bool = True  # gate del Agente BD verificado al generar


# --- Objetivo: estilo, seguridad y convenciones efectivas --------------------


class AuthConfig(_Strict):
    """Esquema de seguridad de la API y de dónde salió la decisión."""

    scheme: AuthScheme = AuthScheme.BEARER_JWT
    #: Producto de la capa ``auth`` del stack (Keycloak, Azure AD…).
    provider: Optional[str] = None
    #: Ref al ``stack[]`` de Arquitectura que lo fijó (``STK-...``).
    source_ref: Optional[str] = None
    #: ``False`` si la arquitectura no decidió y se usó el default de la casa. En
    #: ese caso hay una pregunta bloqueante: el semáforo no se pone verde.
    decided: bool = True


class PaginationConfig(_Strict):
    """Forma de la paginación de los listados (API10: offset/limit)."""

    style: PaginationStyle = PaginationStyle.OFFSET
    limit_param: str = "limit"
    offset_param: str = "offset"
    default_limit: int = Field(default=20, ge=1)
    max_limit: int = Field(default=100, ge=1)
    items_field: str = "items"
    total_field: str = "total"


class Conventions(_Strict):
    """Convenciones efectivas aplicadas al diseño (desde ``api_conventions.yaml``).

    Se persisten en el artefacto —y no solo en el YAML— para que la especificación
    sea auditable a posteriori: si mañana el equipo cambia una convención, se sigue
    sabiendo con qué reglas se generó este contrato.
    """

    #: Idioma de los segmentos de dominio (API6: ``es``). El protocolo va en inglés.
    path_language: str = "es"
    path_case: str = "kebab-case"
    resource_number: str = "plural"
    #: API7: espejo 1:1 de los nombres de columna del modelo de datos.
    property_case: str = "snake_case"
    #: API8: el ``ApiResponse`` de la casa.
    envelope: str = "api_response"
    #: API11: actualización parcial; no se genera ``PUT``.
    update_verb: HttpMethod = HttpMethod.PATCH
    max_nesting: int = Field(default=1, ge=0)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    sort_param: str = "sort"
    date_format: str = "rfc3339"
    #: Los importes viajan como cadena para no perder precisión en JavaScript.
    decimal_as_string: bool = True


class Target(_Strict):
    """Qué API se está diseñando y bajo qué reglas."""

    api_style: ApiStyle = ApiStyle.REST
    spec_version: str = OPENAPI_VERSION
    base_path: str = "/api/v1"
    api_version: str = "v1"
    versioning: VersioningStrategy = VersioningStrategy.PATH
    auth: AuthConfig = Field(default_factory=AuthConfig)
    conventions: Conventions = Field(default_factory=Conventions)
    #: Procedencia y versión de las convenciones (``api_conventions.yaml@v0``).
    conventions_source: Optional[str] = None


# --- Recursos ----------------------------------------------------------------


class Resource(TracedItem):
    """Recurso REST, respaldado por una tabla del modelo de datos.

    Un recurso **no puede existir sin tabla**: el conjunto lo fija ``RESOURCE_MAP``
    en Python desde ``tables[]``, y el LLM solo lo describe.
    """

    name: str  # plural, tal como aparece en la ruta ("siniestros")
    singular: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    #: Tabla del Agente BD que lo respalda (``TBL-...``). Obligatoria.
    table_ref: str
    #: Entidad del EF, resuelta a través de la tabla (``ENT-...``).
    entity_ref: Optional[str] = None
    #: Componente de Arquitectura al que pertenece (``CMP-...``) → ``tags``.
    component_ref: Optional[str] = None
    base_path: str
    exposure: ResourceExposure = ResourceExposure.CRUD
    #: Obligatorio cuando ``exposure`` no es ``crud`` (lo verifica el contrato).
    exposure_reason: Optional[str] = None
    #: Recurso padre cuando este se expone anidado (profundidad máxima 1).
    parent_resource_ref: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _exclusion_con_motivo(self) -> "Resource":
        """Una tabla que no se publica dice por qué (API12).

        Sin esta regla, un recurso ausente y un recurso deliberadamente omitido
        serían indistinguibles al leer el artefacto, y la revisión no podría saber
        si falta algo o si se decidió que faltara.
        """
        if (
            self.exposure is not ResourceExposure.CRUD
            and not (self.exposure_reason or "").strip()
        ):
            raise ValueError(
                f"El recurso {self.id} se expone como «{self.exposure.value}» sin "
                "motivo: toda exclusión debe llevar su razón escrita."
            )
        return self


# --- Esquemas de datos -------------------------------------------------------


class SchemaField(_Strict):
    """Campo de un esquema de request/response.

    **Es la pieza anti-invención del contrato.** Todo campo nace de una columna del
    modelo de datos (``column_ref``); la única excepción es un campo calculado, que
    debe citar la regla de negocio que lo define. Sin esta restricción, el agente
    podría añadir a la API un dato que no existe en ninguna parte y que el Agente
    Backend intentaría después implementar.
    """

    id: str
    name: str
    #: Heredado de la columna: el Agente API **no** vuelve a decidir tipos.
    logical_type: LogicalType
    #: Formato del esquema cuando aplica (``date``, ``uuid``…). Lo deriva el
    #: renderizador del tipo lógico; no lo inventa el modelo.
    format: Optional[str] = None
    required: bool = False
    nullable: bool = True
    read_only: bool = False
    write_only: bool = False
    max_length: Optional[int] = Field(default=None, ge=1)
    #: Valores admitidos, derivados de un CHECK o de un catálogo del modelo.
    enum: Optional[list[str]] = None
    description: Optional[str] = None
    example: Optional[str] = None
    #: Columna del Agente BD que lo origina (``COL-...``).
    column_ref: Optional[str] = None
    table_ref: Optional[str] = None
    #: Campo calculado: no existe como columna. **Exige ``source_refs``**.
    computed: bool = False
    #: Heredado del modelo de datos: gobierna la exigencia de alcance en la
    #: autorización (un endpoint con PII y alcance ambiguo bloquea el semáforo).
    pii: bool = False
    source_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    origin: Optional[Origin] = None

    @model_validator(mode="after")
    def _todo_campo_viene_de_algun_sitio(self) -> "SchemaField":
        """O es una columna, o es un cálculo con regla citada. No hay tercera vía."""
        if self.computed:
            if not self.source_refs:
                raise ValueError(
                    f"El campo calculado {self.id} ({self.name}) no cita la regla "
                    "que lo define: un cálculo sin base es una invención."
                )
        elif not self.column_ref:
            raise ValueError(
                f"El campo {self.id} ({self.name}) no tiene columna de origen. "
                "Todo campo expuesto nace de una columna del modelo de datos; si "
                "es calculado, márcalo como tal y cita la regla."
            )
        return self


class ApiSchema(TracedItem):
    """Esquema de datos de una operación (``components.schemas`` del documento)."""

    name: str  # nombre en el documento: "SiniestroCreate"
    kind: SchemaKind
    resource_ref: Optional[str] = None
    description: Optional[str] = None
    fields: list[SchemaField] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


# --- Endpoints ---------------------------------------------------------------


class Parameter(_Strict):
    """Parámetro de una operación (ruta, query o cabecera)."""

    id: str
    name: str
    location: ParameterLocation
    logical_type: LogicalType
    required: bool = False
    description: Optional[str] = None
    example: Optional[str] = None
    #: Columna que representa, cuando el parámetro filtra por un campo real.
    column_ref: Optional[str] = None


class StatusCode(_Strict):
    """Código de estado declarado por la operación.

    Los códigos **no los decide el LLM**: los estampa el nodo ERRORS desde el
    catálogo y desde las constraints del modelo de datos.
    """

    code: int = Field(ge=100, le=599)
    description: Optional[str] = None
    #: Esquema del cuerpo en las respuestas exitosas (``SCH-...``).
    schema_ref: Optional[str] = None
    #: Entrada del catálogo de errores en las de fallo (``ERR-...``).
    error_ref: Optional[str] = None


class Endpoint(TracedItem):
    """Operación de la API.

    ``auth_rule_refs`` puede venir vacío **a propósito**: un endpoint sin
    autorización resuelta es un defecto que hay que poder representar y reportar
    (lo detecta L1 y bloquea el semáforo), no un artefacto imposible de construir.
    """

    resource_ref: str
    method: HttpMethod
    path: str
    operation_id: str
    kind: EndpointKind
    purpose: str
    description: Optional[str] = None
    parameters: list[Parameter] = Field(default_factory=list)
    request_schema_ref: Optional[str] = None
    response_schema_ref: Optional[str] = None
    response_kind: ResponseKind = ResponseKind.ITEM
    status_codes: list[StatusCode] = Field(default_factory=list)
    #: Campos filtrables. Solo columnas indexadas, PK, FK o de enumeración: un
    #: filtro sin índice es una consulta lenta en producción.
    filters: list[str] = Field(default_factory=list)
    sortable: list[str] = Field(default_factory=list)
    paginated: bool = False
    idempotent: bool = False
    deprecated: bool = False
    #: Reglas de autorización que lo gobiernan (``AUTH-...``).
    auth_rule_refs: list[str] = Field(default_factory=list)
    #: Reglas del EF que este endpoint hace cumplir (``BR-``/``VAL-``).
    rule_refs: list[str] = Field(default_factory=list)
    #: Endpoint que el EF ya declaraba (``API-...``); si existe, ``origin=stated``.
    ef_api_ref: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)
    #: Veredicto de la fase RECONCILE (INV4). Un ``reuse`` aquí significa que la
    #: operación YA la expone el sistema destino y no hay que construirla.
    #: ``None`` = no se reconcilió (retrocompatible).
    reconciliation: Optional[ReconciliationRef] = None

    @model_validator(mode="after")
    def _las_acciones_citan_su_evidencia(self) -> "Endpoint":
        """Un endpoint de acción sin base en el EF es una invención.

        Las operaciones CRUD las fija ``RESOURCE_MAP`` desde las tablas y la matriz
        CRUD, así que su procedencia es estructural. Las **acciones** son la única
        ampliación que propone el LLM, y por eso son las únicas que deben
        justificarse: es el mismo trato que reciben los catálogos en el Agente BD.
        """
        if self.kind is EndpointKind.ACTION and not self.source_refs:
            raise ValueError(
                f"El endpoint de acción {self.id} ({self.method.value} {self.path}) "
                "no cita el proceso o la regla que lo justifica."
            )
        return self


# --- Matriz de autorización --------------------------------------------------


class AuthorizationRule(TracedItem):
    """Fila de la matriz de autorización: qué puede hacer un actor con un endpoint.

    Es una **lista de filas y no un mapa denso** a propósito: cada permiso lleva su
    ``basis`` y sus ``source_refs``, así que se puede auditar de dónde salió. En
    autorización, la trazabilidad es el producto.
    """

    endpoint_ref: str
    #: Actor del EF (``ACT-...``).
    actor_ref: str
    actor_name: Optional[str] = None
    effect: AuthEffect = AuthEffect.DENY
    scope: AuthScope = AuthScope.NONE
    #: Condición legible del filtro por fila ("siniestro.equipo_id = usuario.equipo_id").
    scope_expression: Optional[str] = None
    #: Columnas que materializan el filtro (``COL-...``). Sin ellas, el alcance es
    #: una intención que nadie puede implementar.
    scope_column_refs: list[str] = Field(default_factory=list)
    basis: AuthBasis = AuthBasis.DEFAULT_DENY
    #: ``True`` cuando la regla no se puede aplicar tal como está: genera pregunta
    #: bloqueante. Nunca se resuelve ampliando el permiso.
    ambiguous: bool = False
    note: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _un_alcance_sin_columna_es_ambiguo(self) -> "AuthorizationRule":
        """Fail-closed estructural: la ambigüedad no se puede olvidar.

        "Los jefes solo ven las solicitudes de su equipo" no es implementable si
        ninguna columna dice de qué equipo es cada solicitud. Marcarla ambigua es
        lo que convierte ese vacío en una pregunta bloqueante en vez de en un
        permiso más ancho de lo que nadie autorizó.
        """
        acotado = self.scope not in (AuthScope.ALL, AuthScope.NONE)
        if acotado and not self.scope_column_refs and not self.ambiguous:
            raise ValueError(
                f"La regla {self.id} declara alcance «{self.scope.value}» sin "
                "ninguna columna que lo materialice: debe marcarse ambigua "
                "(ambiguous=True) para que genere una pregunta bloqueante."
            )
        return self


# --- Catálogo de errores -----------------------------------------------------


class ErrorEntry(_Strict):
    """Entrada del catálogo estándar de errores (contrato del renderizador)."""

    id: str
    status: int = Field(ge=100, le=599)
    #: Código estable en español que consume el frontend para decidir el mensaje.
    code: str
    message: str
    #: Cuándo se devuelve. Documentarlo evita que dos endpoints usen el mismo
    #: código para cosas distintas.
    when: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)


# --- Reglas del EF y dónde las hace cumplir la API ---------------------------


class ApiRuleMapping(TracedItem):
    """Destino de una regla/validación del EF en la API.

    **Cierra el círculo que abrió el Agente BD.** ``bd_enforcement`` copia su
    veredicto: una regla que el modelo de datos delegó en la aplicación
    (``application``) y que aquí no encuentra endpoint que la aplique es una regla
    que desaparecería del sistema sin que nadie lo note.
    """

    #: Ref del EF (``BR-...`` / ``VAL-...``).
    rule_ref: str
    enforcement: ApiRuleEnforcement
    endpoint_refs: list[str] = Field(default_factory=list)
    schema_field_refs: list[str] = Field(default_factory=list)
    auth_rule_refs: list[str] = Field(default_factory=list)
    #: Lo que dijo el Agente BD (``declarative`` | ``application`` | ``trigger``).
    bd_enforcement: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def _descartar_exige_explicacion(self) -> "ApiRuleMapping":
        """Ninguna regla se descarta en silencio."""
        if (
            self.enforcement is ApiRuleEnforcement.NOT_APPLICABLE
            and not (self.note or "").strip()
        ):
            raise ValueError(
                f"El mapeo {self.id} deja la regla {self.rule_ref} fuera de la API "
                "sin explicar por qué."
            )
        return self


# --- Documento OpenAPI --------------------------------------------------------


class OpenApiDocument(_Strict):
    """El documento renderizado, listo para descargar.

    Se guarda el YAML canónico —igual que el Agente BD guarda el DDL completo— y
    se puede **re-renderizar** a JSON o a 3.0.3 desde el resto del artefacto sin
    volver a llamar al modelo.
    """

    format: SpecFormat = SpecFormat.YAML
    spec_version: str = OPENAPI_VERSION
    content: str = ""
    operations_total: int = 0
    byte_size: int = 0
    checksum: Optional[str] = None


# --- Validación determinista de la especificación ----------------------------


class SpecValidationIssue(_Strict):
    """Hallazgo de la validación (sin LLM)."""

    #: Código estable y accionable (``schema_ref_missing``, ``path_collision``…).
    code: str
    message: str
    ref: Optional[str] = None


class SpecValidation(_Strict):
    """Resultado de la validación determinista de la especificación.

    ``runtime_checked`` distingue "el documento parsea y cumple el esquema de
    OpenAPI" de "un runtime real lo cargó y validó peticiones contra él": no se
    presenta como certificación lo que solo fue un parseo (mismo criterio que
    ``executed`` en el Agente BD).
    """

    spec_valid: bool = False
    validator: Optional[str] = None
    validator_version: Optional[str] = None
    runtime_checked: bool = False
    checks: dict[str, bool] = Field(default_factory=dict)
    errors: list[SpecValidationIssue] = Field(default_factory=list)
    warnings: list[SpecValidationIssue] = Field(default_factory=list)


# --- Preguntas al líder técnico ----------------------------------------------


class TechLeadQuestion(TracedItem):
    """Duda hacia quien puede responderla (quien tiene el módulo ``api``).

    Se agrupan **por clase de vacío**: cuarenta campos sin descripción producen una
    pregunta con los refs enumerados, no cuarenta que entierran la que importa.
    """

    question: str
    reason: str
    audience: Audience = Audience.TECNICO
    blocking: bool = False
    linked_to_ref: Optional[str] = None
    status: QuestionStatus = QuestionStatus.PENDIENTE


# --- Análisis -----------------------------------------------------------------


class Risk(TracedItem):
    """Riesgo del contrato de API propuesto."""

    description: str
    severity: RiskSeverity = RiskSeverity.MEDIA
    mitigation: Optional[str] = None
    source_ref: Optional[str] = None


class Coverage(_Strict):
    """Cobertura de trazabilidad hacia BD y EF. Nunca oculta huecos.

    Solo la exposición de tablas y los ``API-`` declarados por el EF entran en el
    semáforo; las celdas CRUD, las reglas y los actores generan preguntas (mismo
    criterio que los campos en BD y los RNF en Arquitectura).
    """

    tables_total: int = 0
    tables_exposed: int = 0
    unexposed_table_refs: list[str] = Field(default_factory=list)
    ef_apis_total: int = 0
    ef_apis_covered: int = 0
    uncovered_api_refs: list[str] = Field(default_factory=list)
    crud_cells_total: int = 0
    crud_cells_covered: int = 0
    uncovered_crud_refs: list[str] = Field(default_factory=list)
    rules_total: int = 0
    rules_enforced: int = 0
    unenforced_rule_refs: list[str] = Field(default_factory=list)
    actors_total: int = 0
    actors_with_access: int = 0
    actors_without_access: list[str] = Field(default_factory=list)


class ApiAnalysis(_Strict):
    """Bloque de análisis del ApiArtifact."""

    risks: list[Risk] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    coverage: Coverage = Field(default_factory=Coverage)


# --- Métricas -----------------------------------------------------------------


class ApiMetrics(_Strict):
    """Métricas reales de la corrida del Agente API."""

    tokens: TokenMetrics = Field(default_factory=TokenMetrics)
    cost: float = 0.0  # USD
    duration: float = 0.0  # segundos
    resources_total: int = 0
    endpoints_total: int = 0
    schemas_total: int = 0
    auth_rules_total: int = 0
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    #: Espejo de ``validation.spec_valid`` sin errores: entra en el semáforo.
    spec_valid: bool = False
    #: Endpoints sin ninguna regla de autorización. Entra en el semáforo: un solo
    #: endpoint sin decisión de acceso deja el contrato en rojo.
    endpoints_unauthorized: int = 0
    skipped: list[SkippedItem] = Field(default_factory=list)


# --- Artefacto raíz ------------------------------------------------------------


class ApiArtifact(_Strict):
    """Artefacto completo del Agente API (contrato v1.0.0)."""

    schema_version: str = SCHEMA_VERSION
    source: SourceRef
    target: Target = Field(default_factory=Target)
    resources: list[Resource] = Field(default_factory=list)
    schemas: list[ApiSchema] = Field(default_factory=list)
    endpoints: list[Endpoint] = Field(default_factory=list)
    authorization_matrix: list[AuthorizationRule] = Field(default_factory=list)
    error_catalog: list[ErrorEntry] = Field(default_factory=list)
    rule_mappings: list[ApiRuleMapping] = Field(default_factory=list)
    openapi: OpenApiDocument = Field(default_factory=OpenApiDocument)
    validation: SpecValidation = Field(default_factory=SpecValidation)
    analysis: ApiAnalysis = Field(default_factory=ApiAnalysis)
    questions_for_tech_lead: list[TechLeadQuestion] = Field(default_factory=list)
    metrics: ApiMetrics = Field(default_factory=ApiMetrics)
    #: Resumen de la reconciliación contra el inventario (INV4). Opcional.
    reconciliation: Optional[ReconciliationSummary] = None
