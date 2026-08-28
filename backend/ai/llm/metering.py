"""La medición: se lee el ``usage`` real del proveedor y se anota la fila (GAS1).

**El punto de medición es el CLIENTE, no el ensamblador (GAS-D1).** Toda la
contabilidad se muda de los seis ``assemble.py`` al ``complete_json`` del
cliente: el único sitio por el que pasa cada token, y el único que ya sabe
proveedor, modelo y tarifa. Resuelve de una vez los tres problemas de la
estimación —la cifra es real, existe aunque el job muera en el primer nodo, y hay
un punto donde comprobar un tope **antes** de gastar—.

**El protocolo público NO cambia (GAS-D2).** ``LLMClient.complete_json(system,
user) -> str`` se queda exactamente igual: lo importan los ~30 nodos generativos
y todos los mocks de la suite. Debajo aparece uno interno,
``UsageReportingClient.complete(...) -> Completion``, que sí devuelve el
``usage``. El envoltorio lo aplica **``get_llm``** y no cada proveedor: mismo
patrón que la capa 1 del cortafuegos de tests, y por la misma razón —registrar un
proveedor nuevo hereda la medición sin que nadie se acuerde—.

*Alternativa descartada:* ``client.last_usage``. El cliente es **compartido** por
los workers concurrentes de un *map* (``get_llm`` se llama una vez por job y se
inyecta por ``config``), así que un atributo mutable atribuiría el ``usage`` de
una llamada a otra. No es una imprecisión: es una mentira con forma de dato.

Ver ``docs/diseno-control-de-gasto.md`` §4.
"""

import time
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Optional, Protocol

from ai.llm import budget as _budget
from ai.tools.chunker import estimate_tokens
from app.config.settings import settings
from app.core.logger import logger

MILLON = Decimal(1_000_000)
CENTIMOS = Decimal("0.000001")


@dataclass(frozen=True)
class Usage:
    """Lo que consumió una llamada, según el proveedor.

    ``input_tokens`` es el **TOTAL**, caché incluida (GAS-D3): es lo que reporta
    ``langchain-anthropic``, que suma explícitamente los tokens cacheados de
    vuelta porque la API los excluye.

    ``reasoning`` es un **SUBCONJUNTO** de ``output_tokens``, ya cobrado dentro de
    él: se guarda como información y **nunca** se suma. Es el número que explica
    por qué estimar la salida sobre el JSON volcado subcontaba — los bloques
    ``thinking`` no aparecen ahí y Anthropic los cobra igual.
    """

    input_tokens: int
    output_tokens: int
    cache_read: int = 0
    cache_write: int = 0
    reasoning: int = 0


@dataclass(frozen=True)
class Completion:
    """Respuesta del proveedor con su consumo.

    ``usage=None`` significa que el proveedor **no lo reportó**, que no es lo
    mismo que haber consumido cero (GAS-D4).
    """

    text: str
    usage: Optional[Usage]


class UsageReportingClient(Protocol):
    """Protocolo **interno**: el que sí devuelve el consumo de la llamada."""

    async def complete(self, *, system: str, user: str) -> Completion: ...


def _campo(origen: Any, nombre: str, defecto: Any = None) -> Any:
    """Lee un campo tanto de un dict como de un objeto."""
    if origen is None:
        return defecto
    if isinstance(origen, dict):
        return origen.get(nombre, defecto)
    return getattr(origen, nombre, defecto)


def usage_desde_mensaje(msg: Any) -> Optional[Usage]:
    """Extrae el ``usage`` de un ``AIMessage`` de LangChain, o ``None``.

    Devolver ``None`` cuando falta es deliberado: quien decide qué hacer con la
    ausencia es ``MeteredLLMClient``, y lo que hace es marcarla, no rellenarla
    con ceros.
    """
    meta = _campo(msg, "usage_metadata")
    if not meta:
        return None
    entrada = _campo(meta, "input_tokens")
    salida = _campo(meta, "output_tokens")
    if entrada is None or salida is None:
        return None
    detalle_entrada = _campo(meta, "input_token_details") or {}
    detalle_salida = _campo(meta, "output_token_details") or {}
    return Usage(
        input_tokens=int(entrada),
        output_tokens=int(salida),
        cache_read=int(_campo(detalle_entrada, "cache_read", 0) or 0),
        cache_write=int(_campo(detalle_entrada, "cache_creation", 0) or 0),
        reasoning=int(_campo(detalle_salida, "reasoning", 0) or 0),
    )


