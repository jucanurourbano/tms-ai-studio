"""Utilidades compartidas por los nodos del Agente QA."""

import hashlib
from typing import Any, Optional, Sequence

from ai.knowledge import glossary_block

from .schemas.artifact import DEFAULT_MINUTES_BY_TYPE, DEFAULT_PRIORITY_FACTOR


def knowledge_block(authoritative_context: Optional[str] = None) -> str:
    """Conocimiento inyectable de los nodos generativos del Agente QA.

    Compone el glosario logístico y antepone el contexto autoritativo del refine,
    que tiene prioridad sobre cualquier otra cosa (son respuestas del QA lead a
    preguntas concretas).
    """
    block = glossary_block()
    if authoritative_context:
        return (
            "CONTEXTO AUTORITATIVO (respuestas del QA lead, tienen prioridad sobre "
            f"todo lo demás):\n{authoritative_context}\n\n{block}"
        )
    return block


def merge_metrics(state: dict, tokens: dict, skipped: list[dict]) -> dict:
    """Acumula tokens y cuarentena de un nodo sobre las métricas del estado."""
    metrics = dict(state.get("metrics") or {})
    acc = dict(metrics.get("tokens") or {"input": 0, "output": 0, "total": 0})
    for key in ("input", "output", "total"):
        acc[key] = acc.get(key, 0) + tokens.get(key, 0)
    metrics["tokens"] = acc
    metrics["skipped"] = list(metrics.get("skipped") or []) + list(skipped or [])
    return metrics


def estimated_minutes(
    case_type: str, priority: str, target: Optional[dict[str, Any]] = None
) -> int:
    """Esfuerzo manual de un caso: tabla por tipo × factor por prioridad (QA-D8).

    Determinista a propósito. Pedirle la estimación al modelo haría que dos corridas
    del mismo plan dieran totales distintos, y el número que el equipo usa para
    planificar dejaría de ser comparable entre versiones.
    """
    target = target or {}
    minutos = (target.get("minutes_by_type") or DEFAULT_MINUTES_BY_TYPE).get(
        case_type, 10
    )
    factor = (target.get("priority_factor") or DEFAULT_PRIORITY_FACTOR).get(
        priority, 1.0
    )
    # `int(... + 0.5)` en vez de `round()`: el redondeo bancario de Python haría que
    # 7.5 → 8 y 6.5 → 6, y dos casos con el mismo cálculo darían minutos distintos
    # según el valor. Aquí medio minuto siempre sube.
    return max(1, int(minutos * factor + 0.5))


def next_id(prefix: str, used: set[str]) -> str:
    """Siguiente id libre con el prefijo dado (``TC-001``, ``TC-002``…).

    Los ids los pone Python, no el modelo: dos llamadas concurrentes del *map*
    propondrían el mismo ``TC-001`` sin saberlo.
    """
    n = 1
    while f"{prefix}-{n:03d}" in used:
        n += 1
    return f"{prefix}-{n:03d}"


def normalize_steps(steps: list[dict]) -> list[dict]:
    """Numera los pasos de 1 a N (el modelo propone acciones, no numeración)."""
    return [
        {
            "number": i,
            "action": paso.get("action", ""),
            "expected": paso.get("expected"),
        }
        for i, paso in enumerate(steps or [], start=1)
    ]


# ---------------------------------------------------------------------------
# El tope de la evidencia de un enum (A6 / F3)
#
# Vive AQUÍ, y no en el nodo que lo necesita, porque lo necesitan los DOS modos:
# el Modo A lo aplica hoy en ``edge_cases.api_field_boundaries`` y el Modo C lo
# aplicará en ``SURFACE_MAP`` (QC5, criterio 5 de A6). Dos copias de estas
# constantes se separan en cuanto una se ajusta, y entonces el mismo catálogo
# produciría una evidencia en un modo y otra distinta en el otro.
# ---------------------------------------------------------------------------

