"""Fase EXTRACT: map por dimensiones sobre los chunks, con structured output.

- Concurrencia configurable (default 3).
- Loop de reparación ante schema inválido.
- Si tras reparar sigue inválido: cuarentena en ``skipped`` (nunca tumba el job).
- En single_shot hay un único chunk: un solo pase por todas las dimensiones.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Optional, Protocol

from pydantic import BaseModel, ValidationError

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


class LLMClient(Protocol):
    """Cliente LLM: recibe system+user y devuelve texto JSON crudo."""

    async def complete_json(self, *, system: str, user: str) -> str: ...


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


def _repair_hint(error: str) -> str:
    return (
        "\n\nEl intento anterior falló la validación del esquema:\n"
        f"{error}\n"
        "Corrige el JSON y responde SOLO con JSON válido."
    )


async def extract_dimension(
    llm: LLMClient,
    dimension: Dimension,
    context: str,
    text: str,
    glossary_ctx: str,
    max_repairs: int = 2,
) -> Optional[BaseModel]:
    """Extrae una dimensión de un fragmento, reparando si el schema falla."""
    system = build_system(dimension.prompt_file, glossary_ctx)
    user = build_user(context, text)
    last_error = ""

    for attempt in range(max_repairs + 1):
        prompt = user if attempt == 0 else user + _repair_hint(last_error)
        raw = await llm.complete_json(system=system, user=prompt)
        try:
            data = json.loads(raw)
            return dimension.schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)

    return None  # irreparable -> cuarentena


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
            validated = await extract_dimension(
                llm,
                dimension,
                chunk.get("context", ""),
                chunk.get("text", ""),
                glossary_ctx,
                max_repairs=max_repairs,
            )
        # Estimación de tokens (real vía usage no disponible con mocks; ver CLAUDE.md).
        tokens["input"] += estimate_tokens(system + user)
        if validated is None:
            skipped.append(
                {
                    "ref": f"{chunk['chunk_id']}:{dimension.name}",
                    "stage": "EXTRACT",
                    "reason": "schema inválido tras reparación",
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


class ClaudeLLMClient:
    """Implementación real de LLMClient sobre ChatAnthropic (import perezoso).

    No se usa en tests (REGLA DE PRESUPUESTO): allí se inyecta un mock.
    """

    def __init__(self, client=None) -> None:
        self._client = client

    async def complete_json(self, *, system: str, user: str) -> str:
        from app.dependencies.claude import call_with_retry, get_claude_client

        client = self._client or get_claude_client()

        async def _call() -> str:
            msg = await client.ainvoke([("system", system), ("user", user)])
            return msg.content if isinstance(msg.content, str) else str(msg.content)

        return await call_with_retry(_call)
