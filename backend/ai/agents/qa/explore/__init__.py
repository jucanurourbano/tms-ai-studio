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
3. **Solo lectura impuesta**, no prometida, y con dos mitades: la política de
   pulsado (``clicking.py``) se evalúa sobre el DOM y el presupuesto de clics vive
   en ``ExploreSession``; el aborto en red de todo método ≠ ``GET``/``HEAD``
   —más la neutralización del ``submit``, que va **antes**— vive en
   ``network.py`` (QC5) y lo instala ``driver.py`` sobre el contexto, antes de que
   exista una página.
4. **La credencial nunca sale** (``target.py``: ``redact_url``), ni en el
   artefacto, ni en un log, ni en un mensaje de error. Corolario del navegador:
   **no se guardan capturas de pantalla** (candado AST en
   ``tests/agents/qa/test_explore_candados.py``).
5. **La allowlist se re-verifica en CADA navegación** (``navigation.py``). Una
   base de datos no redirige; una aplicación web sí.

Ninguna de estas capas depende de que alguien recuerde llamarla: el único camino
al destino es ``assert_target_authorized`` y el único camino al navegador es
``ExploreSession``.

Y una pieza que **no** es una capa: ``extract.py``, el extractor determinista de
anclas (QC4.5/QC5). No es parte de la jaula porque no toca nada — recibe el HTML como
cadena y devuelve la lista cerrada de lo anclable, sin red, sin navegador y sin
LLM. Vive aquí porque es la otra mitad de la misma costura (§6.2): lo que hace
ejercitable el 99% del Modo C en un host donde Chromium no arranca.
"""

from ai.agents.qa.explore.clicking import (
    Veredicto,
    elementos_pulsables,
    es_pulsable,
)
from ai.agents.qa.explore.dom import (
    Elemento,
    Selector,
    elementos,
    selector_de,
    selector_estructural,
    selector_por_atributo,
)

# ``build_driver`` NO se reexporta: es una costura parcheable y la regla R1
# prohíbe el enlace por nombre. Un ``from …explore import build_driver`` resolvería
# el atributo al importar y el parche del cortafuegos no lo alcanzaría — y un
# reexport es precisamente la invitación a escribir esa línea. Quien lo necesite
# llama ``driver.build_driver(...)`` por su módulo, como hace ``session.py``.
from ai.agents.qa.explore.driver import (
    BrowserDriver,
    DriverNoDisponibleError,
    RespuestaNavegacion,
)
from ai.agents.qa.explore.extract import (
    ANCLA_ENUM,
    ATRIBUTOS_ANCLA,
    ESTRATEGIAS_DE_ANCLA,
    Ancla,
    anchor_ref,
    anclas_de,
    anclas_por_control,
    selector_de_ancla,
    veces_por_selector,
)
from ai.agents.qa.explore.limits import LimitesExploracion, limites_efectivos
from ai.agents.qa.explore.navigation import (
    ESQUEMAS_PERMITIDOS,
    VeredictoNavegacion,
    assert_navigation_allowed,
    evaluar_navegacion,
)
from ai.agents.qa.explore.sanitize import (
    ORIGEN_DE_FIXTURE,
    CapturaSuciaError,
    Escenario,
    ResultadoSaneado,
    Violacion,
    escenario_saneado,
    sanear_html,
    violaciones,
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
    "ANCLA_ENUM",
    "ATRIBUTOS_ANCLA",
    "Ancla",
    "BrowserDriver",
    "CapturaSuciaError",
    "DriverNoDisponibleError",
    "ESQUEMAS_PERMITIDOS",
    "ESTRATEGIAS_DE_ANCLA",
    "Elemento",
    "Escenario",
    "ExploreSession",
    "ExploreTarget",
    "HOSTS_LOCALES",
    "LimitesExploracion",
    "ORIGEN_DE_FIXTURE",
    "PaginaObservada",
    "RespuestaNavegacion",
    "ResultadoSaneado",
    "SalidaBloqueada",
    "Selector",
    "Veredicto",
    "VeredictoNavegacion",
    "Violacion",
    "alcance_para_prompt",
    "anchor_ref",
    "anclas_de",
    "anclas_por_control",
    "assert_navigation_allowed",
    "assert_target_authorized",
    "available_targets",
    "data_class_de_exploracion",
    "elementos",
    "elementos_pulsables",
    "es_pulsable",
    "escenario_saneado",
    "evaluar_navegacion",
    "limites_efectivos",
    "origin_ref_for",
    "redact_url",
    "sanear_html",
    "selector_de",
    "selector_de_ancla",
    "selector_estructural",
    "selector_por_atributo",
    "veces_por_selector",
    "violaciones",
]
