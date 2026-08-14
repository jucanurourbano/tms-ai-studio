"""Nodo TEST_DESIGN: casos funcionales y negativos (LLM *map*, uno por criterio).

El mapa de criterios llega cerrado desde CRITERION_MAP: cada llamada recibe **un**
criterio con su id, su texto y las reglas del EF que cita. El modelo escribe los
casos; Python decide todo lo que el modelo no debe poder decidir:

- el **criterio de origen** (viene de la tarea, no de la respuesta),
- la **prioridad** (heredada del MoSCoW),
- el **esfuerzo** (tabla determinista),
- los **ids** (concurrentes: dos llamadas propondrían el mismo ``TC-001``),
- la **numeración** de los pasos.

Y verifica lo que el modelo sí propone: las ``source_refs`` se comprueban contra el
EF real, y las que no existen **se quitan del caso con una nota** en vez de invalidar
un caso que por lo demás está bien. Un ref inventado que sobreviviera convertiría el
caso en una cita falsa; tirar el caso entero por una cita de más sería desperdiciar
trabajo correcto.
"""

import json
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import estimated_minutes, knowledge_block, next_id, normalize_steps
from .criterion_map import entry_for
from .prompts import build_system
from .schemas.enums import TestCaseType
from .schemas.extraction import CasesExtract

#: Tope de casos que TEST_DESIGN acepta por criterio. El techo real del plan es
#: ``target.max_cases_per_criterion`` y se aplica al consolidar; este es el límite
#: de lo que se le pide al modelo, para no pagar tokens por casos que se podarán.
MAX_CASES_PER_CALL = 4


def known_refs(sources: dict[str, Any]) -> set[str]:
    """Todos los ids del EF que un caso puede citar legítimamente."""
    ef = sources.get("ef", {}) or {}
    refs: set[str] = set()
    for clave in (
        "functional",
        "business",
        "non_functional",
        "business_rules",
        "validations",
        "fields",
        "entities",
        "actors",
        "processes",
    ):
        for item in ef.get(clave, []) or []:
            if item.get("id"):
                refs.add(item["id"])
    return refs


def build_user(entry: dict[str, Any], sources: dict[str, Any]) -> str:
    """Compone el mensaje de un criterio: su entrada del mapa + contexto del EF."""
    ef = sources.get("ef", {}) or {}
    campos_citados = {v.get("field_ref") for v in entry.get("validations", [])}
    payload = {
        "criterion": {
            "criterion_ref": entry.get("criterion_ref"),
            "story_ref": entry.get("story_ref"),
            "criterion_text": entry.get("criterion_text"),
            "story_statement": entry.get("story_statement"),
            "story_role": entry.get("story_role"),
            "rules": entry.get("rules", []),
            "validations": entry.get("validations", []),
            "requirement_refs": entry.get("requirement_refs", []),
        },
        "context": {
            "fields": [
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "data_type": f.get("data_type"),
                    "required": f.get("required"),
                }
                for f in ef.get("fields", []) or []
                if f.get("id") in campos_citados or not campos_citados
            ][:20],
            "entities": [
                {"id": e.get("id"), "name": e.get("name")}
                for e in ef.get("entities", []) or []
            ][:20],
            "actors": [
                {"id": a.get("id"), "name": a.get("name")}
                for a in ef.get("actors", []) or []
            ][:20],
        },
        "max_cases": MAX_CASES_PER_CALL,
    }
    return "CRITERIO A CUBRIR:\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def _case_from_extract(
    propuesta: dict[str, Any],
    entry: dict[str, Any],
    *,
    case_id: str,
    validos: set[str],
    target: Optional[dict] = None,
) -> tuple[dict[str, Any], list[dict]]:
    """Convierte una propuesta del modelo en un caso del artefacto.

    Devuelve el caso y las observaciones que hayan surgido (refs descartadas).
    """
    observaciones: list[dict] = []
    citadas = propuesta.get("source_refs", []) or []
    reales = [r for r in citadas if r in validos]
    inventadas = [r for r in citadas if r not in validos]
    if inventadas:
        observaciones.append(
            {
                "description": (
                    f"Del caso {case_id} se quitaron referencias que no existen en "
                    f"el EF: {', '.join(sorted(inventadas))}."
                ),
                "reason": "Referencia inexistente en el artefacto de origen.",
                "source_ref": entry.get("criterion_ref"),
            }
        )

    tipo = (
        TestCaseType.NEGATIVE.value
        if propuesta.get("negative")
        else TestCaseType.FUNCTIONAL.value
    )
    prioridad = entry.get("case_priority")
    return (
        {
            "id": case_id,
            "title": propuesta.get("title", ""),
            "story_ref": entry.get("story_ref"),
            "criterion_ref": entry.get("criterion_ref"),
            "epic_ref": entry.get("epic_ref"),
            "type": tipo,
            "preconditions": propuesta.get("preconditions", []) or [],
            "steps": normalize_steps(propuesta.get("steps", []) or []),
            "test_data": [
                {
                    "name": d.get("name", ""),
                    "value": d.get("value", ""),
                    "kind": d.get("kind", "valid"),
                    "field_ref": d.get("field_ref"),
                    "note": d.get("note"),
                }
                for d in propuesta.get("test_data", []) or []
            ],
            "expected_result": propuesta.get("expected_result", ""),
            "priority": prioridad,
            "automation_hint": propuesta.get("automation_hint", "manual"),
            "estimated_minutes": estimated_minutes(tipo, prioridad, target),
            "tags": [],
            "source_refs": reales,
            "confidence": propuesta.get("confidence"),
            # Un caso funcional que reproduce el criterio tal como está escrito es
            # `stated`; un rechazo que hay que deducir de la regla es `derived`.
            "origin": "derived" if propuesta.get("negative") else "stated",
        },
        observaciones,
    )


