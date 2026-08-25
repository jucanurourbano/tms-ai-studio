"""Capas 1, 2 y 4 del guard: el destino explorable, y lo que de él no sale.

El precedente literal es ``app/services/introspection_service.py`` (INV2), con
tres diferencias que este módulo añade a conciencia:

* **A1 — el alias es una fuga.** Todo el diseño protege el host (el ancla guarda
  el *path*, no la URL completa), pero el alias sí viaja al artefacto **y al
  prompt**. Un alias tipo ``tms-prod-urbano-aws`` filtraría al proveedor del
  modelo el mapa de infraestructura que nos esforzamos en no mandar. Se resuelve
  por **estructura y no por nomenclatura**: el alias **no viaja al prompt**
  —lo único que el modelo ve del destino es :func:`alcance_para_prompt`, que no
  tiene dónde escribirlo— y como refuerzo el alias **no puede ser una
  coordenada**: sin puntos, sin dos puntos, sin barras, así que ni siquiera un
  alias mal elegido puede *ser* un host o una URL. Una lista negra de palabras
  ("prod", "aws") habría sido lo contrario: una promesa que un nombre nuevo
  incumple sin que nadie se entere.

* **A2 — el alias sintético.** ``data_class="real"`` sin excepción es correcto
  para sistemas reales y hace el Modo C **imposible de probar de punta a punta**
  sin gastar saldo del proveedor. Explorar el entorno de desarrollo propio
  —``localhost``, con semillas sintéticas— no es una fuente real. Así que un
  destino **puede** declararse sintético, y solo si su host es local, verificado
  por el validador y no por confianza: cualquier host no local es ``real``, y
  declararlo sintético es un error de configuración explícito. No debilita la
  regla; la hace ejecutable.

* **QA-D21 §4.2 — precondición de solo lectura.** Un destino sin
  ``readonly_verified: true`` **no se explora** (``GateError`` 409). Si la
  aplicación explorada no tiene una cuenta de solo lectura, lo único que separa
  una escritura de producción de nosotros son nuestras propias capas: aceptable
  como defensa en profundidad, inaceptable como único control. Afirmarlo es una
  línea de configuración de quien despliega (``admin``, QA-D17).

Los destinos viven en el entorno del despliegue (``settings``/``.env``), **jamás**
en la base de datos de la plataforma ni en un artefacto.
"""

import re
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
    model_validator,
)

from ai.errors import GateError
from ai.llm.base import DataClass
from app.config.settings import settings
from app.errors import ForbiddenError, NotFoundError

#: Hosts que cuentan como "mi propia máquina" para A2. Un nombre que no esté aquí
#: es externo aunque resolviera a loopback: el guard falla cerrado, que es la
#: dirección correcta del error (mismo criterio que ``es_destino_local`` del
#: cortafuegos de tests).
HOSTS_LOCALES = frozenset({"localhost", "localhost.localdomain", "127.0.0.1", "::1"})

#: Esquemas admitidos para la URL base de un destino.
ESQUEMAS_BASE = ("http", "https")

#: Forma del alias: minúsculas, dígitos y guiones. Empieza por letra, 2–32
#: caracteres. Sin puntos, dos puntos, barras, arrobas ni subrayados, de modo que
#: un alias **no pueda ser** un host, una IP ni una URL (A1).
_ALIAS_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")

_PUERTOS_POR_ESQUEMA = {"http": 80, "https": 443}


