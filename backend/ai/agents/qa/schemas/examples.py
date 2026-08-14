"""Ejemplo válido de QaArtifact (dominio: siniestros logísticos).

Cierra la cadena de fixtures EF → Scrum → Arquitectura → BD → API: los casos de
abajo derivan de las historias del ``ScrumArtifact`` de ejemplo (``US-001`` *must*
con ``AC-001``, ``US-002`` *should* con ``AC-002``), citan las reglas reales del
``EFArtifact`` (``BR-001`` "un siniestro sin guía asociada no puede registrarse",
``VAL-001`` "la fecha del siniestro no puede ser futura") y, para autorización, las
reglas de la matriz del ``ApiArtifact`` (``AUTH-001``, ``AUTH-002``).

Incluye a propósito los casos que el contrato debe saber representar:

1. Un caso **funcional** que nace del criterio Gherkin tal cual → ``origin=stated``.
2. Un caso **negativo** sobre la misma regla de negocio.
3. Un caso de **borde** con el límite extraído del **texto** del EF y su **cita
   verbatim** (``VAL-001``): sin la frase, el límite sería una invención.
4. Un caso de **borde** anclado en un **campo estructurado** del contrato de API
   (``SF-005`` es ``required``), que es la vía que prevalece cuando existe.
5. Un caso de **autorización** derivado de ``AUTH-001`` por plantilla, no redactado.
6. Y lo que **no** hay: ``AUTH-002`` es la regla "los jefes solo ven los siniestros
   de su equipo" y está marcada ``ambiguous`` porque ninguna columna dice de qué
   equipo es cada siniestro. Ahí el agente **no** produce el caso cruzado que
   parecería obvio: produce una **pregunta bloqueante**. Es exactamente el ejemplo
   del que nació el nodo AUTH_CASES, y la razón por la que es determinista.

Ojo con el semáforo de este ejemplo: la cobertura de criterios es del **100%** y
aun así el artefacto **no está listo**, porque queda una pregunta bloqueante. Un
plan de pruebas completo sobre una autorización que nadie pudo precisar no es un
plan listo, y el fixture existe también para fijar eso.
"""

from ai.agents.api.schemas.enums import AuthScope
from ai.agents.arquitectura.schemas.enums import RiskSeverity
from ai.agents.ef.schemas.artifact import Observation, TokenMetrics
from ai.agents.ef.schemas.enums import Audience, Origin
from ai.agents.scrum.schemas.enums import MoscowPriority

from .artifact import (
    AuthCase,
    BoundaryAnchor,
    Coverage,
    Dataset,
    DatasetRow,
    ExecutionPlan,
    ExecutionTotals,
    QaAnalysis,
    QaArtifact,
    QaMetrics,
    QaQuestion,
    Risk,
    SourceRef,
    Suite,
    Target,
    TestCase,
    TestDatum,
    TestStep,
    TraceMatrix,
    TraceRow,
)
from .enums import (
    AnchorSource,
    AutomationHint,
    BoundaryKind,
    CoverageStatus,
    DataKind,
    TestCaseType,
    TestPriority,
)


