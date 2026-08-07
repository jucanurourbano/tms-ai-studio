"""Ejemplo válido de ApiArtifact (dominio: siniestros logísticos).

Continúa la cadena de fixtures de EF → Scrum → Arquitectura → BD: los recursos de
abajo son los del ``DatabaseArtifact`` de ejemplo (``TBL-001`` guias, ``TBL-002``
siniestros, ``TBL-003`` siniestro_estados) y sus campos citan las columnas reales
de aquel modelo (``COL-0001``…``COL-0010``). Sirve de fixture en los bloques
posteriores: es aproximadamente lo que el pipeline debería producir a partir de esa
cadena.

Incluye a propósito los cuatro casos que el contrato debe saber representar:

1. Un endpoint que el EF **ya declaraba** (``API-001``) y que por eso nace
   ``origin=stated``, junto a otros derivados.
2. Un recurso **no expuesto como CRUD** (el catálogo) con su motivo escrito.
3. Una regla de autorización **ambigua**: el EF limita la visibilidad por equipo
   pero ninguna columna dice de qué equipo es cada siniestro → pregunta bloqueante.
   Es el caso que el agente existe para no dejar pasar.
4. Una regla que el Agente BD delegó en la aplicación (``application``) y que aquí
   **sí** encuentra endpoint que la haga cumplir: el círculo cerrado.

El documento OpenAPI del ejemplo es **real y válido**: hay un test que lo valida
con ``openapi-spec-validator``, así que sirve de referencia de la forma exacta que
tendrá que renderizar ``OPENAPI_GEN`` en el bloque API6.
"""

from ai.agents.arquitectura.schemas.enums import RiskSeverity
from ai.agents.bd.schemas.enums import LogicalType
from ai.agents.ef.schemas.artifact import Observation, TokenMetrics
from ai.agents.ef.schemas.enums import Audience, HttpMethod, Origin

from .artifact import (
    OPENAPI_VERSION,
    ApiAnalysis,
    ApiArtifact,
    ApiMetrics,
    ApiRuleMapping,
    ApiSchema,
    AuthConfig,
    AuthorizationRule,
    Conventions,
    Coverage,
    Endpoint,
    ErrorEntry,
    OpenApiDocument,
    Parameter,
    Resource,
    Risk,
    SchemaField,
    SourceRef,
    SpecValidation,
    StatusCode,
    Target,
    TechLeadQuestion,
)
from .enums import (
    ApiRuleEnforcement,
    ApiStyle,
    AuthBasis,
    AuthEffect,
    AuthScheme,
    AuthScope,
    EndpointKind,
    ParameterLocation,
    ResourceExposure,
    ResponseKind,
    SchemaKind,
)

