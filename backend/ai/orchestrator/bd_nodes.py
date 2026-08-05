"""Nodos del grafo LangGraph del Agente BD.

Bloque BD2: LOAD_SOURCES (gate + carga triple + resolución de motor) y MODEL_MAP
(andamio determinista) están completos; el resto son **stubs** que devuelven listas
vacías para que el grafo corra de extremo a extremo y el contrato quede fijado
desde el principio. Cada bloque posterior sustituye su stub:

- BD3 → ``tables``, ``relations``
- BD4 → ``constraints``, ``indexes``, ``catalogs``
- BD5 → ``ddl_gen``, ``validate``, ``dictionary``, ``er_diagram``
- BD6 → ``critique``, ``question_gen``
"""

import time

from langchain_core.runnables import RunnableConfig

from ai.agents.base.structured import ClaudeLLMClient
from ai.agents.bd.assemble import assemble_artifact, validate_artifact
from ai.agents.bd.common import merge_metrics
from ai.agents.bd.load_sources import (
    assert_architecture_ready,
    extract_sources,
    resolve_engine,
    resolve_hashes,
)
from ai.agents.bd.model_map import build_model_map, resolve_audit_columns
from ai.agents.bd.relations import run_relations
from ai.agents.bd.state import DatabaseState
from ai.agents.bd.tables import run_tables
from ai.knowledge import default_schema, load_db_conventions
from app.config.settings import settings


def _llm(config: RunnableConfig):
    """LLM inyectado por config (mock en tests); si no, el cliente real."""
    llm = (config or {}).get("configurable", {}).get("llm")
    return llm if llm is not None else ClaudeLLMClient()


def _conventions_payload(engine: str, audit_columns: bool) -> dict:
    """Convenciones efectivas que se persisten en el artefacto (auditables)."""
    data = load_db_conventions()
    naming = data.get("naming", {}) or {}
    keys = data.get("keys", {}) or {}
    audit = data.get("audit", {}) or {}
    strategy = keys.get("pk_strategy", "surrogate_identity")
    return {
        "naming_case": naming.get("case", "snake_case"),
        "table_number": naming.get("tables", "plural"),
        # El YAML habla de `surrogate_identity`; el contrato de `surrogate`.
        "pk_strategy": "surrogate" if strategy == "surrogate_identity" else strategy,
        "fk_pattern": naming.get("fk_column", "{referenced_table_singular}_id"),
        "audit_columns": audit_columns,
        "soft_delete": bool(audit.get("soft_delete", False)),
        "schema_name": default_schema(engine),
    }


async def node_load_sources(state: DatabaseState) -> dict:
    """LOAD_SOURCES: gate de Arquitectura, contexto consolidado y motor destino."""
    assert_architecture_ready(
        bool(state.get("architecture_ready")),
        state.get("architecture_job_id", "?"),
    )
    ef_artifact = state.get("ef_artifact") or {}
    architecture_artifact = state.get("architecture_artifact") or {}
    scrum_artifact = state.get("scrum_artifact") or {}

    sources = extract_sources(ef_artifact, architecture_artifact, scrum_artifact)
    engine_info = resolve_engine(sources, state.get("engine_override"))
    audit_columns = resolve_audit_columns(sources) is not None
    architecture_hash, ef_hash = resolve_hashes(
        state.get("architecture_artifact_hash", ""),
        state.get("ef_artifact_hash", ""),
        architecture_artifact,
        ef_artifact,
    )
    conventions = load_db_conventions()

    return {
        "sources": sources,
        "target": {
            "engine": engine_info["engine"],
            "engine_version": engine_info["version"],
            "engine_source_ref": engine_info["source_ref"],
            "engine_decided": engine_info["decided"],
            "engine_reason": engine_info["reason"],
            "conventions": _conventions_payload(engine_info["engine"], audit_columns),
            "conventions_source": (
                f"ai/knowledge/db_conventions.yaml@v{conventions.get('version', 0)}"
            ),
        },
        "architecture_artifact_hash": architecture_hash,
        "ef_artifact_hash": ef_hash,
        "status": "RUNNING",
        "metrics": dict(state.get("metrics") or {}),
        "errors": [],
        "started_at": time.time(),
    }


async def node_model_map(state: DatabaseState) -> dict:
    """MODEL_MAP: fija en Python qué tablas/columnas existen (anti-invención)."""
    engine = (state.get("target") or {}).get("engine") or "postgresql"
    return {"model_map": build_model_map(state.get("sources") or {}, engine)}


# --- Stubs de los bloques siguientes ----------------------------------------


