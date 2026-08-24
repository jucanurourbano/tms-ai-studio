"""Nodos del grafo LangGraph del Agente API.

Bloque API2: LOAD_SOURCES (gate + carga cuádruple + resolución de estilo y
seguridad) y RESOURCE_MAP (andamio determinista) están completos; el resto son
**stubs** que devuelven vacío para que el grafo corra de extremo a extremo y el
contrato quede fijado desde el principio. Cada bloque posterior sustituye su stub:

- API3 → ``resources``, ``endpoints``
- API4 → ``schemas``, ``errors``
- API5 → ``authorization``, ``rule_mapping``
- API6 → ``openapi_gen``, ``validate``
- API7 → ``critique``, ``question_gen``
- API8 → ``assemble``, ``persist``
"""

import time

from langchain_core.runnables import RunnableConfig

from ai.agents.api.assemble import assemble_artifact, validate_artifact
from ai.agents.api.authorization import run_authorization, unauthorized_endpoints
from ai.agents.api.common import merge_metrics
from ai.agents.api.critique import run_critique
from ai.agents.api.endpoints import build_endpoints, merge_actions, run_actions
from ai.agents.api.errors import apply_errors
from ai.agents.api.load_sources import (
    assert_bd_ready,
    base_path,
    extract_sources,
    resolve_api_style,
    resolve_auth,
    resolve_conventions,
    resolve_hashes,
)
from ai.agents.api.openapi.render import build_openapi
from ai.agents.api.openapi.validate import validate_spec
from ai.agents.api.payloads import run_schemas
from ai.agents.api.question_gen import generate_questions
from ai.agents.api.resource_map import build_resource_map
from ai.agents.api.resources import run_resources
from ai.agents.api.rule_mapping import run_rule_mapping
from ai.agents.api.state import ApiState
from ai.inventory.nodes import conflict_questions, reconcile_endpoints
from ai.knowledge import load_api_conventions
from ai.llm import get_llm
from app.config.settings import settings


def _llm(config: RunnableConfig):
    """LLM inyectado por config (mock en tests); si no, el de la fábrica."""
    llm = (config or {}).get("configurable", {}).get("llm")
    if llm is not None:
        return llm
    # `data_class` es keyword-only y sin default (ver ai/llm/factory.py).
    # Mientras la clasificación de fuentes no exista (LLM2) se declara `real`:
    # el valor conservador, el que NO autoriza a un proveedor de pruebas.
    return get_llm("api", data_class="real")


async def node_load_sources(state: ApiState) -> dict:
    """LOAD_SOURCES: gate del modelo de datos, contexto, estilo y seguridad."""
    assert_bd_ready(bool(state.get("bd_ready")), state.get("bd_job_id", "?"))

    bd_artifact = state.get("bd_artifact") or {}
    ef_artifact = state.get("ef_artifact") or {}
    architecture_artifact = state.get("architecture_artifact") or {}
    scrum_artifact = state.get("scrum_artifact") or {}

    sources = extract_sources(
        bd_artifact, ef_artifact, architecture_artifact, scrum_artifact
    )
    style = resolve_api_style(sources, state.get("style_override"))
    auth = resolve_auth(sources)
    hashes = resolve_hashes(
        state.get("bd_artifact_hash", ""),
        state.get("ef_artifact_hash", ""),
        state.get("architecture_artifact_hash"),
        bd_artifact,
    )
    conventions = load_api_conventions()

    return {
        "sources": sources,
        "target": {
            "api_style": style["style"],
            "style_supported": style["supported"],
            "style_decided": style["decided"],
            "style_source_ref": style["source_ref"],
            "style_reason": style["reason"],
            "base_path": base_path(),
            "auth": {
                "scheme": auth["scheme"],
                "provider": auth["provider"],
                "source_ref": auth["source_ref"],
                "decided": auth["decided"],
                "reason": auth["reason"],
            },
            "conventions": resolve_conventions(),
            "conventions_source": (
                f"ai/knowledge/api_conventions.yaml@v{conventions.get('version', 0)}"
            ),
        },
        "bd_artifact_hash": hashes["bd"],
        "ef_artifact_hash": hashes["ef"],
        "architecture_artifact_hash": hashes["architecture"],
        "scrum_artifact_hash": hashes["scrum"],
        "status": "RUNNING",
        "metrics": dict(state.get("metrics") or {}),
        "errors": [],
        "started_at": time.time(),
    }


async def node_resource_map(state: ApiState) -> dict:
    """RESOURCE_MAP: fija en Python qué recursos y operaciones existen."""
    target = state.get("target") or {}
    mapa = build_resource_map(
        state.get("sources") or {}, target.get("base_path") or "/api/v1"
    )
    return {
        "resource_map": mapa,
        # Las exclusiones del andamio viajan desde ya: acabarán en `Observation`.
        "map_observations": list(mapa.get("observations") or []),
    }