def costo(usage: Usage, precios: tuple[float, float]) -> Decimal:
    """Costo en USD de un consumo, con la aritmética de caché de GAS-D3.

    ``input_tokens`` viene con la caché **ya sumada**, así que aplicarle la tarifa
    de entrada cobraría 10x de más las lecturas (valen 0,1x) y 20% de menos las
    escrituras (valen 1,25x)::

        base  = input_tokens - cache_read - cache_write
        costo = base*tin + cache_read*tin*0,10 + cache_write*tin*1,25 + out*tout

    Hoy el caching no está activado en ninguna parte del árbol, así que los
    contadores vienen en 0 y esto se reduce **byte a byte** a la fórmula de
    siempre. Se escribe igual porque el día que alguien active ``cache_control``
    para abaratar el ``CRITIQUE`` sin techo, el tope no puede empezar a mentir.

    Guarda: si ``base`` sale negativa —no debería—, se cae a ``input_tokens``. Se
    yerra hacia **cobrar de más**, nunca de menos.
    """
    entrada, salida = precios
    tin = Decimal(str(entrada))
    tout = Decimal(str(salida))
    lectura = Decimal(str(settings.LLM_CACHE_READ_FACTOR))
    escritura = Decimal(str(settings.LLM_CACHE_WRITE_FACTOR))

    base = usage.input_tokens - usage.cache_read - usage.cache_write
    if base < 0:
        logger.warning(
            "Libro mayor: input_tokens (%s) es menor que la caché declarada "
            "(%s lectura + %s escritura). Se cobra sobre el total para errar "
            "hacia cobrar de más.",
            usage.input_tokens,
            usage.cache_read,
            usage.cache_write,
        )
        base = usage.input_tokens

    bruto = (
        Decimal(base) * tin
        + Decimal(usage.cache_read) * tin * lectura
        + Decimal(usage.cache_write) * tin * escritura
        + Decimal(usage.output_tokens) * tout
    ) / MILLON
    # ROUND_HALF_EVEN es el redondeo de `round()` de Python: así el resultado
    # coincide con `compute_cost` byte a byte cuando no hay caché.
    return bruto.quantize(CENTIMOS, rounding=ROUND_HALF_EVEN)


def costo_maximo_de_una_llamada(precios: tuple[float, float]) -> Decimal:
    """Techo declarado de lo que puede costar UNA llamada (para el margen).

    Los dos números son **supuestos auditables**, no límites aplicados: hoy no
    existe ningún techo de entrada porque nada acota ``CRITIQUE``. Ese techo lo
    pone el canario de truncamiento de OLL2; aquí solo se usa para dimensionar el
    margen con el que se comprueba el tope (GAS-D5).
    """
    entrada, salida = precios
    bruto = (
        Decimal(settings.LLM_MAX_INPUT_TOKENS_ASSUMED) * Decimal(str(entrada))
        + Decimal(settings.LLM_MAX_OUTPUT_TOKENS_ASSUMED) * Decimal(str(salida))
    ) / MILLON
    return bruto.quantize(CENTIMOS, rounding=ROUND_HALF_EVEN)


