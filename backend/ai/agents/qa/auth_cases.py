"""Nodo AUTH_CASES: casos de autorización derivados de la matriz. **Sin LLM.**

La matriz del ``ApiArtifact`` ya trae todo lo que hace falta: el efecto
(``allow``/``deny``), el alcance (``all``, ``own``, ``own_team``, ``own_branch``,
``custom``, ``none``), las columnas que materializan ese alcance y el actor. Con eso,
los casos **se derivan**; no se redactan.

Que este nodo no llame al LLM es una decisión, no una economía (QA-D7). La
superficie de autorización es el sitio donde una frase verosímil hace más daño: un
caso que "prueba" que un jefe no ve datos de otro equipo, escrito a partir de una
suposición sobre qué columna separa los equipos, deja tranquilo a todo el mundo
mientras el permiso real sigue sin comprobarse. Derivar por plantilla desde el dato
estructurado elimina esa clase de error entera.

Y hay un caso que **deliberadamente no se genera**: cuando la regla está marcada
``ambiguous``, el Agente API ya dictaminó que el alcance no es implementable porque
ninguna columna lo sostiene. Ahí el QA no adivina la columna: devuelve la regla a la
lista de ambiguas, que QUESTION_GEN convierte en **pregunta bloqueante**. Entre
"claramente lo mismo" y "claramente distinto" hay una banda de duda, y en esa banda
no se adivina, se pregunta.
"""

from typing import Any, Optional

from ai.agents.api.schemas.enums import AuthEffect, AuthScope

from .common import estimated_minutes, next_id, normalize_steps
from .schemas.enums import TestCaseType, TestPriority

#: Alcances acotados: describen un filtro por fila, así que admiten el caso cruzado
#: ("el actor pide un registro que no es de su ámbito"). ``ALL`` y ``NONE`` no.
SCOPED = (AuthScope.OWN, AuthScope.OWN_TEAM, AuthScope.OWN_BRANCH, AuthScope.CUSTOM)

#: Cómo se llama el ámbito ajeno en el texto del caso, por alcance.
_AJENO = {
    AuthScope.OWN.value: "de otro usuario",
    AuthScope.OWN_TEAM.value: "de otro equipo",
    AuthScope.OWN_BRANCH.value: "de otra sede",
    AuthScope.CUSTOM.value: "fuera de su ámbito",
}

#: Suelo de prioridad de los casos de autorización (QA-D4): un fallo de
#: autorización es de seguridad, no de funcionalidad. Se despliega y nadie lo nota
#: hasta que alguien lee datos que no le tocan.
_SUELO = (TestPriority.CRITICA.value, TestPriority.ALTA.value)


def priority_with_floor(inherited: Optional[str]) -> str:
    """Aplica el suelo: nunca por debajo de ``alta``."""
    return inherited if inherited in _SUELO else TestPriority.ALTA.value


def _entry_for_endpoint(
    criterion_map: dict[str, Any], endpoint_ref: str, endpoints: list[dict]
) -> Optional[dict]:
    """Busca a qué criterio colgar el caso de un endpoint.

    El enlace no es directo: la matriz habla de endpoints y el plan de criterios. Se
    usa el endpoint → su recurso → la entidad, y de ahí el primer criterio cuya
    historia toque ese terreno. Si no se encuentra nada, se cuelga del primer
    criterio bloqueante: **un caso de autorización sin criterio no se puede emitir**
    (el contrato lo prohíbe), y perderlo sería peor que ubicarlo de forma aproximada
    —queda trazado al endpoint y a la regla en ``source_refs``—.
    """
    endpoint = next((e for e in endpoints if e.get("id") == endpoint_ref), None)
    entradas = criterion_map.get("entries", []) or []
    if not entradas:
        return None
    if endpoint:
        propositos = (endpoint.get("purpose") or "").casefold()
        for entrada in entradas:
            texto = (entrada.get("criterion_text") or "").casefold()
            palabras = [p for p in propositos.split() if len(p) > 5]
            if any(p in texto for p in palabras):
                return entrada
    bloqueantes = [e for e in entradas if e.get("blocking")]
    return bloqueantes[0] if bloqueantes else entradas[0]


