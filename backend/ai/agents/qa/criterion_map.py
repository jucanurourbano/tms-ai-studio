"""Nodo CRITERION_MAP: el cortafuegos anti-invención del Agente QA.

Fija **en Python, antes de gastar un token**, qué pares (historia, criterio)
existen. Es el gemelo de ``MODEL_MAP`` (Agente BD) y ``RESOURCE_MAP`` (Agente API),
y cumple la misma función: el LLM no elige *qué* hay, solo redacta *cómo* se prueba
lo que hay.

Por qué antes y no después. Validar "todo caso cita un criterio real" al final
sería posible, pero significaría descartar trabajo ya pagado al modelo, y —peor—
dejaría al LLM decidiendo el universo de criterios. Aquí el universo llega cerrado:
cada tarea del *map* lleva **un** criterio con su id, y cualquier caso que cite otro
se descarta con ``Observation``.

También sale de aquí, gratis, la base de la matriz de trazabilidad: los criterios
que existen son exactamente las filas que TRACE_MATRIX tendrá que cubrir, incluidos
los que se queden sin ningún caso.
"""

from typing import Any, Optional

from ai.agents.scrum.schemas.enums import MoscowPriority

from .schemas.artifact import MOSCOW_TO_PRIORITY
from .schemas.enums import TestPriority

#: Prioridades MoSCoW cuya cobertura entra en el semáforo (QA-D5). Un criterio de
#: una historia ``could``/``wont`` sin caso es advertencia, no bloqueo.
BLOCKING_PRIORITIES = (MoscowPriority.MUST.value, MoscowPriority.SHOULD.value)


def criterion_text(criterion: dict[str, Any]) -> str:
    """Texto legible de un criterio, sea Gherkin o texto libre.

    Un criterio puede venir en Gherkin (``given``/``when``/``then``) o como texto
    plano cuando el formato no aplicaba. Ambos se prueban; lo que no se puede es
    perder el de texto libre por no tener la forma esperada.
    """
    partes = []
    for etiqueta, clave in (
        ("Dado", "given"),
        ("Cuando", "when"),
        ("Entonces", "then"),
    ):
        valor = (criterion.get(clave) or "").strip()
        if valor:
            partes.append(f"{etiqueta} {valor}")
    if partes:
        return "; ".join(partes)
    return (criterion.get("text") or "").strip()


def priority_for(story_priority: Optional[str]) -> str:
    """Prioridad del caso heredada del MoSCoW de la historia (QA-D4).

    Una historia sin MoSCoW no se queda sin prioridad: cae en ``media``. Dejarla
    vacía obligaría a decidir después, y quien decidiera no tendría más información
    que aquí.
    """
    return MOSCOW_TO_PRIORITY.get(story_priority or "", TestPriority.MEDIA.value)


def _sin_acentos(texto: str) -> str:
    """Normaliza para comparar nombres de entidad ("Guia" vs "guía")."""
    import unicodedata

    plano = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in plano if not unicodedata.combining(c)).casefold()


def matching_entities(entry_text: str, entities: list[dict]) -> list[str]:
    """Entidades del EF mencionadas en el texto de un criterio o su historia.

    Es el enlace que permite alcanzar las validaciones **relevantes** de un
    criterio: un criterio de aceptación cita las reglas que el Agente Scrum eligió
    citar, no todas las que aplican. ``AC-001`` cita ``BR-001`` (la guía es
    obligatoria) y no ``VAL-001`` (la fecha no puede ser futura), pero registrar un
    siniestro **sí** está sujeto a las dos.

    Sin este enlace, EDGE_CASES quedaría casi siempre vacío y las fronteras del EF
    se perderían en silencio — el mismo error que se evita al agrupar validaciones
    sin ``field_ref``. Con él, la relevancia sale de un dato real (el nombre de la
    entidad aparece en el texto), no de una corazonada: la validación llega como
    **candidata**, y sigue necesitando su cita verbatim para producir un caso.
    """
    texto = _sin_acentos(entry_text)
    encontradas = []
    for entidad in entities or []:
        nombre = _sin_acentos(entidad.get("name") or "")
        if len(nombre) >= 4 and nombre in texto and entidad.get("id"):
            encontradas.append(entidad["id"])
    return encontradas