# El documento que renderizará OPENAPI_GEN. Detalles de OpenAPI 3.1 que NO son
# los de 3.0 y que este ejemplo fija como referencia:
#   - la nulabilidad se expresa con `type: [x, "null"]`, no con `nullable: true`;
#   - los ejemplos dentro de un esquema son `examples: [...]` (lista), no `example`;
#   - un binario usaría `contentEncoding`, no `format: binary`.
_OPENAPI_YAML = """openapi: 3.1.0
info:
  title: API de Gestión de Siniestros
  version: 1.0.0
  description: Contrato generado por el Agente API del ISDF a partir del modelo de datos.
servers:
  - url: /api/v1
    description: Servidor de la aplicación.
tags:
  - name: Siniestros
    description: Módulo Siniestros (CMP-001).
  - name: Catálogos
    description: Datos de configuración de solo lectura.
security:
  - bearerAuth: []
paths:
  /api/v1/siniestros:
    get:
      tags: [Siniestros]
      operationId: listarSiniestros
      summary: Lista los siniestros registrados.
      parameters:
        - name: limit
          in: query
          required: false
          description: Tamaño de página (máximo 100).
          schema:
            type: integer
            default: 20
            maximum: 100
        - name: offset
          in: query
          required: false
          description: Desplazamiento desde el inicio del listado.
          schema:
            type: integer
            default: 0
        - name: estado_id
          in: query
          required: false
          description: Filtra por estado del siniestro.
          schema:
            type: integer
            format: int64
        - name: sort
          in: query
          required: false
          description: Orden; prefijo «-» para descendente.
          schema:
            type: string
      responses:
        '200':
          description: Listado paginado de siniestros.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponsePageSiniestroResumen'
        '401':
          $ref: '#/components/responses/NoAutenticado'
        '403':
          $ref: '#/components/responses/SinPermiso'
    post:
      tags: [Siniestros]
      operationId: crearSiniestro
      summary: Registra un nuevo siniestro.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SiniestroCreate'
      responses:
        '201':
          description: Siniestro registrado.
          headers:
            Location:
              description: Ruta del siniestro creado.
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponseSiniestro'
        '401':
          $ref: '#/components/responses/NoAutenticado'
        '403':
          $ref: '#/components/responses/SinPermiso'
        '422':
          $ref: '#/components/responses/ValidacionFallida'
  /api/v1/siniestros/{siniestro_id}:
    get:
      tags: [Siniestros]
      operationId: obtenerSiniestro
      summary: Obtiene el detalle de un siniestro.
      parameters:
        - name: siniestro_id
          in: path
          required: true
          description: Identificador del siniestro.
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Detalle del siniestro.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponseSiniestro'
        '401':
          $ref: '#/components/responses/NoAutenticado'
        '403':
          $ref: '#/components/responses/SinPermiso'
        '404':
          $ref: '#/components/responses/NoEncontrado'
  /api/v1/siniestro-estados:
    get:
      tags: [Catálogos]
      operationId: listarSiniestroEstados
      summary: Lista los estados de siniestro disponibles.
      responses:
        '200':
          description: Catálogo de estados.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponseListaSiniestroEstado'
        '401':
          $ref: '#/components/responses/NoAutenticado'
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    Siniestro:
      type: object
      description: Siniestro registrado sobre una guía.
      properties:
        siniestro_id:
          type: integer
          format: int64
          readOnly: true
        guia_id:
          type: integer
          format: int64
        fecha_siniestro:
          type: string
          format: date
          examples: ['2026-03-14']
        monto:
          type: [string, 'null']
          format: decimal
          examples: ['1500.00']
        estado_id:
          type: integer
          format: int64
      required: [siniestro_id, guia_id, fecha_siniestro, estado_id]
    SiniestroCreate:
      type: object
      description: Datos necesarios para registrar un siniestro.
      properties:
        guia_id:
          type: integer
          format: int64
        fecha_siniestro:
          type: string
          format: date
        monto:
          type: [string, 'null']
          format: decimal
        estado_id:
          type: integer
          format: int64
      required: [guia_id, fecha_siniestro, estado_id]
    SiniestroResumen:
      type: object
      description: Vista reducida para listados.
      properties:
        siniestro_id:
          type: integer
          format: int64
        fecha_siniestro:
          type: string
          format: date
        estado_id:
          type: integer
          format: int64
      required: [siniestro_id, fecha_siniestro, estado_id]
    SiniestroEstado:
      type: object
      description: Estado posible de un siniestro.
      properties:
        estado_id:
          type: integer
          format: int64
        codigo:
          type: string
          maxLength: 30
        nombre:
          type: string
          maxLength: 100
      required: [estado_id, codigo, nombre]
    PageSiniestroResumen:
      type: object
      description: Página de resultados.
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/SiniestroResumen'
        total:
          type: integer
        limit:
          type: integer
        offset:
          type: integer
      required: [items, total, limit, offset]
    ApiResponseSiniestro:
      type: object
      properties:
        success:
          type: boolean
        message:
          type: string
        data:
          $ref: '#/components/schemas/Siniestro'
      required: [success, message, data]
    ApiResponsePageSiniestroResumen:
      type: object
      properties:
        success:
          type: boolean
        message:
          type: string
        data:
          $ref: '#/components/schemas/PageSiniestroResumen'
      required: [success, message, data]
    ApiResponseListaSiniestroEstado:
      type: object
      properties:
        success:
          type: boolean
        message:
          type: string
        data:
          type: array
          items:
            $ref: '#/components/schemas/SiniestroEstado'
      required: [success, message, data]
    ApiResponseError:
      type: object
      description: Respuesta de error con código estable.
      properties:
        success:
          type: boolean
        message:
          type: string
        data:
          type: object
          properties:
            code:
              type: string
          required: [code]
      required: [success, message, data]
  responses:
    NoAutenticado:
      description: Falta el token o no es válido.
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiResponseError'
    SinPermiso:
      description: El actor no está autorizado para esta operación.
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiResponseError'
    NoEncontrado:
      description: El recurso solicitado no existe.
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiResponseError'
    ValidacionFallida:
      description: Los datos enviados no cumplen las validaciones.
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiResponseError'
"""


