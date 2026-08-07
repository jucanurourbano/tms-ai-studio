"""Esquemas de *structured output* de los nodos LLM del Agente API.

Son contratos de la **salida del modelo**, no del artefacto final: se validan con
reparación + cuarentena vía ``ai/agents/base/structured.py``, y los ids estables,
las rutas y la trazabilidad se resuelven después en Python.

Obsérvese que en ninguno de estos esquemas hay un campo donde quepa una **ruta**,
un método HTTP ni nada con la forma del documento OpenAPI. En el nodo de acciones
el modelo entrega un **verbo** (``cerrar``) y Python construye
``/api/v1/siniestros/{siniestro_id}/cerrar``. Es la misma barrera que en el Agente
BD impide que el modelo escriba SQL: no se le pide que no lo haga, se le quita el
sitio donde ponerlo.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .enums import ApiRuleEnforcement


class ResourceExtract(BaseModel):
    """Salida del map de RESOURCES: **un** recurso redactado.

    No incluye ``name`` ni ``exposure``: el recurso que se describe es el que se
    envió en el prompt, y aceptarlos de vuelta abriría la puerta a renombrar un
    recurso o a cambiar cuánto se publica de él.
    """

    display_name: Optional[str] = None
    description: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ActionExtract(BaseModel):
    """Una acción de negocio propuesta sobre un recurso.

    ``evidence`` es una **cita literal** del texto del ``PRO-``/``BR-``/``VAL-``
    citado, y se verifica en Python contra el original. Es el mismo trato que
    reciben los valores de catálogo en el Agente BD, y por la misma razón: es el
    único punto por donde podría entrar al contrato algo que nadie pidió.
    """

    #: Verbo en infinitivo y en español (``cerrar``). Nunca una ruta.
    action: str
    purpose: str
    evidence: str
    source_refs: list[str] = Field(default_factory=list)
    #: ``True`` si la acción necesita datos del cliente además del identificador.
    request_needed: bool = False
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class HiddenColumnExtract(BaseModel):
    """Columna que no debe salir por la API, con su motivo.

    El motivo es obligatorio: ocultar un dato sin explicar por qué convierte una
    decisión de diseño en una omisión que nadie puede revisar.
    """

    name: str
    reason: str


class ResourceSchemaExtract(BaseModel):
    """Salida del map de SCHEMAS: las dos decisiones de exposición de un recurso.

    No incluye la lista de campos: el conjunto lo fija el modelo de datos. Aquí
    solo se decide **qué se esconde** y **qué compone la fila de un listado**.
    """

    hidden_columns: list[HiddenColumnExtract] = Field(default_factory=list)
    summary_columns: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ResourceActionsExtract(BaseModel):
    """Salida del map de ENDPOINTS: las acciones de **un** recurso.

    La lista vacía es un resultado correcto y frecuente: la mayoría de los recursos
    de un sistema de gestión no tienen más operaciones que su CRUD.
    """

    actions: list[ActionExtract] = Field(default_factory=list)


class ScopeExtract(BaseModel):
    """Alcance por fila de un actor sobre un recurso.

    ``scope`` **no admite ``all`` ni ``none``**: el modelo solo puede *restringir*.
    Es una decisión estructural, no una instrucción del prompt — quitarle el sitio
    donde escribir "este actor lo ve todo" hace imposible que una alucinación
    amplíe un permiso. Lo peor que puede pasar con una restricción inventada es que
    alguien vea de menos, y eso se detecta al usarlo; lo contrario no.
    """

    actor_ref: str
    scope: Literal["own", "own_team", "own_branch", "custom"]
    expression: Optional[str] = None
    #: Columnas reales que materializan el filtro. Vacío = no se puede aplicar
    #: todavía, y eso es información valiosa, no un error a esconder.
    column_names: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ResourceScopesExtract(BaseModel):
    """Salida del map de AUTHORIZATION: los alcances por fila de **un** recurso."""

    scopes: list[ScopeExtract] = Field(default_factory=list)


class RuleClassificationExtract(BaseModel):
    """Destino de una regla del EF que quedó sin asignar automáticamente."""

    rule_ref: str
    enforcement: ApiRuleEnforcement
    endpoint_refs: list[str] = Field(default_factory=list)
    note: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RuleMappingsExtract(BaseModel):
    """Salida de RULE_MAPPING: el destino de las reglas huérfanas."""

    mappings: list[RuleClassificationExtract] = Field(default_factory=list)
