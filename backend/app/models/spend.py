"""Libro mayor de gasto en LLM: una fila por llamada al modelo (GAS1).

Hasta este bloque el costo se calculaba en los seis ``assemble.py`` a partir de
``estimate_tokens`` (``len // 4``) y solo existía si el pipeline llegaba a
``ASSEMBLE``. Tres consecuencias, y las tres eran el problema: era una
**estimación** teniendo el ``usage`` real del proveedor a una línea, **no
existía** si el job moría antes del final (6 de 28 jobs del historial reportaban
0 habiendo gastado), y era **por job y al final**, así que ningún tope podía
aplicarse a mitad de corrida — que es cuando se gasta.

Aquí cada llamada deja su fila, con el ``usage`` que devolvió el proveedor.

Detalles que no son cosméticos:

* **``cost_usd`` es ``NUMERIC(12,6)``, no ``float``.** Es dinero que se suma
  miles de veces contra un umbral; el error de coma flotante acumulado no tiene
  por qué aparecer en la decisión de bloquear.
* **``job_id`` es nullable con ``ON DELETE SET NULL``**, mismo criterio que
  ``agent_jobs.created_by``: el total del mes **no puede cambiar** porque alguien
  borró un job, y la fila conserva su ``agent_role``. La ingesta de documentos
  del inventario no tiene job y pasa ``job_id=None`` de forma explícita — si no
  contara, el mes tendría una fuga.
* **No hay columnas ``attempt`` ni ``outcome``.** Son derivables: una fila por
  llamada significa que la tasa de reparación es ``filas / ítems - 1``, y ése es
  justo el número que OLL-D1 declara métrica principal del experimento local. Una
  columna que se puede contar no se guarda.
* **No hay columna ``data_residency``.** Se deriva de ``provider`` vía el
  registro de proveedores; OLL1 la introduce como propiedad del ``ProviderSpec``.
  Guardarla aquí sería desnormalizar una decisión que aún no existe.

Ver ``docs/diseno-control-de-gasto.md`` §5.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, IdMixin, TimestampMixin

#: Valores admitidos de ``usage_source``. La ausencia de ``usage`` **no** es un
#: ``usage`` de cero (GAS-D4): anotar 0 dejaría el tope ciego, que es el peor
#: resultado posible porque el sistema seguiría gastando creyendo que no gasta.
#: La fila se anota con la estimación y se marca, y el total del mes informa qué
#: fracción es estimada.
USAGE_SOURCES: tuple[str, ...] = ("real", "estimado")

#: Vocabulario del ``usage_source`` de un TOTAL (un job, un mes), que no es el
#: de una fila: sumar filas de las dos clases produce un agregado que no es ni
#: una cosa ni la otra, y quien lee la cifra tiene que saberlo en el mismo sitio
#: donde la lee (GAS2, criterio 2).
TOTAL_USAGE_SOURCES: tuple[str, ...] = ("real", "mixto", "estimado", "sin_datos")


def fuente_del_total(llamadas: int, estimadas: int) -> str:
    """Qué clase de dato es un total: ``real`` | ``mixto`` | ``estimado`` | ``sin_datos``.

    ``sin_datos`` no es un adorno. Un mes con cero llamadas devolvería ``real``
    por la aritmética (cero estimadas de cero), y eso afirmaría calidad de
    medición sobre nada — la misma forma que GAS-D4 prohíbe cuando dice que la
    ausencia de un dato no es el valor 0 de ese dato.
    """
    if llamadas <= 0:
        return "sin_datos"
    if estimadas <= 0:
        return "real"
    return "estimado" if estimadas >= llamadas else "mixto"


class LlmSpend(Base, IdMixin, TimestampMixin):
    """Una llamada al LLM: qué la pidió, qué consumió y cuánto costó."""

    __tablename__ = "llm_spend"

    job_id: Mapped[Optional[str]] = mapped_column(
        String(26), ForeignKey("agent_jobs.id", ondelete="SET NULL"), nullable=True
    )
    #: Agente del ISDF (``"ef"``…``"qa"``) o ``"inventory_doc"`` para la ingesta
    #: de documentos del inventario, que no tiene job.
    agent_role: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Nodo del grafo, cuando se conoce (GAS-D10). Los nodos que no son *map*
    #: quedan en ``NULL`` y se atribuyen al agente: el hueco **se ve** en la
    #: consulta, en vez de adivinarse.
    stage: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    usage_source: Mapped[str] = mapped_column(String(16), nullable=False)
    #: TOTAL de entrada, caché incluida (GAS-D3): es lo que reporta el proveedor.
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_read_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cache_write_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    #: SUBCONJUNTO de ``output_tokens``, ya cobrado dentro de él: se guarda como
    #: información y **nunca** se suma. Es el número que explica por qué la
    #: estimación sobre el JSON volcado subcontaba.
    reasoning_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    #: Se fija SIEMPRE en UTC desde Python y no por ``server_default``: el corte
    #: del mes se calcula en ``LLM_BUDGET_TZ`` (GAS-D8) comparando contra
    #: instantes UTC, y en SQLite —el motor de la suite— una fecha con offset se
    #: guarda perdiendo el offset. Escribir siempre UTC hace que la comparación
    #: sea consistente en los dos motores; además deja inyectar un instante fijo
    #: en los tests del corte de mes.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_llm_spend_created_at", "created_at"),
        Index("ix_llm_spend_job_id", "job_id"),
        Index("ix_llm_spend_agent_stage", "agent_role", "stage"),
    )

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return (
            f"<LlmSpend {self.agent_role}/{self.stage or '-'} "
            f"{self.cost_usd} USD ({self.usage_source})>"
        )
