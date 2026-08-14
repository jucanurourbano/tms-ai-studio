"""Consolidación de los casos: techo por criterio y detección de duplicados.

Vive **antes** de DATASET/TRACE_MATRIX/EXEC_PLAN, y no en CRITIQUE, por una razón
mecánica: si el techo se aplicara después de calcular la matriz y el plan, ambos
quedarían contando casos que ya no existen. Un plan de pruebas cuyo total no cuadra
con su lista de casos es peor que uno recortado, porque nadie sabe cuál de los dos
números creer.

El techo (``target.max_cases_per_criterion``) existe por aritmética: 40 historias ×
5 criterios × 4 tipos son 800 casos, y cada caso de más es tiempo de una persona
ejecutándolo. Al podar se conserva **diversidad de tipos antes que cantidad** —un
funcional, un negativo, un borde y una autorización informan más que cuatro
funcionales— y **todo lo que se cae deja `Observation` con su id**. Un tope
silencioso se leería como cobertura completa, que es exactamente la mentira que este
agente no puede permitirse.
"""

from typing import Any, Optional

from .schemas.artifact import Target
from .schemas.enums import TestCaseType

#: Orden de preferencia al podar: primero se asegura uno de cada tipo. El
#: funcional va primero porque sin camino feliz el criterio no está probado en
#: absoluto; la autorización va antes que el borde porque un permiso mal puesto se
#: despliega y un borde mal puesto suele saltar en la primera prueba manual.
_PREFERENCIA = (
    TestCaseType.FUNCTIONAL.value,
    TestCaseType.NEGATIVE.value,
    TestCaseType.AUTHORIZATION.value,
    TestCaseType.BOUNDARY.value,
)


def _clave_duplicado(caso: dict[str, Any]) -> tuple:
    """Identidad de un caso a efectos de duplicado: qué hace, no cómo se llama.

    Dos casos con títulos distintos que ejecutan los mismos pasos sobre los mismos
    datos son el mismo caso escrito dos veces. Comparar por título dejaría pasar
    justo los duplicados que cuestan tiempo.
    """
    pasos = tuple(
        (p.get("action") or "").strip().casefold() for p in caso.get("steps") or []
    )
    datos = tuple(
        sorted(
            (d.get("name") or "", str(d.get("value", "")))
            for d in caso.get("test_data") or []
        )
    )
    return (caso.get("criterion_ref"), caso.get("type"), pasos, datos)


def find_duplicates(test_cases: list[dict[str, Any]]) -> list[list[str]]:
    """Grupos de casos que hacen lo mismo. Se reportan; no se borran aquí."""
    vistos: dict[tuple, list[str]] = {}
    for caso in test_cases or []:
        vistos.setdefault(_clave_duplicado(caso), []).append(caso["id"])
    return [ids for ids in vistos.values() if len(ids) > 1]


def apply_case_cap(
    test_cases: list[dict[str, Any]], target: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Aplica el techo por criterio conservando diversidad de tipos."""
    techo = int(
        (target or {}).get("max_cases_per_criterion")
        or Target().max_cases_per_criterion
    )

    por_criterio: dict[str, list[dict]] = {}
    for caso in test_cases or []:
        por_criterio.setdefault(caso.get("criterion_ref"), []).append(caso)

    conservados: list[dict[str, Any]] = []
    observaciones: list[dict] = []
    podados = 0

    for criterio, casos in por_criterio.items():
        if len(casos) <= techo:
            conservados.extend(casos)
            continue

        # Primero uno de cada tipo, en el orden de preferencia; luego se rellena
        # con el resto en su orden original (que ya es el de generación).
        elegidos: list[dict] = []
        restantes = list(casos)
        for tipo in _PREFERENCIA:
            primero = next((c for c in restantes if c.get("type") == tipo), None)
            if primero is not None and len(elegidos) < techo:
                elegidos.append(primero)
                restantes.remove(primero)
        for caso in list(restantes):
            if len(elegidos) >= techo:
                break
            elegidos.append(caso)

        ids_elegidos = {c["id"] for c in elegidos}
        descartados = [c for c in casos if c["id"] not in ids_elegidos]
        podados += len(descartados)
        conservados.extend(sorted(elegidos, key=lambda c: c["id"]))
        observaciones.append(
            {
                "description": (
                    f"El criterio {criterio} generó {len(casos)} casos y el techo del "
                    f"plan es {techo}: se dejaron fuera "
                    f"{', '.join(c['id'] for c in descartados)}."
                ),
                "reason": (
                    "Techo de casos por criterio (target.max_cases_per_criterion). "
                    "Se conservó diversidad de tipos."
                ),
                "source_ref": criterio,
            }
        )

    return {
        "test_cases": conservados,
        "observations": observaciones,
        "pruned": podados,
    }
