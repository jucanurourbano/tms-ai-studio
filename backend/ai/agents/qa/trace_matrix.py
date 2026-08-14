"""Nodo TRACE_MATRIX: matriz de trazabilidad y cobertura. **Sin LLM.**

Producto de ``CRITERION_MAP`` × ``test_cases``: cada criterio que existe es una fila,
tenga casos o no. Que sea determinista no es una optimización — es lo que hace que la
cobertura sea **auditable**. Si el número lo produjera el modelo, un plan con huecos
podría presentarse como completo y nadie tendría con qué contrastarlo.

Tres estados por fila, y la diferencia entre los dos últimos importa:

- ``covered`` — tiene al menos un caso.
- ``uncovered`` — no tiene ninguno, y nadie dijo por qué. Es un **hueco**.
- ``not_testable`` — no tiene ninguno **porque se declaró no verificable**, con su
  pregunta al QA lead. Es una decisión, no un olvido.

Un plan que confundiera esos dos estados perdería la única información que permite
saber si falta trabajo o falta una respuesta.

La cadena completa que reconstruye: ``REQ-F- → US- → AC- → TC-``. Los requisitos
salen de ``story.source_refs.requirement_refs``, así que un RF sin ningún caso es un
**hallazgo** (``Risk``) y no una simple advertencia: significa que algo que el
negocio pidió no se va a comprobar.
"""

from typing import Any

from .schemas.enums import CoverageStatus


def build_trace_matrix(
    criterion_map: dict[str, Any],
    test_cases: list[dict[str, Any]],
    not_testable: list[dict[str, Any]],
    questions_by_criterion: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Construye la matriz y su resumen de cobertura.

    ``questions_by_criterion`` enlaza cada criterio no verificable con la pregunta
    que lo respalda. Sin ese enlace el contrato rechaza la fila: "no se puede probar"
    sin destinatario sería una excusa.
    """
    preguntas = questions_by_criterion or {}
    no_verificables = {n.get("criterion_ref"): n for n in not_testable or []}

    casos_por_criterio: dict[str, list[str]] = {}
    for caso in test_cases or []:
        casos_por_criterio.setdefault(caso.get("criterion_ref"), []).append(caso["id"])

    filas: list[dict[str, Any]] = []
    huerfanos: list[str] = []
    no_verificables_refs: list[str] = []
    requisitos_totales: set[str] = set()
    requisitos_cubiertos: set[str] = set()
    historias: set[str] = set()
    historias_cubiertas: set[str] = set()
    bloqueantes_total = 0
    bloqueantes_cubiertos = 0

    for entrada in criterion_map.get("entries", []) or []:
        ref = entrada["criterion_ref"]
        ids = sorted(casos_por_criterio.get(ref, []))
        requisitos = list(entrada.get("requirement_refs") or [])
        requisitos_totales.update(requisitos)
        historias.add(entrada["story_ref"])

        if ids:
            estado = CoverageStatus.COVERED.value
            requisitos_cubiertos.update(requisitos)
            historias_cubiertas.add(entrada["story_ref"])
        elif ref in no_verificables:
            estado = CoverageStatus.NOT_TESTABLE.value
            no_verificables_refs.append(ref)
        else:
            estado = CoverageStatus.UNCOVERED.value
            huerfanos.append(ref)

        if entrada.get("blocking"):
            bloqueantes_total += 1
            if ids:
                bloqueantes_cubiertos += 1

        filas.append(
            {
                "requirement_refs": requisitos,
                "story_ref": entrada["story_ref"],
                "criterion_ref": ref,
                "story_priority": entrada.get("story_priority"),
                "test_case_ids": ids,
                "status": estado,
                "question_ref": (
                    preguntas.get(ref)
                    if estado == CoverageStatus.NOT_TESTABLE.value
                    else None
                ),
            }
        )

    total = len(filas)
    cubiertos = sum(1 for f in filas if f["status"] == CoverageStatus.COVERED.value)
    cobertura = {
        "criteria_total": total,
        "criteria_covered": cubiertos,
        "criteria_ratio": (cubiertos / total) if total else 0.0,
        "uncovered_criterion_refs": huerfanos,
        "not_testable_criterion_refs": no_verificables_refs,
        "blocking_criteria_total": bloqueantes_total,
        "blocking_criteria_covered": bloqueantes_cubiertos,
        "stories_total": len(historias),
        "stories_covered": len(historias_cubiertas),
        "uncovered_story_refs": sorted(historias - historias_cubiertas),
        "requirements_total": len(requisitos_totales),
        "requirements_covered": len(requisitos_cubiertos),
        "uncovered_requirement_refs": sorted(requisitos_totales - requisitos_cubiertos),
    }

    return {
        "rows": filas,
        "coverage": cobertura,
        "orphan_criterion_refs": huerfanos,
    }


def blocking_coverage_ratio(coverage: dict[str, Any]) -> float:
    """Cobertura de los criterios que entran en el semáforo (``must``/``should``).

    Si no hay ninguno, devuelve 1.0: un plan sin criterios bloqueantes no está
    incompleto por eso. Devolver 0.0 dejaría en rojo un plan que no tiene nada que
    cubrir, que es un falso negativo tan malo como el contrario.
    """
    total = coverage.get("blocking_criteria_total", 0)
    if not total:
        return 1.0
    return coverage.get("blocking_criteria_covered", 0) / total


def uncovered_requirements_risks(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    """Un RF sin ningún caso es un hallazgo: el negocio lo pidió y nadie lo probará."""
    riesgos = []
    for i, ref in enumerate(coverage.get("uncovered_requirement_refs") or [], start=1):
        riesgos.append(
            {
                "id": f"RSK-REQ-{i:03d}",
                "description": (
                    f"El requisito {ref} no tiene ningún caso de prueba: quedaría "
                    "sin comprobar en el entregable."
                ),
                "severity": "alta",
                "mitigation": (
                    "Revisar si la historia que lo cubre tiene criterios de "
                    "aceptación suficientes, o completar el plan."
                ),
                "source_ref": ref,
                "origin": "derived",
            }
        )
    return riesgos