def build_criterion_map(sources: dict[str, Any]) -> dict[str, Any]:
    """Enumera los pares (historia, criterio) del plan, con su contexto.

    Cada entrada trae lo que TEST_DESIGN necesita para redactar sin inventar: el
    texto del criterio, el enunciado de la historia, las reglas del EF que el
    criterio cita y la prioridad heredada.
    """
    scrum = sources.get("scrum", {}) or {}
    ef = sources.get("ef", {}) or {}
    reglas = {r.get("id"): r for r in ef.get("business_rules", []) or []}
    validaciones = {v.get("id"): v for v in ef.get("validations", []) or []}
    entidades = ef.get("entities", []) or []
    campos = {c.get("id"): c for c in ef.get("fields", []) or []}

    entradas: list[dict[str, Any]] = []
    historias_sin_criterio: list[str] = []

    for historia in scrum.get("stories", []) or []:
        criterios = historia.get("acceptance_criteria", []) or []
        if not criterios:
            # Una historia sin criterios no se puede probar y no se inventa un
            # criterio para ella: se declara, y QUESTION_GEN la convierte en
            # pregunta al QA lead.
            historias_sin_criterio.append(historia.get("id", "?"))
            continue
        refs = historia.get("source_refs", {}) or {}
        for criterio in criterios:
            citadas = list(criterio.get("source_refs", []) or [])
            # Las reglas que la HISTORIA cita también aplican a sus criterios: el
            # criterio es una faceta de la historia, no un universo aparte.
            citadas += [r for r in (refs.get("rule_refs") or []) if r not in citadas]

            texto_criterio = criterion_text(criterio)
            entity_refs = matching_entities(
                f"{texto_criterio} {historia.get('statement') or ''}", entidades
            )
            # Validaciones alcanzables por entidad y aún no citadas: candidatas.
            # Siguen necesitando cita verbatim para convertirse en caso.
            por_entidad = [
                {
                    "id": vid,
                    "rule": val.get("rule"),
                    "field_ref": val.get("field_ref"),
                    "entity_ref": (campos.get(val.get("field_ref")) or {}).get(
                        "entity_ref"
                    ),
                }
                for vid, val in validaciones.items()
                if vid not in citadas
                and (campos.get(val.get("field_ref")) or {}).get("entity_ref")
                in entity_refs
            ]

            entradas.append(
                {
                    "story_ref": historia.get("id"),
                    "criterion_ref": criterio.get("id"),
                    "epic_ref": historia.get("epic_ref"),
                    "criterion_text": texto_criterio,
                    "story_statement": historia.get("statement"),
                    "story_role": historia.get("role"),
                    "story_priority": historia.get("priority"),
                    "case_priority": priority_for(historia.get("priority")),
                    "blocking": (historia.get("priority") or "") in BLOCKING_PRIORITIES,
                    "requirement_refs": refs.get("requirement_refs", []) or [],
                    "process_refs": refs.get("process_refs", []) or [],
                    # Las reglas que el criterio cita, resueltas a su texto: sin
                    # esto el modelo tendría el id pero no lo que dice la regla.
                    "rules": [
                        {"id": rid, "statement": reglas[rid].get("statement")}
                        for rid in citadas
                        if rid in reglas
                    ],
                    "validations": [
                        {
                            "id": vid,
                            "rule": validaciones[vid].get("rule"),
                            "field_ref": validaciones[vid].get("field_ref"),
                        }
                        for vid in citadas
                        if vid in validaciones
                    ],
                    "entity_refs": entity_refs,
                    "entity_validations": por_entidad,
                    # Refs citadas que no resuelven a nada conocido del EF. No se
                    # tiran: viajan para que CRITIQUE pueda reportarlas.
                    "unresolved_refs": [
                        rid
                        for rid in citadas
                        if rid not in reglas and rid not in validaciones
                    ],
                }
            )

    return {
        "entries": entradas,
        "criterion_refs": [e["criterion_ref"] for e in entradas],
        "blocking_criterion_refs": [
            e["criterion_ref"] for e in entradas if e["blocking"]
        ],
        "stories_without_criteria": historias_sin_criterio,
    }


def known_criteria(criterion_map: dict[str, Any]) -> set[str]:
    """Conjunto cerrado de criterios válidos: contra este se filtra todo caso."""
    return {ref for ref in criterion_map.get("criterion_refs", []) or [] if ref}


def entry_for(criterion_map: dict[str, Any], criterion_ref: str) -> Optional[dict]:
    """Devuelve la entrada del mapa de un criterio, o ``None`` si no existe."""
    for entrada in criterion_map.get("entries", []) or []:
        if entrada.get("criterion_ref") == criterion_ref:
            return entrada
    return None
