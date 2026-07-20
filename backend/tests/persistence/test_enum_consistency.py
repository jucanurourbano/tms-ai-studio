"""Consistencia de enums modelo <-> migraciones y humo del seed (regresión B0).

Bug detectado: SQLAlchemy persistía el NOMBRE del miembro (``TEXT``) mientras que
las migraciones crean los tipos enum de Postgres a partir del VALOR (``text``).
SQLite no lo detectaba porque ``create_all`` usa el mismo modelo. Estos tests
fijan que las columnas persistan VALORES y que esos valores coincidan con los que
declaran las migraciones.
"""

import importlib.util
from pathlib import Path

from app.models.agent import (
    AgentJob,
    AgentType,
    AgentValidation,
    EFSourceDoc,
    EFSourceDocType,
    JobStatus,
    ValidationStatus,
    ValidationTargetType,
)
from app.models.ef import JobStatus as EFJobStatusAlias
from app.repositories.ef_repository import EFRepository

_MIGRATIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# Valores canónicos: los que crean las migraciones 0001/0002 en Postgres.
CANONICAL = {
    EFSourceDocType: {"document", "text"},
    AgentType: {
        "ef",
        "scrum",
        "arquitectura",
        "bd",
        "api",
        "backend",
        "frontend",
        "qa",
        "devops",
    },
    JobStatus: {
        "PENDING",
        "RUNNING",
        "NEEDS_INPUT",
        "COMPLETED",
        "COMPLETED_WITH_WARNINGS",
        "FAILED",
    },
    ValidationTargetType: {"question", "assumption", "estimate"},
    ValidationStatus: {"pendiente", "confirmado", "corregido"},
}

_ENUM_COLUMNS = [
    (EFSourceDoc.__table__.c.type, EFSourceDocType),
    (AgentJob.__table__.c.agent_type, AgentType),
    (AgentJob.__table__.c.status, JobStatus),
    (AgentValidation.__table__.c.target_type, ValidationTargetType),
    (AgentValidation.__table__.c.status, ValidationStatus),
]


def _load_migration(filename: str):
    path = _MIGRATIONS / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path.read_text(encoding="utf-8")


def test_columnas_persisten_valores_no_nombres():
    """Cada columna enum debe persistir el VALOR del miembro (no el nombre)."""
    for column, enum_cls in _ENUM_COLUMNS:
        expected = [m.value for m in enum_cls]
        assert column.type.enums == expected, (
            f"{column.name}: persiste {column.type.enums}, se esperaba {expected}. "
            "¿Falta values_callable (pg_enum)?"
        )


def test_valores_del_modelo_coinciden_con_canonico():
    """Los valores del enum del modelo == los que crean las migraciones."""
    for enum_cls, expected in CANONICAL.items():
        assert {m.value for m in enum_cls} == expected


def test_migraciones_declaran_los_valores():
    """Las migraciones 0001/0002 declaran exactamente los valores canónicos."""
    _mod1, text1 = _load_migration("0001_initial.py")
    mod2, text2 = _load_migration("0002_generalizar_agentes.py")

    # 0001: source_doc_type, job_status, validation_target/status (por valor).
    for value in CANONICAL[EFSourceDocType] | CANONICAL[JobStatus]:
        assert f'"{value}"' in text1, f"0001 no declara el valor '{value}'"
    for value in {"question", "assumption", "pendiente", "confirmado", "corregido"}:
        assert f'"{value}"' in text1

    # 0002: agent_type (variable _AGENT_TYPES) y el valor extendido 'estimate'.
    assert set(mod2._AGENT_TYPES) == CANONICAL[AgentType]
    assert "'estimate'" in text2 or '"estimate"' in text2


def test_alias_ef_jobstatus_apunta_al_mismo_enum():
    """El shim EF (app.models.ef.JobStatus) es el mismo enum generalizado."""
    assert EFJobStatusAlias is JobStatus


async def test_seed_demo_roundtrip(session):
    """Humo del seed contra el esquema del modelo: source TEXT + job + artefacto."""
    seed, _ = _load_migration("../../scripts/seed_demo.py")
    artifact = seed.build_demo_artifact()
    data = artifact.model_dump(mode="json")

    repo = EFRepository(session)
    doc = await repo.get_or_create_source_doc(
        content_hash="seed-test-0001",
        doc_type=EFSourceDocType.TEXT,
        filename="demo.txt",
        doc_metadata={"seed": True},
    )
    job = await repo.create_job(source_doc_id=doc.id)
    await repo.update_job_status(job.id, JobStatus.COMPLETED)
    await repo.update_job_metrics(job.id, data["metrics"])
    await repo.save_artifact(job.id, data, data["schema_version"])
    await session.commit()

    # Round-trip: el tipo enum se guarda/lee por valor.
    fetched_doc = await session.get(type(doc), doc.id)
    assert fetched_doc.type == EFSourceDocType.TEXT
    refreshed = await repo.get_job(job.id)
    assert refreshed.status == JobStatus.COMPLETED
    assert refreshed.agent_type == AgentType.EF
    assert (await repo.get_artifact(job.id)).schema_version == "1.2.0"
