"""Esquemas de **structured output** de los nodos generativos del Agente QA.

Deliberadamente **más estrechos que el artefacto**: el modelo devuelve solo lo que
decide (título, pasos, datos, resultado esperado, y para los bordes el límite con su
cita), y Python le añade lo que no puede elegir — el criterio de origen, la
prioridad heredada, el esfuerzo estimado y los ids.

Esa asimetría es el cortafuegos hecho tipo: si el esquema no tiene campo para
``criterion_ref``, el LLM no puede reasignar un caso a otro criterio, y si no tiene
campo para ``priority``, no puede subirle la prioridad a su propio caso.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import AutomationHint, BoundaryKind, DataKind


class _Strict(BaseModel):
    """Base estricta: prohíbe claves desconocidas (structured output cerrado)."""

    model_config = ConfigDict(extra="forbid")


class StepExtract(_Strict):
    """Paso propuesto. El número lo pone Python: numerar es de la máquina."""

    action: str
    expected: Optional[str] = None


class DatumExtract(_Strict):
    """Dato de prueba propuesto."""

    name: str
    value: str
    kind: DataKind = DataKind.VALID
    field_ref: Optional[str] = None
    note: Optional[str] = None


class CaseExtract(_Strict):
    """Un caso funcional o negativo propuesto para el criterio en curso."""

    title: str
    #: ``True`` cuando el caso comprueba un rechazo. Es lo único que el modelo
    #: decide del tipo: funcional o negativo. Borde y autorización no salen de
    #: aquí, porque exigen anclaje que este esquema no puede aportar.
    negative: bool = False
    preconditions: list[str] = Field(default_factory=list)
    steps: list[StepExtract] = Field(min_length=1)
    test_data: list[DatumExtract] = Field(default_factory=list)
    expected_result: str
    automation_hint: AutomationHint = AutomationHint.MANUAL
    #: Refs del EF que el caso ejercita. Se **verifican** contra el EF real: las
    #: que no existan se descartan con nota (no invalidan el caso entero).
    source_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CasesExtract(_Strict):
    """Salida de TEST_DESIGN para un criterio: sus casos, y si no es verificable.

    ``not_testable`` es una salida **legítima y deseada**: un criterio como "el
    sistema debe ser rápido" no se convierte en un caso vago que alguien marcará
    "pasa" sin saber qué comprobó. Se declara, y QUESTION_GEN lo lleva al QA lead.
    """

    cases: list[CaseExtract] = Field(default_factory=list)
    not_testable: bool = False
    not_testable_reason: Optional[str] = None


class BoundaryExtract(_Strict):
    """Un límite extraído del **texto** de una validación o regla del EF.

    ``evidence`` es la cita **verbatim**, y se verifica en Python contra el texto
    real de la regla: si la frase no está ahí, el límite se descarta. Sin ese
    control, la cita sería una formalidad que el modelo podría rellenar solo.
    """

    rule_ref: str
    kind: BoundaryKind
    operator: Optional[str] = None
    value: Optional[str] = None
    evidence: str
    #: Valor concreto que cae **fuera** del límite (el que debe ser rechazado).
    invalid_value: str
    #: Valor concreto que cae justo **dentro** (el último aceptable), si aplica.
    valid_value: Optional[str] = None
    field_name: Optional[str] = None
    rationale: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class BoundariesExtract(_Strict):
    """Salida de EDGE_CASES para un criterio: los límites que encontró."""

    boundaries: list[BoundaryExtract] = Field(default_factory=list)


class DatasetRowExtract(_Strict):
    """Fila de dataset propuesta: solo los valores y qué debe pasar con ella."""

    kind: DataKind = DataKind.VALID
    values: dict[str, str] = Field(min_length=1)
    expectation: str


class DatasetExtract(_Strict):
    """Salida de DATASET para una entidad."""

    rows: list[DatasetRowExtract] = Field(default_factory=list)