class MeteredLLMClient:
    """Comprueba el tope, delega, y anota la fila. **En ese orden.**

    El freno vive aquí dentro y **antes de delegar** —no en el servicio ni en el
    nodo—. Un freno en el servicio es un freno que un nodo se salta; ya nos pasó
    con la ingesta de documentos del inventario, que se saltaba incluso el runner.
    """

    def __init__(
        self,
        inner: Any,
        *,
        agent_role: str,
        job_id: Optional[str],
        stage: Optional[str] = None,
    ) -> None:
        self._inner = inner
        self._agent_role = agent_role
        self._job_id = job_id
        self._stage = stage

    # -- Identidad: se delega, no se falsea -------------------------------
    # Quien pregunte por el proveedor, el modelo o la clase de dato tiene que
    # recibir la verdad del cliente de debajo: si el envoltorio contestara por su
    # cuenta, los tests que inspeccionan la fábrica estarían comprobando el
    # envoltorio y dejarían de detectar una resolución equivocada.

    @property
    def inner(self) -> Any:
        return self._inner

    @property
    def provider(self) -> str:
        return getattr(self._inner, "provider", "desconocido")

    @property
    def model(self) -> str:
        return getattr(self._inner, "model", "desconocido")

    @property
    def data_class(self) -> Any:
        return getattr(self._inner, "data_class", None)

    @property
    def stage(self) -> Optional[str]:
        return self._stage

    @property
    def job_id(self) -> Optional[str]:
        return self._job_id

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return self._inner.estimate_cost(input_tokens, output_tokens)

    def for_stage(self, stage: str) -> "MeteredLLMClient":
        """Copia etiquetada con el nodo, para atribuir la fila (GAS-D10).

        Comparte el cliente de debajo: es una **etiqueta**, no un cliente nuevo.
        """
        return MeteredLLMClient(
            self._inner,
            agent_role=self._agent_role,
            job_id=self._job_id,
            stage=stage,
        )

    # -- La llamada -------------------------------------------------------

    def _precios(self) -> tuple[float, float]:
        # Import perezoso: el registro importa los proveedores y éstos importan
        # este módulo. Resolverlo aquí evita el ciclo sin duplicar la tarifa.
        from ai.llm.registry import get_spec

        return get_spec(self.provider).price_per_mtok(self.model)

    async def _llamar(self, *, system: str, user: str) -> Completion:
        """Delega en el protocolo interno; si el cliente no lo tiene, sin usage.

        Un proveedor sin ``complete`` produciría filas 100% estimadas, así que hay
        un candado parametrizado sobre ``PROVIDERS`` que exige el método. La caída
        existe para los dobles de la suite, no como camino de producción.
        """
        completar = getattr(self._inner, "complete", None)
        if completar is not None:
            return await completar(system=system, user=user)
        return Completion(
            text=await self._inner.complete_json(system=system, user=user), usage=None
        )

    def _usage_o_estimacion(
        self, completion: Completion, system: str, user: str
    ) -> tuple[Usage, str]:
        """``usage`` ausente NO es ``usage`` cero (GAS-D4).

        Tercera vez que el proyecto se topa con la misma forma: ``sqlglot``
        degradando a ``Command``, *redactar en vez de rechazar*, Ollama truncando
        en silencio. **La ausencia de un dato no es el valor 0 de ese dato.**
        Anotar 0 aquí dejaría el tope ciego —el peor resultado posible, porque el
        sistema seguiría gastando creyendo que no gasta—.
        """
        if completion.usage is not None:
            return completion.usage, "real"
        logger.warning(
            "El proveedor '%s' no reportó usage en una llamada de %s/%s: la fila "
            "del libro mayor va con una ESTIMACIÓN y así queda marcada. Si esto "
            "aparece con Anthropic, es un bug del cliente.",
            self.provider,
            self._agent_role,
            self._stage or "-",
        )
        return (
            Usage(
                input_tokens=estimate_tokens(system + user),
                output_tokens=estimate_tokens(completion.text),
            ),
            "estimado",
        )

    async def complete_json(self, *, system: str, user: str) -> str:
        """Comprueba el tope, llama, anota. El orden **es** la garantía."""
        sumidero = _budget.current_sink()
        precios = self._precios()
        tope_llamada = costo_maximo_de_una_llamada(precios)
        desde, hasta = _budget.limites_del_mes()

        try:
            totales = await sumidero.totales(
                desde=desde, hasta=hasta, job_id=self._job_id
            )
        except _budget.BudgetError:
            raise
        except Exception as exc:  # libro mayor ilegible: se niega (GAS-D7)
            raise _budget.BudgetUnavailableError(
                "No se puede llamar al modelo porque falló la lectura del libro "
                f"mayor de gasto ({type(exc).__name__}: {exc}). El control de "
                "gasto es fail-closed: sin libro mayor no hay gasto."
            ) from exc

        _budget.verificar(totales, tope_llamada, job_id=self._job_id)

        inicio = time.monotonic()
        completion = await self._llamar(system=system, user=user)
        duracion_ms = int((time.monotonic() - inicio) * 1000)

        usage, fuente = self._usage_o_estimacion(completion, system, user)
        await self._anotar(sumidero, usage, fuente, precios, duracion_ms)
        return completion.text

    async def _anotar(
        self,
        sumidero: Any,
        usage: Usage,
        fuente: str,
        precios: tuple[float, float],
        duracion_ms: int,
    ) -> None:
        """Escribe la fila. Si no se puede escribir, **falla**.

        Tentador swallowear: el dinero ya está gastado y devolver el texto no
        cuesta nada más. Pero una fila que no se escribe es gasto que el tope no
        ve, y a partir de ahí el freno protege un número que no es el real —la
        ceguera que este bloque existe para eliminar—. Se falla ruidosamente, y
        la siguiente llamada se negará igual porque el sumidero sigue roto.
        """
        fila = _budget.SpendRow(
            job_id=self._job_id,
            agent_role=self._agent_role,
            stage=self._stage,
            provider=self.provider,
            model=self.model,
            usage_source=fuente,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read,
            cache_write_tokens=usage.cache_write,
            reasoning_tokens=usage.reasoning,
            cost_usd=costo(usage, precios),
            duration_ms=duracion_ms,
        )
        try:
            await sumidero.anotar(fila)
        except _budget.BudgetError:
            raise
        except Exception as exc:
            logger.error(
                "No se pudo anotar en el libro mayor una llamada YA FACTURADA "
                "(%s/%s, %s USD): el tope deja de ver ese gasto.",
                self._agent_role,
                self._stage or "-",
                fila.cost_usd,
            )
            raise _budget.BudgetUnavailableError(
                "La llamada al modelo se hizo pero no se pudo anotar en el libro "
                f"mayor ({type(exc).__name__}: {exc}). Se falla en vez de seguir: "
                "gasto que no se anota es gasto que el tope no ve."
            ) from exc


__all__ = [
    "Completion",
    "MeteredLLMClient",
    "Usage",
    "UsageReportingClient",
    "costo",
    "costo_maximo_de_una_llamada",
    "usage_desde_mensaje",
]
