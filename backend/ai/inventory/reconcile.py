"""Fase RECONCILE: clasificar lo propuesto contra lo que YA existe (INV4).

Es lo que convierte al ISDF en un framework *brownfield*. Sin esta fase, cada
agente diseña como si la organización partiese de cero y propone crear una tabla
``usuarios`` que lleva diez años en producción.

Las cuatro clasificaciones
--------------------------
- ``reuse``   — existe y sirve tal cual. Referencia al activo, no se crea nada.
- ``extend``  — existe pero le falta algo. El Agente BD emite **ALTER**, no
  ``CREATE``; el Agente API referencia el endpoint existente en vez de definirlo.
- ``new``     — no existe: se crea. Es el caso por defecto del diseño *greenfield*.
- ``conflict``— hay algo parecido pero **incompatible**. NUNCA se decide solo:
  genera una **pregunta bloqueante**.

Por qué ``conflict`` bloquea
---------------------------
Los otros tres errores se corrigen en revisión. Éste no: si el agente decide por
su cuenta que su ``cliente`` es el ``clientes`` de producción cuando en realidad
son cosas distintas, el diseño resultante propone escribir sobre una tabla viva.
Ante la duda, se pregunta — que es exactamente lo que un arquitecto humano haría.

Y por eso la banda de duda existe: entre "claramente lo mismo" y "claramente
distinto" hay una franja donde el emparejamiento léxico no alcanza. Ahí no se
adivina, se pregunta. Es la diferencia entre no saber y equivocarse.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .matching import (
    NAME_DOUBT_THRESHOLD,
    NAME_MATCH_THRESHOLD,
    STRUCTURE_MATCH_THRESHOLD,
    MatchCandidate,
    best_candidate,
    column_overlap,
    name_similarity,
)


class ReconciliationStatus(str, Enum):
    """Veredicto de la reconciliación de un elemento propuesto."""

    REUSE = "reuse"
    EXTEND = "extend"
    NEW = "new"
    CONFLICT = "conflict"


@dataclass
class Reconciliation:
    """Veredicto + su justificación + a qué activo del inventario apunta."""

    status: ReconciliationStatus
    reason: str
    candidate: Optional[MatchCandidate] = None
    #: Lo que le falta al elemento existente para servir (solo en ``extend``).
    missing: Optional[list[str]] = None
    #: ``True`` si hay que preguntar al humano antes de dar el diseño por bueno.
    blocking: bool = False

    def as_dict(self) -> dict[str, Any]:
        datos: dict[str, Any] = {
            "status": self.status.value,
            "reason": self.reason,
            "blocking": self.blocking,
        }
        if self.candidate is not None:
            datos["matched"] = self.candidate.as_dict()
        if self.missing:
            datos["missing"] = self.missing
        return datos


def candidates_for(
    nombre: str,
    inventario: list[dict[str, Any]],
    *,
    columnas_propuestas: Optional[list[str]] = None,
) -> list[MatchCandidate]:
    """Elementos del inventario con algún parecido al nombre propuesto.

    ``inventario`` es una lista plana de elementos ya aplanados por
    :func:`flatten_db_schema` (o equivalente para otros tipos de activo).
    """
    encontrados: list[MatchCandidate] = []
    for elemento in inventario:
        parecido = name_similarity(nombre, elemento["name"])
        if parecido < NAME_DOUBT_THRESHOLD:
            continue
        estructura = None
        if columnas_propuestas is not None:
            estructura = column_overlap(
                columnas_propuestas, elemento.get("columns") or []
            )
        encontrados.append(
            MatchCandidate(
                name=elemento["name"],
                asset_id=elemento.get("asset_id", ""),
                asset_name=elemento.get("asset_name", ""),
                system_id=elemento.get("system_id", ""),
                system_name=elemento.get("system_name", ""),
                name_score=parecido,
                structure_score=estructura,
                payload=elemento,
            )
        )
    return encontrados


def classify(
    nombre: str,
    inventario: list[dict[str, Any]],
    *,
    columnas_propuestas: Optional[list[str]] = None,
) -> Reconciliation:
    """Clasifica un elemento propuesto contra el inventario del sistema destino.

    El árbol de decisión, en orden:

    1. Sin candidato por encima de la banda de duda → ``new``.
    2. Nombre en la banda de duda (parecido pero no concluyente) → ``conflict``
       **bloqueante**: puede ser lo mismo con otro nombre, o algo distinto que se
       le parece. Solo una persona lo sabe.
    3. Nombre claramente igual, sin columnas que comparar → ``reuse``.
    4. Nombre igual y estructura compatible:
       - todas las columnas propuestas existen → ``reuse``;
       - faltan algunas pero hay base común → ``extend`` con la lista de lo que
         falta (el Agente BD generará ALTER para exactamente eso).
    5. Nombre igual pero estructura **incompatible** (casi nada en común) →
       ``conflict`` bloqueante: dos cosas distintas llamadas igual es el escenario
       más peligroso de todos, porque un ``reuse`` automático apuntaría el diseño
       nuevo contra una tabla que no es la que cree.
    """
    candidatos = candidates_for(
        nombre, inventario, columnas_propuestas=columnas_propuestas
    )
    mejor = best_candidate(nombre, candidatos)

    if mejor is None:
        return Reconciliation(
            status=ReconciliationStatus.NEW,
            reason=(
                f"No hay nada parecido a «{nombre}» en el inventario del sistema "
                "destino: se crea."
            ),
        )

    if mejor.name_score < NAME_MATCH_THRESHOLD:
        return Reconciliation(
            status=ReconciliationStatus.CONFLICT,
            reason=(
                f"«{nombre}» se parece a «{mejor.name}» (parecido "
                f"{mejor.name_score:.2f}) pero no lo suficiente para darlo por "
                "seguro. Confirma si son lo mismo antes de construir."
            ),
            candidate=mejor,
            blocking=True,
        )

    if columnas_propuestas is None:
        return Reconciliation(
            status=ReconciliationStatus.REUSE,
            reason=(
                f"«{nombre}» ya existe en el inventario como «{mejor.name}»: se "
                "reutiliza."
            ),
            candidate=mejor,
        )

    existentes = mejor.payload.get("columns") or []
    solapamiento = mejor.structure_score or 0.0
    faltantes = _missing_columns(columnas_propuestas, existentes)

    # Cuánta estructura común hace falta depende de cuánta evidencia da el nombre.
    # Con nombres canónicamente IDÉNTICOS (`Trabajador` y `usuarios` lo son tras
    # aplicar sinónimos) el nombre ya es evidencia fuerte, y basta con que algo
    # coincida para confirmar que es la misma cosa a la que se le añaden columnas.
    # Exigir el umbral completo ahí convertía en «conflicto» el caso más normal de
    # todos: una propuesta de 2 columnas de las que 1 ya existe.
    # Con nombres solo parecidos se exige el umbral entero, porque el nombre por sí
    # solo no distingue "lo mismo" de "algo que se llama parecido".
    nombre_exacto = mejor.name_score >= 1.0
    estructura_compatible = solapamiento >= STRUCTURE_MATCH_THRESHOLD or (
        nombre_exacto and solapamiento > 0.0
    )

    if estructura_compatible and not faltantes:
        return Reconciliation(
            status=ReconciliationStatus.REUSE,
            reason=(
                f"«{mejor.name}» ya existe con todas las columnas necesarias: se "
                "reutiliza sin cambios."
            ),
            candidate=mejor,
        )

    if estructura_compatible:
        return Reconciliation(
            status=ReconciliationStatus.EXTEND,
            reason=(
                f"«{mejor.name}» ya existe pero le faltan "
                f"{len(faltantes)} columnas: se extiende con ALTER en vez de "
                "crearla de cero."
            ),
            candidate=mejor,
            missing=faltantes,
        )

    return Reconciliation(
        status=ReconciliationStatus.CONFLICT,
        reason=(
            f"Existe «{mejor.name}» con un nombre casi idéntico, pero su estructura "
            f"apenas coincide (solapamiento {solapamiento:.2f}). Puede ser otra cosa "
            "que se llama igual: confírmalo antes de construir."
        ),
        candidate=mejor,
        missing=faltantes,
        blocking=True,
    )


def _missing_columns(propuestas: list[str], existentes: list[str]) -> list[str]:
    """Columnas propuestas que NO están en la tabla existente (nombres canónicos)."""
    from .matching import canonical_name

    canon = {canonical_name(c) for c in existentes}
    return [c for c in propuestas if canonical_name(c) not in canon]


# --- Aplanado del inventario -------------------------------------------------


def flatten_db_schema(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Activos ``db_schema`` → lista plana de tablas comparables.

    Cada tabla arrastra de qué activo y de qué sistema viene, para que el veredicto
    pueda enseñar la procedencia y la UI pueda enlazar al activo real.
    """
    tablas: list[dict[str, Any]] = []
    for asset in assets:
        contenido = asset.get("content") or {}
        for tabla in contenido.get("tables") or []:
            tablas.append(
                {
                    "name": tabla.get("name", ""),
                    "columns": [c.get("name", "") for c in tabla.get("columns") or []],
                    "table": tabla,
                    "asset_id": asset.get("id", ""),
                    "asset_name": asset.get("name", ""),
                    "system_id": asset.get("system_id", ""),
                    "system_name": asset.get("system_name", ""),
                }
            )
    return tablas


