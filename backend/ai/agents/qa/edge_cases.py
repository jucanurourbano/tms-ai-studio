"""Nodo EDGE_CASES: casos de borde anclados en evidencia (LLM *map* + verificación).

Este nodo es donde el agente puede hacer más daño, y por eso es el que más
desconfía de su propia salida.

El EF **no guarda límites estructurados**: ``FieldDef`` solo tiene
``data_type``/``required`` y ``ValidationRule`` es texto libre. El límite hay que
leerlo del texto, y un límite leído mal produce un caso que **pasa** certificando
una frontera que nadie definió. Así que se exige la **cita verbatim** y se
**verifica en Python** contra el texto real de la regla (QA-D2):

- Cita que aparece en el texto → el borde vive.
- Cita que no aparece → el borde **se descarta** y pasa a la lista de *sin anclaje*,
  que QUESTION_GEN convierte en pregunta al QA lead. No se produce el caso.

Verificar en Python y no confiar en el prompt es la diferencia entre una regla y un
ruego. Un modelo que "cita" puede rellenar el campo con una paráfrasis; el
comparador no.

Cuando hay contrato de API, sus campos aportan la **otra** vía de anclaje: límites
estructurados (``required``, ``max_length``, ``enum``) que **prevalecen** sobre lo
extraído del texto, porque son datos duros y no interpretación.
"""

import json
import re
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.tools.chunker import estimate_tokens

from .common import estimated_minutes, knowledge_block, next_id, normalize_steps
from .criterion_map import entry_for
from .prompts import build_system
from .schemas.enums import AnchorSource, BoundaryKind, DataKind, TestCaseType
from .schemas.extraction import BoundariesExtract

_ESPACIOS = re.compile(r"\s+")


def _normaliza(texto: str) -> str:
    """Colapsa espacios y baja a minúsculas para comparar la cita.

    No se exige igualdad byte a byte porque el modelo cambia legítimamente la
    mayúscula inicial o el espaciado al copiar dentro de un JSON, y rechazar por eso
    tiraría citas correctas. Lo que **sí** se conserva es lo que importa: los
    acentos, los números y las palabras. Con esta normalización sigue siendo
    imposible "citar" un límite que no está escrito.
    """
    return _ESPACIOS.sub(" ", (texto or "").strip()).casefold()


def evidence_matches(evidence: str, rule_text: str) -> bool:
    """¿La cita aparece de verdad en el texto de la regla?"""
    cita = _normaliza(evidence)
    texto = _normaliza(rule_text)
    if not cita or not texto:
        return False
    return cita in texto


def candidate_validations(entry: dict[str, Any]) -> list[dict]:
    """Validaciones acotables por el criterio: las citadas + las de su entidad.

    Las citadas son las que el Agente Scrum eligió referenciar; las de la entidad
    son las que aplican al mismo objeto de negocio. Ambas son enlaces reales del
    artefacto, y ninguna se convierte en caso sin su cita verbatim.
    """
    return list(entry.get("validations", []) or []) + list(
        entry.get("entity_validations", []) or []
    )


def rule_texts(entry: dict[str, Any]) -> dict[str, str]:
    """Índice ``ref -> texto`` de las reglas y validaciones acotables."""
    textos: dict[str, str] = {}
    for regla in entry.get("rules", []) or []:
        if regla.get("id"):
            textos[regla["id"]] = regla.get("statement") or ""
    for val in candidate_validations(entry):
        if val.get("id"):
            textos[val["id"]] = val.get("rule") or ""
    return textos


