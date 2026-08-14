"""Contrato de datos QaArtifact v1.0.0 (Pydantic 2).

Artefacto que produce el Agente QA a partir del ``ScrumArtifact`` listo, del
``EFArtifact`` resuelto transitivamente y —**si se indicó**— del ``ApiArtifact``:
casos de prueba, matriz de trazabilidad, datasets reutilizables y plan de ejecución.

Claves en inglés, valores/descripciones en español. Todo ítem trazable lleva ``id``
y, donde aplique, ``source_refs``, ``confidence`` y ``origin``. Reusa
``TokenMetrics``/``SkippedItem``/``Observation`` del EF, ``RiskSeverity`` de
Arquitectura, ``MoscowPriority`` del Scrum y ``AuthScope`` del Agente API — el
vocabulario de alcances de autorización es **uno solo** en todo el sistema.

**Qué valida el contrato y qué no.** Igual que en el Agente API, el contrato solo
impide lo que sería *invención* u *omisión muda*, no lo que sería un *defecto
reportable*:

- Impide (lanza ``ValidationError``): un caso sin criterio de origen, un caso de
  borde sin el límite que lo justifica, un límite extraído del EF sin cita
  verbatim, un caso de autorización sin la regla de la que se deriva, un caso sin
  pasos, un criterio declarado "no verificable" sin la pregunta que lo respalda, y
  casos de autorización cuando no hubo ApiArtifact. Nada de eso puede existir en un
  artefacto correcto **ni en uno defectuoso**: sería cobertura falsa.
- No impide: cobertura incompleta, criterios huérfanos, casos duplicados, un plan
  sin suites. Eso lo detecta CRITIQUE y lo refleja el semáforo. Un contrato que se
  negara a representar un plan de pruebas incompleto impediría al agente
  **reportar** que está incompleto, que es justo su trabajo.

La asimetría de fondo: un caso de prueba ausente se ve en la cobertura; un caso de
prueba **falso** pasa la ejecución y certifica una mentira.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai.agents.api.schemas.enums import AuthScope
from ai.agents.arquitectura.schemas.enums import RiskSeverity
from ai.agents.ef.schemas.artifact import Observation, SkippedItem, TokenMetrics
from ai.agents.ef.schemas.enums import Audience, Origin, QuestionStatus
from ai.agents.scrum.schemas.enums import MoscowPriority

from .enums import (
    AnchorSource,
    AutomationHint,
    BoundaryKind,
    CoverageStatus,
    DataKind,
    TestCaseType,
    TestPriority,
)

SCHEMA_VERSION = "1.0.0"

#: Minutos de ejecución **manual** por tipo de caso. Viven aquí y no en la cabeza
#: del modelo (QA-D8): el esfuerzo de un plan tiene que ser reproducible, y una
#: estimación pedida al LLM cambiaría entre dos corridas del mismo plan.
DEFAULT_MINUTES_BY_TYPE: dict[str, int] = {
    TestCaseType.FUNCTIONAL.value: 10,
    TestCaseType.NEGATIVE.value: 6,
    TestCaseType.BOUNDARY.value: 5,
    TestCaseType.AUTHORIZATION.value: 8,
}

#: Multiplicador por prioridad: un caso crítico se ejecuta con más cuidado (y más
#: evidencia adjunta) que uno de prioridad baja.
DEFAULT_PRIORITY_FACTOR: dict[str, float] = {
    TestPriority.CRITICA.value: 1.5,
    TestPriority.ALTA.value: 1.2,
    TestPriority.MEDIA.value: 1.0,
    TestPriority.BAJA.value: 0.8,
}

#: Mapeo MoSCoW → prioridad del caso (QA-D4). El suelo de los casos de
#: autorización se aplica en el nodo, no aquí: el contrato no decide política.
MOSCOW_TO_PRIORITY: dict[str, str] = {
    MoscowPriority.MUST.value: TestPriority.CRITICA.value,
    MoscowPriority.SHOULD.value: TestPriority.ALTA.value,
    MoscowPriority.COULD.value: TestPriority.MEDIA.value,
    MoscowPriority.WONT.value: TestPriority.BAJA.value,
}


class _Strict(BaseModel):
    """Base estricta: prohíbe claves desconocidas (structured output cerrado)."""

    model_config = ConfigDict(extra="forbid")


class TracedItem(_Strict):
    """Ítem trazable con provenance y confianza.

    Atributos:
        id: Identificador estable del ítem (renumerable de forma determinística).
        confidence: Confianza [0, 1] donde aplique.
        origin: ``stated`` cuando el contenido está dicho en un artefacto de
            origen (el criterio Gherkin que se convierte en caso funcional es
            ``stated``); ``derived`` cuando el agente lo construyó (un caso de
            borde, un dato de prueba concreto).
    """

    id: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    origin: Optional[Origin] = None


# --- Origen y configuración efectiva ------------------------------------------


class SourceRef(_Strict):
    """Enlace a los jobs de origen, con hashes para poder reproducir la corrida.

    El Scrum es la entrada directa (``input_job_id``) y el EF se resuelve hacia
    atrás. El ApiArtifact es la **excepción estructural** del agente: no está en la
    cadena hacia atrás sino hacia delante, así que no se descubre — se indica
    (QA-D1). Cuando no se indica, ``api_available=False`` y el motivo queda escrito.
    """

    scrum_job_id: str
    scrum_artifact_hash: str
    scrum_schema_version: str = "1.0.0"
    ef_job_id: str
    ef_artifact_hash: str
    ef_schema_version: str = "1.2.0"
    #: Contrato de API usado para los casos de autorización, si se indicó uno.
    api_job_id: Optional[str] = None
    api_artifact_hash: Optional[str] = None
    api_schema_version: Optional[str] = None
    #: Si es ``False`` no hay casos de autorización, y el motivo es obligatorio.
    api_available: bool = False
    api_absent_reason: Optional[str] = None
    #: Gate del Scrum verificado al generar (``ready_for_next_stage``).
    ready_snapshot: bool = True

    @model_validator(mode="after")
    def _la_ausencia_del_api_se_explica(self) -> "SourceRef":
        """Sin ApiArtifact hay que decir por qué; con él, quién es.

        Sin esta regla, "no se diseñaron casos de autorización" y "no se pudo
        diseñarlos" serían indistinguibles al leer el artefacto, y quien lo revise
        no sabría si falta cobertura o si nunca hubo contrato que probar.
        """
        if self.api_available:
            if not (self.api_job_id or "").strip():
                raise ValueError(
                    "api_available=True exige api_job_id: un contrato de API que "
                    "se usó tiene que quedar identificado."
                )
            if not (self.api_artifact_hash or "").strip():
                raise ValueError(
                    f"El contrato de API {self.api_job_id} se usó sin registrar su "
                    "hash: la corrida no sería reproducible."
                )
        elif not (self.api_absent_reason or "").strip():
            raise ValueError(
                "Sin ApiArtifact hay que escribir api_absent_reason: la ausencia "
                "de los casos de autorización se declara, no se disimula."
            )
        return self


class Target(_Strict):
    """Umbrales y política **efectivos** de esta corrida.

    Se persisten para que el cálculo determinista quede auditable: leyendo el
    artefacto se puede recomputar la cobertura y el esfuerzo y obtener los mismos
    números, sin adivinar con qué parámetros se generó.
    """

    #: Cobertura exigida de criterios de historias ``must``/``should`` (QA-D5).
    coverage_threshold: float = Field(default=1.0, ge=0.0, le=1.0)
    #: Techo de casos por criterio. Si se poda, queda ``Observation``: un tope
    #: silencioso se leería como cobertura completa.
    max_cases_per_criterion: int = Field(default=6, ge=1)
    minutes_by_type: dict[str, int] = Field(
        default_factory=lambda: dict(DEFAULT_MINUTES_BY_TYPE)
    )
    priority_factor: dict[str, float] = Field(
        default_factory=lambda: dict(DEFAULT_PRIORITY_FACTOR)
    )
    #: Sprint de capacidad de QA (minutos disponibles), si el equipo lo fijó.
    manual_capacity_minutes: Optional[int] = Field(default=None, ge=1)


# --- Casos de prueba ----------------------------------------------------------


class TestStep(_Strict):
    """Paso numerado de un caso de prueba."""

    number: int = Field(ge=1)
    action: str
    #: Resultado intermedio observable, cuando el paso lo tiene. El resultado
    #: final del caso vive en ``TestCase.expected_result``.
    expected: Optional[str] = None


class TestDatum(_Strict):
    """Dato de prueba concreto usado por un caso.

    ``value`` es una cadena a propósito: un caso de borde necesita expresar ``""``,
    ``null``, ``"2026-02-30"`` o un decimal con exceso de escala, y tipar esto
    perdería justo los valores que interesan probar.
    """

    name: str
    value: str
    kind: DataKind = DataKind.VALID
    #: Campo del EF al que corresponde (``FLD-...``), si se pudo determinar.
    field_ref: Optional[str] = None
    entity_ref: Optional[str] = None
    note: Optional[str] = None


class BoundaryAnchor(_Strict):
    """El límite que justifica un caso de borde, con su evidencia (QA-D2).

    Es el cortafuegos del tipo de caso más peligroso del agente. Un borde inventado
    ("el saldo máximo es 5000" cuando nadie lo dijo) produce un test que **pasa** y
    certifica un límite que no existe. Por eso un límite extraído del texto del EF
    exige **cita verbatim**: si el revisor no puede encontrar la frase, el caso no
    debería existir.
    """

    #: Regla o validación de origen (``VAL-...`` / ``BR-...``). Obligatorio cuando
    #: el límite se extrajo del texto del EF; un límite estructural del contrato de
    #: API (``required``, ``max_length``, ``enum``) no nace de ninguna regla y por
    #: eso puede no tenerlo: cita el campo en su lugar.
    rule_ref: Optional[str] = None
    kind: BoundaryKind
    #: Operador tal como se probará (``>``, ``>=``, ``<=``, ``!=``, ``in``…).
    operator: Optional[str] = None
    #: Valor del límite. Cadena por la misma razón que ``TestDatum.value``.
    value: Optional[str] = None
    anchor_source: AnchorSource = AnchorSource.EF_TEXT
    #: Cita **verbatim** del EF. Obligatoria si ``anchor_source=ef_text``.
    evidence: Optional[str] = None
    #: Campo estructurado del ApiArtifact que fijó el límite, cuando prevaleció.
    api_field_ref: Optional[str] = None

    @model_validator(mode="after")
    def _todo_limite_esta_anclado(self) -> "BoundaryAnchor":
        """O hay regla del EF citada verbatim, o hay campo estructurado del API."""
        if self.anchor_source is AnchorSource.EF_TEXT:
            if not (self.rule_ref or "").strip():
                raise ValueError(
                    "Un límite extraído del EF debe citar la regla o validación "
                    "(rule_ref) de la que sale."
                )
            if not (self.evidence or "").strip():
                raise ValueError(
                    f"El límite de {self.rule_ref} se extrajo del texto del EF sin "
                    "cita verbatim: sin la frase, el límite es una invención."
                )
        elif not (self.api_field_ref or "").strip():
            raise ValueError(
                "El límite dice venir del contrato de API pero no cita el campo "
                "(api_field_ref) que lo fija."
            )
        return self


class AuthCase(_Strict):
    """Contexto de un caso de autorización, derivado de la matriz del API (QA-D7).

    No lo redacta el LLM: sale por plantilla de ``AuthorizationRule``, donde ya
    están ``effect``, ``scope`` y las columnas que materializan el alcance. La
    superficie de autorización no se diseña a ojo, y una regla marcada
    ``ambiguous`` no produce caso sino pregunta bloqueante.
    """

    #: Regla de la matriz de autorización del ApiArtifact (``AUTH-...``).
    auth_rule_ref: str
    endpoint_ref: str
    #: Actor que ejecuta el intento (``ACT-...`` del EF), si la regla lo nombra.
    actor_ref: Optional[str] = None
    scope: AuthScope = AuthScope.NONE
    #: Código HTTP esperado (403 al denegar, 200 al permitir, 404 si se oculta).
    expected_status: int = Field(default=403, ge=100, le=599)
    #: ``True`` cuando el caso comprueba un **rechazo** (lo habitual aquí).
    negative: bool = True
    #: Columna que separa lo propio de lo ajeno (``COL-...``), para armar el dato.
    scope_column_refs: list[str] = Field(default_factory=list)


class TestCase(TracedItem):
    """Caso de prueba derivado de un criterio de aceptación."""

    title: str
    #: Historia de origen (``US-...``). Obligatorio.
    story_ref: str
    #: Criterio de aceptación de origen (``AC-...``). **Obligatorio**: es el
    #: cortafuegos anti-invención del agente. ``CRITERION_MAP`` fija en Python qué
    #: pares (historia, criterio) existen, y un caso que cite uno inexistente se
    #: descarta con ``Observation`` antes de llegar aquí.
    criterion_ref: str
    epic_ref: Optional[str] = None
    type: TestCaseType = TestCaseType.FUNCTIONAL
    preconditions: list[str] = Field(default_factory=list)
    steps: list[TestStep] = Field(min_length=1)
    test_data: list[TestDatum] = Field(default_factory=list)
    expected_result: str
    priority: TestPriority = TestPriority.MEDIA
    automation_hint: AutomationHint = AutomationHint.MANUAL
    estimated_minutes: int = Field(default=10, ge=1)
    #: Obligatorio si ``type=boundary``.
    boundary: Optional[BoundaryAnchor] = None
    #: Obligatorio si ``type=authorization``.
    auth_context: Optional[AuthCase] = None
    tags: list[str] = Field(default_factory=list)
    #: Refs del EF que el caso ejercita (``REQ-F-``, ``BR-``, ``VAL-``, ``PRO-``).
    source_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cada_tipo_trae_lo_que_lo_sostiene(self) -> "TestCase":
        """Un borde sin límite y una autorización sin regla son cobertura falsa."""
        if self.type is TestCaseType.BOUNDARY and self.boundary is None:
            raise ValueError(
                f"El caso de borde {self.id} no declara el límite que prueba: sin "
                "boundary no se puede saber qué frontera se está verificando."
            )
        if self.type is TestCaseType.AUTHORIZATION and self.auth_context is None:
            raise ValueError(
                f"El caso de autorización {self.id} no cita la regla de la matriz "
                "de la que se deriva: la autorización no se diseña a ojo."
            )
        return self


# --- Matriz de trazabilidad (determinista) ------------------------------------


class TraceRow(_Strict):
    """Fila requisito ↔ historia ↔ criterio ↔ casos.

    La calcula ``TRACE_MATRIX`` en Python desde ``CRITERION_MAP`` × ``test_cases``:
    no la escribe el LLM y por eso no puede maquillar la cobertura.
    """

    requirement_refs: list[str] = Field(default_factory=list)
    story_ref: str
    criterion_ref: str
    #: MoSCoW de la historia: decide si un hueco es advertencia o bloqueo (QA-D5).
    story_priority: Optional[MoscowPriority] = None
    test_case_ids: list[str] = Field(default_factory=list)
    status: CoverageStatus = CoverageStatus.UNCOVERED
    #: Obligatorio si ``status=not_testable``: la pregunta que lo respalda.
    question_ref: Optional[str] = None

    @model_validator(mode="after")
    def _coherencia_de_la_fila(self) -> "TraceRow":
        """Cubierto exige casos; no verificable exige pregunta."""
        if self.status is CoverageStatus.COVERED and not self.test_case_ids:
            raise ValueError(
                f"El criterio {self.criterion_ref} se declara cubierto sin ningún "
                "caso: eso es exactamente la cobertura falsa que el agente evita."
            )
        if (
            self.status is CoverageStatus.NOT_TESTABLE
            and not (self.question_ref or "").strip()
        ):
            raise ValueError(
                f"El criterio {self.criterion_ref} se declara no verificable sin "
                "pregunta al QA lead: sería una excusa sin destinatario."
            )
        return self


class Coverage(_Strict):
    """Cobertura del plan. Nunca oculta huecos: enumera los refs descubiertos."""

    criteria_total: int = 0
    criteria_covered: int = 0
    criteria_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    uncovered_criterion_refs: list[str] = Field(default_factory=list)
    not_testable_criterion_refs: list[str] = Field(default_factory=list)
    #: Cobertura restringida a historias ``must``/``should``: la que entra en el
    #: semáforo. Un criterio de una historia ``wont`` sin caso es advertencia.
    blocking_criteria_total: int = 0
    blocking_criteria_covered: int = 0
    stories_total: int = 0
    stories_covered: int = 0
    uncovered_story_refs: list[str] = Field(default_factory=list)
    requirements_total: int = 0
    requirements_covered: int = 0
    #: RF sin ningún caso: **hallazgo** (``Risk``), no advertencia.
    uncovered_requirement_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cubierto_no_supera_al_total(self) -> "Coverage":
        """Un ratio imposible sería una mentira sobre el estado del plan."""
        for cubierto, total, nombre in (
            (self.criteria_covered, self.criteria_total, "criterios"),
            (
                self.blocking_criteria_covered,
                self.blocking_criteria_total,
                "must/should",
            ),
            (self.stories_covered, self.stories_total, "historias"),
            (self.requirements_covered, self.requirements_total, "requisitos"),
        ):
            if cubierto > total:
                raise ValueError(
                    f"Cobertura de {nombre} imposible: {cubierto} cubiertos de "
                    f"{total} totales."
                )
        return self


class TraceMatrix(_Strict):
    """Matriz completa + su resumen de cobertura."""

    rows: list[TraceRow] = Field(default_factory=list)
    coverage: Coverage = Field(default_factory=Coverage)
    #: Criterios sin ningún caso (advertencia). Espejo navegable de la cobertura.
    orphan_criterion_refs: list[str] = Field(default_factory=list)


# --- Datasets -----------------------------------------------------------------


class DatasetRow(_Strict):
    """Fila de datos de prueba reutilizable."""

    id: str
    kind: DataKind = DataKind.VALID
    #: Valores por nombre de campo. Cadenas por la razón de ``TestDatum.value``.
    values: dict[str, str] = Field(default_factory=dict)
    #: Qué debe pasar con esta fila ("se acepta", "se rechaza por VAL-003").
    expectation: str
    field_refs: list[str] = Field(default_factory=list)
    #: Límite que la fila ejercita, si es de tipo ``boundary``.
    anchor: Optional[BoundaryAnchor] = None

    @model_validator(mode="after")
    def _una_fila_sin_valores_no_es_un_dato(self) -> "DatasetRow":
        if not self.values:
            raise ValueError(
                f"La fila {self.id} del dataset no tiene ningún valor: un dataset "
                "vacío aparentaría datos de prueba que nadie puede usar."
            )
        return self


class Dataset(TracedItem):
    """Datos de prueba de una entidad: válidos, inválidos y de frontera."""

    name: str
    #: Entidad del EF (``ENT-...``).
    entity_ref: Optional[str] = None
    description: Optional[str] = None
    rows: list[DatasetRow] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


# --- Plan de ejecución (determinista) -----------------------------------------


class Suite(_Strict):
    """Suite de casos, una por épica."""

    id: str
    name: str
    epic_ref: Optional[str] = None
    test_case_ids: list[str] = Field(default_factory=list)
    estimated_minutes: int = 0
    #: Suites que deben ejecutarse antes (derivadas de ``story.dependencies``).
    depends_on_suite_ids: list[str] = Field(default_factory=list)


class ExecutionTotals(_Strict):
    """Totales del plan, todos recomputables desde ``test_cases`` y ``target``."""

    cases_total: int = 0
    manual_minutes: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_priority: dict[str, int] = Field(default_factory=dict)
    #: Sprints de QA necesarios si el equipo declaró capacidad.
    estimated_sessions: Optional[int] = Field(default=None, ge=1)


class ExecutionPlan(_Strict):
    """Suites, orden topológico y esfuerzo."""

    suites: list[Suite] = Field(default_factory=list)
    #: Ids de suite en orden de ejecución (topológico por dependencias).
    order: list[str] = Field(default_factory=list)
    #: Ciclos detectados entre suites. Se **reportan**, no se lanzan: el plan
    #: existe igual y CRITIQUE lo convierte en hallazgo.
    dependency_cycles: list[list[str]] = Field(default_factory=list)
    totals: ExecutionTotals = Field(default_factory=ExecutionTotals)


# --- Análisis, preguntas y métricas -------------------------------------------


class QaQuestion(TracedItem):
    """Pregunta al QA lead (criterio ambiguo o no verificable)."""

    question: str
    reason: str
    audience: Audience = Audience.TECNICO
    blocking: bool = False
    linked_to_ref: Optional[str] = None
    status: QuestionStatus = QuestionStatus.PENDIENTE


class Risk(TracedItem):
    """Riesgo del plan de pruebas (p. ej. un RF sin ningún caso)."""

    description: str
    severity: RiskSeverity = RiskSeverity.MEDIA
    mitigation: Optional[str] = None
    source_ref: Optional[str] = None


class QaAnalysis(_Strict):
    """Bloque de análisis del QaArtifact."""

    risks: list[Risk] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    coverage: Coverage = Field(default_factory=Coverage)


class QaMetrics(_Strict):
    """Métricas reales de la corrida + contadores del plan."""

    tokens: TokenMetrics = Field(default_factory=TokenMetrics)
    cost: float = 0.0  # USD
    duration: float = 0.0  # segundos
    test_cases_total: int = 0
    datasets_total: int = 0
    suites_total: int = 0
    questions_total: int = 0
    blocking_questions_total: int = 0
    manual_minutes: int = 0
    #: Espejo de ``analysis.coverage.criteria_ratio``: entra en el semáforo.
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    #: Casos podados por el techo de ``target.max_cases_per_criterion``. Nunca
    #: silenciosos: cada poda deja además su ``Observation``.
    pruned_cases: int = 0
    skipped: list[SkippedItem] = Field(default_factory=list)


# --- Artefacto raíz ------------------------------------------------------------


class QaArtifact(_Strict):
    """Artefacto completo del Agente QA (contrato v1.0.0)."""

    schema_version: str = SCHEMA_VERSION
    source: SourceRef
    target: Target = Field(default_factory=Target)
    test_cases: list[TestCase] = Field(default_factory=list)
    trace_matrix: TraceMatrix = Field(default_factory=TraceMatrix)
    datasets: list[Dataset] = Field(default_factory=list)
    execution_plan: ExecutionPlan = Field(default_factory=ExecutionPlan)
    questions_for_qa_lead: list[QaQuestion] = Field(default_factory=list)
    analysis: QaAnalysis = Field(default_factory=QaAnalysis)
    metrics: QaMetrics = Field(default_factory=QaMetrics)

    @model_validator(mode="after")
    def _sin_contrato_de_api_no_hay_casos_de_autorizacion(self) -> "QaArtifact":
        """La dependencia opcional no puede colarse por la puerta de atrás.

        Un caso de autorización sin ApiArtifact detrás no tendría matriz de la que
        derivarse: sería una suposición sobre quién puede ver qué, escrita con la
        autoridad de un caso de prueba. Es el error más caro que este agente podría
        cometer, así que el contrato lo hace imposible.
        """
        if self.source.api_available:
            return self
        intrusos = [
            tc.id for tc in self.test_cases if tc.type is TestCaseType.AUTHORIZATION
        ]
        if intrusos:
            raise ValueError(
                "Hay casos de autorización sin ApiArtifact de origen "
                f"({', '.join(intrusos)}): sin la matriz del contrato de API, "
                "quién puede ver qué sería una suposición."
            )
        return self