def _recursos() -> list[Resource]:
    """Dos recursos CRUD y un catálogo de solo lectura con su motivo."""
    return [
        Resource(
            id="RES-001",
            name="siniestros",
            singular="siniestro",
            display_name="Siniestros",
            description="Siniestros registrados sobre las guías de envío.",
            table_ref="TBL-002",
            entity_ref="ENT-001",
            component_ref="CMP-001",
            base_path="/siniestros",
            exposure=ResourceExposure.CRUD,
            source_refs=["ENT-001", "TBL-002", "CRUD-001"],
            confidence=0.9,
            origin=Origin.DERIVED,
        ),
        Resource(
            id="RES-002",
            name="guias",
            singular="guia",
            display_name="Guías",
            description="Documento de envío asociado al siniestro.",
            table_ref="TBL-001",
            entity_ref="ENT-002",
            component_ref="CMP-002",
            base_path="/guias",
            exposure=ResourceExposure.CRUD,
            source_refs=["ENT-002", "TBL-001"],
            confidence=0.85,
            origin=Origin.DERIVED,
        ),
        Resource(
            id="RES-003",
            name="siniestro-estados",
            singular="siniestro-estado",
            display_name="Estados de siniestro",
            description="Catálogo de estados por los que pasa un siniestro.",
            table_ref="TBL-003",
            entity_ref=None,  # es un catálogo derivado, no una entidad del EF
            component_ref="CMP-001",
            base_path="/siniestro-estados",
            exposure=ResourceExposure.READ_ONLY,
            exposure_reason=(
                "Catálogo de configuración: se consulta desde la aplicación y se "
                "mantiene por script de datos, no por API pública."
            ),
            source_refs=["TBL-003"],
            confidence=0.8,
            origin=Origin.DERIVED,
        ),
    ]


