"""Nodo LOAD_SOURCES: única fuente de verdad del Agente QA.

Cuatro responsabilidades:

1. **Gate de entrada** (defensivo): el plan Scrum debe estar listo
   (``ready_for_next_stage=true``). El servicio ya lo verificó antes de crear el
   job; aquí se re-verifica porque un refine o un reintento podrían partir de un
   estado distinto.
2. **Contexto consolidado**: del **Scrum** las épicas, historias y criterios (la
   materia prima); del **EF** las reglas ``BR-``, las validaciones ``VAL-`` con su
   ``field_ref``, los campos ``FLD-``, las entidades y los actores; del **API**, si
   se indicó, la matriz de autorización, los endpoints y los campos de esquema.
3. **Declaración de la dependencia opcional**: con contrato de API se diseñan casos
   de autorización; sin él **no**, y el motivo queda escrito (QA-D1).
4. **Umbrales efectivos**: los del ``target``, para que el cálculo determinista de
   cobertura y esfuerzo sea reproducible leyendo el artefacto.

Nota sobre los límites de borde (QA-D2): el EF **no** guarda límites
estructurados —``FieldDef`` solo tiene ``data_type``/``required`` y
``ValidationRule`` es texto libre—, así que aquí se preparan las dos vías: el texto
de las validaciones (que EDGE_CASES tendrá que citar verbatim) y, cuando hay
contrato de API, los campos con sus restricciones duras, **que prevalecen**.
"""

from typing import Any, Optional

from ai.errors import GateError

#: Motivo por defecto cuando el plan se generó sin contrato de API. Se escribe en
#: el artefacto: "no hay casos de autorización" y "no se pudo diseñarlos" no
#: pueden leerse igual.
NO_API_REASON = (
    "No se indicó un contrato de API para este plan de pruebas, así que no hay "
    "matriz de autorización de la que derivar casos. Vuelve a generar el plan "
    "indicando api_job_id cuando el contrato exista."
)


def assert_scrum_ready(ready: bool, scrum_job_id: str) -> None:
    """Re-verifica el gate de entrada; si no está listo, corta con ``GateError``."""
    if not ready:
        raise GateError(
            f"El plan Scrum {scrum_job_id} no está listo para diseñar las pruebas: "
            "quedan preguntas bloqueantes al PO sin responder, cobertura de "
            "requisitos por debajo del umbral, historias sin estimar o alguna "
            "`must` sin sprint. Complétalas o genera un plan afinado "
            f"(POST /scrum/jobs/{scrum_job_id}/refine)."
        )


def _validations_by_field(ef_artifact: dict[str, Any]) -> dict[str, list[dict]]:
    """Agrupa las validaciones del EF por campo, para armar bordes por campo.

    Una validación sin ``field_ref`` no se pierde: queda bajo la clave vacía, y
    EDGE_CASES la trata como validación de entidad o de proceso. Descartarla aquí
    sería perder silenciosamente una frontera que alguien escribió.
    """
    agrupadas: dict[str, list[dict]] = {}
    for val in ef_artifact.get("validations", []) or []:
        agrupadas.setdefault(val.get("field_ref") or "", []).append(val)
    return agrupadas


def _api_fields(api_artifact: dict[str, Any]) -> list[dict]:
    """Aplana los campos de todos los esquemas del contrato de API.

    Son la vía **estructurada** de los límites (``required``, ``max_length``,
    ``enum``): la que prevalece sobre lo extraído del texto del EF cuando existe.
    """
    campos: list[dict] = []
    for esquema in api_artifact.get("schemas", []) or []:
        for campo in esquema.get("fields", []) or []:
            campos.append({**campo, "schema_ref": esquema.get("id")})
    return campos