class ExploreTarget(BaseModel):
    """Un destino explorable, tal como lo declara el despliegue.

    ``extra="forbid"`` a propósito: una clave mal escrita
    (``readonly_verifed: true``) dejaría el destino con el default ``false`` y
    fallaría luego con un mensaje sobre solo-lectura que no explica nada. Así
    falla al validar, diciendo cuál es la clave que no existe.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    alias: str
    url: str
    readonly_verified: bool = False
    data_class: DataClass = "real"
    #: Ruta en el servidor del ``storage_state`` que deja el CLI de login (QC6).
    #: Nunca se expone por la API ni se escribe en el artefacto.
    storage_state: Optional[str] = None

    @field_validator("alias")
    @classmethod
    def _el_alias_no_puede_ser_una_coordenada(cls, valor: str) -> str:
        if not _ALIAS_RE.match(valor or ""):
            raise ValueError(
                f"Alias inválido: «{valor}». Debe empezar por letra y usar solo "
                "minúsculas, dígitos y guiones (2–32). Sin puntos, dos puntos ni "
                "barras: un alias no puede ser un host ni una URL, porque el "
                "alias se lee en el plan y en el PDF y el host no debe viajar ahí."
            )
        return valor

    @field_validator("url")
    @classmethod
    def _la_url_base_es_http(cls, valor: str) -> str:
        partes = urlparse(valor or "")
        if partes.scheme not in ESQUEMAS_BASE or not partes.hostname:
            raise ValueError(
                "La URL base del destino debe ser http(s) con host explícito "
                f"(recibido: «{redact_url(valor)}»)."
            )
        return valor

    @model_validator(mode="after")
    def _sintetico_solo_si_el_host_es_local(self) -> "ExploreTarget":
        """A2, verificado por candado y no por confianza."""
        if self.data_class == "sintetico" and self.host not in HOSTS_LOCALES:
            raise ValueError(
                f"El destino «{self.alias}» se declara sintético pero su host "
                f"«{self.host}» no es local. Solo un host local "
                f"({', '.join(sorted(HOSTS_LOCALES))}) puede declararse sintético: "
                "una aplicación desplegada muestra datos reales, y clasificarlos "
                "como sintéticos enviaría producción a un proveedor no autorizado."
            )
        return self

    @property
    def host(self) -> str:
        """Host del destino, en minúsculas y sin puerto."""
        return (urlparse(self.url).hostname or "").lower()

    @property
    def origin(self) -> str:
        """Origen normalizado (``esquema://host:puerto``) para el mismo-origen."""
        partes = urlparse(self.url)
        esquema = (partes.scheme or "").lower()
        puerto = partes.port or _PUERTOS_POR_ESQUEMA.get(esquema, 0)
        return f"{esquema}://{self.host}:{puerto}"

    @property
    def url_publica(self) -> str:
        """La URL base sin credencial, apta para logs y respuestas."""
        return redact_url(self.url)


def redact_url(url: str) -> str:
    """Devuelve la URL sin credenciales, apta para logs, API y artefacto.

    Mismo criterio que ``redact_dsn`` de INV2: la credencial no aparece **en
    ningún** sitio del que se pueda copiar.
    """
    return re.sub(r"//[^/@]*@", "//***@", url or "")


def _construir(alias: str, crudo: Any) -> ExploreTarget:
    """Valida un destino declarado. La clave del mapa manda sobre el contenido."""
    if not isinstance(crudo, dict):
        raise ValueError(
            f"El destino «{alias}» debe ser un objeto con al menos «url» y "
            "«readonly_verified»."
        )
    return ExploreTarget.model_validate({**crudo, "alias": alias})


def _hosts_permitidos() -> set[str]:
    return {h.strip().lower() for h in settings.QA_EXPLORE_ALLOWED_HOSTS if h.strip()}


def available_targets() -> list[dict[str, str]]:
    """Destinos configurados que además superan TODAS las capas del guard.

    Solo alias y host: la API nunca devuelve una URL con credencial (capa 4). Un
    destino mal declarado, no autorizado o sin solo-lectura **no se lista**, para
    que la pantalla no ofrezca un botón que siempre va a fallar — mismo criterio
    que ``available_sources()`` de INV2. Quien pregunte por él **por alias** sí
    recibe el motivo exacto: ver :func:`assert_target_authorized`.
    """
    if not settings.QA_EXPLORE_ENABLED:
        return []
    permitidos = _hosts_permitidos()
    if not permitidos:
        return []

    listados: list[dict[str, str]] = []
    for alias, crudo in (settings.QA_EXPLORE_TARGETS or {}).items():
        try:
            destino = _construir(alias, crudo)
        except (ValidationError, ValueError):
            continue
        if destino.host not in permitidos or not destino.readonly_verified:
            continue
        listados.append(
            {
                "alias": destino.alias,
                "host": destino.host,
                "data_class": destino.data_class,
            }
        )
    return listados


def assert_target_authorized(alias: str) -> ExploreTarget:
    """Resuelve el alias comprobando TODAS las capas. Fail-closed.

    Devuelve el destino; lanza ``ForbiddenError`` / ``NotFoundError`` /
    ``GateError`` si algo no cuadra. **Nunca** incluye la credencial en el
    mensaje.
    """
    if not settings.QA_EXPLORE_ENABLED:
        raise ForbiddenError(
            "La exploración de aplicaciones vivas (Modo C) está desactivada. "
            "Actívala con QA_EXPLORE_ENABLED en la configuración del despliegue."
        )

    permitidos = _hosts_permitidos()
    if not permitidos:
        raise ForbiddenError(
            "No hay ningún host autorizado para exploración "
            "(QA_EXPLORE_ALLOWED_HOSTS está vacía). Sin allowlist no se navega a "
            "ninguna parte."
        )

    crudo = (settings.QA_EXPLORE_TARGETS or {}).get(alias)
    if not crudo:
        raise NotFoundError(
            f"No hay ningún destino explorable llamado «{alias}». Los destinos se "
            "declaran en la configuración del despliegue, no desde la API: la "
            "exploración no acepta URLs."
        )

    try:
        destino = _construir(alias, crudo)
    except (ValidationError, ValueError) as exc:
        raise ForbiddenError(
            f"El destino «{alias}» está mal declarado y no se explora: {exc}"
        ) from exc

    if destino.host not in permitidos:
        raise ForbiddenError(
            f"El host «{destino.host}» del destino «{alias}» no está en la "
            "allowlist de exploración. Añádelo explícitamente si debe explorarse."
        )

    if not destino.readonly_verified:
        raise GateError(
            f"El destino «{alias}» no declara «readonly_verified: true». La "
            "exploración exige una cuenta de SOLO LECTURA en la aplicación "
            "explorada: sin ella, lo único que separa una escritura de producción "
            "de nosotros son nuestras propias capas."
        )

    return destino


def data_class_de_exploracion(target: ExploreTarget) -> DataClass:
    """Clase de datos derivada del destino (A2 + QA-D22).

    El Modo C es el caso donde **el sistema sabe más que quien llama**: el destino
    es un alias registrado por un admin contra una aplicación desplegada, y el DOM
    que se captura contiene guías, RUC y nombres reales. Así que no se declara, se
    deriva — y solo un host local puede derivar ``sintetico`` (el validador de
    :class:`ExploreTarget` es quien lo garantiza).

    QC2 conecta esta función con ``clasificar()`` y con
    ``agent_jobs.input_params``; aquí vive la única decisión.
    """
    return target.data_class


def origin_ref_for(target: ExploreTarget) -> str:
    """Referencia de origen legible y **sin credenciales** para el artefacto."""
    return f"exploración {target.alias} ({target.host})"


def alcance_para_prompt(target: ExploreTarget, paths: list[str]) -> dict[str, Any]:
    """Lo ÚNICO que el modelo llega a saber del destino (A1).

    Ni alias, ni host, ni URL, ni credencial: solo los *paths* recorridos y la
    clase de datos. El modelo no necesita saber contra qué aplicación se exploró
    para redactar un caso sobre un campo ``ruc`` con ``maxlength=11``, y lo que no
    necesita saber no se le manda.

    QC5 amplía este diccionario con las anclas observadas. Ampliarlo aquí —y no
    en el prompt— es lo que mantiene el candado vivo: el test que comprueba que ni
    el alias ni el host aparecen en la proyección cubre por construcción todo lo
    que se añada después.
    """
    return {
        "origen": "aplicación web explorada en solo lectura",
        "data_class": target.data_class,
        "paths": list(paths),
    }