#: Cuántos valores caben en la evidencia antes de que deje de ser evidencia. Un
#: enum de **dominio** real —estados de guía, motivos de DEO, tipos de documento,
#: el enum de motor de BD— vive holgadamente por debajo; por encima ya no es un
#: dominio, es un **catálogo**, y un catálogo no se lee en la celda «Límite
#: probado» del CSV ni en el título de un caso.
ENUM_MAX_OPCIONES = 25

#: El mismo tope medido en caracteres, porque pocas opciones muy largas rompen lo
#: mismo que muchas cortas. **No es el límite de Excel** (32.767 caracteres por
#: celda, que es el punto de ROTURA del fichero que abre el analista): es muy
#: anterior, el punto en que la celda se abre pero ya no se lee. Se topa donde
#: deja de servir, no donde revienta.
ENUM_MAX_CHARS = 1000

#: Cuántos valores acompañan a la huella. Tres bastan para reconocer de qué
#: catálogo se habla y **no amplían la exposición**: el primero ya viaja en el
#: ``valid_value`` del propio caso. No son un recorte del conjunto — la huella
#: dice su cardinalidad completa al lado, así que no se pueden leer como «el
#: enum».
ENUM_DIGEST_MUESTRA = 3


def enum_digest(values: Sequence[str]) -> str:
    """Huella de un conjunto de valores: cardinalidad + hash + primeros valores.

    Existe porque lo único que el conjunto **completo** aportaba a un caso de enum
    es responder *«¿cambió el catálogo?»* —el ``invalid_value`` es un centinela y
    el ``valid_value`` es el primer valor, ninguno se deriva del conjunto—, y para
    esa pregunta la huella es estrictamente mejor: **detecta el cambio sin
    transportarlo**. Un ``<select>`` de clientes o de colaboradores es un volcado
    de producción con forma de enum, y la huella no lo lleva a un PDF exportable.

    El hash es del conjunto **ordenado**, así que reordenar el catálogo no se
    reporta como un cambio que no ocurrió. No se deduplica a propósito: un valor
    repetido **es** un cambio del catálogo, y la huella existe para verlo.

    La muestra se recorta al presupuesto de :data:`ENUM_MAX_CHARS` —y desaparece
    entera si ni un valor cabe—, de modo que la huella cumple siempre el tope que
    la motivó.
    """
    valores = [str(v) for v in values]
    huella = hashlib.sha256("\n".join(sorted(valores)).encode("utf-8")).hexdigest()
    cabecera = f"{len(valores)} valores · sha256:{huella[:16]}"
    texto = cabecera
    muestra: list[str] = []
    for valor in valores[:ENUM_DIGEST_MUESTRA]:
        candidato = f"{cabecera}; primeros: {', '.join(muestra + [valor])}"
        if len(candidato) > ENUM_MAX_CHARS:
            break
        muestra.append(valor)
        texto = candidato
    return texto


def enum_evidence(values: Optional[Sequence[str]], *, separator: str = ", ") -> str:
    """El conjunto de valores aceptados, o su huella si no cabe. **Nunca un recorte.**

    Ésa es toda la regla, y es la asimetría rectora del agente aplicada a un enum:
    un conjunto **a medias** produce un caso que afirma que un valor legítimo debe
    rechazarse, y ese caso pasa la ejecución certificando una mentira. Un hueco se
    ve en la cobertura; una mentira con formato de evidencia, no. Por eso por
    encima del tope se cambia de **tipo** de evidencia (:func:`enum_digest`) en
    vez de cortar la lista.

    El ``separator`` es del modo que llama —el Modo A une con ``", "`` y el
    extractor del Modo C con ``" | "``— y no afecta a la huella: la huella no es
    una lista.
    """
    valores = [str(v) for v in values or []]
    if not valores:
        return ""
    unidos = separator.join(valores)
    if len(valores) <= ENUM_MAX_OPCIONES and len(unidos) <= ENUM_MAX_CHARS:
        return unidos
    return enum_digest(valores)