def _esquemas() -> list[ApiSchema]:
    """Esquemas de siniestros: creación, detalle y resumen de listado."""
    guia_id = SchemaField(
        id="SF-002",
        name="guia_id",
        logical_type=LogicalType.BIGINT,
        required=True,
        nullable=False,
        column_ref="COL-0004",
        table_ref="TBL-002",
        description="Guía sobre la que se registra el siniestro.",
        source_refs=["REL-001", "BR-001"],
        confidence=0.9,
        origin=Origin.DERIVED,
    )
    fecha = SchemaField(
        id="SF-003",
        name="fecha_siniestro",
        logical_type=LogicalType.DATE,
        format="date",
        required=True,
        nullable=False,
        example="2026-03-14",
        column_ref="COL-0005",
        table_ref="TBL-002",
        description="Fecha en que ocurrió el siniestro.",
        source_refs=["FLD-002", "VAL-001"],
        confidence=0.9,
        origin=Origin.DERIVED,
    )
    monto = SchemaField(
        id="SF-004",
        name="monto",
        logical_type=LogicalType.DECIMAL,
        format="decimal",
        required=False,
        nullable=True,
        example="1500.00",
        column_ref="COL-0006",
        table_ref="TBL-002",
        description="Importe estimado de la pérdida. Viaja como cadena.",
        source_refs=["BR-002"],
        confidence=0.8,
        origin=Origin.DERIVED,
    )
    estado = SchemaField(
        id="SF-005",
        name="estado_id",
        logical_type=LogicalType.BIGINT,
        required=True,
        nullable=False,
        column_ref="COL-0007",
        table_ref="TBL-002",
        description="Estado actual del siniestro (catálogo).",
        source_refs=["TBL-003"],
        confidence=0.85,
        origin=Origin.DERIVED,
    )
    identificador = SchemaField(
        id="SF-001",
        name="siniestro_id",
        logical_type=LogicalType.BIGINT,
        required=True,
        nullable=False,
        read_only=True,
        column_ref="COL-0003",
        table_ref="TBL-002",
        description="Identificador del siniestro. Lo genera el motor.",
        source_refs=["ENT-001"],
        confidence=0.95,
        origin=Origin.DERIVED,
    )
    return [
        ApiSchema(
            id="SCH-001",
            name="SiniestroCreate",
            kind=SchemaKind.CREATE,
            resource_ref="RES-001",
            description="Datos necesarios para registrar un siniestro.",
            # La PK no entra: la genera el motor, no la envía el cliente.
            fields=[guia_id, fecha, monto, estado],
            source_refs=["TBL-002"],
            confidence=0.9,
            origin=Origin.DERIVED,
        ),
        ApiSchema(
            id="SCH-002",
            name="Siniestro",
            kind=SchemaKind.READ,
            resource_ref="RES-001",
            description="Siniestro registrado sobre una guía.",
            fields=[identificador, guia_id, fecha, monto, estado],
            source_refs=["TBL-002"],
            confidence=0.9,
            origin=Origin.DERIVED,
        ),
        ApiSchema(
            id="SCH-003",
            name="SiniestroResumen",
            kind=SchemaKind.LIST_ITEM,
            resource_ref="RES-001",
            description="Vista reducida para listados.",
            fields=[identificador, fecha, estado],
            source_refs=["TBL-002"],
            confidence=0.85,
            origin=Origin.DERIVED,
        ),
    ]


