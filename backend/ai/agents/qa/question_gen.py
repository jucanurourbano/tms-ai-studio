"""Nodo QUESTION_GEN: preguntas al QA lead. **Sin LLM, y agrupadas por vacío.**

Dos decisiones, con su motivo.

**Sin LLM.** La sustancia de cada pregunta ya existe: el motivo se escribió donde se
detectó el vacío —la cita que no se pudo verificar, el criterio que nadie puede
observar, la regla que el Agente API marcó ambigua—. Pedirle al modelo que redacte
esas preguntas no añade información y sí añade una oportunidad de deformar el motivo.
Y una pregunta cuyo motivo cambió por el camino es una pregunta que se responde mal.

**Agrupadas por clase de vacío**, como en el Agente BD: treinta criterios no
verificables son **una** pregunta con los refs enumerados, no treinta que entierran
la que importa. Quien responde tiene tiempo limitado, y una bandeja con treinta
preguntas parecidas se contesta en bloque y sin leer — que es como se pierde la
única que tenía consecuencias.

Qué bloquea. Bloquea lo que dejaría el plan **certificando algo que no comprobó**:
una autorización que nadie precisó (el peor caso, y por eso siempre bloquea) y los
criterios de historias ``must``/``should`` que no se pueden probar. No bloquea lo que
solo resta cobertura declarada: un límite sin anclar (el caso simplemente no existe y
se ve en la matriz) ni los criterios de historias ``could``/``wont``.
"""

from typing import Any, Optional

from .schemas.enums import CoverageStatus


def _pregunta(
    qid: str,
    *,
    question: str,
    reason: str,
    blocking: bool,
    linked_to_ref: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "id": qid,
        "question": question,
        "reason": reason,
        "audience": "tecnico",
        "blocking": blocking,
        "linked_to_ref": linked_to_ref,
        "status": "pendiente",
        "origin": "derived",
    }


def _refs(items: list[str], limite: int = 12) -> str:
    """Enumera refs sin dejar que la pregunta se vuelva ilegible.

    Si hay más de ``limite``, se nombran los primeros y se dice **cuántos** quedan.
    Truncar sin decir cuántos faltan haría creer que el problema es más pequeño de lo
    que es.
    """
    orden = sorted(set(items))
    if len(orden) <= limite:
        return ", ".join(orden)
    mostrados = ", ".join(orden[:limite])
    return f"{mostrados} (y {len(orden) - limite} más)"


