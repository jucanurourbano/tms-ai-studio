"""Modo C del Agente QA — **el guard, antes del navegador** (QC3).

Este paquete es la jaula. Se construye ANTES de que exista una sola línea de
Playwright, y el orden no es casual: la capa 4 del cortafuegos de tests (LLM1,
``tests/firewall.py``) parchea ``socket.socket.connect`` **en el proceso de
Python**, y un navegador es **otro proceso del sistema operativo**. Sus sockets
no pasan por ese parche. Es decir: hoy existe una garantía que se cree existente
y no lo es, y el día en que se instale el navegador un test podría salir a
producción sin que ninguna capa lo viera. La valla antes del animal.

Las cinco capas fail-closed (heredadas de INV2,
``app/services/introspection_service.py``, más una que INV2 no necesitaba):

1. **El cliente NUNCA envía una URL**, envía un *alias* (``target.py``). Si
   enviara la URL, cualquiera con permiso de lanzar exploraciones podría apuntar
   el servidor a un host arbitrario — un SSRF de manual. Y aquí hay un segundo
   motivo: el destino transporta la **credencial de la cuenta de QA**.
2. **Allowlist de hosts** (``target.py``). Lista vacía = **nada autorizado**.
3. **Solo lectura impuesta**, no prometida: la política de pulsado
   (``clicking.py``) se evalúa sobre el DOM y el presupuesto de clics vive en
   ``ExploreSession``; el aborto de todo método ≠ ``GET``/``HEAD`` en la red se
   instala con el driver real (QC5), sobre esta misma costura.
4. **La credencial nunca sale** (``target.py``: ``redact_url``), ni en el
   artefacto, ni en un log, ni en un mensaje de error. Corolario del navegador:
   **no se guardan capturas de pantalla** (candado AST en
   ``tests/agents/qa/test_explore_candados.py``).
5. **La allowlist se re-verifica en CADA navegación** (``navigation.py``). Una
   base de datos no redirige; una aplicación web sí.

Ninguna de estas capas depende de que alguien recuerde llamarla: el único camino
al destino es ``assert_target_authorized`` y el único camino al navegador es
``ExploreSession``.
"""

from ai.agents.qa.explore.clicking import (
    Veredicto,
    elementos_pulsables,
    es_pulsable,
)
from ai.agents.qa.explore.dom import Elemento, elementos, selector_de
from ai.agents.qa.explore.driver import (
    BrowserDriver,
    DriverNoDisponibleError,
    RespuestaNavegacion,
    build_driver,
)
from ai.agents.qa.explore.limits import LimitesExploracion, limites_efectivos
from ai.agents.qa.explore.navigation import (
    ESQUEMAS_PERMITIDOS,
    VeredictoNavegacion,
    assert_navigation_allowed,
    evaluar_navegacion,
)
from ai.agents.qa.explore.session import (
    ExploreSession,
    PaginaObservada,
    SalidaBloqueada,
)
from ai.agents.qa.explore.target import (
    HOSTS_LOCALES,
    ExploreTarget,
    alcance_para_prompt,
    assert_target_authorized,
    available_targets,
    data_class_de_exploracion,
    origin_ref_for,
    redact_url,
)

__all__ = [
    "BrowserDriver",
    "DriverNoDisponibleError",
    "ESQUEMAS_PERMITIDOS",
    "Elemento",
    "ExploreSession",
    "ExploreTarget",
    "HOSTS_LOCALES",
    "LimitesExploracion",
    "PaginaObservada",
    "RespuestaNavegacion",
    "SalidaBloqueada",
    "Veredicto",
    "VeredictoNavegacion",
    "alcance_para_prompt",
    "assert_navigation_allowed",
    "assert_target_authorized",
    "available_targets",
    "build_driver",
    "data_class_de_exploracion",
    "elementos",
    "elementos_pulsables",
    "es_pulsable",
    "evaluar_navegacion",
    "limites_efectivos",
    "origin_ref_for",
    "redact_url",
    "selector_de",
]