async def node_tables(state: DatabaseState, config: RunnableConfig) -> dict:
    """TABLES: completa cada tabla candidata (LLM map por tabla, concurrencia N).

    Las observaciones que devuelve el nodo son correcciones aplicadas sobre la
    propuesta del modelo (columnas inventadas, tipos que contradicen al EF): se
    acumulan en el estado para que CRITIQUE/ASSEMBLE las publiquen. Nada se
    corrige en silencio.
    """
    tables, observations, skipped, tokens = await run_tables(
        _llm(config),
        state.get("model_map") or {},
        state.get("sources") or {},
        (state.get("target") or {}).get("engine") or "postgresql",
        authoritative_context=state.get("authoritative_context"),
        concurrency=settings.BD_TABLES_CONCURRENCY,
    )
    return {
        "tables": tables,
        "model_observations": list(state.get("model_observations") or [])
        + observations,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_relations(state: DatabaseState, config: RunnableConfig) -> dict:
    """RELATIONS: FK deterministas (1:N y puentes) + 1:1 y cascadas por LLM."""
    tables, observations, skipped, tokens = await run_relations(
        _llm(config),
        state.get("tables") or [],
        state.get("model_map") or {},
        state.get("sources") or {},
        (state.get("target") or {}).get("engine") or "postgresql",
        authoritative_context=state.get("authoritative_context"),
    )
    return {
        "tables": tables,
        "model_observations": list(state.get("model_observations") or [])
        + observations,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_constraints(state: DatabaseState, config: RunnableConfig) -> dict:
    """CONSTRAINTS (BD4): reglas/validaciones del EF → constraints declarativas."""
    return {"rule_mappings": []}


async def node_indexes(state: DatabaseState, config: RunnableConfig) -> dict:
    """INDEXES (BD4): índices de FK (det) + justificados por patrón de acceso."""
    return {}


async def node_catalogs(state: DatabaseState, config: RunnableConfig) -> dict:
    """CATALOGS (BD4): catálogos detectados + semilla con evidencia citada."""
    return {"seed_data": []}


async def node_ddl_gen(state: DatabaseState) -> dict:
    """DDL_GEN (BD5): render determinista del DDL en el dialecto del motor."""
    return {"ddl_scripts": []}


async def node_validate(state: DatabaseState) -> dict:
    """VALIDATE (BD5): validación determinista del DDL (estructural + sqlglot)."""
    return {"validation": {}}


async def node_dictionary(state: DatabaseState) -> dict:
    """DICTIONARY (BD5): diccionario derivado de las tablas (sin LLM)."""
    return {"data_dictionary": []}


async def node_er_diagram(state: DatabaseState) -> dict:
    """ER_DIAGRAM (BD5): Mermaid ``erDiagram`` determinista desde las tablas."""
    return {"er_diagram": {}}


async def node_critique(state: DatabaseState, config: RunnableConfig) -> dict:
    """CRITIQUE (BD6): chequeos deterministas + riesgos (LLM)."""
    return {"critique": {}}


async def node_question_gen(state: DatabaseState) -> dict:
    """QUESTION_GEN (BD6): preguntas al DBA, agrupadas por clase de vacío."""
    return {"questions": []}


# --- ASSEMBLE / PERSIST -----------------------------------------------------


async def node_assemble(state: DatabaseState) -> dict:
    """ASSEMBLE + VALIDATE: construye el DatabaseArtifact y lo valida (v1.0.0)."""
    artifact, _ = assemble_artifact(state)
    dumped = artifact.model_dump(mode="json")
    validate_artifact(dumped)
    return {"artifact": dumped}


async def node_persist(state: DatabaseState, config: RunnableConfig) -> dict:
    """PERSIST: guarda el artefacto y marca COMPLETED[_WITH_WARNINGS].

    La persistencia es inyectable por config (tests sin Postgres); si no se
    inyecta, usa la BD real vía ``session_scope``.
    """
    artifact = state["artifact"]
    metrics = artifact.get("metrics") or {}
    validation = artifact.get("validation") or {}
    # Un DDL con errores estructurales no puede pasar por COMPLETED limpio.
    has_warnings = bool(metrics.get("skipped")) or bool(validation.get("errors"))
    status = "COMPLETED_WITH_WARNINGS" if has_warnings else "COMPLETED"

    persist = (config or {}).get("configurable", {}).get("persist")
    if persist is not None:
        await persist(state["job_id"], artifact, status, metrics)
    else:  # pragma: no cover - ruta runtime con Postgres real
        from app.dependencies.database import session_scope
        from app.models.agent import JobStatus
        from app.repositories.agent_job_repository import AgentJobRepository

        async with session_scope() as session:
            repo = AgentJobRepository(session)
            await repo.save_artifact(
                state["job_id"], artifact, artifact["schema_version"]
            )
            await repo.update_job_metrics(state["job_id"], metrics)
            await repo.update_job_status(state["job_id"], JobStatus[status])

    return {"status": status}
