"""Campos de reconciliación que los artefactos de diseño incorporan (INV4).

Vive aquí, y no duplicado en los tres agentes, porque el veredicto significa lo
MISMO en Arquitectura, BD y API: la UI pinta el mismo badge, el semáforo aplica la
misma regla y quien lee el artefacto no tiene que aprenderlo tres veces.

**Todo es opcional.** Un artefacto generado antes de INV4 —o generado para un
sistema que no está en el inventario— sigue validando exactamente igual. La
reconciliación añade información; su ausencia no invalida nada.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    """Prohíbe campos no declarados (mismo criterio que el resto de contratos)."""

    model_config = ConfigDict(extra="forbid")


class MatchedAsset(_Strict):
    """El elemento del inventario con el que se emparejó la propuesta.

    Lleva los identificadores del activo y del sistema para que la vista pueda
    enlazar al inventario real y enseñar lo existente junto a lo propuesto: un
    veredicto que no se puede comprobar no es revisable.
    """

    name: str
    asset_id: str = ""
    asset_name: str = ""
    system_id: str = ""
    system_name: str = ""
    #: Parecido del nombre, en [0,1]. Se guarda para poder auditar el umbral.
    name_score: float = Field(default=0.0, ge=0.0, le=1.0)
    #: Solapamiento estructural, cuando aplica (tablas). ``None`` si no se midió.
    structure_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ReconciliationRef(_Strict):
    """Veredicto de reconciliación de UN elemento propuesto."""

    #: ``reuse`` | ``extend`` | ``new`` | ``conflict``.
    status: str
    #: Por qué se decidió así, en español y legible por una persona.
    reason: str
    #: ``True`` si exige respuesta humana antes de dar el diseño por bueno. Solo
    #: los ``conflict`` lo son.
    blocking: bool = False
    matched: Optional[MatchedAsset] = None
    #: Lo que le falta a lo existente para servir (solo en ``extend``).
    missing: list[str] = Field(default_factory=list)


class ReconciliationSummary(_Strict):
    """Resumen de la fase para la cabecera del artefacto y el semáforo."""

    #: Sistema del inventario contra el que se reconcilió. ``None`` = no se hizo.
    system_id: Optional[str] = None
    system_name: Optional[str] = None
    counts: dict[str, int] = Field(default_factory=dict)
    blocking: int = 0
    reconciled: int = 0
    total: int = 0
    #: ``False`` cuando no había inventario contra el que comparar. Distingue "no
    #: se reconcilió" de "se reconcilió y no había nada": la primera no es un
    #: diseño greenfield validado, es una fase que no se ejecutó.
    performed: bool = False
    #: Por qué NO se ejecutó, cuando ``performed`` es ``False``. Una fase saltada
    #: sin motivo escrito es indistinguible de una que no existe, y quien lea el
    #: artefacto merece saber si el diseño es greenfield por decisión o por
    #: descuido.
    reason: str = ""
