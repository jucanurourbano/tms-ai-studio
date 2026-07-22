"""Ejemplo válido de ArchitectureArtifact (dominio: siniestros logísticos).

Deriva del par EF + Scrum de ejemplo (mismos MOD-/PRO-/ENT-/API-/REQ-/EPIC-/US-
refs) para reutilizarse como fixture en tests de bloques posteriores.
"""

from ai.agents.ef.schemas.artifact import Observation, TokenMetrics
from ai.agents.ef.schemas.enums import Audience, Origin

from .artifact import (
    Adr,
    ArchitectQuestion,
    ArchitectureAnalysis,
    ArchitectureArtifact,
    ArchitectureContext,
    ArchitectureMetrics,
    BoundedContext,
    Component,
    ComponentSourceRefs,
    Contract,
    Coverage,
    CrossCutting,
    Diagram,
    Diagrams,
    Integration,
    Risk,
    ScopeProfile,
    SourceRef,
    StackChoice,
    StyleDecision,
)
from .enums import (
    AdrStatus,
    ArchitectureStyle,
    ComponentType,
    ContractKind,
    CrossCuttingConcern,
    IntegrationDirection,
    IntegrationProtocol,
    RiskSeverity,
    SizeClass,
)

_COMPONENT_DIAGRAM = """flowchart LR
  subgraph presentacion
    CMP004[Frontend Siniestros]
  end
  subgraph aplicacion
    CMP003[API Siniestros]
  end
  subgraph dominio
    CMP001[Módulo Siniestros]
    CMP002[Módulo Guías]
  end
  subgraph datos
    CMP005[(Base de Datos)]
  end
  CMP004 --> CMP003 --> CMP001
  CMP001 --> CMP002
  CMP001 --> CMP005
  CMP001 -.-> INT001[Sistema de Planillas]
"""

_CONTEXT_DIAGRAM = """flowchart LR
  OP[Operador de Siniestros] --> SYS[Sistema de Siniestros]
  SYS -.->|papeleta / descuentos| PLAN[Sistema de Planillas]
"""


