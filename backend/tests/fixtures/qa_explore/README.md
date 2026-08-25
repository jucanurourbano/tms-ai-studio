# Fixtures del Modo C (exploración)

HTML congelado con el que la suite ejerce el Modo C **sin navegador, sin servidor
local y sin red**. Es posible porque la costura del Modo C es que *el extractor no
conoce el navegador*: `SURFACE_MAP` y la política de pulsado reciben **HTML como
cadena**, y solo `ExploreSession` toca el driver. Y además es obligatorio: en este
host Chromium no arranca (falta `libnspr4`, sin `sudo`).

## Qué hay

| Escenario | Para qué |
|---|---|
| `tms_guias/` | Una aplicación observada de punta a punta: entrada con redirección, acceso, listado con tabla y alta con validaciones. |
| `spa_router/` | Navegación de cliente: el formulario **no existe** en el HTML servido y aparece al pulsar una pestaña. Es el motivo entero del nivel 1. |
| `trampas/` | Una fixture por trampa, deliberadamente hostil. Ver abajo. |

## `manifest.json` es lo que sustituye al navegador

Da `status`, redirecciones (`location`), la URL final (`url`), el fichero de cada
*path* y el resultado de cada clic, de modo que la **capa 5** —revalidar la
allowlist en cada navegación— se ejerce sin navegar. Claves en inglés, valores en
español, como en los artefactos.

`clicks` admite `method`: un clic declarado con un método distinto de `GET`/`HEAD`
es el que la **capa 3 aborta en red**. El doble de la suite modela ese aborto
devolviendo la página **sin cambios** — que es lo que un explorador observaría.

## Las trampas

| Fichero | Qué demuestra |
|---|---|
| `button_sin_type.html` | Un `<button>` sin `type` dentro de un `<form>` es `submit`: **no** se pulsa. Su hermano con `type` explícito sí, y el de fuera con `form=` tampoco. |
| `redirect_fuera_de_host.html` | Un enlace del mismo origen que responde `302` a otro host. Se bloquea en el salto, no en el enlace. |
| `fetch_post_en_click.html` | El residual declarado: leyendo el DOM **no** se puede saber que un botón manda un `POST`. Lo para la red, no la lista blanca. |
| `javascript_href.html` | Esquema `javascript:` (y una descarga): rechazados por la política de navegación. |

## Cómo se regeneran

`backend/scripts/capture_explore_fixture.py --alias <alias> --out <directorio>`
explora **una vez**, a mano, con autorización explícita, y guarda. No forma parte
de la suite y no corre en CI. Entre capturar y guardar está el **saneador**
(`ai/agents/qa/explore/sanitize.py`), que no es opcional: conserva la estructura,
los rótulos, los atributos de validación y las opciones de un `select`; borra el
contenido del atributo de valor, los `<script>`, los manejadores en línea, los
comentarios, las celdas de datos y las secuencias largas de dígitos, y reescribe
las URLs absolutas del host explorado a su *path*.

Las trampas se escriben **a mano**: el saneador borra los manejadores en línea, así
que la del `POST` no sobreviviría a una captura.

## El candado

`tests/agents/qa/test_fixtures_candado.py` recorre **todos** los ficheros de este
árbol y exige tres cosas: ninguna secuencia de 8 o más dígitos (guía, RUC, DNI),
ningún dominio de la organización y ningún atributo de valor con contenido. Si
alguien comitea una captura cruda, la suite lo dice — y `escenario_saneado()`
revienta antes de escribir nada.