def _endpoints() -> list[Endpoint]:
    """Cuatro operaciones: una declarada por el EF y tres derivadas del modelo."""
    no_autenticado = StatusCode(
        code=401, description="Falta el token o no es válido.", error_ref="ERR-401"
    )
    sin_permiso = StatusCode(
        code=403,
        description="El actor no está autorizado para esta operación.",
        error_ref="ERR-403",
    )
    return [
        Endpoint(
            id="EP-001",
            resource_ref="RES-001",
            method=HttpMethod.POST,
            path="/api/v1/siniestros",
            operation_id="crearSiniestro",
            kind=EndpointKind.CREATE,
            purpose="Registra un nuevo siniestro.",
            request_schema_ref="SCH-001",
            response_schema_ref="SCH-002",
            response_kind=ResponseKind.ITEM,
            status_codes=[
                StatusCode(
                    code=201, description="Siniestro registrado.", schema_ref="SCH-002"
                ),
                no_autenticado,
                sin_permiso,
                StatusCode(
                    code=422,
                    description="Los datos enviados no cumplen las validaciones.",
                    error_ref="ERR-422",
                ),
            ],
            auth_rule_refs=["AUTH-001"],
            rule_refs=["BR-001", "VAL-001"],
            # El EF ya declaraba este endpoint: por eso nace `stated`.
            ef_api_ref="API-001",
            source_refs=["API-001", "CRUD-001", "TBL-002"],
            confidence=0.9,
            origin=Origin.STATED,
        ),
        Endpoint(
            id="EP-002",
            resource_ref="RES-001",
            method=HttpMethod.GET,
            path="/api/v1/siniestros",
            operation_id="listarSiniestros",
            kind=EndpointKind.LIST,
            purpose="Lista los siniestros registrados.",
            parameters=[
                Parameter(
                    id="PRM-001",
                    name="estado_id",
                    location=ParameterLocation.QUERY,
                    logical_type=LogicalType.BIGINT,
                    description="Filtra por estado del siniestro.",
                    column_ref="COL-0007",
                )
            ],
            response_schema_ref="SCH-003",
            response_kind=ResponseKind.PAGE,
            status_codes=[
                StatusCode(
                    code=200,
                    description="Listado paginado de siniestros.",
                    schema_ref="SCH-003",
                ),
                no_autenticado,
                sin_permiso,
            ],
            # Solo columnas indexadas: `estado_id` participa del índice
            # ix_siniestros_estado_fecha del modelo de datos.
            filters=["estado_id"],
            sortable=["fecha_siniestro"],
            paginated=True,
            idempotent=True,
            auth_rule_refs=["AUTH-002"],
            source_refs=["CRUD-001", "TBL-002", "IDX-001"],
            confidence=0.85,
            origin=Origin.DERIVED,
        ),
        Endpoint(
            id="EP-003",
            resource_ref="RES-001",
            method=HttpMethod.GET,
            path="/api/v1/siniestros/{siniestro_id}",
            operation_id="obtenerSiniestro",
            kind=EndpointKind.READ_ITEM,
            purpose="Obtiene el detalle de un siniestro.",
            parameters=[
                Parameter(
                    id="PRM-002",
                    name="siniestro_id",
                    location=ParameterLocation.PATH,
                    logical_type=LogicalType.BIGINT,
                    required=True,
                    description="Identificador del siniestro.",
                    column_ref="COL-0003",
                )
            ],
            response_schema_ref="SCH-002",
            response_kind=ResponseKind.ITEM,
            status_codes=[
                StatusCode(
                    code=200, description="Detalle del siniestro.", schema_ref="SCH-002"
                ),
                no_autenticado,
                sin_permiso,
                StatusCode(
                    code=404,
                    description="El recurso solicitado no existe.",
                    error_ref="ERR-404",
                ),
            ],
            idempotent=True,
            auth_rule_refs=["AUTH-003"],
            source_refs=["CRUD-001", "TBL-002"],
            confidence=0.85,
            origin=Origin.DERIVED,
        ),
        Endpoint(
            id="EP-004",
            resource_ref="RES-003",
            method=HttpMethod.GET,
            path="/api/v1/siniestro-estados",
            operation_id="listarSiniestroEstados",
            kind=EndpointKind.LIST,
            purpose="Lista los estados de siniestro disponibles.",
            response_kind=ResponseKind.PAGE,
            status_codes=[
                StatusCode(code=200, description="Catálogo de estados."),
                no_autenticado,
            ],
            idempotent=True,
            auth_rule_refs=["AUTH-004"],
            source_refs=["TBL-003"],
            confidence=0.8,
            origin=Origin.DERIVED,
        ),
    ]


def _autorizacion() -> list[AuthorizationRule]:
    """La matriz, incluido el caso ambiguo que bloquea el semáforo."""
    return [
        AuthorizationRule(
            id="AUTH-001",
            endpoint_ref="EP-001",
            actor_ref="ACT-001",
            actor_name="Operador de siniestros",
            effect=AuthEffect.ALLOW,
            scope=AuthScope.ALL,
            basis=AuthBasis.CRUD_MATRIX,
            source_refs=["CRUD-001"],
            confidence=0.9,
            origin=Origin.DERIVED,
        ),
        AuthorizationRule(
            id="AUTH-002",
            endpoint_ref="EP-002",
            actor_ref="ACT-002",
            actor_name="Jefe de operaciones",
            effect=AuthEffect.ALLOW,
            scope=AuthScope.OWN_TEAM,
            scope_expression="siniestro.equipo_id = usuario.equipo_id",
            # Ninguna columna del modelo dice de qué equipo es cada siniestro: el
            # alcance no es implementable tal como está, así que se marca ambiguo
            # en vez de conceder un permiso más ancho del que nadie autorizó.
            scope_column_refs=[],
            basis=AuthBasis.BUSINESS_RULE,
            ambiguous=True,
            note=(
                "BR-003 limita la visibilidad por equipo, pero el modelo de datos "
                "no tiene columna de equipo en siniestros."
            ),
            source_refs=["BR-003"],
            confidence=0.55,
            origin=Origin.DERIVED,
        ),
        AuthorizationRule(
            id="AUTH-003",
            endpoint_ref="EP-003",
            actor_ref="ACT-001",
            actor_name="Operador de siniestros",
            effect=AuthEffect.ALLOW,
            scope=AuthScope.ALL,
            basis=AuthBasis.CRUD_MATRIX,
            source_refs=["CRUD-001"],
            confidence=0.9,
            origin=Origin.DERIVED,
        ),
        AuthorizationRule(
            id="AUTH-004",
            endpoint_ref="EP-004",
            actor_ref="ACT-001",
            actor_name="Operador de siniestros",
            effect=AuthEffect.ALLOW,
            scope=AuthScope.ALL,
            basis=AuthBasis.INFERRED,
            note="Catálogo de apoyo: lo necesita cualquier actor que registre.",
            source_refs=["TBL-003"],
            confidence=0.7,
            origin=Origin.DERIVED,
        ),
    ]