def generate_questions(
    *,
    not_testable: list[dict[str, Any]],
    unanchored: list[dict[str, Any]],
    ambiguous_auth_refs: list[str],
    criterion_map: dict[str, Any],
    trace_matrix: dict[str, Any],
) -> dict[str, Any]:
    """Arma las preguntas y devuelve además el enlace criterio → pregunta.

    El enlace lo necesita la matriz: el contrato exige que una fila
    ``not_testable`` cite la pregunta que la respalda, y esa pregunta nace aquí.
    """
    preguntas: list[dict[str, Any]] = []
    por_criterio: dict[str, str] = {}
    n = 0

    def siguiente() -> str:
        nonlocal n
        n += 1
        return f"QQ-{n:03d}"

    # --- 1. Autorizaciones ambiguas. Siempre bloqueante. ---
    if ambiguous_auth_refs:
        qid = siguiente()
        preguntas.append(
            _pregunta(
                qid,
                question=(
                    "¿Con qué dato se determina el ámbito de cada registro en estas "
                    f"reglas de autorización: {_refs(ambiguous_auth_refs)}? El "
                    "contrato de API las marcó ambiguas porque el alcance limita por "
                    "equipo, sede o propietario y no hay columna que lo materialice, "
                    "así que no se pudo diseñar el caso cruzado."
                ),
                reason=(
                    "Sin la columna que separa lo propio de lo ajeno, el caso de "
                    "autorización solo se podría escribir adivinando, y una prueba "
                    "que pasa verificando un permiso inventado deja tranquilo a todo "
                    "el mundo mientras el permiso real sigue sin comprobarse."
                ),
                blocking=True,
                linked_to_ref=sorted(set(ambiguous_auth_refs))[0],
            )
        )

    # --- 2. Criterios no verificables. Bloquea si alguno es must/should. ---
    if not_testable:
        refs = [n_["criterion_ref"] for n_ in not_testable if n_.get("criterion_ref")]
        bloquea = any(n_.get("blocking") for n_ in not_testable)
        qid = siguiente()
        motivos = "; ".join(
            f"{n_['criterion_ref']}: {n_.get('reason', '').rstrip('.')}"
            for n_ in not_testable[:6]
            if n_.get("criterion_ref")
        )
        preguntas.append(
            _pregunta(
                qid,
                question=(
                    f"¿Cómo se verifican estos criterios: {_refs(refs)}? Tal como "
                    "están redactados no describen un resultado observable, así que "
                    f"no se pudo diseñar ningún caso. Detalle — {motivos}."
                ),
                reason=(
                    "Un criterio no observable no se convierte en un caso vago: "
                    "alguien lo ejecutaría, lo marcaría como aprobado y no habría "
                    "comprobado nada. Es preferible declararlo."
                ),
                blocking=bloquea,
                linked_to_ref=sorted(set(refs))[0] if refs else None,
            )
        )
        for ref in refs:
            por_criterio[ref] = qid

    # --- 3. Límites que no se pudieron anclar. No bloquea. ---
    if unanchored:
        reglas = [u.get("rule_ref") for u in unanchored if u.get("rule_ref")]
        preguntas.append(
            _pregunta(
                siguiente(),
                question=(
                    f"¿Cuál es el límite exacto de estas reglas: {_refs(reglas)}? Se "
                    "detectó que podrían tener una frontera que probar, pero el texto "
                    "del EF no la dice de forma verificable y no se generó el caso de "
                    "borde."
                ),
                reason=(
                    "El límite no se completó con un valor verosímil: un caso de borde "
                    "sobre un límite inventado pasa la ejecución y certifica una "
                    "frontera que nadie definió."
                ),
                blocking=False,
                linked_to_ref=sorted(set(reglas))[0] if reglas else None,
            )
        )

    # --- 4. Historias sin criterios de aceptación. Bloquea. ---
    sin_criterios = criterion_map.get("stories_without_criteria") or []
    if sin_criterios:
        preguntas.append(
            _pregunta(
                siguiente(),
                question=(
                    f"¿Cuáles son los criterios de aceptación de {_refs(sin_criterios)}? "
                    "Sin criterios no hay nada que probar y no se inventó ninguno."
                ),
                reason=(
                    "Una historia sin criterios entraría al sprint sin definición de "
                    "terminado, y su plan de pruebas sería una suposición sobre lo que "
                    "el PO quiso decir."
                ),
                blocking=True,
                linked_to_ref=sorted(set(sin_criterios))[0],
            )
        )

    # --- 5. Criterios sin casos que nadie explicó. Bloquea si son must/should. ---
    huecos = [
        f["criterion_ref"]
        for f in trace_matrix.get("rows") or []
        if f.get("status") == CoverageStatus.UNCOVERED.value
    ]
    if huecos:
        bloqueantes = set(criterion_map.get("blocking_criterion_refs") or [])
        preguntas.append(
            _pregunta(
                siguiente(),
                question=(
                    f"Estos criterios quedaron sin ningún caso de prueba: "
                    f"{_refs(huecos)}. ¿Falta información para diseñarlos o deben "
                    "quedar fuera del alcance de esta versión?"
                ),
                reason=(
                    "No se declararon no verificables ni se cubrieron: es un hueco sin "
                    "explicación, y un plan con huecos sin explicar no se puede dar "
                    "por completo."
                ),
                blocking=bool(set(huecos) & bloqueantes),
                linked_to_ref=sorted(set(huecos))[0],
            )
        )

    return {"questions": preguntas, "questions_by_criterion": por_criterio}
