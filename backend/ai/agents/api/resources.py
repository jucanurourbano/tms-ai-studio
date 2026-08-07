"""Nodo RESOURCES: redacta cada recurso (LLM *map*, una pasada por recurso).

El andamio de RESOURCE_MAP llega ya cerrado: qué recursos hay, cómo se llaman, qué
tabla los respalda y cuánto se publica de cada uno. Este nodo tiene un trabajo
deliberadamente **estrecho**: escribir el nombre para humanos y la descripción
desde el punto de vista de quien va a consumir la API.

Es poco, y es a propósito. La tabla del modelo de datos ya dice *qué guarda*; lo
que aquí se añade es *para qué sirve el recurso*, que es lo que lee un desarrollador
al integrarse. Todo lo que sí decide algo —qué se expone, qué operaciones existen,
qué columnas viajan— ya está fijado antes de llegar aquí, y este nodo **no puede
cambiarlo**: lo que devuelva de más se descarta con una nota.

Un fallo del modelo no pierde un recurso: se cae al nombre y la descripción
deterministas. Perder un recurso por un error de redacción sería absurdo.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .prompts import build_system
from .schemas.extraction import ResourceExtract


def _display_name_fallback(resource: dict) -> str:
    """Nombre para humanos sin LLM: el del recurso, capitalizado."""
    return (resource.get("name") or "").replace("_", " ").capitalize()


def build_resources_user(resource: dict, sources: dict[str, Any]) -> str:
    """Compone el mensaje de un recurso: su andamio + el contexto del EF que lo toca."""
    ef = sources.get("ef", {}) or {}
    entity_ref = resource.get("entity_ref")
    entidad = next(
        (e for e in ef.get("entities", []) or [] if e.get("id") == entity_ref), None
    )
    payload = {
        "resource": {
            "name": resource.get("name"),
            "table_ref": resource.get("table_ref"),
            "entity_ref": entity_ref,
            "exposure": resource.get("exposure"),
            "table_description": resource.get("description"),
            "columns": [
                {
                    "name": col.get("name"),
                    "logical_type": col.get("logical_type"),
                    "description": col.get("description"),
                }
                for col in resource.get("columns", [])
            ],
        },
        "context": {
            "entity": (
                {
                    "id": entidad.get("id"),
                    "name": entidad.get("name"),
                    "description": entidad.get("description"),
                }
                if entidad
                else None
            ),
            # Procesos que mencionan la entidad: dan el "para qué".
            "processes": [
                {"id": p.get("id"), "name": p.get("name"), "steps": p.get("steps")}
                for p in ef.get("processes", []) or []
            ],
        },
    }
    return "RECURSO A DESCRIBIR:\n" + json.dumps(payload, ensure_ascii=False)


def build_resource(resource: dict, extracted: Optional[dict]) -> dict:
    """Ensambla un recurso del artefacto desde su andamio + la salida del modelo."""
    propuesto = extracted or {}
    return {
        "id": resource["id"],
        "name": resource["name"],
        "singular": resource["singular"],
        "display_name": propuesto.get("display_name")
        or _display_name_fallback(resource),
        "description": propuesto.get("description") or resource.get("description"),
        "table_ref": resource["table_ref"],
        "entity_ref": resource.get("entity_ref"),
        "component_ref": resource.get("component_ref"),
        "base_path": f"/{resource['segment']}",
        "exposure": resource["exposure"],
        "exposure_reason": resource.get("exposure_reason"),
        "parent_resource_ref": resource.get("parent_resource_ref"),
        "source_refs": list(resource.get("source_refs") or []),
        "confidence": propuesto.get("confidence"),
        "origin": "derived",
    }


async def run_resources(
    llm: LLMClient,
    resource_map: dict,
    sources: dict[str, Any],
    *,
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
) -> tuple[list[dict], list[dict], dict, list[dict]]:
    """Redacta todos los recursos del andamio.

    Devuelve ``(resources, skipped, tokens, observations)``.
    """
    candidatos = resource_map.get("resources", []) or []
    context_block = knowledge_block(authoritative_context)
    system = build_system("resources.md", context_block)

    results, skipped, tokens = await run_structured_map(
        llm,
        candidatos,
        build_system=lambda _: system,
        build_user=lambda item: build_resources_user(item, sources),
        schema=ResourceExtract,
        ref_of=lambda item: item["id"],
        stage="resources",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
    )

    por_ref = {r["ref"]: r["data"] for r in results}
    observaciones: list[dict] = []
    recursos: list[dict] = []
    for candidato in candidatos:
        extraido = por_ref.get(candidato["id"])
        if extraido is None:
            observaciones.append(
                {
                    "description": (
                        f"El recurso «{candidato['name']}» se describe con los datos "
                        "del modelo de datos."
                    ),
                    "reason": (
                        "La redacción por modelo no fue válida; el recurso se "
                        "conserva con su descripción determinista."
                    ),
                }
            )
        recursos.append(build_resource(candidato, extraido))
    return recursos, skipped, tokens, observaciones
