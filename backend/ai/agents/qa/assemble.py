"""Fase ASSEMBLE + VALIDATE del Agente QA.

Ensambla el ``QaArtifact`` desde el estado del grafo, calcula métricas reales y
registra los descartes como ``Observation`` (NUNCA silenciosos, regla heredada del
EF). ``validate_artifact`` revalida contra el esquema v1.0.0.

Un ítem que no valide contra el contrato **se descarta con su motivo** en vez de
tumbar el job. Las invariantes que de verdad importan ya viven dentro del contrato
—un caso sin criterio, un borde sin evidencia, una autorización sin regla—, así que
si un ítem cae aquí es porque violaba una de ellas, y la observación resultante lo
dice con el error completo. Entregar el resto del plan señalando la pieza rota es
más útil que no entregar nada: el equipo puede ejecutar 40 casos buenos mientras se
corrige el que falló.

Con una excepción que sí importa aquí: si un caso de tipo ``authorization`` cae
porque no hay contrato de API, el descarte es **correcto y necesario** —es el
contrato negándose a representar una suposición sobre quién puede ver qué—, y la
observación lo dice con esas palabras para que nadie lo lea como un bug.
"""

import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.dependencies.claude import estimate_cost

from .schemas.artifact import (
    Coverage,
    Dataset,
    ExecutionPlan,
    Observation,
    QaAnalysis,
    QaArtifact,
    QaMetrics,
    QaQuestion,
    Risk,
    SkippedItem,
    SourceRef,
    Target,
    TestCase,
    TokenMetrics,
    TraceMatrix,
)


def _map_list(
    raw_items: list, model: type[BaseModel], discards: list[dict], stage: str
) -> list[BaseModel]:
    """Valida cada ítem; los inválidos se descartan dejando una Observation."""
    out: list[BaseModel] = []
    for raw in raw_items or []:
        try:
            out.append(model.model_validate(raw))
        except ValidationError as exc:
            out_id = raw.get("id") if isinstance(raw, dict) else "?"
            discards.append(
                {
                    "description": f"Ítem descartado en {stage} (id={out_id}).",
                    "reason": str(exc)[:300],
                }
            )
    return out


def _build_source(state: dict[str, Any]) -> SourceRef:
    """Bloque ``source``, con la dependencia opcional declarada como quedó."""
    hashes = state.get("hashes") or {}
    disponible = bool(state.get("api_available"))
    return SourceRef(
        scrum_job_id=state.get("scrum_job_id", ""),
        scrum_artifact_hash=hashes.get("scrum_artifact_hash")
        or state.get("scrum_artifact_hash", ""),
        ef_job_id=state.get("ef_job_id", ""),
        ef_artifact_hash=hashes.get("ef_artifact_hash")
        or state.get("ef_artifact_hash", ""),
        api_job_id=state.get("api_job_id") if disponible else None,
        api_artifact_hash=hashes.get("api_artifact_hash") if disponible else None,
        api_schema_version="1.0.0" if disponible else None,
        api_available=disponible,
        api_absent_reason=state.get("api_absent_reason") if not disponible else None,
        ready_snapshot=bool(state.get("scrum_ready", True)),
    )


