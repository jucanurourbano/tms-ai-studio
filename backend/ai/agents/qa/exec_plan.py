"""Nodo EXEC_PLAN: suites, orden de ejecución y esfuerzo. **Sin LLM.**

Una suite por épica, y el **orden** sale de las dependencias entre historias del
plan Scrum: si ``US-002`` depende de ``US-001``, la suite que contiene a la segunda
va después. No es una cortesía de presentación — probar el cambio de estado de un
siniestro antes de poder registrarlo obliga a inventarse el dato de entrada a mano,
que es justo lo que un plan bien ordenado evita.

El esfuerzo se suma de los ``estimated_minutes`` de cada caso, que a su vez salen de
la tabla determinista de ``target``. Dos corridas del mismo plan dan el mismo total,
así que el número sirve para comparar versiones — que es para lo que el equipo lo
quiere.

Los **ciclos** de dependencias se reportan, no se lanzan: el plan existe igual (se
ordena lo ordenable y el ciclo queda documentado), y CRITIQUE lo convierte en
hallazgo. Tumbar el job por un ciclo heredado del plan Scrum dejaría al equipo sin
plan de pruebas por un defecto que no es suyo.
"""

from typing import Any, Optional

from ai.agents.scrum.critique import detect_cycles

SIN_EPICA = "SUITE-SIN-EPICA"


def _suite_id(indice: int) -> str:
    return f"SUITE-{indice:03d}"


def build_execution_plan(
    test_cases: list[dict[str, Any]],
    sources: dict[str, Any],
    *,
    target: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Agrupa los casos en suites por épica y las ordena topológicamente."""
    target = target or {}
    scrum = sources.get("scrum", {}) or {}
    epicas = scrum.get("epics", []) or []
    historias = {h.get("id"): h for h in scrum.get("stories", []) or []}

    # --- Suites: una por épica, en el orden en que el plan las declara ---
    orden_epicas = [e.get("id") for e in epicas if e.get("id")]
    nombres = {e.get("id"): e.get("title") or e.get("id") for e in epicas}

    por_epica: dict[Optional[str], list[dict]] = {}
    for caso in test_cases or []:
        # Un caso sin épica no se pierde: cae en una suite propia. Colgarlo de la
        # primera épica lo daría por agrupado siendo mentira.
        por_epica.setdefault(caso.get("epic_ref"), []).append(caso)

    suites: list[dict[str, Any]] = []
    suite_de_epica: dict[Optional[str], str] = {}
    indice = 1
    for epic_ref in orden_epicas + [k for k in por_epica if k not in orden_epicas]:
        casos = por_epica.get(epic_ref) or []
        if not casos:
            continue
        sid = _suite_id(indice) if epic_ref else SIN_EPICA
        indice += 1 if epic_ref else 0
        suite_de_epica[epic_ref] = sid
        suites.append(
            {
                "id": sid,
                "name": nombres.get(epic_ref, "Casos sin épica"),
                "epic_ref": epic_ref,
                "test_case_ids": [c["id"] for c in casos],
                "estimated_minutes": sum(
                    int(c.get("estimated_minutes") or 0) for c in casos
                ),
                "depends_on_suite_ids": [],
            }
        )

    # --- Dependencias entre suites, derivadas de las de las historias ---
    epica_de_historia = {hid: h.get("epic_ref") for hid, h in historias.items()}
    for suite in suites:
        dependencias: set[str] = set()
        for caso in por_epica.get(suite["epic_ref"]) or []:
            historia = historias.get(caso.get("story_ref")) or {}
            for dep in historia.get("dependencies", []) or []:
                epica_dep = epica_de_historia.get(dep)
                sid_dep = suite_de_epica.get(epica_dep)
                if sid_dep and sid_dep != suite["id"]:
                    dependencias.add(sid_dep)
        suite["depends_on_suite_ids"] = sorted(dependencias)

    orden = _orden_topologico(suites)
    ciclos = detect_cycles(list(historias.values()))

    minutos = sum(s["estimated_minutes"] for s in suites)
    por_tipo: dict[str, int] = {}
    por_prioridad: dict[str, int] = {}
    for caso in test_cases or []:
        por_tipo[caso.get("type")] = por_tipo.get(caso.get("type"), 0) + 1
        por_prioridad[caso.get("priority")] = (
            por_prioridad.get(caso.get("priority"), 0) + 1
        )

    capacidad = target.get("manual_capacity_minutes")
    sesiones = None
    if capacidad and minutos:
        # Techo: media sesión de trabajo pendiente sigue siendo una sesión.
        sesiones = max(1, -(-minutos // int(capacidad)))

    return {
        "suites": suites,
        "order": orden,
        "dependency_cycles": ciclos,
        "totals": {
            "cases_total": len(test_cases or []),
            "manual_minutes": minutos,
            "by_type": por_tipo,
            "by_priority": por_prioridad,
            "estimated_sessions": sesiones,
        },
    }


def _orden_topologico(suites: list[dict[str, Any]]) -> list[str]:
    """Orden de ejecución respetando ``depends_on_suite_ids`` (Kahn estable).

    Ante un ciclo entre suites no se cuelga ni se lanza: coloca lo ordenable y
    añade el resto en su orden de declaración. Un plan parcialmente ordenado sigue
    siendo utilizable; ninguno no lo es.
    """
    pendientes = {s["id"]: set(s["depends_on_suite_ids"]) for s in suites}
    orden: list[str] = []
    while pendientes:
        listas = sorted(
            [sid for sid, deps in pendientes.items() if not (deps - set(orden))]
        )
        if not listas:
            orden.extend(sid for sid in pendientes if sid not in orden)
            break
        for sid in listas:
            orden.append(sid)
            del pendientes[sid]
    return orden