def flatten_endpoints(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Activos ``api`` → lista plana de endpoints comparables.

    El nombre comparable de un endpoint es ``método ruta``: dos endpoints con la
    misma ruta y distinto verbo son operaciones distintas.
    """
    endpoints: list[dict[str, Any]] = []
    for asset in assets:
        contenido = asset.get("content") or {}
        for endpoint in contenido.get("endpoints") or []:
            metodo = (endpoint.get("method") or "").upper()
            ruta = endpoint.get("path") or ""
            endpoints.append(
                {
                    "name": f"{metodo} {ruta}".strip(),
                    "endpoint": endpoint,
                    "asset_id": asset.get("id", ""),
                    "asset_name": asset.get("name", ""),
                    "system_id": asset.get("system_id", ""),
                    "system_name": asset.get("system_name", ""),
                }
            )
    return endpoints


def flatten_modules(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Activos ``module`` → lista plana de componentes comparables."""
    return [
        {
            "name": asset.get("name", ""),
            "module": asset.get("content") or {},
            "asset_id": asset.get("id", ""),
            "asset_name": asset.get("name", ""),
            "system_id": asset.get("system_id", ""),
            "system_name": asset.get("system_name", ""),
        }
        for asset in assets
    ]


# --- Resumen para el artefacto ----------------------------------------------


def summarize(veredictos: list[Reconciliation]) -> dict[str, Any]:
    """Conteos por estado + si queda algo bloqueante pendiente.

    Lo consume el semáforo de cada agente: un ``conflict`` sin resolver no puede
    dejar el diseño en verde.
    """
    conteo = {estado.value: 0 for estado in ReconciliationStatus}
    for veredicto in veredictos:
        conteo[veredicto.status.value] += 1
    return {
        "counts": conteo,
        "blocking": sum(1 for v in veredictos if v.blocking),
        "reconciled": sum(
            conteo[e.value]
            for e in (ReconciliationStatus.REUSE, ReconciliationStatus.EXTEND)
        ),
        "total": len(veredictos),
    }