def assemble_artifact(state: dict[str, Any]) -> tuple[QaArtifact, bool]:
    """Construye el artefacto y devuelve ``(artifact, hubo_avisos)``."""
    discards: list[dict] = []

    casos = _map_list(state.get("test_cases"), TestCase, discards, "test_cases")
    datasets = _map_list(state.get("datasets"), Dataset, discards, "datasets")
    preguntas = _map_list(
        state.get("questions"), QaQuestion, discards, "questions_for_qa_lead"
    )
    riesgos = _map_list(state.get("risks"), Risk, discards, "risks")

    matriz_raw = state.get("trace_matrix") or {}
    try:
        matriz = TraceMatrix.model_validate(matriz_raw)
    except ValidationError as exc:
        # La matriz es el resumen de honestidad del plan: si no valida, se entrega
        # vacía y se dice, en vez de entregar una cobertura que nadie calculó.
        discards.append(
            {
                "description": "La matriz de trazabilidad no validó y se entrega vacía.",
                "reason": str(exc)[:300],
            }
        )
        matriz = TraceMatrix()

    try:
        plan = ExecutionPlan.model_validate(state.get("execution_plan") or {})
    except ValidationError as exc:
        discards.append(
            {
                "description": "El plan de ejecución no validó y se entrega vacío.",
                "reason": str(exc)[:300],
            }
        )
        plan = ExecutionPlan()

    # Un caso de autorización descartado por falta de contrato no es un fallo del
    # ensamblado: es el cortafuegos funcionando. Se dice con esas palabras.
    if not state.get("api_available"):
        intrusos = [
            c.get("id")
            for c in state.get("test_cases") or []
            if c.get("type") == "authorization"
        ]
        if intrusos:
            discards.append(
                {
                    "description": (
                        "Se descartaron casos de autorización porque este plan no "
                        f"tuvo contrato de API: {', '.join(str(i) for i in intrusos)}."
                    ),
                    "reason": (
                        "Sin matriz de autorización, quién puede ver qué sería una "
                        "suposición con la autoridad de un caso de prueba."
                    ),
                }
            )
            casos = [c for c in casos if c.type.value != "authorization"]

    observations: list[Observation] = []
    for indice, nota in enumerate(state.get("map_observations") or [], start=1):
        observations.append(
            Observation(
                id=f"OBS-{indice:03d}",
                description=nota.get("description", ""),
                reason=nota.get("reason"),
                source_ref=nota.get("source_ref"),
            )
        )
    for nota in state.get("observations") or []:
        observations.append(
            Observation(
                id=f"OBS-{len(observations) + 1:03d}",
                description=nota.get("description", ""),
                reason=nota.get("reason"),
                source_ref=nota.get("source_ref"),
            )
        )
    for extra in discards:
        observations.append(
            Observation(
                id=f"OBS-D-{len(observations) + 1:03d}",
                description=extra.get("description", ""),
                reason=extra.get("reason"),
            )
        )

    cobertura = matriz.coverage or Coverage()
    analysis = QaAnalysis(risks=riesgos, observations=observations, coverage=cobertura)

    metrics_in = dict(state.get("metrics") or {})
    tokens = metrics_in.get("tokens") or {"input": 0, "output": 0, "total": 0}
    duration = max(0.0, time.time() - state.get("started_at", time.time()))
    skipped = metrics_in.get("skipped") or []
    bloqueantes = [q for q in preguntas if q.blocking and q.status.value == "pendiente"]

    metrics = QaMetrics(
        tokens=TokenMetrics(**tokens),
        cost=estimate_cost(tokens.get("input", 0), tokens.get("output", 0)),
        duration=round(duration, 3),
        test_cases_total=len(casos),
        datasets_total=len(datasets),
        suites_total=len(plan.suites),
        questions_total=len(preguntas),
        blocking_questions_total=len(bloqueantes),
        manual_minutes=plan.totals.manual_minutes,
        coverage=cobertura.criteria_ratio,
        pruned_cases=int(metrics_in.get("pruned_cases") or 0),
        skipped=[SkippedItem(**s) for s in skipped],
    )

    artifact = QaArtifact(
        source=_build_source(state),
        target=Target.model_validate(state.get("target") or {}),
        test_cases=casos,
        trace_matrix=matriz,
        datasets=datasets,
        execution_plan=plan,
        questions_for_qa_lead=preguntas,
        analysis=analysis,
        metrics=metrics,
    )

    has_warnings = bool(skipped) or bool(discards)
    return artifact, has_warnings


def validate_artifact(artifact_dict: dict) -> QaArtifact:
    """VALIDATE: revalida el artefacto contra el esquema v1.0.0."""
    return QaArtifact.model_validate(artifact_dict)