def build_auth_cases(
    criterion_map: dict[str, Any],
    sources: dict[str, Any],
    *,
    used_ids: Optional[set[str]] = None,
    target: Optional[dict] = None,
) -> dict[str, Any]:
    """Deriva los casos de autorización de la matriz del contrato de API."""
    api = sources.get("api", {}) or {}
    usados = set(used_ids or set())

    if not api.get("available"):
        return {
            "test_cases": [],
            "ambiguous_auth_refs": [],
            "observations": [],
        }

    matriz = api.get("authorization_matrix", []) or []
    endpoints = api.get("endpoints", []) or []
    rutas = {e.get("id"): e for e in endpoints}

    casos: list[dict[str, Any]] = []
    ambiguas: list[str] = []
    observaciones: list[dict] = []

    for regla in matriz:
        ref = regla.get("id")
        if regla.get("ambiguous"):
            ambiguas.append(ref)
            observaciones.append(
                {
                    "description": (
                        f"No se generó el caso de autorización de {ref}: la regla "
                        "está marcada ambigua en el contrato de API, así que el "
                        "alcance no tiene columna que lo materialice."
                    ),
                    "reason": "Alcance sin columna: se pregunta, no se adivina.",
                    "source_ref": ref,
                }
            )
            continue

        entry = _entry_for_endpoint(criterion_map, regla.get("endpoint_ref"), endpoints)
        if entry is None:
            continue

        endpoint = rutas.get(regla.get("endpoint_ref")) or {}
        metodo = (endpoint.get("method") or "GET").upper()
        ruta = endpoint.get("path") or ""
        actor = regla.get("actor_name") or regla.get("actor_ref") or "el actor"
        efecto = regla.get("effect")
        alcance = regla.get("scope")
        prioridad = priority_with_floor(entry.get("case_priority"))

        if efecto == AuthEffect.DENY.value:
            # Regla que deniega: el caso es que el intento se rechace.
            titulo = f"{actor} no puede {metodo} {ruta}".strip()
            pasos = [
                {"action": f"Autenticarse como {actor}."},
                {"action": f"Invocar {metodo} {ruta}."},
            ]
            esperado = f"La API responde 403: la matriz deniega el acceso ({ref})."
            estado = 403
            negativo = True
        elif alcance in [s.value for s in SCOPED]:
            # Alcance acotado: el caso que importa es el CRUZADO. Es el que el
            # enunciado pedía ("un jefe no puede ver solicitudes de otro equipo") y
            # el que solo existe cuando hay columna que separe lo propio de lo ajeno.
            ajeno = _AJENO.get(alcance, "fuera de su ámbito")
            titulo = f"{actor} no puede acceder a un registro {ajeno}"
            pasos = [
                {"action": f"Autenticarse como {actor}."},
                {
                    "action": (
                        f"Invocar {metodo} {ruta} sobre un registro {ajeno}, usando "
                        "un identificador que exista pero no le corresponda."
                    )
                },
            ]
            esperado = (
                f"La API no devuelve el registro {ajeno}: responde 403 (o 404 si el "
                f"recurso se oculta). El alcance {alcance} de {ref} se respeta."
            )
            estado = 403
            negativo = True
        else:
            # Alcance `all`/`none` con `allow`: el caso comprueba que quien SÍ tiene
            # permiso puede operar. Sin él, una restricción de más pasaría inadvertida.
            titulo = f"{actor} puede {metodo} {ruta}".strip()
            pasos = [
                {"action": f"Autenticarse como {actor}."},
                {"action": f"Invocar {metodo} {ruta} con datos válidos."},
            ]
            esperado = f"La API atiende la petición: {ref} concede el acceso."
            estado = 200
            negativo = False

        case_id = next_id("TC", usados)
        usados.add(case_id)
        casos.append(
            {
                "id": case_id,
                "title": titulo,
                "story_ref": entry.get("story_ref"),
                "criterion_ref": entry.get("criterion_ref"),
                "epic_ref": entry.get("epic_ref"),
                "type": TestCaseType.AUTHORIZATION.value,
                "preconditions": [
                    f"El usuario autenticado corresponde al actor {actor}.",
                ],
                "steps": normalize_steps(pasos),
                "test_data": [],
                "expected_result": esperado,
                "priority": prioridad,
                "automation_hint": "api",
                "estimated_minutes": estimated_minutes(
                    TestCaseType.AUTHORIZATION.value, prioridad, target
                ),
                "auth_context": {
                    "auth_rule_ref": ref,
                    "endpoint_ref": regla.get("endpoint_ref"),
                    "actor_ref": regla.get("actor_ref"),
                    "scope": alcance or AuthScope.NONE.value,
                    "expected_status": estado,
                    "negative": negativo,
                    "scope_column_refs": regla.get("scope_column_refs", []) or [],
                },
                "tags": [],
                "source_refs": [
                    r for r in [ref] + (regla.get("source_refs") or []) if r
                ],
                "confidence": regla.get("confidence"),
                "origin": "derived",
            }
        )

    return {
        "test_cases": casos,
        "ambiguous_auth_refs": ambiguas,
        "observations": observaciones,
    }