def _errores() -> list[ErrorEntry]:
    """Subconjunto del catálogo estándar que usan estos endpoints."""
    return [
        ErrorEntry(
            id="ERR-401",
            status=401,
            code="no_autenticado",
            message="Debes iniciar sesión para realizar esta operación.",
            when="Falta el token o no es válido.",
        ),
        ErrorEntry(
            id="ERR-403",
            status=403,
            code="sin_permiso",
            message="No tienes permiso para realizar esta operación.",
            when="El actor no está autorizado, o el recurso queda fuera de su alcance.",
        ),
        ErrorEntry(
            id="ERR-404",
            status=404,
            code="no_encontrado",
            message="El recurso solicitado no existe.",
            when="Identificador inexistente, o fuera del alcance del actor.",
        ),
        ErrorEntry(
            id="ERR-422",
            status=422,
            code="validacion_fallida",
            message="Los datos enviados no cumplen las validaciones.",
            when="Falla una validación de campo o una regla declarativa.",
            source_refs=["CK-001"],
        ),
    ]


def _reglas() -> list[ApiRuleMapping]:
    """Toda regla del EF con su destino, y el veredicto del BD al lado."""
    return [
        ApiRuleMapping(
            id="ARM-001",
            rule_ref="BR-001",
            enforcement=ApiRuleEnforcement.SCHEMA,
            endpoint_refs=["EP-001"],
            schema_field_refs=["SF-002"],
            bd_enforcement="declarative",
            note=(
                "«Un siniestro sin guía asociada no puede registrarse» se cumple "
                "con guia_id obligatorio en el cuerpo de creación."
            ),
            confidence=0.9,
            origin=Origin.DERIVED,
        ),
        ApiRuleMapping(
            id="ARM-002",
            rule_ref="VAL-001",
            # El Agente BD la dejó en `application`: no era expresable como CHECK
            # portable. Aquí encuentra endpoint. El círculo queda cerrado.
            enforcement=ApiRuleEnforcement.ENDPOINT,
            endpoint_refs=["EP-001"],
            bd_enforcement="application",
            note=(
                "«La fecha del siniestro no puede ser futura» la valida la "
                "operación de registro."
            ),
            confidence=0.85,
            origin=Origin.DERIVED,
        ),
        ApiRuleMapping(
            id="ARM-003",
            rule_ref="BR-003",
            enforcement=ApiRuleEnforcement.AUTHORIZATION,
            auth_rule_refs=["AUTH-002"],
            bd_enforcement="application",
            note="Pendiente de resolver el alcance por equipo (Q-001).",
            confidence=0.5,
            origin=Origin.DERIVED,
        ),
        ApiRuleMapping(
            id="ARM-004",
            rule_ref="BR-002",
            enforcement=ApiRuleEnforcement.DATABASE,
            bd_enforcement="declarative",
            note=(
                "El importe no negativo ya lo garantiza el CHECK del modelo; la "
                "API no lo duplica."
            ),
            confidence=0.8,
            origin=Origin.DERIVED,
        ),
    ]


