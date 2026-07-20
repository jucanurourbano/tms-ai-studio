"""Structured output genérico para los agentes del ISDF.

Extrae el patrón embebido en ``ai/agents/ef/extract.py`` a una base compartida:

- ``LLMClient``: protocolo agnóstico (system + user -> texto JSON crudo).
- ``ClaudeLLMClient``: implementación real sobre ChatAnthropic (import perezoso;
  NUNCA se usa en tests por la REGLA DE PRESUPUESTO).
- ``complete_structured``: una llamada con loop de reparación ante schema inválido.
- ``run_structured_map``: map (ítem × tarea) con concurrencia limitada y cuarentena
  de los ítems irreparables (nunca tumba el job).
"""

import asyncio
import json
from typing import Awaitable, Callable, Optional, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    """Cliente LLM: recibe system+user y devuelve texto JSON crudo."""

    async def complete_json(self, *, system: str, user: str) -> str: ...


def repair_hint(error: str) -> str:
    """Pista de reparación que se anexa al prompt tras un schema inválido."""
    return (
        "\n\nEl intento anterior falló la validación del esquema:\n"
        f"{error}\n"
        "Corrige el JSON y responde SOLO con JSON válido."
    )


async def complete_structured(
    llm: LLMClient,
    *,
    system: str,
    user: str,
    schema: type[T],
    max_repairs: int = 2,
) -> tuple[Optional[T], str]:
    """Llama al LLM y valida contra ``schema``, reparando si falla.

    Devuelve ``(modelo, "")`` si valida, o ``(None, ultimo_error)`` si tras
    ``max_repairs`` reintentos sigue inválido (candidato a cuarentena).
    """
    last_error = ""
    for attempt in range(max_repairs + 1):
        prompt = user if attempt == 0 else user + repair_hint(last_error)
        raw = await llm.complete_json(system=system, user=prompt)
        try:
            return schema.model_validate(json.loads(raw)), ""
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)
    return None, last_error


async def run_structured_map(
    llm: LLMClient,
    items: list[dict],
    *,
    build_system: Callable[[dict], str],
    build_user: Callable[[dict], str],
    schema: type[T],
    ref_of: Callable[[dict], str],
    stage: str,
    estimate_tokens: Callable[[str], int],
    concurrency: int = 3,
    max_repairs: int = 2,
) -> tuple[list[dict], list[dict], dict]:
    """Map genérico con concurrencia + reparación + cuarentena.

    Por cada ítem construye system/user, llama al LLM con structured output y:
    - si valida, agrega ``{"ref", "data"}`` a ``results``;
    - si no, agrega ``{"ref", "stage", "reason"}`` a ``skipped`` (cuarentena).

    Devuelve ``(results, skipped, tokens)`` con tokens estimados (usage real no
    disponible con mocks; ver CLAUDE.md).
    """
    results: list[dict] = []
    skipped: list[dict] = []
    tokens = {"input": 0, "output": 0}
    semaphore = asyncio.Semaphore(concurrency)

    async def worker(item: dict) -> None:
        system = build_system(item)
        user = build_user(item)
        async with semaphore:
            model, error = await complete_structured(
                llm, system=system, user=user, schema=schema, max_repairs=max_repairs
            )
        tokens["input"] += estimate_tokens(system + user)
        if model is None:
            skipped.append(
                {
                    "ref": ref_of(item),
                    "stage": stage,
                    "reason": f"schema inválido tras reparación: {error[:150]}",
                }
            )
        else:
            dumped = model.model_dump(mode="json")
            tokens["output"] += estimate_tokens(json.dumps(dumped, ensure_ascii=False))
            results.append({"ref": ref_of(item), "data": dumped})

    await asyncio.gather(*(worker(item) for item in items))

    results.sort(key=lambda r: r["ref"])
    skipped.sort(key=lambda s: s["ref"])
    tokens["total"] = tokens["input"] + tokens["output"]
    return results, skipped, tokens


class ClaudeLLMClient:
    """Implementación real de ``LLMClient`` sobre ChatAnthropic (import perezoso).

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


# Reexport para tipado explícito de factories.
CoroFactory = Callable[[], Awaitable[str]]