def build_user(entry: dict[str, Any], sources: dict[str, Any], today: str) -> str:
    """Compone el mensaje: el criterio, sus reglas y los campos implicados."""
    ef = sources.get("ef", {}) or {}
    candidatas = candidate_validations(entry)
    campos_citados = {v.get("field_ref") for v in candidatas if v.get("field_ref")}
    payload = {
        "criterion": {
            "criterion_ref": entry.get("criterion_ref"),
            "criterion_text": entry.get("criterion_text"),
            "validations": [
                {
                    "id": v.get("id"),
                    "rule": v.get("rule"),
                    "field_ref": v.get("field_ref"),
                }
                for v in candidatas
            ],
            "rules": entry.get("rules", []),
        },
        "fields": [
            {
                "id": f.get("id"),
                "name": f.get("name"),
                "data_type": f.get("data_type"),
                "required": f.get("required"),
            }
            for f in ef.get("fields", []) or []
            if f.get("id") in campos_citados
        ],
        # La fecha de hoy la pone el sistema: pedirle al modelo que la suponga haría
        # que un borde de fecha dejara de ser reproducible.
        "today": today,
    }
    return "CRITERIO A ACOTAR:\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def api_field_boundaries(
    entry: dict[str, Any], sources: dict[str, Any]
) -> list[dict[str, Any]]:
    """Límites **estructurales** del contrato de API para los campos del criterio.

    No pasan por el LLM ni necesitan cita: ``required``/``max_length``/``enum`` son
    datos duros del contrato. Prevalecen sobre lo extraído del texto porque no son
    interpretación de nadie.
    """
    api = sources.get("api", {}) or {}
    if not api.get("available"):
        return []

    # El enlace es una **cita explícita**, no un parecido de nombres: el Agente API
    # dejó en `source_refs` de cada campo los `FLD-`/`VAL-` del EF de los que nace.
    # Emparejar por nombre ("fecha_siniestro" contra "fecha") habría sido adivinar.
    esperados = {
        v.get("field_ref") for v in candidate_validations(entry) if v.get("field_ref")
    }
    esperados |= {v.get("id") for v in candidate_validations(entry) if v.get("id")}

    limites: list[dict[str, Any]] = []
    for campo in api.get("fields", []) or []:
        if not (set(campo.get("source_refs") or []) & esperados):
            continue
        if campo.get("required") and not campo.get("nullable", True):
            limites.append(
                {
                    "kind": BoundaryKind.REQUIRED.value,
                    "anchor_source": AnchorSource.API_FIELD.value,
                    "api_field_ref": campo.get("id"),
                    "field_name": campo.get("name"),
                    "invalid_value": "null",
                    "valid_value": campo.get("example"),
                }
            )
        if campo.get("max_length"):
            limites.append(
                {
                    "kind": BoundaryKind.LENGTH.value,
                    "anchor_source": AnchorSource.API_FIELD.value,
                    "api_field_ref": campo.get("id"),
                    "field_name": campo.get("name"),
                    "operator": "<=",
                    "value": str(campo["max_length"]),
                    "invalid_value": "x" * (int(campo["max_length"]) + 1),
                    "valid_value": "x" * int(campo["max_length"]),
                }
            )
        if campo.get("enum"):
            limites.append(
                {
                    "kind": BoundaryKind.ENUM.value,
                    "anchor_source": AnchorSource.API_FIELD.value,
                    "api_field_ref": campo.get("id"),
                    "field_name": campo.get("name"),
                    "operator": "in",
                    "value": ", ".join(campo["enum"]),
                    "invalid_value": "VALOR_FUERA_DEL_CATALOGO",
                    "valid_value": campo["enum"][0] if campo["enum"] else None,
                }
            )
    return limites


def _caso_de_borde(
    limite: dict[str, Any],
    entry: dict[str, Any],
    *,
    case_id: str,
    target: Optional[dict],
) -> dict[str, Any]:
    """Arma el caso de borde a partir de un límite ya anclado."""
    campo = limite.get("field_name") or "el campo"
    prioridad = entry.get("case_priority")
    anchor = {
        "rule_ref": limite.get("rule_ref"),
        "kind": limite.get("kind"),
        "operator": limite.get("operator"),
        "value": limite.get("value"),
        "anchor_source": limite.get("anchor_source", AnchorSource.EF_TEXT.value),
        "evidence": limite.get("evidence"),
        "api_field_ref": limite.get("api_field_ref"),
    }
    invalido = limite.get("invalid_value", "")
    pasos = [
        {"action": f"Preparar el registro del criterio {entry.get('criterion_ref')}."},
        {"action": f"Informar «{campo}» con el valor {invalido}."},
        {"action": "Intentar guardar."},
    ]
    return {
        "id": case_id,
        "title": f"Rechazar {campo} fuera de su límite ({limite.get('kind')})",
        "story_ref": entry.get("story_ref"),
        "criterion_ref": entry.get("criterion_ref"),
        "epic_ref": entry.get("epic_ref"),
        "type": TestCaseType.BOUNDARY.value,
        "preconditions": [],
        "steps": normalize_steps(pasos),
        "test_data": [
            {
                "name": campo,
                "value": str(invalido),
                "kind": DataKind.BOUNDARY.value,
                "note": limite.get("rationale"),
            }
        ],
        "expected_result": (
            f"El sistema rechaza el valor por incumplir el límite de {campo}."
        ),
        "priority": prioridad,
        "automation_hint": "api",
        "estimated_minutes": estimated_minutes(
            TestCaseType.BOUNDARY.value, prioridad, target
        ),
        "boundary": anchor,
        "tags": [],
        "source_refs": [
            r for r in (limite.get("rule_ref"), limite.get("api_field_ref")) if r
        ],
        "confidence": limite.get("confidence"),
        "origin": "derived",
    }