def extract_sources(
    scrum_artifact: dict[str, Any],
    ef_artifact: dict[str, Any],
    api_artifact: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Consolida las dimensiones de Scrum + EF (+ API) que necesita el QA."""
    scrum_artifact = scrum_artifact or {}
    ef_artifact = ef_artifact or {}
    api_artifact = api_artifact or {}
    requirements = ef_artifact.get("requirements", {}) or {}
    return {
        "scrum": {
            "epics": scrum_artifact.get("epics", []) or [],
            "stories": scrum_artifact.get("stories", []) or [],
            "sprints": scrum_artifact.get("sprints", []) or [],
        },
        "ef": {
            # Los tres bloques de requisitos: los funcionales son los que la
            # cobertura persigue, pero un caso puede citar cualquiera.
            "functional": requirements.get("functional", []) or [],
            "business": requirements.get("business", []) or [],
            "non_functional": requirements.get("non_functional", []) or [],
            "business_rules": ef_artifact.get("business_rules", []) or [],
            "validations": ef_artifact.get("validations", []) or [],
            "validations_by_field": _validations_by_field(ef_artifact),
            "fields": ef_artifact.get("fields", []) or [],
            "entities": ef_artifact.get("entities", []) or [],
            "actors": ef_artifact.get("actors", []) or [],
            "processes": ef_artifact.get("processes", []) or [],
        },
        "api": {
            "available": bool(api_artifact),
            "endpoints": api_artifact.get("endpoints", []) or [],
            "authorization_matrix": api_artifact.get("authorization_matrix", []) or [],
            "fields": _api_fields(api_artifact),
            "base_path": (api_artifact.get("target", {}) or {}).get("base_path", ""),
        },
    }


def resolve_api_availability(
    api_job_id: Optional[str],
    api_artifact: Optional[dict[str, Any]],
    api_artifact_hash: Optional[str],
) -> dict[str, Any]:
    """Decide si hay contrato de API utilizable y, si no, escribe el motivo.

    Un ``api_job_id`` sin artefacto no se trata como "hay API": se trata como
    ausencia **con su motivo concreto**. Seguir adelante como si el contrato
    estuviera disponible produciría casos de autorización sin matriz detrás, que es
    justo lo que el contrato del artefacto prohíbe.
    """
    if not api_job_id:
        return {"available": False, "reason": NO_API_REASON}
    if not api_artifact:
        return {
            "available": False,
            "reason": (
                f"El contrato de API {api_job_id} no tiene artefacto disponible, así "
                "que no se pudieron diseñar los casos de autorización."
            ),
        }
    if not (api_artifact_hash or "").strip():
        return {
            "available": False,
            "reason": (
                f"El contrato de API {api_job_id} no tiene hash registrado: sin él la "
                "corrida no sería reproducible y no se usó."
            ),
        }
    return {"available": True, "reason": None}


def resolve_target(
    coverage_threshold: Optional[float] = None,
    max_cases_per_criterion: Optional[int] = None,
    manual_capacity_minutes: Optional[int] = None,
) -> dict[str, Any]:
    """Umbrales efectivos de la corrida (solo lo informado pisa el default)."""
    from .schemas.artifact import Target

    datos: dict[str, Any] = {}
    if coverage_threshold is not None:
        datos["coverage_threshold"] = coverage_threshold
    if max_cases_per_criterion is not None:
        datos["max_cases_per_criterion"] = max_cases_per_criterion
    if manual_capacity_minutes is not None:
        datos["manual_capacity_minutes"] = manual_capacity_minutes
    return Target(**datos).model_dump(mode="json")


def resolve_hashes(
    scrum_artifact_hash: str,
    ef_artifact_hash: str,
    api_artifact_hash: Optional[str],
    api_available: bool,
) -> dict[str, Any]:
    """Hashes de la cadena para el bloque ``source`` del artefacto."""
    return {
        "scrum_artifact_hash": scrum_artifact_hash or "",
        "ef_artifact_hash": ef_artifact_hash or "",
        "api_artifact_hash": api_artifact_hash if api_available else None,
    }