# --- Stubs de los bloques siguientes ----------------------------------------


async def node_resources(state: ApiState, config: RunnableConfig) -> dict:
    """RESOURCES: redacta cada recurso del andamio (LLM *map*)."""
    recursos, skipped, tokens, observaciones = await run_resources(
        _llm(config),
        state.get("resource_map") or {},
        state.get("sources") or {},
        authoritative_context=state.get("authoritative_context"),
        concurrency=settings.API_SCHEMAS_CONCURRENCY,
    )
    return {
        "resources": recursos,
        "map_observations": list(state.get("map_observations") or []) + observaciones,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_endpoints(state: ApiState, config: RunnableConfig) -> dict:
    """ENDPOINTS: CRUD determinista del andamio + acciones con evidencia verificada."""
    resource_map = state.get("resource_map") or {}
    acciones, skipped, tokens, observaciones = await run_actions(
        _llm(config),
        resource_map,
        state.get("sources") or {},
        authoritative_context=state.get("authoritative_context"),
        concurrency=settings.API_SCHEMAS_CONCURRENCY,
    )
    # Las acciones aceptadas vuelven al andamio: SCHEMAS y ERRORS leen de ahí, y
    # una operación que viviera en dos sitios acabaría tratándose de dos formas.
    merge_actions(resource_map, acciones)
    conventions = (state.get("target") or {}).get("conventions") or {}
    endpoints = build_endpoints(resource_map, state.get("resources") or [], conventions)
    return {
        "endpoints": endpoints,
        "resource_map": resource_map,
        "map_observations": list(state.get("map_observations") or []) + observaciones,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_schemas(state: ApiState, config: RunnableConfig) -> dict:
    """SCHEMAS: esqueleto determinista desde las columnas + exposición por LLM."""
    endpoints = list(state.get("endpoints") or [])
    esquemas, skipped, tokens, observaciones = await run_schemas(
        _llm(config),
        state.get("resource_map") or {},
        endpoints,
        authoritative_context=state.get("authoritative_context"),
        concurrency=settings.API_SCHEMAS_CONCURRENCY,
    )
    return {
        "schemas": esquemas,
        # `attach_schema_refs` enlaza los endpoints con sus esquemas in situ.
        "endpoints": endpoints,
        "map_observations": list(state.get("map_observations") or []) + observaciones,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_authorization(state: ApiState, config: RunnableConfig) -> dict:
    """AUTHORIZATION: matriz desde la CRUD del EF + alcances por fila (fail-closed)."""
    endpoints = list(state.get("endpoints") or [])
    matriz, skipped, tokens, observaciones = await run_authorization(
        _llm(config),
        endpoints,
        state.get("resource_map") or {},
        state.get("sources") or {},
        authoritative_context=state.get("authoritative_context"),
        concurrency=settings.API_SCHEMAS_CONCURRENCY,
    )
    metrics = merge_metrics(state, tokens, skipped)
    # Entra en el semáforo: un endpoint que nadie puede llamar deja el contrato
    # incompleto por mucho que el documento sea válido.
    metrics["endpoints_unauthorized"] = len(unauthorized_endpoints(endpoints, matriz))
    return {
        "authorization_matrix": matriz,
        "endpoints": endpoints,
        "map_observations": list(state.get("map_observations") or []) + observaciones,
        "metrics": metrics,
    }


async def node_rule_mapping(state: ApiState, config: RunnableConfig) -> dict:
    """RULE_MAPPING: destino de cada BR-/VAL-, cerrando el círculo que abrió el BD."""
    mapeos, delegadas, skipped, tokens, observaciones = await run_rule_mapping(
        _llm(config),
        state.get("endpoints") or [],
        state.get("schemas") or [],
        state.get("authorization_matrix") or [],
        state.get("sources") or {},
        authoritative_context=state.get("authoritative_context"),
    )
    return {
        "rule_mappings": mapeos,
        # Reglas que el modelo de datos delegó y que nadie recoge: QUESTION_GEN
        # las convierte en preguntas bloqueantes.
        "unenforced_delegated_rules": delegadas,
        "map_observations": list(state.get("map_observations") or []) + observaciones,
        "metrics": merge_metrics(state, tokens, skipped),
    }


async def node_errors(state: ApiState) -> dict:
    """ERRORS: catálogo y códigos por endpoint, desde el modelo de datos y la matriz."""
    endpoints = list(state.get("endpoints") or [])
    catalogo = apply_errors(
        endpoints,
        state.get("resource_map") or {},
        state.get("sources") or {},
        state.get("authorization_matrix") or [],
    )
    return {"error_catalog": catalogo, "endpoints": endpoints}


async def node_openapi_gen(state: ApiState) -> dict:
    """OPENAPI_GEN: render determinista del documento 3.1 (el LLM no lo toca)."""
    documento, bloque = build_openapi(
        state.get("target") or {},
        state.get("resources") or [],
        state.get("schemas") or [],
        state.get("endpoints") or [],
        state.get("error_catalog") or [],
        state.get("sources") or {},
    )
    return {"openapi": bloque, "openapi_document": documento}


async def node_validate(state: ApiState) -> dict:
    """VALIDATE: L1 estructural + L2 del esquema + L2b round-trip, sin LLM."""
    documento = state.get("openapi_document") or {}
    bloque = state.get("openapi") or {}
    validacion = validate_spec(
        documento,
        bloque.get("content", ""),
        state.get("endpoints") or [],
        state.get("schemas") or [],
        (state.get("resource_map") or {}).get("resources") or [],
        state.get("authorization_matrix") or [],
        state.get("error_catalog") or [],
        unenforced_delegated_rules=state.get("unenforced_delegated_rules") or [],
        base_path=(state.get("target") or {}).get("base_path") or "/api/v1",
    )
    metrics = dict(state.get("metrics") or {})
    metrics["spec_valid"] = bool(validacion["spec_valid"])
    return {"validation": validacion, "metrics": metrics}


async def node_critique(state: ApiState, config: RunnableConfig) -> dict:
    """CRITIQUE: cobertura que enumera lo que falta + riesgos por LLM."""
    critique, skipped, tokens, observaciones = await run_critique(
        _llm(config),
        state.get("resource_map") or {},
        state.get("endpoints") or [],
        state.get("schemas") or [],
        state.get("authorization_matrix") or [],
        state.get("rule_mappings") or [],
        state.get("target") or {},
        state.get("sources") or {},
        unenforced_delegated_rules=state.get("unenforced_delegated_rules") or [],
        validation=state.get("validation") or {},
        authoritative_context=state.get("authoritative_context"),
    )
    metrics = merge_metrics(state, tokens, skipped)
    metrics["coverage"] = critique["coverage_ratio"]
    return {
        "critique": critique,
        "map_observations": list(state.get("map_observations") or []) + observaciones,
        "metrics": metrics,
    }


async def node_reconcile(state: ApiState, config: RunnableConfig) -> dict:
    """RECONCILE: contrasta los endpoints propuestos con la API ya existente (INV4).

    Un endpoint ``reuse`` es una operación que el sistema destino YA expone: el
    Agente Backend no tiene que construirla, y el Frontend puede consumirla hoy.
    Proponerla como nueva duplicaría la operación con otra ruta.

    Nunca tumba el pipeline: sin inventario, la fase se declara no ejecutada.
    """
    endpoints = state.get("endpoints") or []
    reconcile = (config or {}).get("configurable", {}).get("reconcile_endpoints")
    reconcile = reconcile or reconcile_endpoints

    veredictos, resumen = await reconcile(
        endpoints, system_id=state.get("target_system_id")
    )
    for endpoint in endpoints:
        veredicto = veredictos.get(endpoint["id"])
        if veredicto is not None:
            endpoint["reconciliation"] = veredicto
    return {"endpoints": endpoints, "reconciliation": resumen}


async def node_question_gen(state: ApiState) -> dict:
    """QUESTION_GEN: preguntas al líder técnico, agrupadas por clase de vacío."""
    critique = state.get("critique") or {}
    endpoints = state.get("endpoints") or []
    questions = generate_questions(
        critique.get("findings") or {},
        endpoints,
        state.get("schemas") or [],
        state.get("resource_map") or {},
        state.get("target") or {},
    )
    # RECONCILE (INV4): un endpoint que se parece a uno existente sin serlo
    # claramente lo decide el líder técnico, no el agente.
    veredictos = {
        e["id"]: e["reconciliation"] for e in endpoints if e.get("reconciliation")
    }
    questions.extend(
        conflict_questions(
            veredictos, endpoints, audience="tecnico", prefijo="QAPI-REC"
        )
    )
    return {"questions": questions}


async def node_assemble(state: ApiState) -> dict:
    """ASSEMBLE + VALIDATE: construye el ApiArtifact y lo valida (v1.0.0)."""
    artifact, _ = assemble_artifact(state)
    dumped = artifact.model_dump(mode="json")
    validate_artifact(dumped)
    return {"artifact": dumped}


async def node_persist(state: ApiState, config: RunnableConfig) -> dict:
    """PERSIST: guarda el artefacto y marca COMPLETED[_WITH_WARNINGS].

    La persistencia es inyectable por config (tests sin Postgres); si no se
    inyecta, usa la BD real vía ``session_scope``.
    """
    artifact = state["artifact"]
    metrics = artifact.get("metrics") or {}
    validation = artifact.get("validation") or {}
    # Una especificación con errores no puede pasar por COMPLETED limpio.
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

    return {"status": status, "metrics": metrics}
