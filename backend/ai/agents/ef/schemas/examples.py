"""Ejemplo válido de EFArtifact (dominio: siniestros logísticos).

Reutilizable como fixture en tests de bloques posteriores (persistencia, API...).
"""

from .artifact import (
    Actor,
    Analysis,
    ApiEndpoint,
    Assumption,
    BusinessRule,
    CrudMatrixEntry,
    EFArtifact,
    Entity,
    FieldDef,
    Menu,
    Metrics,
    MissingInfo,
    Module,
    Observation,
    Process,
    Question,
    Relationship,
    Requirement,
    RequirementsBlock,
    ScopeItem,
    SourceInfo,
    SystemsInterpretation,
    TokenMetrics,
    ValidationRule,
)
from .enums import (
    Audience,
    Cardinality,
    HttpMethod,
    Origin,
    Priority,
    SourceFidelity,
    SourceType,
)


def example_artifact() -> EFArtifact:
    """Devuelve un EFArtifact v1.2.0 válido de ejemplo (siniestros)."""
    return EFArtifact(
        source=SourceInfo(
            type=SourceType.DOCUMENT,
            hash="a1b2c3d4e5f6",
            fidelity=SourceFidelity.FULL,
            filename="proceso_siniestros.docx",
        ),
        summary=(
            "Proceso de registro y seguimiento de siniestros (eventos logísticos "
            "no asegurados) desde su reporte hasta el recupero económico."
        ),
        requirements=RequirementsBlock(
            business=[
                Requirement(
                    id="REQ-B-001",
                    text="Registrar cada siniestro asociándolo a su guía de envío.",
                    priority=Priority.ALTA,
                    source_ref="sec-1/p-3",
                    evidence="Todo siniestro debe quedar registrado con su guía.",
                    confidence=0.95,
                    origin=Origin.STATED,
                )
            ],
            functional=[
                Requirement(
                    id="REQ-F-001",
                    text="Permitir cambiar el estado (checkpoint) del siniestro.",
                    priority=Priority.MEDIA,
                    source_ref="sec-2/p-1",
                    evidence="El operador actualiza el estado del siniestro.",
                    confidence=0.9,
                    origin=Origin.STATED,
                )
            ],
            non_functional=[
                Requirement(
                    id="REQ-N-001",
                    text="El registro de un siniestro no debe superar 2 segundos.",
                    priority=Priority.BAJA,
                    source_ref="sec-3/p-2",
                    confidence=0.6,
                    origin=Origin.DERIVED,
                )
            ],
        ),
        actors=[
            Actor(
                id="ACT-001",
                name="Operador de siniestros",
                description="Registra y da seguimiento a los siniestros.",
                responsibilities=["Registrar siniestro", "Actualizar estado"],
                source_ref="sec-1/p-1",
                confidence=0.9,
                origin=Origin.STATED,
            )
        ],
        modules=[
            Module(
                id="MOD-001",
                name="Gestión de Siniestros",
                description="Módulo de registro y seguimiento de siniestros.",
                source_ref="sec-1/h-1",
                origin=Origin.DERIVED,
                confidence=0.7,
            )
        ],
        menus=[
            Menu(
                id="MEN-001",
                name="Siniestros",
                module_ref="MOD-001",
                path="/siniestros",
                origin=Origin.DERIVED,
                confidence=0.6,
            )
        ],
        processes=[
            Process(
                id="PRO-001",
                name="Registro de siniestro",
                description="Flujo desde el reporte hasta el cierre del siniestro.",
                steps=["Reportar", "Registrar", "Investigar", "Recuperar", "Cerrar"],
                actor_refs=["ACT-001"],
                source_ref="sec-2",
                confidence=0.85,
                origin=Origin.STATED,
            )
        ],
        business_rules=[
            BusinessRule(
                id="BR-001",
                statement="Un siniestro sin guía asociada no puede registrarse.",
                source_ref="sec-1/p-3",
                confidence=0.9,
                origin=Origin.STATED,
            )
        ],
        validations=[
            ValidationRule(
                id="VAL-001",
                rule="La fecha del siniestro no puede ser futura.",
                field_ref="FLD-002",
                confidence=0.8,
                origin=Origin.DERIVED,
            )
        ],
        fields=[
            FieldDef(
                id="FLD-001",
                name="numero_guia",
                entity_ref="ENT-001",
                data_type="string",
                required=True,
                source_ref="sec-1/tbl-1",
                confidence=0.9,
                origin=Origin.STATED,
            ),
            FieldDef(
                id="FLD-002",
                name="fecha_siniestro",
                entity_ref="ENT-001",
                data_type="date",
                required=True,
                origin=Origin.DERIVED,
                confidence=0.7,
            ),
        ],
        entities=[
            Entity(
                id="ENT-001",
                name="Siniestro",
                description="Evento logístico no asegurado.",
                origin=Origin.STATED,
                source_ref="sec-1/p-3",
                confidence=0.9,
            ),
            Entity(
                id="ENT-002",
                name="Guia",
                description="Documento de envío asociado al siniestro.",
                origin=Origin.DERIVED,
                confidence=0.75,
            ),
        ],
        relationships=[
            Relationship(
                id="REL-001",
                source_entity_ref="ENT-002",
                target_entity_ref="ENT-001",
                cardinality=Cardinality.ONE_TO_MANY,
                name="una guía puede tener varios siniestros",
                origin=Origin.DERIVED,
                confidence=0.7,
            )
        ],
        crud=[
            CrudMatrixEntry(
                id="CRUD-001",
                entity_ref="ENT-001",
                actor_ref="ACT-001",
                module_ref="MOD-001",
                create=True,
                read=True,
                update=True,
                delete=False,
                origin=Origin.DERIVED,
                confidence=0.7,
            )
        ],
        apis=[
            ApiEndpoint(
                id="API-001",
                method=HttpMethod.POST,
                path="/api/v1/siniestros",
                description="Registrar un nuevo siniestro.",
                entity_ref="ENT-001",
                origin=Origin.DERIVED,
                confidence=0.65,
            )
        ],
        systems_interpretation=SystemsInterpretation(
            what_process_requests=(
                "Procesos necesita un módulo para registrar siniestros ligados a "
                "guías y dar seguimiento a su estado hasta el recupero."
            ),
            scope_for_systems=[
                ScopeItem(
                    id="SCOPE-001",
                    description="CRUD de siniestros con máquina de estados.",
                    requirement_refs=["REQ-B-001", "REQ-F-001"],
                )
            ],
            apparent_out_of_scope=[
                ScopeItem(
                    id="OOS-001",
                    description="Cálculo automático del monto de recupero.",
                    reason="No se describe la fórmula en la fuente.",
                )
            ],
            interpretation_assumptions=[
                Assumption(
                    id="SUP-001",
                    assumption=(
                        "Se asume que 'checkpoint' se refiere al estado del "
                        "siniestro, no a un punto de control físico."
                    ),
                    rationale="Uso del glosario logístico del dominio.",
                    confidence=0.8,
                    origin=Origin.DERIVED,
                )
            ],
        ),
        analysis=Analysis(
            missing_info=[
                MissingInfo(
                    id="MISS-001",
                    description="No se especifica quién autoriza el cierre.",
                    expected_where="Sección de responsabilidades.",
                    confidence=0.7,
                )
            ],
            observations=[
                Observation(
                    id="OBS-001",
                    description="El término 'papeleta' no aparece; sin impacto.",
                    reason="Registro informativo.",
                )
            ],
        ),
        questions_for_analyst=[
            Question(
                id="Q-001",
                question="¿Quién debe autorizar el cierre de un siniestro?",
                reason="No está definido el responsable de la aprobación final.",
                audience=Audience.NEGOCIO,
                blocking=True,
                linked_to_ref="PRO-001",
            )
        ],
        metrics=Metrics(
            tokens=TokenMetrics(input=1200, output=800, total=2000),
            cost=0.0156,
            duration=12.4,
            chunks_total=5,
            chunks_skipped=0,
            coverage=1.0,
        ),
    )
