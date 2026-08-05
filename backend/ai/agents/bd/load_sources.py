"""Nodo LOAD_SOURCES: única fuente de verdad del Agente BD.

Tres responsabilidades:

1. **Gate de entrada** (defensivo): el diseño de arquitectura debe estar listo
   (``ready_for_next_stage=true``). El servicio ya lo verificó antes de crear el
   job; aquí se re-verifica porque un refine o un reintento podrían partir de un
   estado distinto.
2. **Contexto consolidado**: expone la materia prima. Del **EF** (la principal):
   entidades, relaciones, campos, validaciones, reglas, matriz CRUD, APIs y
   procesos. De la **Arquitectura**: el stack (de donde sale el motor), los
   componentes de datos, los contextos acotados y los transversales.
3. **Resolución del motor**: qué motor relacional se usa y de dónde salió.

El Scrum no participa del modelado: se carga solo para completar la trazabilidad
de la cadena en ``source``.
"""

from typing import Any, Optional

from ai.errors import GateError
from ai.knowledge import DB_ENGINES, load_tech_stack

#: Capa del ``stack[]`` de Arquitectura que fija el motor relacional.
DB_STACK_LAYER = "database_relational"

#: Nombres de producto del allow-list → clave del motor. Se compara normalizado
#: (minúsculas sin espacios) para tolerar "SQL Server" / "sqlserver" / "SQLServer".
_ENGINE_ALIASES = {
    "sqlserver": "sqlserver",
    "microsoftsqlserver": "sqlserver",
    "mssql": "sqlserver",
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "oracle": "oracle",
    "oracledatabase": "oracle",
    "mysql": "mysql",
    "mariadb": "mysql",
}


def assert_architecture_ready(ready: bool, architecture_job_id: str) -> None:
    """Re-verifica el gate de entrada; si no está listo, corta con ``GateError``."""
    if not ready:
        raise GateError(
            f"El diseño de arquitectura {architecture_job_id} no está listo para "
            "modelar la base de datos: quedan preguntas bloqueantes al Arquitecto "
            "sin responder o falta contenido mínimo. Complétalas o genera un "
            f"diseño afinado (POST /arquitectura/jobs/{architecture_job_id}/refine)."
        )


