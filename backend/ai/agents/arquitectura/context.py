"""Nodo CONTEXT (parte determinista): perfil de alcance y clasificación de tamaño.

Calcula un *scope profile* (conteos) a partir del contexto consolidado EF+Scrum y
lo clasifica en ``S`` | ``M`` | ``L`` con umbrales configurables. Es la base
**reproducible** de la recomendación de estilo (monolito modular por defecto); el
LLM solo la justifica en bloques posteriores.

La detección de integraciones externas y de *bounded contexts* (parte LLM del
nodo CONTEXT) llega en bloques posteriores; aquí ``integrations_detected`` es 0.
"""

from typing import Any


def build_scope_profile(sources: dict[str, Any]) -> dict[str, int]:
    """Conteos deterministas del alcance a partir del contexto EF+Scrum."""
    ef = sources.get("ef", {}) or {}
    scrum = sources.get("scrum", {}) or {}
    requirements = ef.get("requirements", {}) or {}
    return {
        "entities": len(ef.get("entities", []) or []),
        "relationships": len(ef.get("relationships", []) or []),
        "modules": len(ef.get("modules", []) or []),
        "processes": len(ef.get("processes", []) or []),
        "stories": len(scrum.get("stories", []) or []),
        "points_total": int(scrum.get("points_total", 0) or 0),
        "integrations_detected": 0,  # se completa en bloques posteriores (LLM)
        "nfr_count": len(requirements.get("non_functional", []) or []),
    }


def scope_score(profile: dict[str, int]) -> int:
    """Puntaje ponderado del alcance (transparente y determinista).

    Da más peso a los módulos (frontera de contexto) y a las integraciones
    (superficie de acoplamiento externo), que son los que empujan hacia estilos
    distribuidos.
    """
    return (
        profile.get("entities", 0)
        + profile.get("modules", 0) * 2
        + profile.get("processes", 0)
        + profile.get("stories", 0)
        + profile.get("integrations_detected", 0) * 3
    )


def classify_size(profile: dict[str, int], small_max: int, large_min: int) -> str:
    """Clasifica el tamaño del alcance en ``S`` | ``M`` | ``L``."""
    score = scope_score(profile)
    if score <= small_max:
        return "S"
    if score >= large_min:
        return "L"
    return "M"
