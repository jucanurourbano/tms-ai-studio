"""Nodo CRITIQUE: revisa el plan terminado y reporta lo que no cuadra.

Parte determinista (siempre): duplicados, huecos de cobertura, ciclos de
dependencias entre suites, referencias que no resolvieron y casos que quedaron en
cuarentena. Nada de esto invalida el plan — **lo describe**. Un artefacto que se
negara a representar un plan incompleto impediría al agente reportar que está
incompleto, que es justo su trabajo.

Parte con LLM (opcional y mockeable): un pase de riesgos que mira el plan como un
todo y señala lo que las comprobaciones mecánicas no ven —un área del negocio con
mucha regla y poco caso, una dependencia de datos entre suites que el orden no
resuelve—. Si el modelo falla, el nodo sigue: se pierde matiz, no correctitud.
"""

import json
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ai.agents.arquitectura.schemas.enums import RiskSeverity
from ai.agents.base.structured import LLMClient, complete_structured
from ai.tools.chunker import estimate_tokens

from .common import knowledge_block
from .consolidate import find_duplicates
from .prompts import build_system
from .trace_matrix import blocking_coverage_ratio


class _RiskExtract(BaseModel):
    """Riesgo propuesto por el pase LLM (estrecho: no puede tocar el plan)."""

    model_config = ConfigDict(extra="forbid")

    description: str
    severity: str = "media"
    mitigation: Optional[str] = None
    source_ref: Optional[str] = None


class _RisksExtract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risks: list[_RiskExtract] = Field(default_factory=list)


#: Severidades válidas, derivadas del enum compartido en vez de reescritas: una
#: lista propia se desincronizaría del contrato en el primer cambio, y el síntoma
#: sería un riesgo real rechazado al validar el artefacto.
_SEVERIDADES = tuple(s.value for s in RiskSeverity)

#: Severidad máxima disponible. ``RiskSeverity`` no tiene "crítica": lo más grave
#: que puede declarar un riesgo del ISDF es ``alta``.
_MAXIMA = RiskSeverity.ALTA.value


def deterministic_findings(
    test_cases: list[dict[str, Any]],
    trace_matrix: dict[str, Any],
    execution_plan: dict[str, Any],
    criterion_map: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Comprobaciones mecánicas del plan. Devuelve riesgos y observaciones."""
    riesgos: list[dict[str, Any]] = []
    observaciones: list[dict[str, Any]] = []
    cobertura = trace_matrix.get("coverage") or {}

    # --- Duplicados: dos casos que ejecutan lo mismo ---
    for grupo in find_duplicates(test_cases):
        observaciones.append(
            {
                "description": (
                    f"Los casos {', '.join(grupo)} ejecutan los mismos pasos con los "
                    "mismos datos sobre el mismo criterio: son el mismo caso escrito "
                    "más de una vez."
                ),
                "reason": "Duplicado: no añade cobertura, añade tiempo de ejecución.",
            }
        )

    # --- Cobertura bloqueante por debajo del umbral ---
    ratio = blocking_coverage_ratio(cobertura)
    if ratio < 1.0:
        riesgos.append(
            {
                "id": "RSK-COV-001",
                "description": (
                    "La cobertura de criterios de historias must/should es del "
                    f"{ratio:.0%}: hay definición de terminado sin ninguna prueba "
                    "que la respalde."
                ),
                "severity": _MAXIMA,
                "mitigation": (
                    "Responder las preguntas al QA lead y regenerar el plan, o "
                    "completar los criterios que faltan en el plan Scrum."
                ),
                "origin": "derived",
            }
        )

    # --- Ciclos de dependencias heredados del plan Scrum ---
    for ciclo in execution_plan.get("dependency_cycles") or []:
        riesgos.append(
            {
                "id": f"RSK-CYC-{'-'.join(ciclo[:2])}",
                "description": (
                    "Hay un ciclo de dependencias entre historias que impide fijar un "
                    f"orden de ejecución completo: {' → '.join(ciclo)}."
                ),
                "severity": "media",
                "mitigation": (
                    "Romper el ciclo en el plan Scrum; el orden de las suites se "
                    "recalcula solo."
                ),
                "source_ref": ciclo[0] if ciclo else None,
                "origin": "derived",
            }
        )

    # --- Referencias citadas que el EF no reconoce ---
    no_resueltas = sorted(
        {
            ref
            for entrada in criterion_map.get("entries") or []
            for ref in entrada.get("unresolved_refs") or []
        }
    )
    if no_resueltas:
        observaciones.append(
            {
                "description": (
                    "Los criterios del plan citan referencias que no existen en el "
                    f"EF: {', '.join(no_resueltas)}."
                ),
                "reason": (
                    "Viene del plan Scrum, no del diseño de pruebas; se reporta para "
                    "que se corrija en origen."
                ),
            }
        )

    # --- Cuarentena: criterios que el modelo no supo responder ---
    for saltado in metrics.get("skipped") or []:
        observaciones.append(
            {
                "description": (
                    f"El criterio {saltado.get('ref')} quedó sin casos en la etapa "
                    f"{saltado.get('stage')}: {saltado.get('reason')}"
                ),
                "reason": "Cuarentena del map: el criterio aparece como hueco.",
                "source_ref": saltado.get("ref"),
            }
        )

    # --- Un plan sin casos ---
    if not test_cases:
        riesgos.append(
            {
                "id": "RSK-EMPTY-001",
                "description": (
                    "El plan no tiene ningún caso de prueba: no hay nada que ejecutar."
                ),
                "severity": _MAXIMA,
                "origin": "derived",
            }
        )

    return {"risks": riesgos, "observations": observaciones}


async def llm_risks(
    llm: LLMClient,
    test_cases: list[dict[str, Any]],
    trace_matrix: dict[str, Any],
    execution_plan: dict[str, Any],
    *,
    authoritative_context: Optional[str] = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Pase de riesgos sobre el plan completo. Ante fallo, sin riesgos."""
    payload = {
        "coverage": trace_matrix.get("coverage") or {},
        "totals": execution_plan.get("totals") or {},
        "cases": [
            {
                "id": c["id"],
                "type": c.get("type"),
                "priority": c.get("priority"),
                "criterion_ref": c.get("criterion_ref"),
                "title": c.get("title"),
            }
            for c in test_cases
        ][:80],
        "suites": [
            {
                "id": s["id"],
                "epic_ref": s.get("epic_ref"),
                "cases": len(s.get("test_case_ids") or []),
                "minutes": s.get("estimated_minutes"),
            }
            for s in execution_plan.get("suites") or []
        ],
    }
    system = build_system("critique.md", knowledge_block(authoritative_context))
    user = "PLAN CONSOLIDADO:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    modelo, _error = await complete_structured(
        llm,
        system=system,
        user=user,
        schema=_RisksExtract,
        stage="CRITIQUE",
    )
    tokens = {"input": estimate_tokens(system + user), "output": 0}
    if modelo is None:
        tokens["total"] = tokens["input"]
        return [], tokens

    riesgos = []
    for i, riesgo in enumerate(modelo.risks, start=1):
        severidad = riesgo.severity if riesgo.severity in _SEVERIDADES else "media"
        riesgos.append(
            {
                "id": f"RSK-LLM-{i:03d}",
                "description": riesgo.description,
                "severity": severidad,
                "mitigation": riesgo.mitigation,
                "source_ref": riesgo.source_ref,
                "origin": "derived",
            }
        )
    tokens["output"] = estimate_tokens(json.dumps(riesgos, ensure_ascii=False))
    tokens["total"] = tokens["input"] + tokens["output"]
    return riesgos, tokens