def _casos() -> list[TestCase]:
    """Los seis casos del ejemplo, uno por cada forma que el contrato admite."""
    return [
        TestCase(
            id="TC-001",
            title="Registrar un siniestro con su guía asociada",
            story_ref="US-001",
            criterion_ref="AC-001",
            epic_ref="EPIC-001",
            type=TestCaseType.FUNCTIONAL,
            preconditions=[
                "Existe la guía 000123456 en estado vigente.",
                "El usuario tiene el rol de operador de siniestros.",
            ],
            steps=[
                TestStep(number=1, action="Abrir el registro de siniestros."),
                TestStep(
                    number=2,
                    action="Informar la guía 000123456 y la fecha 2026-08-10.",
                    expected="El formulario acepta la guía y muestra al shipper.",
                ),
                TestStep(number=3, action="Guardar el siniestro."),
            ],
            test_data=[
                TestDatum(
                    name="numero_guia",
                    value="000123456",
                    kind=DataKind.VALID,
                    field_ref="FLD-001",
                    entity_ref="ENT-001",
                ),
                TestDatum(
                    name="fecha_siniestro",
                    value="2026-08-10",
                    kind=DataKind.VALID,
                    field_ref="FLD-002",
                    entity_ref="ENT-001",
                ),
            ],
            expected_result=(
                "El siniestro queda registrado y asociado a la guía 000123456."
            ),
            priority=TestPriority.CRITICA,
            automation_hint=AutomationHint.API,
            estimated_minutes=15,
            source_refs=["REQ-B-001", "PRO-001", "BR-001"],
            tags=["siniestros", "alta"],
            confidence=0.9,
            # El criterio lo dice tal cual: no hay nada inferido en este caso.
            origin=Origin.STATED,
        ),
        TestCase(
            id="TC-002",
            title="Rechazar el registro de un siniestro sin guía",
            story_ref="US-001",
            criterion_ref="AC-001",
            epic_ref="EPIC-001",
            type=TestCaseType.NEGATIVE,
            preconditions=["El usuario tiene el rol de operador de siniestros."],
            steps=[
                TestStep(number=1, action="Abrir el registro de siniestros."),
                TestStep(number=2, action="Dejar la guía vacía e informar la fecha."),
                TestStep(number=3, action="Intentar guardar."),
            ],
            test_data=[
                TestDatum(
                    name="numero_guia",
                    value="",
                    kind=DataKind.INVALID,
                    field_ref="FLD-001",
                    note="Guía ausente: es lo que BR-001 prohíbe.",
                )
            ],
            expected_result=(
                "El sistema no guarda y exige la guía, citando la regla BR-001."
            ),
            priority=TestPriority.CRITICA,
            automation_hint=AutomationHint.API,
            estimated_minutes=9,
            source_refs=["BR-001"],
            confidence=0.85,
            origin=Origin.DERIVED,
        ),
        TestCase(
            id="TC-003",
            title="Rechazar una fecha de siniestro futura",
            story_ref="US-001",
            criterion_ref="AC-001",
            epic_ref="EPIC-001",
            type=TestCaseType.BOUNDARY,
            preconditions=["Existe la guía 000123456."],
            steps=[
                TestStep(number=1, action="Abrir el registro de siniestros."),
                TestStep(
                    number=2,
                    action="Informar la guía y la fecha de mañana (2026-08-15).",
                ),
                TestStep(number=3, action="Intentar guardar."),
            ],
            test_data=[
                TestDatum(
                    name="fecha_siniestro",
                    value="2026-08-15",
                    kind=DataKind.BOUNDARY,
                    field_ref="FLD-002",
                    note="Un día después de hoy: el primer valor que debe fallar.",
                )
            ],
            expected_result="El sistema rechaza la fecha por ser posterior a hoy.",
            priority=TestPriority.CRITICA,
            automation_hint=AutomationHint.API,
            estimated_minutes=8,
            boundary=BoundaryAnchor(
                rule_ref="VAL-001",
                kind=BoundaryKind.MAX,
                operator="<=",
                value="hoy",
                anchor_source=AnchorSource.EF_TEXT,
                # La frase exacta del EF. Sin ella este límite no podría existir.
                evidence="La fecha del siniestro no puede ser futura.",
            ),
            source_refs=["VAL-001", "FLD-002"],
            confidence=0.8,
            origin=Origin.DERIVED,
        ),
        TestCase(
            id="TC-004",
            title="Cambiar el estado (checkpoint) de un siniestro registrado",
            story_ref="US-002",
            criterion_ref="AC-002",
            epic_ref="EPIC-001",
            type=TestCaseType.FUNCTIONAL,
            preconditions=["Existe el siniestro del caso TC-001."],
            steps=[
                TestStep(number=1, action="Abrir el siniestro registrado."),
                TestStep(
                    number=2,
                    action="Cambiar el estado a «en evaluación».",
                    expected="El selector solo ofrece estados del catálogo.",
                ),
                TestStep(number=3, action="Guardar el cambio."),
            ],
            test_data=[
                TestDatum(
                    name="estado_id",
                    value="2",
                    kind=DataKind.VALID,
                    note="Segundo estado del catálogo de siniestros.",
                )
            ],
            expected_result="El siniestro queda con el nuevo checkpoint registrado.",
            priority=TestPriority.ALTA,
            automation_hint=AutomationHint.API,
            estimated_minutes=12,
            source_refs=["REQ-F-001", "PRO-001"],
            confidence=0.85,
            origin=Origin.STATED,
        ),
        TestCase(
            id="TC-005",
            title="Rechazar un cambio de estado sin informar el estado",
            story_ref="US-002",
            criterion_ref="AC-002",
            epic_ref="EPIC-001",
            type=TestCaseType.BOUNDARY,
            preconditions=["Existe el siniestro del caso TC-001."],
            steps=[
                TestStep(number=1, action="Abrir el siniestro registrado."),
                TestStep(number=2, action="Enviar el cambio sin el campo estado_id."),
            ],
            test_data=[
                TestDatum(
                    name="estado_id",
                    value="null",
                    kind=DataKind.BOUNDARY,
                    note="Obligatoriedad estructural: el contrato lo exige.",
                )
            ],
            expected_result="La API responde 422 indicando que estado_id es requerido.",
            priority=TestPriority.ALTA,
            automation_hint=AutomationHint.API,
            estimated_minutes=6,
            boundary=BoundaryAnchor(
                kind=BoundaryKind.REQUIRED,
                anchor_source=AnchorSource.API_FIELD,
                # Dato duro del contrato: SF-005 es required y no nullable. No hay
                # regla del EF detrás, y por eso no hay rule_ref ni cita verbatim.
                api_field_ref="SF-005",
            ),
            source_refs=["SF-005"],
            confidence=0.9,
            origin=Origin.DERIVED,
        ),
        TestCase(
            id="TC-006",
            title="Un actor sin permiso no puede registrar siniestros",
            story_ref="US-001",
            criterion_ref="AC-001",
            epic_ref="EPIC-001",
            type=TestCaseType.AUTHORIZATION,
            preconditions=[
                "El usuario autenticado NO es operador de siniestros.",
                "Existe la guía 000123456.",
            ],
            steps=[
                TestStep(
                    number=1,
                    action="Autenticarse como jefe de operaciones (ACT-002).",
                ),
                TestStep(number=2, action="Invocar POST /api/v1/siniestros."),
            ],
            expected_result=(
                "La API responde 403: la matriz solo concede el registro al "
                "operador de siniestros (AUTH-001)."
            ),
            # Suelo de QA-D4: aunque la historia fuera «should», un caso de
            # autorización no baja de «alta». Aquí la historia es «must».
            priority=TestPriority.CRITICA,
            automation_hint=AutomationHint.API,
            estimated_minutes=12,
            auth_context=AuthCase(
                auth_rule_ref="AUTH-001",
                endpoint_ref="EP-001",
                actor_ref="ACT-002",
                scope=AuthScope.ALL,
                expected_status=403,
                negative=True,
            ),
            source_refs=["AUTH-001", "CRUD-001"],
            confidence=0.85,
            origin=Origin.DERIVED,
        ),
    ]


