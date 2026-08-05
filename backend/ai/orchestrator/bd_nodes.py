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
from ai.agents.bd.catalogs import run_catalogs
from ai.agents.bd.common import merge_metrics
from ai.agents.bd.constraints import run_constraints
from ai.agents.bd.critique import run_critique
from ai.agents.bd.ddl.render import build_ddl_scripts, render_type
from ai.agents.bd.ddl.validate import validate_ddl
from ai.agents.bd.dictionary import build_data_dictionary
from ai.agents.bd.er_diagram import build_er_diagram
from ai.agents.bd.indexes import run_indexes
from ai.agents.bd.load_sources import (
    assert_architecture_ready,
    extract_sources,
    resolve_engine,
    resolve_hashes,
)
from ai.agents.bd.model_map import build_model_map, resolve_audit_columns
from ai.agents.bd.question_gen import generate_questions
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
    """CONSTRAINTS: reglas/validaciones del EF → integridad declarativa.

    Toda regla del EF sale de aquí con un destino en ``rule_mappings``, incluso las
    que no caben en el esquema.
    """
    tables, mappings, observations, skipped, tokens = await run_constraints(
        _llm(config),
        state.get("tables") or [],
        state.get("sources") or {},
        (state.get("target") or {}).get("engine") or "postgresql",
        authoritative_context=state.get("authoritative_context"),
        concurrency=settings.BD_TABLES_CONCURRENCY,
    )
    return {
        "tables": tables,
        "rule_mappings": mappings,
        "model_observations": list(state.get("model_observations") or [])
        + observations,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_indexes(state: DatabaseState, config: RunnableConfig) -> dict:
    """INDEXES: índices de FK (deterministas) + los justificados por acceso real."""
    tables, observations, skipped, tokens = await run_indexes(
        _llm(config),
        state.get("tables") or [],
        state.get("sources") or {},
        (state.get("target") or {}).get("engine") or "postgresql",
        max_per_table=settings.BD_MAX_INDEXES_PER_TABLE,
        authoritative_context=state.get("authoritative_context"),
    )
    return {
        "tables": tables,
        "model_observations": list(state.get("model_observations") or [])
        + observations,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_catalogs(state: DatabaseState, config: RunnableConfig) -> dict:
    """CATALOGS: catálogos detectados + semilla, solo con evidencia citada del EF."""
    tables, seeds, observations, skipped, tokens = await run_catalogs(
        _llm(config),
        state.get("tables") or [],
        state.get("sources") or {},
        (state.get("target") or {}).get("engine") or "postgresql",
        authoritative_context=state.get("authoritative_context"),
    )
    return {
        "tables": tables,
        "seed_data": seeds,
        "model_observations": list(state.get("model_observations") or [])
        + observations,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_ddl_gen(state: DatabaseState) -> dict:
    """DDL_GEN: renderiza el DDL en el dialecto del motor. Sin LLM.

    Aquí es donde el ``logical_type`` de cada columna se convierte por fin en
    sintaxis de un motor concreto (decisión DB2): el tipo físico se escribe en la
    propia columna para que el artefacto muestre exactamente lo que dice el script.
    """
    engine = (state.get("target") or {}).get("engine") or "postgresql"
    tables = state.get("tables") or []
    for table in tables:
        for column in table.get("columns", []):
            column["type"] = render_type(column, engine)

    scripts, cycles = build_ddl_scripts(tables, state.get("seed_data") or [], engine)
    return {"tables": tables, "ddl_scripts": scripts, "ddl_cycles": cycles}


async def node_validate(state: DatabaseState) -> dict:
    """VALIDATE: validación determinista del DDL (L1 estructural + L2 sqlglot).

    Un DDL con errores **no** tumba el pipeline: queda registrado, el job termina
    con advertencias y el semáforo se mantiene en rojo. Entregar un esquema roto
    avisando es útil; caerse, no.
    """
    validation = validate_ddl(
        state.get("tables") or [],
        state.get("seed_data") or [],
        state.get("ddl_scripts") or [],
        (state.get("target") or {}).get("engine") or "postgresql",
        cycles=state.get("ddl_cycles") or [],
    )
    return {"validation": validation}


async def node_dictionary(state: DatabaseState) -> dict:
    """DICTIONARY: diccionario derivado de las tablas (sin una segunda pasada LLM)."""
    return {
        "data_dictionary": build_data_dictionary(
            state.get("tables") or [],
            (state.get("target") or {}).get("engine") or "postgresql",
        )
    }


async def node_er_diagram(state: DatabaseState) -> dict:
    """ER_DIAGRAM: Mermaid ``erDiagram`` determinista desde el modelo."""
    return {"er_diagram": build_er_diagram(state.get("tables") or [])}


async def node_critique(state: DatabaseState, config: RunnableConfig) -> dict:
    """CRITIQUE: cobertura y hallazgos deterministas + riesgos (pase LLM)."""
    critique, tokens = await run_critique(
        state.get("tables") or [],
        state.get("rule_mappings") or [],
        state.get("validation") or {},
        state.get("sources") or {},
        state.get("model_map") or {},
        state.get("seed_data") or [],
        state.get("target") or {},
        llm=_llm(config),
        engine=(state.get("target") or {}).get("engine") or "postgresql",
        authoritative_context=state.get("authoritative_context"),
    )
    # Las correcciones acumuladas en los nodos anteriores se publican aquí, junto
    # a las observaciones de la crítica: ninguna se queda por el camino.
    critique["observations"] = list(state.get("model_observations") or []) + list(
        critique.get("observations") or []
    )
    for i, observation in enumerate(critique["observations"], start=1):
        observation.setdefault("id", f"OBS-{i:03d}")
    return {"critique": critique, "metrics": merge_metrics(state, tokens, [])}


async def node_question_gen(state: DatabaseState) -> dict:
    """QUESTION_GEN: preguntas al DBA, agrupadas por clase de vacío."""
    return {"questions": generate_questions(state.get("critique") or {})}


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
