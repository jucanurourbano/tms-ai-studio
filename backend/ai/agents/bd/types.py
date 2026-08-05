"""Normalización determinista de tipos: ``data_type`` del EF → ``logical_type``.

``FieldDef.data_type`` del EF es **texto libre en español** ("texto", "fecha y
hora", "monto", vacío...), porque sale de lo que dijera el documento de Procesos.
Aquí se traduce a un ``LogicalType`` del enum cerrado, con tres niveles de
certeza explícitos (``TypeSource``):

- ``declared``: el EF declara un tipo y se reconoce en la tabla de sinónimos.
- ``inferred_from_name``: el EF no declara tipo, pero el **nombre** del campo lo
  delata (``fecha_siniestro`` → date, ``monto`` → decimal, ``guia_id`` → bigint).
- ``unknown``: no hay base para decidir. Se propone un candidato conservador y se
  marca ``ambiguous``: **el vacío queda visible y se pregunta al DBA**, nunca se
  adivina en silencio.

Que esto viva en Python y no en el prompt es deliberado: es la parte reproducible
del tipado (mismo EF ⇒ mismo tipo) y deja al LLM solo el juicio que no se puede
tabular (longitudes, precisión, semántica del campo).
"""

from enum import Enum
from typing import Optional

from ai.knowledge import load_db_conventions, type_synonyms

from .naming import snake, strip_accents
from .schemas.enums import LogicalType


class TypeSource(str, Enum):
    """De dónde salió el tipo lógico de una columna."""

    DECLARED = "declared"
    INFERRED_FROM_NAME = "inferred_from_name"
    UNKNOWN = "unknown"


#: Candidato conservador cuando no hay ninguna base para decidir. Se elige
#: ``string`` porque es el tipo que menos información destruye si la suposición
#: resulta equivocada (un número cabe en texto; lo contrario, no).
FALLBACK_TYPE = LogicalType.STRING

#: Sufijos/nombres que delatan el tipo cuando el EF no declara ninguno. El orden
#: importa: gana la primera coincidencia, así que lo más específico va antes.
_NAME_HINTS: tuple[tuple[tuple[str, ...], LogicalType], ...] = (
    (("_id", "id_", "codigo_interno"), LogicalType.BIGINT),
    (("fecha_hora", "fechahora", "timestamp"), LogicalType.TIMESTAMP),
    (("fecha", "fec_"), LogicalType.DATE),
    (("hora",), LogicalType.TIME),
    (("monto", "importe", "precio", "costo", "total", "saldo"), LogicalType.DECIMAL),
    (("peso", "volumen", "porcentaje", "tarifa"), LogicalType.DECIMAL),
    (("cantidad", "numero_de", "contador", "correlativo"), LogicalType.INTEGER),
    (("es_", "tiene_", "activo", "habilitado", "vigente"), LogicalType.BOOLEAN),
    (("observacion", "descripcion", "comentario", "detalle"), LogicalType.TEXT),
    (("correo", "email", "nombre", "codigo", "numero"), LogicalType.STRING),
)


class TypeDecision:
    """Resultado de normalizar el tipo de un campo del EF."""

    __slots__ = ("logical_type", "source", "ambiguous", "raw", "confidence")

    def __init__(
        self,
        logical_type: LogicalType,
        source: TypeSource,
        ambiguous: bool,
        raw: Optional[str],
        confidence: float,
    ) -> None:
        self.logical_type = logical_type
        self.source = source
        self.ambiguous = ambiguous
        self.raw = raw
        self.confidence = confidence

    def as_dict(self) -> dict:
        """Serializable para el estado del grafo (compatible con checkpointer)."""
        return {
            "logical_type": self.logical_type.value,
            "type_source": self.source.value,
            "type_ambiguous": self.ambiguous,
            "raw_type": self.raw,
            "confidence": self.confidence,
        }


def _normalize(text: str) -> str:
    """Minúsculas sin acentos y con espacios colapsados, para comparar."""
    return " ".join(strip_accents(text or "").lower().split())


def _from_declared(raw: str) -> Optional[LogicalType]:
    """Busca el tipo declarado en la tabla de sinónimos del YAML."""
    needle = _normalize(raw)
    if not needle:
        return None

    # 1) El propio nombre del logical_type ("string", "date"): el EF de ejemplo ya
    #    trae valores así cuando el documento venía tabulado.
    for logical in LogicalType:
        if needle == logical.value:
            return logical

    # 2) Sinónimos exactos en español.
    for logical, words in type_synonyms().items():
        if any(needle == _normalize(word) for word in words):
            return LogicalType(logical)

    # 3) Sinónimo contenido en la frase ("número decimal de 2 posiciones"). Se
    #    prefiere el sinónimo más largo para que "texto largo" gane a "texto".
    candidates = [
        (len(word), logical)
        for logical, words in type_synonyms().items()
        for word in words
        if _normalize(word) in needle
    ]
    if candidates:
        return LogicalType(max(candidates)[1])
    return None


def _from_name(field_name: str) -> Optional[LogicalType]:
    """Infiere el tipo desde el nombre del campo (segunda oportunidad)."""
    name = snake(field_name)
    if not name:
        return None
    for hints, logical in _NAME_HINTS:
        for hint in hints:
            if name == hint.strip("_") or hint in name:
                return logical
    return None


def normalize_type(
    data_type: Optional[str], field_name: str = "", required: bool = False
) -> TypeDecision:
    """Traduce el tipo de un campo del EF a un ``LogicalType`` con su certeza.

    ``required`` no cambia el tipo: se conserva en el candidato para que
    QUESTION_GEN decida si la ambigüedad es **bloqueante** (columna obligatoria
    sin tipo claro) o no (columna opcional).
    """
    declared = _from_declared(data_type or "")
    if declared is not None:
        return TypeDecision(declared, TypeSource.DECLARED, False, data_type, 0.9)

    inferred = _from_name(field_name)
    if inferred is not None:
        return TypeDecision(
            inferred, TypeSource.INFERRED_FROM_NAME, False, data_type, 0.6
        )

    return TypeDecision(
        FALLBACK_TYPE,
        TypeSource.UNKNOWN,
        True,
        data_type,
        0.3 if required else 0.4,
    )


def default_length(logical_type: LogicalType, field_name: str = "") -> Optional[int]:
    """Longitud por defecto de un ``string`` según las convenciones de la casa.

    Devuelve ``None`` para los tipos que no llevan longitud. Aplicar un default
    **no** es silencioso: la columna queda con ``type_ambiguous`` si el EF no
    precisaba nada y QUESTION_GEN agrupa todas esas columnas en una pregunta.
    """
    if logical_type is not LogicalType.STRING:
        return None
    defaults = load_db_conventions().get("defaults", {}) or {}
    name = snake(field_name)
    if "codigo" in name or name.endswith("_cod"):
        return int(defaults.get("code_length", 30))
    if "nombre" in name or "razon_social" in name:
        return int(defaults.get("name_length", 150))
    return int(defaults.get("string_length", 100))


def default_precision(logical_type: LogicalType) -> tuple[Optional[int], Optional[int]]:
    """Precisión/escala por defecto de un ``decimal`` (``(None, None)`` si no aplica)."""
    if logical_type is not LogicalType.DECIMAL:
        return None, None
    decimal = (load_db_conventions().get("defaults", {}) or {}).get("decimal", {}) or {}
    return int(decimal.get("precision", 12)), int(decimal.get("scale", 2))