def example_artifact() -> ApiArtifact:
    """Construye el ApiArtifact de ejemplo (fixture de los bloques siguientes)."""
    return ApiArtifact(
        source=SourceRef(
            bd_job_id="01JBD00000000000000000000",
            bd_artifact_hash="b" * 64,
            architecture_job_id="01JAR00000000000000000000",
            architecture_artifact_hash="a" * 64,
            scrum_job_id="01JSC00000000000000000000",
            scrum_artifact_hash="s" * 64,
            ef_job_id="01JEF00000000000000000000",
            ef_artifact_hash="e" * 64,
            ready_snapshot=True,
        ),
        target=Target(
            api_style=ApiStyle.REST,
            base_path="/api/v1",
            auth=AuthConfig(
                scheme=AuthScheme.BEARER_JWT,
                provider="Keycloak",
                source_ref="STK-003",
                decided=True,
            ),
            conventions=Conventions(),
            conventions_source="api_conventions.yaml@v0",
        ),
        resources=_recursos(),
        schemas=_esquemas(),
        endpoints=_endpoints(),
        authorization_matrix=_autorizacion(),
        error_catalog=_errores(),
        rule_mappings=_reglas(),
        openapi=OpenApiDocument(
            spec_version=OPENAPI_VERSION,
            content=_OPENAPI_YAML,
            operations_total=4,
            byte_size=len(_OPENAPI_YAML.encode("utf-8")),
            checksum="sha256:" + "0" * 64,
        ),
        validation=SpecValidation(
            spec_valid=True,
            validator="estructural+openapi-spec-validator",
            validator_version="0.8.5",
            runtime_checked=False,
            checks={
                "refs_resolve": True,
                "no_path_collisions": True,
                "all_endpoints_authorized": True,
                "http_semantics": True,
                "spec_schema": True,
                "round_trip": True,
            },
        ),
        analysis=ApiAnalysis(
            risks=[
                Risk(
                    id="RISK-001",
                    description=(
                        "El alcance por equipo de BR-003 no es implementable: "
                        "ninguna columna identifica al equipo responsable, así que "
                        "el listado devolvería todos los siniestros a un jefe."
                    ),
                    severity=RiskSeverity.ALTA,
                    mitigation=(
                        "Resolver Q-001 y, si procede, pedir la columna al Agente "
                        "BD antes de construir."
                    ),
                    source_ref="AUTH-002",
                    confidence=0.7,
                    origin=Origin.DERIVED,
                )
            ],
            observations=[
                Observation(
                    id="OBS-001",
                    description=(
                        "El catálogo de estados se expone solo en lectura; su "
                        "mantenimiento queda fuera de la API."
                    ),
                    reason="Convención de exposición por naturaleza de tabla (API12).",
                )
            ],
            coverage=Coverage(
                tables_total=3,
                tables_exposed=3,
                unexposed_table_refs=[],
                ef_apis_total=1,
                ef_apis_covered=1,
                uncovered_api_refs=[],
                crud_cells_total=3,
                crud_cells_covered=3,
                uncovered_crud_refs=[],
                rules_total=4,
                rules_enforced=4,
                unenforced_rule_refs=[],
                actors_total=2,
                actors_with_access=2,
                actors_without_access=[],
            ),
        ),
        questions_for_tech_lead=[
            TechLeadQuestion(
                id="Q-001",
                question=(
                    "¿Un jefe de operaciones ve todos los siniestros o solo los de "
                    "su equipo?"
                ),
                reason=(
                    "BR-003 limita la visibilidad por equipo, pero ninguna columna "
                    "de siniestros identifica al equipo responsable. Afecta a "
                    "EP-002. Sin respuesta, el listado se abriría a todos los "
                    "registros."
                ),
                audience=Audience.TECNICO,
                blocking=True,
                linked_to_ref="AUTH-002",
                confidence=0.6,
                origin=Origin.DERIVED,
            )
        ],
        metrics=ApiMetrics(
            tokens=TokenMetrics(input=0, output=0, total=0),
            resources_total=3,
            endpoints_total=4,
            schemas_total=3,
            auth_rules_total=4,
            coverage=1.0,
            spec_valid=True,
            endpoints_unauthorized=0,
        ),
    )