async def run_test_design(
    llm: LLMClient,
    criterion_map: dict[str, Any],
    sources: dict[str, Any],
    *,
    target: Optional[dict] = None,
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
) -> dict[str, Any]:
    """Ejecuta el *map* y consolida los casos, con sus descartes explicados."""
    entradas = criterion_map.get("entries", []) or []
    if not entradas:
        return {
            "test_cases": [],
            "not_testable": [],
            "observations": [],
            "skipped": [],
            "tokens": {"input": 0, "output": 0, "total": 0},
        }

    system = build_system("test_design.md", knowledge_block(authoritative_context))
    resultados, cuarentena, tokens = await run_structured_map(
        llm,
        entradas,
        build_system=lambda _entry: system,
        build_user=lambda entry: build_user(entry, sources),
        schema=CasesExtract,
        ref_of=lambda entry: entry.get("criterion_ref") or "?",
        stage="TEST_DESIGN",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
    )

    validos = known_refs(sources)
    casos: list[dict[str, Any]] = []
    no_verificables: list[dict[str, Any]] = []
    observaciones: list[dict] = []
    usados: set[str] = set()

    for resultado in resultados:
        entry = entry_for(criterion_map, resultado["ref"])
        if entry is None:
            # No debería ocurrir (el ref viene del propio mapa), pero si ocurriera
            # sería el fallo que este agente no puede permitirse: un caso sin
            # criterio real detrás. Se descarta declarándolo.
            observaciones.append(
                {
                    "description": (
                        f"Se descartaron los casos del criterio {resultado['ref']}: "
                        "no está en el mapa de criterios del plan."
                    ),
                    "reason": "Criterio inexistente (invención).",
                }
            )
            continue

        data = resultado["data"]
        if data.get("not_testable"):
            no_verificables.append(
                {
                    "criterion_ref": entry["criterion_ref"],
                    "story_ref": entry["story_ref"],
                    "reason": data.get("not_testable_reason")
                    or "El criterio no describe un resultado observable.",
                    "blocking": entry.get("blocking", False),
                }
            )
            continue

        for propuesta in (data.get("cases") or [])[:MAX_CASES_PER_CALL]:
            case_id = next_id("TC", usados)
            usados.add(case_id)
            caso, obs = _case_from_extract(
                propuesta,
                entry,
                case_id=case_id,
                validos=validos,
                target=target,
            )
            casos.append(caso)
            observaciones.extend(obs)

    # Los criterios que el modelo no respondió (cuarentena) tampoco se pierden:
    # quedan sin casos y TRACE_MATRIX los verá como huecos, con la cuarentena en
    # métricas explicando por qué.
    return {
        "test_cases": casos,
        "not_testable": no_verificables,
        "observations": observaciones,
        "skipped": cuarentena,
        "tokens": tokens,
    }