async def run_edge_cases(
    llm: LLMClient,
    criterion_map: dict[str, Any],
    sources: dict[str, Any],
    *,
    today: str,
    used_ids: Optional[set[str]] = None,
    target: Optional[dict] = None,
    not_testable_refs: Optional[set[str]] = None,
    authoritative_context: Optional[str] = None,
    concurrency: int = 3,
) -> dict[str, Any]:
    """Ejecuta el *map*, **verifica cada cita** y arma los casos de borde.

    Los criterios que TEST_DESIGN declaró **no verificables** se saltan enteros. Un
    borde sobre un criterio que nadie puede comprobar dejaría al plan afirmando dos
    cosas incompatibles —hay una prueba de esto / esto no se puede probar— y la
    matriz lo contaría como cubierto, borrando la pregunta que ya se hizo. Además
    ahorra los tokens de pedir fronteras de algo que no se va a ejecutar.
    """
    excluidos = set(not_testable_refs or set())
    entradas = [
        e
        for e in criterion_map.get("entries", []) or []
        if e.get("criterion_ref") not in excluidos
    ]
    usados = set(used_ids or set())
    if not entradas:
        return {
            "test_cases": [],
            "unanchored": [],
            "observations": [],
            "skipped": [],
            "tokens": {"input": 0, "output": 0, "total": 0},
        }

    system = build_system("edge_cases.md", knowledge_block(authoritative_context))
    resultados, cuarentena, tokens = await run_structured_map(
        llm,
        entradas,
        build_system=lambda _entry: system,
        build_user=lambda entry: build_user(entry, sources, today),
        schema=BoundariesExtract,
        ref_of=lambda entry: entry.get("criterion_ref") or "?",
        stage="EDGE_CASES",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
    )

    casos: list[dict[str, Any]] = []
    sin_anclaje: list[dict[str, Any]] = []
    observaciones: list[dict] = []

    for resultado in resultados:
        entry = entry_for(criterion_map, resultado["ref"])
        if entry is None:
            continue
        textos = rule_texts(entry)

        for propuesta in resultado["data"].get("boundaries", []) or []:
            ref = propuesta.get("rule_ref")
            texto = textos.get(ref)
            if texto is None:
                # Cita una regla que este criterio no menciona: no se puede
                # verificar, así que no se convierte en caso.
                sin_anclaje.append(
                    {
                        "criterion_ref": entry["criterion_ref"],
                        "rule_ref": ref,
                        "reason": (
                            f"El límite dice venir de {ref}, que no es una regla ni "
                            "una validación citada por este criterio."
                        ),
                    }
                )
                continue
            if not evidence_matches(propuesta.get("evidence", ""), texto):
                sin_anclaje.append(
                    {
                        "criterion_ref": entry["criterion_ref"],
                        "rule_ref": ref,
                        "reason": (
                            f"La cita del límite no aparece en el texto de {ref}. Sin "
                            "evidencia verbatim el límite sería una invención, así "
                            "que no se generó el caso."
                        ),
                    }
                )
                observaciones.append(
                    {
                        "description": (
                            f"Se descartó un límite de {ref} en "
                            f"{entry['criterion_ref']}: la cita no está en el texto "
                            "de la regla."
                        ),
                        "reason": "Evidencia verbatim no verificable.",
                        "source_ref": ref,
                    }
                )
                continue

            case_id = next_id("TC", usados)
            usados.add(case_id)
            casos.append(
                _caso_de_borde(
                    {**propuesta, "anchor_source": AnchorSource.EF_TEXT.value},
                    entry,
                    case_id=case_id,
                    target=target,
                )
            )

        # Límites duros del contrato de API: prevalecen y no necesitan cita.
        for limite in api_field_boundaries(entry, sources):
            if any(
                c.get("boundary", {}).get("kind") == limite["kind"]
                and c.get("criterion_ref") == entry["criterion_ref"]
                for c in casos
            ):
                # El texto del EF ya cubrió esta clase de frontera para el criterio:
                # el dato duro no añade un caso, solo lo habría duplicado.
                continue
            case_id = next_id("TC", usados)
            usados.add(case_id)
            casos.append(_caso_de_borde(limite, entry, case_id=case_id, target=target))

    return {
        "test_cases": casos,
        "unanchored": sin_anclaje,
        "observations": observaciones,
        "skipped": cuarentena,
        "tokens": tokens,
    }