def extract_sources(
    ef_artifact: dict[str, Any],
    architecture_artifact: dict[str, Any],
    scrum_artifact: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Consolida las dimensiones de EF + Arquitectura que necesita el modelo físico."""
    requirements = ef_artifact.get("requirements", {}) or {}
    architecture_artifact = architecture_artifact or {}
    scrum_artifact = scrum_artifact or {}
    return {
        "ef": {
            "summary": ef_artifact.get("summary"),
            "entities": ef_artifact.get("entities", []) or [],
            "relationships": ef_artifact.get("relationships", []) or [],
            "fields": ef_artifact.get("fields", []) or [],
            "validations": ef_artifact.get("validations", []) or [],
            "business_rules": ef_artifact.get("business_rules", []) or [],
            "crud": ef_artifact.get("crud", []) or [],
            "apis": ef_artifact.get("apis", []) or [],
            "processes": ef_artifact.get("processes", []) or [],
            "modules": ef_artifact.get("modules", []) or [],
            "actors": ef_artifact.get("actors", []) or [],
            "requirements": {
                "functional": requirements.get("functional", []) or [],
                "non_functional": requirements.get("non_functional", []) or [],
            },
        },
        "architecture": {
            "style": (architecture_artifact.get("architecture_style") or {}).get(
                "chosen"
            ),
            "size_class": (architecture_artifact.get("context") or {}).get(
                "size_class"
            ),
            "stack": architecture_artifact.get("stack", []) or [],
            "components": architecture_artifact.get("components", []) or [],
            "bounded_contexts": (architecture_artifact.get("context") or {}).get(
                "bounded_contexts", []
            )
            or [],
            "cross_cutting": architecture_artifact.get("cross_cutting", []) or [],
            "integrations": architecture_artifact.get("integrations", []) or [],
        },
        # Solo trazabilidad de la cadena: el Scrum no alimenta el modelo de datos.
        "scrum": {"epics": scrum_artifact.get("epics", []) or []},
    }


def _normalize_engine(value: str) -> Optional[str]:
    """Traduce un nombre de producto a la clave del motor, o ``None``."""
    key = "".join((value or "").lower().split()).replace("-", "").replace("_", "")
    resolved = _ENGINE_ALIASES.get(key)
    if resolved is None and key in DB_ENGINES:
        return key
    return resolved


def resolve_engine(
    sources: dict[str, Any], override: Optional[str] = None
) -> dict[str, Any]:
    """Decide el motor destino y **declara de dónde salió**.

    Prioridad:

    1. ``override`` explícito de la petición (permite modelar sin esperar a que la
       arquitectura se corrija).
    2. La capa ``database_relational`` del ``stack[]`` de Arquitectura.
    3. El ``default`` de ``tech_stack.yaml``, como último recurso.

    En el caso 3 —y también si el stack propone un motor fuera del allow-list—
    ``decided`` sale ``False``: el artefacto lo declara y QUESTION_GEN emite una
    pregunta **bloqueante**, de modo que el semáforo no se pone verde con un motor
    que nadie confirmó. El pipeline igualmente corre y produce valor.
    """
    if override:
        engine = _normalize_engine(override)
        if engine is None:
            raise GateError(
                f"El motor «{override}» no está en el allow-list de la casa "
                f"({', '.join(DB_ENGINES)}). Revisa tech_stack.yaml o corrige la "
                "petición."
            )
        return {
            "engine": engine,
            "version": _default_version_for(engine),
            "source_ref": None,
            "decided": True,
            "reason": "Motor indicado explícitamente en la petición.",
        }

    for choice in (sources.get("architecture", {}) or {}).get("stack", []) or []:
        if choice.get("layer") != DB_STACK_LAYER:
            continue
        engine = _normalize_engine(choice.get("technology") or "")
        if engine is not None:
            return {
                "engine": engine,
                "version": choice.get("version"),
                "source_ref": choice.get("id"),
                "decided": True,
                "reason": (
                    f"Motor decidido por la arquitectura ({choice.get('id')}): "
                    f"{choice.get('technology')}."
                ),
            }
        fallback, fallback_version = _fallback_engine()
        return {
            "engine": fallback,
            "version": fallback_version,
            "source_ref": choice.get("id"),
            "decided": False,
            "reason": (
                f"La arquitectura propone «{choice.get('technology')}», que no está "
                "en el allow-list de motores de la casa. Se modela con el motor por "
                "defecto y se pregunta al DBA."
            ),
        }

    fallback, fallback_version = _fallback_engine()
    return {
        "engine": fallback,
        "version": fallback_version,
        "source_ref": None,
        "decided": False,
        "reason": (
            "La arquitectura no decidió motor relacional: se modela con el motor "
            "por defecto de tech_stack.yaml y se pregunta al DBA."
        ),
    }


def _fallback_engine() -> tuple[str, Optional[str]]:
    """Motor por defecto del stack de la casa, con su versión de referencia.

    Se usa cuando la arquitectura no decidió motor. Arrastra ``default_version``
    para que el DDL se genere contra una versión concreta y no contra "PostgreSQL
    a secas": la capa ``database_relational`` del stack está validada
    (PostgreSQL 16), aunque el resto del archivo siga en borrador.
    """
    layers = load_tech_stack().get("layers", {}) or {}
    layer = layers.get(DB_STACK_LAYER, {}) or {}
    engine = _normalize_engine(layer.get("default", "")) or "postgresql"
    return engine, layer.get("default_version")


def _default_version_for(engine: str) -> Optional[str]:
    """Versión de referencia del stack, si el motor pedido es el de la casa."""
    fallback, version = _fallback_engine()
    return version if engine == fallback else None


def resolve_hashes(
    state_architecture_hash: str,
    state_ef_hash: str,
    architecture_artifact: dict[str, Any],
    ef_artifact: dict[str, Any],
) -> tuple[str, str]:
    """Resuelve los hashes de origen: estado > ``source`` del artefacto de arriba."""
    arch_source = architecture_artifact.get("source") or {}
    architecture_hash = state_architecture_hash or ""
    ef_hash = (
        state_ef_hash
        or arch_source.get("ef_artifact_hash")
        or (ef_artifact.get("source") or {}).get("hash", "")
    )
    return architecture_hash, ef_hash
