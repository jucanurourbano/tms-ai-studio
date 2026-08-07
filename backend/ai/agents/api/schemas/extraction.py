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

from typing import Optional

from pydantic import BaseModel, Field


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


class ResourceActionsExtract(BaseModel):
    """Salida del map de ENDPOINTS: las acciones de **un** recurso.

    La lista vacía es un resultado correcto y frecuente: la mayoría de los recursos
    de un sistema de gestión no tienen más operaciones que su CRUD.
    """

    actions: list[ActionExtract] = Field(default_factory=list)
