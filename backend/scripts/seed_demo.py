"""Siembra un job COMPLETED con un EFArtifact v1.2.0 sintético (dominio siniestros).

Permite probar el frontend SIN gastar API de Anthropic. Todas las preguntas y
supuestos quedan en estado de validación PENDIENTE.

Uso (desde backend/, con el venv y Postgres arriba + migración aplicada):
    .venv/bin/python scripts/seed_demo.py
"""

import asyncio
import os
import sys

# Permite ejecutar el archivo directamente (agrega backend/ al path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.agents.ef.schemas import (  # noqa: E402
    Actor,
    Ambiguity,
    Analysis,
    ApiEndpoint,
    Assumption,
    BusinessRule,
    CrudMatrixEntry,
    EFArtifact,
    Entity,
    FieldDef,
    Inconsistency,
    Metrics,
    MissingInfo,
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
from app.dependencies.database import session_scope  # noqa: E402
from app.models.ef import EFSourceDocType, JobStatus  # noqa: E402
from app.repositories.ef_repository import EFRepository  # noqa: E402


def build_demo_artifact() -> EFArtifact:
    """Construye un EFArtifact v1.2.0 sintético y rico para la demo."""
    return EFArtifact(
        source=SourceInfo(
            type="text",
            hash="seed-demo",
            fidelity="full",
            filename="demo_siniestros.txt",
        ),
        summary=(
            "Proceso de registro y seguimiento de siniestros (eventos logísticos "
            "no asegurados) ligados a guías de envío, hasta el recupero económico."
        ),
        requirements=RequirementsBlock(
            business=[
                Requirement(
                    id="REQ-B-001",
                    text="Registrar cada siniestro asociándolo a su guía de envío.",
                    priority="alta",
                    source_ref="sec-1/p-3",
                    evidence="Todo siniestro debe quedar registrado con su guía.",
                    confidence=0.95,
                    origin="stated",
                )
            ],
            functional=[
                Requirement(
                    id="REQ-F-001",
                    text="Permitir cambiar el estado (checkpoint) del siniestro.",
                    priority="media",
                    source_ref="sec-2/p-1",
                    evidence="El operador actualiza el estado del siniestro.",
                    confidence=0.9,
                    origin="stated",
                )
            ],
            non_functional=[
                Requirement(
                    id="REQ-N-001",
                    text="El registro de un siniestro no debe superar 2 segundos.",
                    confidence=0.5,
                    origin="derived",
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
                origin="stated",
            )
        ],
        processes=[
            Process(
                id="PRO-001",
                name="Registro de siniestro",
                description="Del reporte al cierre del siniestro.",
                steps=["Reportar", "Registrar", "Investigar", "Recuperar", "Cerrar"],
                actor_refs=["ACT-001"],
                source_ref="sec-2",
                confidence=0.85,
                origin="stated",
            )
        ],
        business_rules=[
            BusinessRule(
                id="BR-001",
                statement="Un siniestro sin guía asociada no puede registrarse.",
                source_ref="sec-1/p-3",
                confidence=0.9,
                origin="stated",
            )
        ],
        validations=[
            ValidationRule(
                id="VAL-001",
                rule="La fecha del siniestro no puede ser futura.",
                field_ref="FLD-002",
                confidence=0.8,
                origin="derived",
            )
        ],
        fields=[
            FieldDef(
                id="FLD-001",
                name="numero_guia",
                entity_ref="ENT-001",
                data_type="string",
                required=True,
                origin="derived",
                confidence=0.9,
            ),
            FieldDef(
                id="FLD-002",
                name="fecha_siniestro",
                entity_ref="ENT-001",
                data_type="date",
                required=True,
                origin="derived",
                confidence=0.7,
            ),
        ],
        entities=[
            Entity(
                id="ENT-001",
                name="Siniestro",
                description="Evento logístico no asegurado.",
                origin="derived",
                confidence=0.8,
            ),
            Entity(
                id="ENT-002",
                name="Guia",
                description="Documento de envío asociado.",
                origin="derived",
                confidence=0.75,
            ),
        ],
        relationships=[
            Relationship(
                id="REL-001",
                source_entity_ref="ENT-002",
                target_entity_ref="ENT-001",
                cardinality="1:N",
                name="una guía puede tener varios siniestros",
                origin="derived",
                confidence=0.7,
            )
        ],
        crud=[
            CrudMatrixEntry(
                id="CRUD-001",
                entity_ref="ENT-001",
                actor_ref="ACT-001",
                create=True,
                read=True,
                update=True,
                delete=False,
                origin="derived",
                confidence=0.6,
            )
        ],
        apis=[
            ApiEndpoint(
                id="API-001",
                method="POST",
                path="/api/v1/siniestros",
                description="Registrar un siniestro.",
                entity_ref="ENT-001",
                origin="derived",
                confidence=0.6,
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
                    rationale="Glosario logístico del dominio.",
                    origin="derived",
                    confidence=0.8,
                ),
                Assumption(
                    id="SUP-002",
                    assumption=(
                        "Se asume que 'recupero' es la recuperación económica del "
                        "monto del siniestro."
                    ),
                    rationale="Glosario logístico del dominio.",
                    origin="derived",
                    confidence=0.75,
                ),
            ],
        ),
        analysis=Analysis(
            ambiguities=[
                Ambiguity(
                    id="AMB-001",
                    description="No se aclara si un siniestro puede reabrirse tras cerrarse.",
                    confidence=0.6,
                )
            ],
            missing_info=[
                MissingInfo(
                    id="MISS-001",
                    description="No se especifica quién autoriza el cierre.",
                    expected_where="Sección de responsabilidades.",
                )
            ],
            inconsistencies=[
                Inconsistency(
                    id="INC-001",
                    description="El estado 'Recuperar' aparece antes y después de 'Cerrar'.",
                    conflicting_refs=["PRO-001"],
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
                audience="negocio",
                blocking=True,
                linked_to_ref="PRO-001",
            ),
            Question(
                id="Q-002",
                question="¿Un siniestro puede estar ligado a más de una guía?",
                reason="La cardinalidad guía–siniestro no es explícita.",
                audience="negocio",
                blocking=True,
                linked_to_ref="ENT-001",
            ),
            Question(
                id="Q-003",
                question="¿Qué estados intermedios debe tener el checkpoint?",
                reason="El detalle de la máquina de estados afecta el modelo.",
                audience="tecnico",
                blocking=False,
                linked_to_ref="REQ-F-001",
            ),
        ],
        metrics=Metrics(
            tokens=TokenMetrics(input=1800, output=1200, total=3000),
            cost=0.0234,
            duration=14.7,
            chunks_total=4,
            chunks_skipped=0,
            coverage=1.0,
        ),
    )


async def main() -> None:
    artifact = build_demo_artifact()
    data = artifact.model_dump(mode="json")

    async with session_scope() as session:
        repo = EFRepository(session)
        doc = await repo.get_or_create_source_doc(
            content_hash="seed-demo-siniestros-0001",
            doc_type=EFSourceDocType.TEXT,
            filename="demo_siniestros.txt",
            doc_metadata={"seed": True, "source_type": "text"},
        )
        job = await repo.create_job(source_doc_id=doc.id)
        job_id = job.id
        await repo.update_job_status(job_id, JobStatus.COMPLETED)
        await repo.update_job_metrics(job_id, data["metrics"])
        await repo.save_artifact(job_id, data, data["schema_version"])

    print("=" * 60)
    print("Job COMPLETED sembrado:")
    print(f"  job_id: {job_id}")
    print(f"  Abrir en el navegador:")
    print(f"    http://localhost:3000/agents/ef/jobs/{job_id}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