def _matriz() -> TraceMatrix:
    """Matriz determinista: la calcularía TRACE_MATRIX con estos mismos datos."""
    cobertura = Coverage(
        criteria_total=2,
        criteria_covered=2,
        criteria_ratio=1.0,
        blocking_criteria_total=2,
        blocking_criteria_covered=2,
        stories_total=2,
        stories_covered=2,
        requirements_total=2,
        requirements_covered=2,
    )
    return TraceMatrix(
        rows=[
            TraceRow(
                requirement_refs=["REQ-B-001"],
                story_ref="US-001",
                criterion_ref="AC-001",
                story_priority=MoscowPriority.MUST,
                test_case_ids=["TC-001", "TC-002", "TC-003", "TC-006"],
                status=CoverageStatus.COVERED,
            ),
            TraceRow(
                requirement_refs=["REQ-F-001"],
                story_ref="US-002",
                criterion_ref="AC-002",
                story_priority=MoscowPriority.SHOULD,
                test_case_ids=["TC-004", "TC-005"],
                status=CoverageStatus.COVERED,
            ),
        ],
        coverage=cobertura,
    )


def example_artifact() -> QaArtifact:
    """Construye el QaArtifact de ejemplo (fixture de los bloques posteriores)."""
    casos = _casos()
    matriz = _matriz()
    return QaArtifact(
        source=SourceRef(
            scrum_job_id="01SC00000000000000000000SC",
            scrum_artifact_hash="f6e5d4c3b2a1",
            scrum_schema_version="1.0.0",
            ef_job_id="01EF00000000000000000000EF",
            ef_artifact_hash="a1b2c3d4e5f6",
            ef_schema_version="1.2.0",
            api_job_id="01AP00000000000000000000AP",
            api_artifact_hash="9f8e7d6c5b4a",
            api_schema_version="1.0.0",
            api_available=True,
            ready_snapshot=True,
        ),
        target=Target(),
        test_cases=casos,
        trace_matrix=matriz,
        datasets=[
            Dataset(
                id="DS-001",
                name="Siniestros",
                entity_ref="ENT-001",
                description=(
                    "Datos reutilizables de siniestros: válidos, inválidos y de "
                    "frontera, derivados de FLD-001/FLD-002 y VAL-001."
                ),
                rows=[
                    DatasetRow(
                        id="DS-001-R1",
                        kind=DataKind.VALID,
                        values={
                            "numero_guia": "000123456",
                            "fecha_siniestro": "2026-08-10",
                        },
                        expectation="Se acepta.",
                        field_refs=["FLD-001", "FLD-002"],
                    ),
                    DatasetRow(
                        id="DS-001-R2",
                        kind=DataKind.INVALID,
                        values={"numero_guia": "", "fecha_siniestro": "2026-08-10"},
                        expectation="Se rechaza por BR-001 (guía obligatoria).",
                        field_refs=["FLD-001"],
                    ),
                    DatasetRow(
                        id="DS-001-R3",
                        kind=DataKind.BOUNDARY,
                        values={
                            "numero_guia": "000123456",
                            "fecha_siniestro": "2026-08-15",
                        },
                        expectation="Se rechaza por VAL-001 (fecha futura).",
                        field_refs=["FLD-002"],
                        anchor=BoundaryAnchor(
                            rule_ref="VAL-001",
                            kind=BoundaryKind.MAX,
                            operator="<=",
                            value="hoy",
                            anchor_source=AnchorSource.EF_TEXT,
                            evidence="La fecha del siniestro no puede ser futura.",
                        ),
                    ),
                ],
                source_refs=["ENT-001", "FLD-001", "FLD-002", "VAL-001"],
                confidence=0.85,
                origin=Origin.DERIVED,
            )
        ],
        execution_plan=ExecutionPlan(
            suites=[
                Suite(
                    id="SUITE-001",
                    name="Gestión de Siniestros",
                    epic_ref="EPIC-001",
                    test_case_ids=[c.id for c in casos],
                    estimated_minutes=62,
                )
            ],
            order=["SUITE-001"],
            totals=ExecutionTotals(
                cases_total=6,
                manual_minutes=62,
                by_type={
                    TestCaseType.FUNCTIONAL.value: 2,
                    TestCaseType.NEGATIVE.value: 1,
                    TestCaseType.BOUNDARY.value: 2,
                    TestCaseType.AUTHORIZATION.value: 1,
                },
                by_priority={
                    TestPriority.CRITICA.value: 4,
                    TestPriority.ALTA.value: 2,
                },
            ),
        ),
        questions_for_qa_lead=[
            QaQuestion(
                id="QQ-001",
                question=(
                    "¿Con qué dato se determina el equipo de un siniestro? La regla "
                    "BR-003 limita la visibilidad de los jefes a su equipo, pero el "
                    "modelo de datos no tiene ninguna columna de equipo, así que no "
                    "se puede construir el caso «un jefe no ve los siniestros de "
                    "otro equipo»."
                ),
                reason=(
                    "AUTH-002 está marcada ambigua en el contrato de API. Diseñar el "
                    "caso adivinando la columna produciría una prueba que pasa "
                    "verificando un permiso que nadie definió."
                ),
                audience=Audience.TECNICO,
                blocking=True,
                linked_to_ref="AUTH-002",
                confidence=0.9,
                origin=Origin.DERIVED,
            )
        ],
        analysis=QaAnalysis(
            risks=[
                Risk(
                    id="RSK-001",
                    description=(
                        "La visibilidad por equipo queda sin probar hasta que se "
                        "defina la columna que la materializa."
                    ),
                    severity=RiskSeverity.ALTA,
                    mitigation=(
                        "Responder QQ-001 y regenerar el plan: el caso cruzado se "
                        "deriva solo en cuanto la regla deja de ser ambigua."
                    ),
                    source_ref="AUTH-002",
                    origin=Origin.DERIVED,
                )
            ],
            observations=[
                Observation(
                    id="OBS-001",
                    description=(
                        "No se generó el caso de autorización de AUTH-002: la regla "
                        "está marcada ambigua en el contrato de API. La ausencia es "
                        "deliberada y queda como pregunta bloqueante QQ-001."
                    ),
                    reason="Alcance own_team sin columna que lo materialice.",
                    source_ref="AUTH-002",
                )
            ],
            coverage=matriz.coverage,
        ),
        metrics=QaMetrics(
            tokens=TokenMetrics(input=18400, output=7200, total=25600),
            cost=0.163,
            duration=54.8,
            test_cases_total=6,
            datasets_total=1,
            suites_total=1,
            questions_total=1,
            blocking_questions_total=1,
            manual_minutes=62,
            coverage=1.0,
        ),
    )
