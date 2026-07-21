"""Fase EXTRACT: map por dimensiones sobre los chunks, con structured output.

- Concurrencia configurable (default 3).
- Loop de reparación ante schema inválido.
- Si tras reparar sigue inválido: cuarentena en ``skipped`` (nunca tumba el job).
- En single_shot hay un único chunk: un solo pase por todas las dimensiones.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel

from ai.agents.base.structured import ClaudeLLMClient, LLMClient, complete_structured
from ai.knowledge import glossary_block
from ai.tools.chunker import estimate_tokens

from .prompts import build_system, build_user
from .schemas.extraction import (
    ActorsExtract,
    FieldsExtract,
    ModulesMenusExtract,
    ProcessesExtract,
    RequirementsExtract,
    RulesValidationsExtract,
)

# ``LLMClient`` y ``ClaudeLLMClient`` viven ahora en la base compartida
# (``ai/agents/base/structured.py``); se re-exportan para no romper imports.
__all__ = [
    "ClaudeLLMClient",
    "DIMENSIONS",
    "Dimension",
    "LLMClient",
    "extract_dimension",
    "run_extract",
]


@dataclass(frozen=True)
class Dimension:
    """Dimensión de extracción: nombre, esquema de validación y prompt."""

    name: str
    schema: type[BaseModel]
    prompt_file: str


DIMENSIONS: list[Dimension] = [
    Dimension("requirements", RequirementsExtract, "requirements.md"),
    Dimension("actors", ActorsExtract, "actors.md"),
    Dimension("modules_menus", ModulesMenusExtract, "modules_menus.md"),
    Dimension("processes", ProcessesExtract, "processes.md"),
    Dimension("rules_validations", RulesValidationsExtract, "rules_validations.md"),
    Dimension("fields", FieldsExtract, "fields.md"),
]


async def extract_dimension(
    llm: LLMClient,
    dimension: Dimension,
    context: str,
    text: str,
    glossary_ctx: str,
    max_repairs: int = 2,
) -> Optional[BaseModel]:
    """Extrae una dimensión de un fragmento, reparando si el schema falla.

    Delega el loop de reparación en la base compartida (``complete_structured``);
    el ``None`` indica cuarentena (irreparable).
    """
    system = build_system(dimension.prompt_file, glossary_ctx)
    user = build_user(context, text)
    model, _error = await complete_structured(
        llm,
        system=system,
        user=user,
        schema=dimension.schema,
        max_repairs=max_repairs,
    )
    return model


async def run_extract(
    llm: LLMClient,
    chunks: list[dict],
    *,
    glossary_ctx: Optional[str] = None,
    concurrency: int = 3,
    max_repairs: int = 2,
    dimensions: Optional[list[Dimension]] = None,
    authoritative_context: Optional[str] = None,
) -> tuple[list[dict], list[dict], dict]:
    """Ejecuta EXTRACT como map (chunk × dimensión) con concurrencia limitada.

    ``authoritative_context`` (ciclo de afinamiento) se antepone al glosario.
    Devuelve (results, skipped, token_stats).
    """
    glossary_ctx = glossary_ctx if glossary_ctx is not None else glossary_block()
    if authoritative_context:
        glossary_ctx = (
            "CONTEXTO AUTORITATIVO (respuestas del analista, tienen prioridad):\n"
            f"{authoritative_context}\n\n" + glossary_ctx
        )
    dimensions = dimensions or DIMENSIONS

    results: list[dict] = []
    skipped: list[dict] = []
    tokens = {"input": 0, "output": 0}
    semaphore = asyncio.Semaphore(concurrency)

    async def worker(chunk: dict, dimension: Dimension) -> None:
        system = build_system(dimension.prompt_file, glossary_ctx)
        user = build_user(chunk.get("context", ""), chunk.get("text", ""))
        async with semaphore:
            # Se llama a ``complete_structured`` en vez de ``extract_dimension``
            # para conservar el ERROR real y reportarlo en la cuarentena (antes
            # se descartaba, dejando "schema inválido" sin detalle en la BD).
            validated, error = await complete_structured(
                llm,
                system=system,
                user=user,
                schema=dimension.schema,
                max_repairs=max_repairs,
            )
        # Estimación de tokens (real vía usage no disponible con mocks; ver CLAUDE.md).
        tokens["input"] += estimate_tokens(system + user)
        if validated is None:
            skipped.append(
                {
                    "ref": f"{chunk['chunk_id']}:{dimension.name}",
                    "stage": "EXTRACT",
                    "reason": f"schema inválido tras reparación: {error[:200]}",
                }
            )
        else:
            dumped = validated.model_dump(mode="json")
            tokens["output"] += estimate_tokens(json.dumps(dumped, ensure_ascii=False))
            results.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "dimension": dimension.name,
                    "data": dumped,
                }
            )

    await asyncio.gather(
        *(worker(chunk, dim) for chunk in chunks for dim in dimensions)
    )

    # Orden estable para consolidación/renumeración determinística.
    results.sort(key=lambda r: (r["chunk_id"], r["dimension"]))
    skipped.sort(key=lambda s: s["ref"])
    tokens["total"] = tokens["input"] + tokens["output"]
    return results, skipped, tokens