def example_artifact() -> ArchitectureArtifact:
    """Devuelve un ArchitectureArtifact v1.0.0 válido de ejemplo (siniestros)."""
    return ArchitectureArtifact(
        source=SourceRef(
            scrum_job_id="01SC00000000000000000000SC",
            scrum_artifact_hash="sc123456",
            scrum_schema_version="1.0.0",
            ef_job_id="01EF00000000000000000000EF",
            ef_artifact_hash="a1b2c3d4e5f6",
            ef_schema_version="1.2.0",
            ready_snapshot=True,
        ),
        context=ArchitectureContext(
            scope_profile=ScopeProfile(
                entities=2,
                relationships=1,
                modules=2,
                processes=1,
                stories=2,
                points_total=8,
                integrations_detected=1,
                nfr_count=1,
            ),
            size_class=SizeClass.M,
            bounded_contexts=[
                BoundedContext(
                    id="BC-001",
                    name="Siniestros",
                    source_refs=["MOD-001", "PRO-001"],
                    confidence=0.75,
                    origin=Origin.DERIVED,
                )
            ],
        ),
        architecture_style=StyleDecision(
            chosen=ArchitectureStyle.MODULAR_MONOLITH,
            rationale=(
                "Alcance moderado (size M), un solo equipo de Sistemas y "
                "simplicidad operativa; el monolito modular minimiza el costo de "
                "coordinación frente a microservicios."
            ),
            adr_ref="ADR-001",
            confidence=0.8,
            origin=Origin.DERIVED,
        ),
        components=[
            Component(
                id="CMP-001",
                name="Módulo Siniestros",
                type=ComponentType.DOMAIN,
                layer="dominio",
                responsibility=(
                    "Registrar y dar seguimiento a los siniestros y su estado."
                ),
                source_refs=ComponentSourceRefs(
                    epic_refs=["EPIC-001"],
                    story_refs=["US-001", "US-002"],
                    entity_refs=["ENT-001"],
                    api_refs=["API-001"],
                    module_refs=["MOD-001"],
                    process_refs=["PRO-001"],
                ),
                depends_on=["CMP-002", "CMP-005"],
                confidence=0.8,
                origin=Origin.DERIVED,
            ),
            Component(
                id="CMP-002",
                name="Módulo Guías",
                type=ComponentType.DOMAIN,
                layer="dominio",
                responsibility="Gestionar las guías de envío asociadas a siniestros.",
                source_refs=ComponentSourceRefs(
                    entity_refs=["ENT-002"],
                    module_refs=["MOD-002"],
                ),
                depends_on=["CMP-005"],
                confidence=0.7,
                origin=Origin.DERIVED,
            ),
            Component(
                id="CMP-003",
                name="API Siniestros",
                type=ComponentType.API,
                layer="aplicación",
                responsibility="Exponer los casos de uso de siniestros vía REST.",
                source_refs=ComponentSourceRefs(api_refs=["API-001"]),
                depends_on=["CMP-001"],
                confidence=0.75,
                origin=Origin.DERIVED,
            ),
            Component(
                id="CMP-004",
                name="Frontend Siniestros",
                type=ComponentType.UI,
                layer="presentación",
                responsibility="Interfaz de registro y seguimiento de siniestros.",
                source_refs=ComponentSourceRefs(epic_refs=["EPIC-001"]),
                depends_on=["CMP-003"],
                confidence=0.7,
                origin=Origin.DERIVED,
            ),
            Component(
                id="CMP-005",
                name="Base de Datos",
                type=ComponentType.DATASTORE,
                layer="datos",
                responsibility="Persistencia relacional de siniestros y guías.",
                source_refs=ComponentSourceRefs(entity_refs=["ENT-001", "ENT-002"]),
                depends_on=[],
                confidence=0.8,
                origin=Origin.DERIVED,
            ),
            Component(
                id="CMP-006",
                name="Integración Planillas",
                type=ComponentType.INTEGRATION,
                layer="aplicación",
                responsibility="Registrar descuentos (papeleta) en el sistema de planillas.",
                source_refs=ComponentSourceRefs(process_refs=["PRO-001"]),
                depends_on=["CMP-001"],
                confidence=0.55,
                origin=Origin.DERIVED,
            ),
        ],
        stack=[
            StackChoice(
                id="STK-001",
                layer="framework_backend",
                technology="Spring Boot",
                version=None,
                rationale="Stack de negocio de la casa (allow-list); equipo disponible.",
                alternatives=["ASP.NET Core", "Django"],
                source_refs=["RNF-001"],
                confidence=0.7,
                origin=Origin.DERIVED,
            ),
            StackChoice(
                id="STK-002",
                layer="database_relational",
                technology="SQL Server",
                rationale="Motor transaccional estándar para sistemas de negocio.",
                alternatives=["PostgreSQL", "Oracle"],
                source_refs=["ENT-001"],
                confidence=0.65,
                origin=Origin.DERIVED,
            ),
        ],
        adrs=[
            Adr(
                id="ADR-001",
                title="Estilo arquitectónico: monolito modular",
                decision=(
                    "Construir la solución como un monolito modular con módulos de "
                    "dominio bien delimitados."
                ),
                context=(
                    "Alcance moderado, un solo equipo y una integración externa; "
                    "no hay necesidad de escalado independiente por servicio."
                ),
                alternatives_considered=["microservicios", "serverless"],
                consequences=[
                    "+ Simplicidad operativa y despliegue único.",
                    "- Escalado independiente por módulo limitado.",
                ],
                status=AdrStatus.PROPOSED,
                source_refs=["RNF-001", "EPIC-001"],
                confidence=0.8,
                origin=Origin.DERIVED,
            )
        ],
        integrations=[
            Integration(
                id="INT-001",
                name="Sistema de Planillas",
                system="planillas",
                direction=IntegrationDirection.OUTBOUND,
                protocol=IntegrationProtocol.UNKNOWN,
                purpose="Registrar descuentos a personal (papeleta) por siniestro.",
                data_exchanged="Identificador de empleado, monto y motivo.",
                source_refs=["PRO-001", "BR-001"],
                contract_known=False,
                confidence=0.6,
                origin=Origin.DERIVED,
            )
        ],
        contracts=[
            Contract(
                id="CON-001",
                from_ref="CMP-003",
                to_ref="CMP-001",
                kind=ContractKind.SYNC_API,
                description="La API invoca los casos de uso del módulo de siniestros.",
                source_refs=["API-001"],
                confidence=0.75,
                origin=Origin.DERIVED,
            ),
            Contract(
                id="CON-002",
                from_ref="CMP-006",
                to_ref="INT-001",
                kind=ContractKind.EXTERNAL,
                description="Envío de descuentos al sistema de planillas (contrato por confirmar).",
                source_refs=["PRO-001"],
                confidence=0.5,
                origin=Origin.DERIVED,
            ),
        ],
        cross_cutting=[
            CrossCutting(
                id="XC-001",
                concern=CrossCuttingConcern.AUDIT,
                requirement=(
                    "Toda operación sobre un siniestro debe quedar auditada "
                    "(quién, cuándo, qué cambió)."
                ),
                approach="Interceptor de auditoría por módulo, tabla de bitácora.",
                source_refs=["BR-001"],
                confidence=0.65,
                origin=Origin.DERIVED,
            )
        ],
        diagrams=Diagrams(
            component=Diagram(code=_COMPONENT_DIAGRAM),
            context=Diagram(code=_CONTEXT_DIAGRAM),
        ),
        analysis=ArchitectureAnalysis(
            risks=[
                Risk(
                    id="RISK-001",
                    description=(
                        "El contrato de integración con Planillas es desconocido; "
                        "podría cambiar el diseño de la integración."
                    ),
                    severity=RiskSeverity.ALTA,
                    mitigation="Confirmar protocolo con el equipo de Planillas.",
                    source_ref="INT-001",
                    confidence=0.7,
                    origin=Origin.DERIVED,
                )
            ],
            observations=[
                Observation(
                    id="OBS-001",
                    description=(
                        "No se detecta necesidad de mensajería asíncrona en v1."
                    ),
                    reason="Los flujos son síncronos dentro del monolito.",
                )
            ],
            coverage=Coverage(
                epics_total=1,
                epics_mapped=1,
                uncovered_epic_refs=[],
                entities_total=2,
                entities_mapped=2,
                uncovered_entity_refs=[],
                nfr_total=1,
                nfr_addressed=1,
                uncovered_nfr_refs=[],
            ),
        ),
        questions_for_architect=[
            ArchitectQuestion(
                id="Q-001",
                question=(
                    "¿Qué protocolo expone el sistema de Planillas (REST, archivo "
                    "batch, base de datos)?"
                ),
                reason="El contrato de la integración no está definido en el EF.",
                audience=Audience.TECNICO,
                blocking=True,
                linked_to_ref="INT-001",
                confidence=0.6,
                origin=Origin.DERIVED,
            )
        ],
        metrics=ArchitectureMetrics(
            tokens=TokenMetrics(input=1800, output=1200, total=3000),
            cost=0.0234,
            duration=12.4,
            components_total=6,
            adrs_total=1,
            integrations_total=1,
            coverage=1.0,
        ),
    )
