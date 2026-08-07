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

from ai.agents.api.common import merge_metrics
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
from ai.agents.api.payloads import run_schemas
from ai.agents.api.resource_map import build_resource_map
from ai.agents.api.resources import run_resources
from ai.agents.api.state import ApiState
from ai.agents.base.structured import ClaudeLLMClient
from ai.knowledge import load_api_conventions
from app.config.settings import settings


def _llm(config: RunnableConfig):
    """LLM inyectado por config (mock en tests); si no, el cliente real."""
    llm = (config or {}).get("configurable", {}).get("llm")
    return llm if llm is not None else ClaudeLLMClient()


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
    """AUTHORIZATION (API5): matriz desde CRUD + alcances desde las reglas."""
    return {"authorization_matrix": []}


async def node_rule_mapping(state: ApiState, config: RunnableConfig) -> dict:
    """RULE_MAPPING (API5): destino de cada BR-/VAL-, cerrando el círculo del BD."""
    return {"rule_mappings": []}


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
    """OPENAPI_GEN (API6): render determinista del documento 3.1."""
    return {"openapi": {}}


async def node_validate(state: ApiState) -> dict:
    """VALIDATE (API6): L1 estructural + L2 de la especificación, sin LLM."""
    return {"validation": {}}


async def node_critique(state: ApiState, config: RunnableConfig) -> dict:
    """CRITIQUE (API7): cobertura determinista + riesgos por LLM."""
    return {"critique": {}}


async def node_question_gen(state: ApiState) -> dict:
    """QUESTION_GEN (API7): preguntas agrupadas por clase de vacío."""
    return {"questions": []}


async def node_assemble(state: ApiState) -> dict:
    """ASSEMBLE (API8): ensambla el ApiArtifact y valida el contrato."""
    return {"artifact": {}}


async def node_persist(state: ApiState, config: RunnableConfig) -> dict:
    """PERSIST (API8): guarda artefacto y métricas reales."""
    return {"status": "COMPLETED"}
