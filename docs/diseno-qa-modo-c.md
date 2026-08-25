# Diseño — Agente QA, Modo C (exploración de una URL viva)

> **Estado: DISEÑO APROBADO. QC0 (este documento), QC3 (el guard), QC4 (fixtures
> y saneador) y QC4.5 (el extractor de anclas) están IMPLEMENTADOS —los tres
> últimos sin una línea de Playwright—; el resto sigue en cero.** El inventario de §1
> se verificó en HEAD `9e1064a` (LLM1) y describe el punto de partida; lo que QC3
> cambió está en §11 y en la tabla de bloques de la PARTE 3.
>
> **Este documento NO reemplaza a `docs/diseno-agente-qa.md` PARTE II (§11–§17).**
> Aquella sigue siendo la fuente de verdad de QA-D9…QA-D18: la distinción
> especificación/observación, las cinco capas fail-closed, `SURFACE_MAP`, el
> contrato v1.1.0 y la migración `0011`. Aquí se decide **solo lo que quedó
> abierto**, se numera de QA-D19 a QA-D25, y se ordena en bloques `QC*` con las
> colisiones contra LLM1/LLM2/LLM3/LLM5 marcadas.

---

## 0. Por qué hace falta un documento más

La PARTE II resolvió el problema **de seguridad** del Modo C (cómo conducir un
navegador contra producción sin causar daño) y el problema **de contrato** (cómo
representar una observación sin que se confunda con una especificación).

Dejó abiertos siete asuntos que no son de plomería:

1. Un caso observado **no tiene padre `BR-`/`VAL-`**: qué es exactamente su
   `source_ref`, qué hace la matriz con él y qué hace `CRITIQUE`.
2. "Solo lectura" está definido en la **red**; no está definido qué se puede
   **tocar** en el DOM, que es donde se descubren los campos.
3. El TMS está **detrás de login** y la PARTE II dice "el alias transporta la
   credencial" sin decidir **qué credencial**.
4. `data_class` no existía cuando se escribió la PARTE II. Ahora existe (LLM0) y
   el Modo C es, por definición, **la fuente más real que tiene el sistema**.
5. "Tests contra HTML de fixtures" es una intención sin estructura — y hay un
   hallazgo del inventario que la vuelve obligatoria, no preferible (§4.5).
6. El frontend está congelado y QA16 estaba descrito en una línea.
7. El Modo C explora para **derivar** casos. La **ejecución** es del futuro Agente
   Testing, y nada impide hoy que el Modo C se deslice hacia allí.

---

## 1. Inventario verificado (HEAD `9e1064a`)

### 1.1 Modo C

| Pieza | Estado | Evidencia |
|---|---|---|
| Nodos `EXPLORE` / `SURFACE_MAP` | **no existe** | `ai/orchestrator/qa_graph.py:31-44` lista los 12 nodos del Modo A y ninguno más |
| Discriminador `mode` en el artefacto | **no existe** | `ai/agents/qa/schemas/enums.py` tiene 8 enums; ninguno es `QaMode`. `SCHEMA_VERSION = "1.0.0"` en `schemas/artifact.py:56` |
| `evidence_class`, `observed_anchor`, `SurfaceAnchor` | **no existe** | grep global sobre `backend/**.py` + `frontend/src/**.ts(x)`: **cero coincidencias** |
| `mode` en `agent_jobs` / `input_params` | **no existe** | `app/models/agent.py:169-207`: no hay `input_params`; la última migración es `0010_inventario_de_sistemas.py` |
| Allowlist `QA_EXPLORE_*` | **no existe** | `app/config/settings.py` solo tiene `QA_MAP_CONCURRENCY:108`, `QA_COVERAGE_THRESHOLD:113`, `QA_MAX_CASES_PER_CRITERION:117`. La única allowlist de hosts es `INVENTORY_INTROSPECTION_ALLOWED_HOSTS:138` |
| Integración Playwright | **no existe** | no aparece en `backend/requirements.txt`; no está en `backend/.venv/lib/python3.12/site-packages` |
| Chromium | **descargado, NO ejecutable** | `~/.cache/ms-playwright/chromium-1234` existe; `ldconfig -p \| grep nspr4` → **0 resultados** (falta `libnspr4`, sin `sudo`) |
| `source_ref` de casos de UI | **no existe** | `SourceRef` (`schemas/artifact.py:107`) solo modela `scrum_job_id` / `ef` / `api` |
| Endpoints y UI del Modo C | **no existe** | `app/api/v1/qa.py`: 12 rutas, ninguna de exploración. `frontend/src/app/agents/qa/new/page.tsx` solo ofrece plan Scrum + contrato de API opcional |

**Conclusión: el Modo C está en cero.** No hay esqueleto ni parcial que rescatar.
Lo único que existe es el diseño de la PARTE II (commit `34f5826`, solo `docs/`).

### 1.2 Modo B (más breve)

**También en cero.** `LOAD_INVENTORY` y `ASSET_MAP` no existen (grep global sin
coincidencias). Lo que sí existe y el Modo B reutilizaría **tal cual**:

- `ai/inventory/loader.py:15` `load_target_inventory(system_id=None, …)` — pero con
  `system_id` **opcional**, que es justo lo que §12.6 declara inaceptable para un job.
- `ai/inventory/promote.py:25` `_column_from_artifact` y `:104`
  `api_surface_from_artifact` — confirman el nivel 3 de la jerarquía de anclas: la
  superficie inventariada **no guarda códigos de estado ni esquemas**.
- El módulo `inventario` completo con su UI (INV1–INV6).

No hay nada a medias: no se empezó.

### 1.3 Lo que sí cambió desde que se escribió la PARTE II

LLM0 y LLM1 aterrizaron (`8874ffa`, `9e1064a`) y **alteran dos supuestos del
Modo C**:

- La fábrica `ai/llm/get_llm(rol, *, data_class)` es la única puerta al proveedor
  (`ai/llm/factory.py:57`), y `data_class` es keyword-only sin default. El Modo C
  tiene que declararla — §4.4.
- El cortafuegos de tests tiene cuatro capas (`tests/firewall.py`), y la cuarta es
  un guard sobre `socket.socket.connect`. **Esa capa es ciega al navegador** — §4.5.

---

# PARTE 2 — Decisiones (QA-D19…QA-D25)

## 2. QA-D19 — Trazabilidad de un caso sin requisito padre

**Lo que ya estaba decidido** (PARTE II §14): `evidence_class` obligatorio,
`SurfaceAnchor{kind, url, selector, attribute, value, evidence, observed_at}`,
`criterion_ref` prohibido por el tipo en modo `exploration`, `TraceRow` con
`anchor_ref`/`anchor_kind`.

**Lo que se decide aquí.**

### 2.1 El `source_ref` de un caso observado es una terna, y su forma es canónica

Un caso del Modo A cita `AC-042`: un identificador que **otro artefacto** emitió.
Un caso del Modo C no tiene a quién citar, así que su referencia tiene que ser
**autocontenida y reconstruible**: si dos exploraciones de la misma pantalla
producen refs distintas, no se pueden comparar dos corridas, y sin eso una suite de
caracterización no sirve para lo único que existe —detectar que algo cambió—.

Forma del `anchor_ref`:

```
UI:<path>#<selector_canónico>@<atributo>

UI:/guias/nueva#form[name=guia] input[name=ruc]@maxlength
UI:/guias/nueva#form[name=guia] input[name=fecha_emision]@required
```

- **`path`, no URL completa**: el host viene del alias y **no se guarda en el ref**
  (capa 4: la credencial y el destino no viajan en el artefacto más de lo necesario).
  La `url` completa sin credencial ya vive en el `SurfaceAnchor`.
- **`selector_canónico`** con orden de preferencia fijo y **declarado**:
  `[name=…]` › `#id` › `[data-testid=…]` › ruta estructural `nth-of-type`. El
  `SurfaceAnchor` gana un campo `selector_strategy` con cuál se usó. Motivo: un
  ancla que solo se pudo fijar por posición estructural es **frágil** —un `<div>`
  nuevo la rompe— y quien lea el plan tiene derecho a saber cuáles son frágiles
  antes de que fallen. `CRITIQUE` emite un `Risk` con el porcentaje de anclas
  `structural`, igual que hace con los activos `importado` en el Modo B (QA-D13).
- **Un atributo por ancla.** `required` y `maxlength` del mismo campo son **dos**
  anclas, porque habilitan casos distintos y se pueden romper por separado.

### 2.2 El prefijo del id es parte de la garantía, no decoración

El requisito del enunciado —*un caso de modo C nunca debe poder confundirse con uno
trazado a requisito*— **no lo cumple `evidence_class` por sí solo**. Lo cumple
dentro del artefacto; no lo cumple cuando una fila del CSV se pega en un ticket, o
cuando alguien nombra `TC-017` en una reunión. En ese momento la columna se quedó
atrás y el identificador viaja solo.

**Decisión: los casos de observación se numeran `TC-OBS-###`.** Redundante con
`evidence_class` dentro del artefacto, y por eso mismo barato; imprescindible
fuera de él. Es la misma razón por la que `BR-` y `VAL-` no comparten espacio de
numeración en el EF.

### 2.3 Qué hace la matriz

En modo `exploration` la matriz **cambia de denominador, no de forma**:

| | Modo A | Modo C |
|---|---|---|
| Fila | criterio de aceptación | ancla de `SURFACE_MAP` |
| Denominador | criterios del `ScrumArtifact` | **anclas observadas** |
| `coverage.ratio` significa | "del acuerdo, cuánto se prueba" | "**de lo que se vio**, cuánto se fija" |

Y por eso el artefacto lleva una `scope_statement` obligatoria en `coverage` — una
frase, no un booleano. Un `ratio: 1.0` en Modo C **no** dice "el sistema está
cubierto": dice "todo lo que el explorador alcanzó a ver quedó fijado", que es
compatible con no haber visto media aplicación. Sin la frase, ese `1.0` es la
métrica más engañosa que podría producir el agente. Va acompañada, en el mismo
bloque, de `pages_skipped[]` y `budget_exhausted` (§13.6 de la PARTE II).

### 2.4 Qué hace `CRITIQUE` con los huérfanos — y el cortafuegos que falta

**Un caso huérfano es imposible por contrato** en modo `exploration`
(`evidence_class=observation` sin `observed_anchor` → `ValidationError`). Así que
`CRITIQUE` no busca huérfanos: busca las **tres** patologías que sí pueden existir.

1. **Ancla sin caso** → hueco de cobertura, con su `anchor_ref` enumerado.
2. **Ancla que ya no resuelve** contra el `SURFACE_MAP` de la corrida (un caso
   arrastrado de un refine cuando la pantalla cambió) → se descarta y **se reporta**
   con `SkippedItem`, nunca en silencio.
3. **Evidencia que no está en el DOM capturado** ← **este es el cortafuegos
   anti-invención propio del Modo C, y no estaba en la PARTE II.**

   El Modo A obliga a cita verbatim para un límite de borde porque el EF es texto
   libre y no hay forma de comprobar mecánicamente la cita. **En el Modo C sí la
   hay: tenemos el DOM.** Después de `TEST_DESIGN`/`EDGE_CASES` y **antes** de
   `TRACE_MATRIX`, una comprobación determinista verifica que la `evidence` de cada
   caso sea **subcadena literal** del fragmento de DOM del ancla, y que el `value`
   coincida con el atributo realmente observado. Lo que no pasa se descarta con
   `SkippedItem`.

   Es el mismo mecanismo que INV3 aplica a la extracción documental (verificar que
   la `source_ref` sea un `element_id` real y que haya evidencia verbatim, en Python
   y no en el prompt). Aquí es **más fuerte**, porque el DOM es una cadena exacta y
   no una interpretación. Un `maxlength="11"` alucinado como `12` muere aquí.

---

## 3. QA-D20 — Política de interacción

**Lo que ya estaba decidido** (§13.2 capa 3): abortar en red todo método
≠ `GET`/`HEAD`, `route.abort()` de descargas y del selector de ficheros,
`permissions: []`, no escribir en campos, no pulsar botones de envío.

Eso define qué **sale** del navegador. No define qué se **toca** dentro, y ahí está
el problema real: la mayor parte del DOM de una SPA no existe hasta que alguien
abre una pestaña o un acordeón.

### 3.1 Lo que se gana tocando, y lo que no

Descubrir campos y validaciones **no requiere interacción**: los atributos ya están
en el HTML servido. Tocar solo compra tres cosas:

| Se gana | Coste |
|---|---|
| Alcanzar vistas de un router de cliente sin `href` real | un clic en un elemento de navegación |
| Revelar campos **condicionales** (pestañas, "añadir línea", `aria-expanded`) | un clic en un control de expansión |
| Ver mensajes de validación nativos | **escribir en el campo** |

Las dos primeras son la mayor parte del valor. La tercera es la que obliga a teclear.

### 3.2 Decisión: tres niveles, y el tercero no se implementa

- **Nivel 0 — leer.** Navegación `GET` a enlaces del **mismo origen**, lectura del
  DOM. Siempre permitido.
- **Nivel 1 — pulsar lo demostrablemente inocuo.** Un elemento es pulsable si y
  solo si supera **todas** estas comprobaciones, evaluadas en el DOM antes del clic:
  `<a>` con `href` del mismo origen o `href="#…"`; o `role="tab"`, `role="button"`,
  `[aria-expanded]`, `<summary>`, o `<button type="button">` **explícito**.
  Y en ningún caso si tiene un ancestro `<form>` cuyo envío pudiera disparar.

  > **La trampa que hay que nombrar:** `<button>` **sin** atributo `type` dentro de
  > un `<form>` es `type="submit"` por defecto en HTML. Una lista blanca "los
  > `<button>` se pueden pulsar" sería una lista blanca de envíos. Por eso el
  > `type="button"` tiene que ser **explícito en el atributo**, no inferido.

- **Nivel 2 — teclear: FUERA DE v1.** No por el riesgo de escritura (la capa de red
  lo aborta) sino por algo peor: si un `keyup` dispara un autoguardado y la petición
  muere abortada, el explorador **observa que no hubo validación** y emite un caso
  que afirma un comportamiento falso. Un aborto convierte un riesgo de escritura en
  un riesgo de **observación falsa**, que es la única cosa que este agente no puede
  producir (§0 de la PARTE I). Añádase que teclear en un buscador de producción
  deja rastros de consulta en los logs del cliente.

  Las validaciones se toman de los atributos y del **texto rotulado citado
  verbatim** (§13.1), que es exactamente el estatus que QA-D2 da al texto libre de
  una `VAL-`.

### 3.3 Cómo se hace cumplir en código (no por convención)

Cuatro mecanismos, ninguno de los cuales es "acordamos no hacerlo":

1. **Una sola clase dueña del contexto.** `ExploreSession` es el único sitio del
   backend que puede crear un `BrowserContext` o una `Page`. Los nodos no reciben
   la `Page`, reciben `ExploreSession` y llaman a `visitar()` / `pulsar_si_procede()`
   / `dom()`. Un nodo no tiene acceso al objeto con el que se podría escribir.
2. **Neutralización en el DOM, antes de cualquier interacción.** `add_init_script`
   inyecta, en cada documento y antes de su script: `submit` con
   `preventDefault()` en captura, `HTMLFormElement.prototype.submit` sustituido,
   `beforeunload` neutralizado. Un envío accidental muere **antes** de la capa de
   red, no en ella. Defensa en profundidad: la capa de red sigue puesta.
3. **Candado por AST sobre el código fuente.** El repositorio ya tiene el
   precedente exacto: `tests/llm/test_construcciones.py:72` recorre el AST de los
   consumidores y falla si un `get_llm(` no lleva `data_class`, con el argumento
   escrito en su docstring —*"un test de comportamiento no ve al que mañana escriba
   otra construcción directa; un grep sí, y falla en el momento en que se escribe"*—.
   Se replica: ninguna llamada a `fill`, `type`, `press`, `set_input_files`,
   `select_option`, `check`, `evaluate`, `screenshot` (QA-D16) fuera de
   `PERMITIDOS = {"ai/agents/qa/explore/login.py"}` (§4.3). `click` solo dentro de
   `ExploreSession.pulsar_si_procede`.
4. **Presupuesto de clics por página** (`QA_EXPLORE_MAX_CLICKS_PER_PAGE`, default 8),
   contado en `ExploreSession`. Un acordeón recursivo no convierte la exploración en
   un generador de carga.

### 3.4 Residual declarado, no escondido

`page.route` no intercepta WebSockets en todas las versiones. Se declara: si el
destino usa WS para mutar estado, la capa 3 no lo cubre; se mitiga con
`context.route_web_socket` cuando la versión pinneada lo soporte, y si no, se anota
junto al *DNS rebinding* de §13.2 como pendiente conocido.

---

## 4. QA-D21 — Autenticación

Las pantallas del TMS están detrás de login, así que sin resolver esto el Modo C
solo ve la pantalla de acceso.

| Opción | A favor | En contra |
|---|---|---|
| **(a) No autenticar** | cero credenciales, cero riesgo | el TMS no tiene superficie pública: el plan resultante tendría un caso —el formulario de login— y el modo no se justifica |
| **(b) Sesión inyectada por el usuario** (cookie / `storage_state` pegado en la petición) | nada persistido en el servidor; caduca sola; el humano decide el alcance | es **la identidad de quien la pega**, que será un admin, así que el radio de acción vuelve a ser total y toda la garantía recae en nuestras capas; no permite reejecutar (caduca) y por tanto **rompe la reproducibilidad**, que es lo único que hace útil una suite de caracterización; y devuelve al cliente una decisión que la capa 1 le quitó a propósito |
| **(c) Cuenta dedicada de solo lectura, credencial en el alias** | mínimo privilegio **en el origen**, no en nuestro código; auditable en los logs del sistema explorado como `qa-explorer`; reejecutable sin intervención; la credencial no cruza la API en ningún sentido | exige que el sistema explorado **tenga** un rol de solo lectura; credencial de vida larga en `.env` |

### 4.1 Recomendación: (c), y (b) no se construye

(b) es tentador porque parece más seguro —no guardamos nada— y es lo contrario: es
una llave maestra de un solo uso, con caducidad impredecible y sin trazabilidad de
quién exploró qué. Y una vez que el endpoint acepta una sesión del cliente, la
acepta para siempre: **añadirlo después es fácil, quitarlo no.**

### 4.2 Precondición fail-closed: el alias declara que la cuenta es de solo lectura

Si el sistema explorado no tiene rol de lectura, la cuenta de (c) es una cuenta
normal y lo único que separa una escritura de producción de nosotros son nuestras
capas. Eso es aceptable como defensa en profundidad e inaceptable como único
control.

Cada alias declara `readonly_verified: bool`, y **un alias sin `true` no se explora**
(`GateError` 409, mensaje que dice qué falta). No es una carga: quien registra el
alias es `admin` (QA-D17) y afirmarlo es una línea de configuración. Es la misma
forma de la allowlist vacía: *ausencia significa no autorizado*.

### 4.3 Dónde vive el login: fuera de la sesión de exploración

El login es **la única operación que necesita teclear**, y §3.3 acaba de prohibir
teclear en toda la ruta de exploración. Resolverlo con una excepción dentro de
`ExploreSession` destruiría el candado.

Decisión: el login vive en un **CLI de administración**,
`backend/scripts/qa_explore_login.py --alias tms-qa`, que abre un navegador, se
autentica, guarda `storage_state` en el servidor (fuera del repositorio, permisos
`600`) y termina. La exploración **carga** ese estado y su código no contiene una
sola llamada capaz de escribir. Ventajas colaterales: la caducidad se ve como un
fallo claro ("el estado de sesión de `tms-qa` expiró, vuelve a ejecutar el CLI") en
vez de como una exploración que devuelve la pantalla de login 40 veces; y el
`storage_state` se puede rotar sin desplegar.

`ExploreSession` comprueba al arrancar que el estado autentica —una navegación de
sondeo a una ruta protegida— y si no, aborta el job **antes** de gastar un token.

---

## 5. QA-D22 — `data_class` del Modo C

### 5.1 Es derivada, no declarada

LLM-D9 hace `data_class` obligatorio en los **tres puntos de ingesta** porque solo
el humano sabe si un documento que sube es real o de laboratorio.

**El Modo C es el caso donde el sistema sabe más que quien llama.** El destino es un
alias registrado por un admin, con host en allowlist y credencial de una cuenta real
contra una aplicación desplegada. El DOM que se captura contiene números de guía,
RUC y nombres reales.

Decisión: **`mode=exploration` ⇒ `data_class="real"`, calculado en el servidor.** El
endpoint **no acepta** el campo; si el cliente lo envía, **422** en vez de
sobrescribirlo en silencio. Un override silencioso ocultaría a un llamador que cree
estar trabajando con datos sintéticos, y ese llamador es precisamente el que hay que
corregir.

```python
# ai/agents/qa/data_class.py  (propuesto)
def clasificar(mode: QaMode, declarada: DataClass | None) -> DataClass:
    """`exploration` es real por construcción; el resto se declara (LLM-D9)."""
    if mode is QaMode.EXPLORATION:
        if declarada is not None:
            raise ConflictError(
                "Un job de exploración es 'real' por construcción: no se declara."
            )
        return "real"
    ...
```

### 5.2 Dónde se aplica, y por qué ahí

- **Se persiste** en `agent_jobs.input_params` (migración `0011`, QA-D18) junto al
  `target_alias`. Motivo idéntico al de QA-D18: **un job que falla no tiene
  artefacto**, y "¿con qué clase de datos se lanzó esto?" es exactamente la pregunta
  que se hace después de un fallo.
- **Se pasa** desde el estado del grafo a cada `get_llm(rol, data_class=…)`. El
  candado de `tests/llm/test_construcciones.py:72` ya obliga a que ninguna llamada
  nueva lo omita: los nodos del Modo C entran cubiertos por un test que ya existe.
- **Se hace cumplir** en la fábrica, y eso es **LLM2**: proveedor ≠ `anthropic` con
  `data_class="real"` → `ProviderPolicyError` **antes de la primera llamada**.

### 5.3 Las dos puertas de atrás que hay que cerrar con candado

1. **`LLM_ROLE_OVERRIDES["qa"] = "gemini"`.** Es el caso de uso legítimo del banco
   de pruebas (LLM-D2) y sería la fuga perfecta. No hace falta prohibirlo: la
   política se evalúa **después** de resolver el proveedor
   (`factory.py:57-70`), así que el override resuelve a Gemini y **ahí** salta
   `ProviderPolicyError`. Test candado: override de rol + `mode=exploration` ⇒
   excepción, **no** una llamada.
2. **Un refine del job.** `create_refine` reconstruye el job hijo desde el padre
   (`app/services/qa_service.py:438`). Si el hijo no arrastra la `data_class` del
   padre, el refine sería la puerta trasera: mismo contenido, clasificación perdida.
   Test candado: el hijo hereda `real`. Es la **herencia monótona** de LLM-D9 (*si
   una fuente de la cadena es real, todo el descendiente es real*) aplicada a la
   relación padre/hijo.

### 5.4 Consecuencia para el Modo B, que conviene decir ahora

Un sistema del inventario contiene esquemas de producción → `real`. Pero
`scripts/seed_inventario_demo.py` siembra sistemas **sintéticos**, y hoy
`inventory_systems` **no tiene** columna para distinguirlos. En v1 el Modo B se
clasifica **`real` sin excepción** (dirección segura), y marcar un sistema como
sintético queda como trabajo dependiente de LLM2 + Modo B, con su propia migración.
No se resuelve aquí y no se finge resuelto.

---

## 6. QA-D23 — Fixtures y captura

### 6.1 El hallazgo que vuelve las fixtures obligatorias

La capa 4 de LLM1 parchea `socket.socket.connect` **en el proceso de Python**
(`tests/firewall.py`, `blindar_red`). Un navegador de Playwright es **otro proceso
del sistema operativo**: sus sockets no pasan por ese parche. Playwright se comunica
con él por un canal local, que la capa 4 permite —correctamente—.

> **La capa 4 es ciega al navegador.** Un test que arranque Chromium y navegue a
> `https://tms.urbano.com.pe` **saldría a la red** y ninguna de las cuatro capas lo
> vería.

Por eso `sin_navegador_real` (§13.7) **no es un hermano de conveniencia de
`sin_api_real`: es la única capa que existe para este riesgo**, y es autouse por la
misma razón que sus hermanas: la protección no puede depender de que cada test se
acuerde de pedirla. Parchea la fábrica del driver, no `ExploreSession`, para cubrir
también a quien importe Playwright directamente.

### 6.2 La costura: el extractor no conoce el navegador

`SURFACE_MAP` y la extracción de anclas reciben **HTML como cadena** más la URL y el
instante. Solo `ExploreSession` toca Playwright. Consecuencia: la suite ejerce el
99% del Modo C **sin navegador, sin servidor local y sin red** — determinista y
gratis. Y no hay que servir las fixtures por HTTP: `file:` está rechazado por la
capa 5 y no hace falta, porque nada las navega.

### 6.3 Estructura

```
backend/tests/fixtures/qa_explore/
├── tms_guias/                     # un escenario = una aplicación observada
│   ├── manifest.json              # rutas, status, redirecciones, orden de visita
│   ├── 00_login.html
│   ├── 01_guias_lista.html
│   └── 02_guias_nueva.html        # el formulario con required/maxlength/pattern
├── spa_router/                    # navegación de cliente sin href real
├── trampas/                       # una fixture por trampa, deliberadamente hostil
│   ├── button_sin_type.html       # <button> dentro de <form> → NO pulsable (§3.2)
│   ├── redirect_fuera_de_host.html
│   ├── fetch_post_en_click.html   # el clic dispara POST → debe abortarse
│   └── javascript_href.html
└── README.md
```

`manifest.json` es lo que sustituye al navegador: da `status`, cabeceras y
redirecciones, de modo que el guard (capa 5, revalidación por navegación) se ejerza
sin navegar.

### 6.4 Cómo se capturan, y la parte que no es opcional

`backend/scripts/capture_explore_fixture.py --alias tms-qa --out tests/fixtures/qa_explore/tms_guias`:
ejecuta el explorador real **una vez**, a mano, con autorización explícita, y
guarda. **No** forma parte de la suite y **no** corre en CI.

Y entre capturar y guardar hay un paso obligatorio, porque una captura de una app
autenticada es un volcado de datos de producción y el repositorio es para siempre.
El **saneador** conserva lo que ancla y descarta lo que identifica:

| Se conserva | Se elimina |
|---|---|
| `<form>`, `<input>`, `<select>`, `<label>`, atributos de validación | `value=` de todo input; `<script>`; `<tbody>` de tablas de datos; comentarios |
| encabezados, textos de rótulo (evidencia verbatim) | cookies, cabeceras, tokens, `<meta>` de sesión |

**Candado sobre las propias fixtures** (un test, no una nota en el README): ninguna
fixture contiene una secuencia de 8+ dígitos (RUC, guía, DNI), ni la cadena del
host de producción, ni un `value=` no vacío. Si alguien comitea una captura cruda,
la suite lo dice. Es el mismo criterio con el que `redact_dsn` protege la
introspección de INV2, aplicado al artefacto de test.

---

## 7. QA-D24 — Frontend mínimo

El frontend está congelado; el cambio se ajusta al patrón del hub (§5.1 de
`CLAUDE.md`) y **todo lo nuevo va detrás de una comprobación de presencia**, así que
un artefacto de Modo A —que por defecto es `mode: "specification"` sin
`observed_anchor`— renderiza **exactamente** lo que renderiza hoy.

### 7.1 Lo más importante del frontend es lo que NO se añade

**No hay campo de URL.** Un `<Input>` para la URL sería la afordancia del SSRF que
la capa 1 quitó a nivel de API: la pantalla no debe ofrecer lo que el backend
rechaza. Se ofrece un `NativeSelect` de **alias autorizados** con su host visible
**en texto plano no editable**, alimentado por `GET /qa/explore-targets` (hermano
literal de `GET /inventario/introspection/sources`, `app/api/v1/inventario.py:323`,
que ya devuelve alias + host y nunca cadenas de conexión).

Si la lista viene vacía —`QA_EXPLORE_ENABLED=false` o allowlist vacía— la opción
aparece **deshabilitada con el motivo escrito**, no oculta: un QA lead tiene que
poder distinguir "no existe" de "no está habilitado en este despliegue", y ya hay
precedente de esa decisión en el botón "Enviar a ClickUp".

### 7.2 Los cinco cambios, y ninguno más

1. **`/agents/qa/new`** — selector de modo (3 tarjetas radio) sobre los componentes
   que ya usa la pantalla. Modo A queda **preseleccionado**: la ruta actual no
   cambia de comportamiento para quien no elija otra cosa. Elegir C sustituye el
   `SourceJobPicker` por el select de alias; el bloque de contrato de API desaparece
   (§13.3: sin casos de autorización en Modo C).
2. **`lib/evidence-class.ts`** — vocabulario único (badge + `hint`), hermano de
   `lib/test-case-kind.ts` y `lib/reconciliation.ts`, con clases Tailwind literales.
   `observation` lleva además la marca de **confianza menor**: el badge muestra el
   `confidence` del ancla y `structural` (§2.1) se distingue visualmente de
   `[name=…]`.
3. **Ancla en la fila del caso** — dos líneas condicionales
   (`observed_anchor && …`): `path#selector@atributo` y la evidencia verbatim.
4. **Una `HubSection` nueva, "Exploración"** — alias, host, páginas visitadas,
   `pages_skipped[]` con su motivo, y **urgencia (borde rojo) si
   `budget_exhausted`**. Al ser un elemento del array `HubSection[]`, alimenta sola
   la tarjeta, el panel y el PDF: cero cambios en el shell (§5.1).
5. **`lib/qa-refs.ts`** — el prefijo `UI:` se declara **sin destino**: pulsar un
   ancla de superficie no abre panel, avisa con un toast. Reutiliza la ruta ya
   existente para "este id pertenece a otro artefacto". Un ancla que finge tener
   destino es peor que una que no lo tiene.

**Cero regresión, comprobable:** el CSV gana una columna al final (`evidence_class`),
que Excel con `;` y BOM sigue abriendo igual (QA-D6); `qa-refs.test.ts` y
`test-case-kind.test.ts` no se tocan; y el candado real es que todo lo nuevo
depende de campos ausentes en un artefacto v1.0.0.

---

## 8. QA-D25 — Frontera con el futuro Agente Testing

El Modo C **observa para derivar casos**. El Agente Testing **ejecuta casos**. La
frontera es fácil de cruzar por deslizamiento —"ya que el navegador está abierto,
comprobemos que el campo rechaza 12 dígitos"— y ese único paso convertiría al Modo C
en un ejecutor con permisos de solo lectura, es decir en un ejecutor que **solo puede
verificar lo que no importa** y que ya tiene la mitad de la infraestructura para
dejar de ser de solo lectura.

Cuatro impedimentos **en código**, no en la documentación:

1. **La misma capa que protege producción prohíbe ejecutar.** Ejecutar un caso
   funcional exige mutar estado, y mutar estado exige un método ≠ `GET`/`HEAD`, que
   el contexto **aborta en la red**. No hay que añadir nada: el guard de seguridad
   **es** el guard de alcance. Es la propiedad más limpia de este diseño y conviene
   escribirla donde se lea.
2. **El contrato no tiene dónde escribir un resultado.** `QaArtifact` no tiene
   `result`, `passed`, `executed_at`, `run_id`, `actual`, `duration_ms` ni
   `screenshot`. **Candado sobre el esquema**: un test recorre los campos de
   `QaArtifact` (y anidados) y falla si aparece alguno de una lista negra explícita.
   Añadir uno exige **borrar un test con nombre**, que es un acto visible en la
   revisión — no un campo que se cuela.
3. **El artefacto es inmutable** (§7 de `CLAUDE.md`: las validaciones se persisten
   aparte y el artefacto no se muta). Un resultado de ejecución no se puede escribir
   de vuelta ni siquiera saltándose el contrato. El Agente Testing necesitará su
   propio almacén (`test_runs`), y **QA no escribe en él**: esa es la frontera, y es
   estructural.
4. **Los topes no admiten "sin límite".** `QA_EXPLORE_MAX_PAGES`,
   `MAX_DEPTH`, `TOTAL_BUDGET_S` son enteros positivos **validados**: `0` no
   significa infinito, es inválido. Un ejecutor necesita corridas repetidas y sin
   techo; el Modo C no las puede pedir.

Y la consecuencia de diseño hacia adelante: cuando exista el Agente Testing, su
entrada natural es un `QaArtifact` con `evidence_class=observation` —una suite de
caracterización lista para ejecutar—. La frontera no es una pared, es una interfaz.

---

# PARTE 3 — Plan por bloques

Método de la casa: tests mockeados por bloque, `pytest` y `tsc` en verde,
commit+push por bloque, **aprobación explícita antes de empezar cada uno**.
**Los Modos A (y B, cuando exista) deben seguir verdes en todos.**

| Bloque | Contenido | Tests del bloque | Choca con |
|---|---|---|---|
| **QC0** | Este documento. QA-D19…QA-D25. | — | — |
| **QC1** | Contrato **`QaArtifact v1.1.0`** completo (= **QA10** de la PARTE II, sin recortar a Modo C: el contrato no se toca dos veces). `mode`, `evidence_class`, `source` como unión discriminada, `AssetAnchor`/`SurfaceAnchor` + `selector_strategy`, `TraceRow` generalizado, `coverage.scope_statement`, ids `TC-OBS-`. | round-trip de un artefacto **v1.0.0 real** que sigue validando · observación sin ancla → `ValidationError` · `criterion_ref` en modo C → `ValidationError` · `exploration` + `type=authorization` → `ValidationError` · **candado de la lista negra de campos de ejecución** (QA-D25.2) | — |
| **QC2** | Migración **`0011`** `agent_jobs.input_params` JSONB + repositorio + `clasificar()` de `data_class` + herencia en refine. Cierra de paso el `target_system_id` huérfano de INV. | `mode=exploration` ⇒ `real` · declararla → 422 · el hijo del refine hereda `real` · `input_params` sobrevive a un job que **falla** | **⚠️ LLM2** — §9.1 |
| **QC3** ✅ | **El guard, antes del navegador.** `QA_EXPLORE_*` en settings, alias con `readonly_verified`, allowlist, validación de esquema, revalidación por navegación, redacción, topes, política de pulsado (§3.2) evaluada sobre HTML, `ExploreSession` **con el driver inyectado**, `sin_navegador_real` autouse, candado AST (§3.3.3). **Sin una línea de Playwright.** | alias inexistente → error · allowlist vacía ⇒ nada autorizado · `302` fuera de host no se sigue y se registra · `file:`/`data:`/`javascript:` rechazados · `readonly_verified=false` → 409 · credencial ausente de artefacto, log y respuesta · `<button>` sin `type` en `<form>` **no** es pulsable · candado AST: cero `fill`/`type`/`screenshot` | — **IMPLEMENTADO** (§11) |
| **QC4** ✅ | Fixtures y saneador (§6.3, §6.4): estructura, `manifest.json`, escenarios `trampas/`, `capture_explore_fixture.py`, candado de fixtures. | ninguna fixture con 8+ dígitos, host de producción ni atributo de valor con contenido · el saneador conserva los atributos de validación **y los rótulos de dentro del `<tbody>`** (A3), y vacía las celdas de datos | — **IMPLEMENTADO** (§12) |
| **QC4.5** ✅ | **El extractor determinista de anclas**: vocabulario cerrado de atributos-ancla, `anchor_ref` canónico, cinco estrategias de selector con unicidad comprobada, `@enum`, y un lector de `.html` de disco para mirar la tabla con los ojos. Sin red, sin LLM, sin navegador, sin clic. | cada atributo del vocabulario produce su ancla y `value`/`disabled`/`placeholder` no · una etiqueta que no se escribe en CSS **no** ancla (fail-closed) · dos pasadas dan los mismos refs en el mismo orden · toda evidencia es subcadena exacta del HTML · **F2 fijada**: el enum se ve en crudo y no en la fixture saneada | — **IMPLEMENTADO** (§13) |
| **QC5** | `EXPLORE` real (Playwright pinneado, `QA_EXPLORE_ENABLED=false`) + `SURFACE_MAP` + verificación verbatim contra DOM (§2.4.3), ejercidos **contra fixtures**. | `POST` interceptado se aborta · `add_init_script` neutraliza el submit · evidencia que no está en el DOM se descarta con `SkippedItem` · presupuesto agotado ⇒ `Observation` con las URLs pendientes · **un `<select>` de 1.874 opciones no mete el catálogo en el prompt ni en el artefacto y el ancla sigue en pie (A6)** · ninguna `evidence` supera los 32.767 caracteres de una celda de Excel | **entorno**: `libnspr4` con `sudo` (§1.1) — solo para una prueba manual, no para la suite |
| **QC6** | `qa_explore_login.py` (CLI, el único sitio que teclea) + carga de `storage_state` + sondeo de sesión válida. | estado caducado ⇒ aborta **antes** de la primera llamada al LLM · el CLI está en `PERMITIDOS` del candado AST y nada más lo está | **entorno** (igual que QC5) |
| **QC7** | Cabecera de grafo C sobre la cola compartida + servicio + `POST /qa/jobs` con `mode` + `GET /qa/explore-targets` + semáforo C con su frase. | los 9 nodos de cola no se duplican · semáforo C exige ancla resoluble en todo caso · `budget_exhausted` ⇒ `ready` posible + `Risk` · `qa` FULL explora, `admin` registra | — |
| **QC8** | Frontend (§7): selector de modo, select de alias **sin campo de URL**, `evidence-class.ts`, ancla en la fila, `HubSection` "Exploración", `UI:` sin destino, columna del CSV. | Modo A renderiza idéntico · alias vacío ⇒ opción deshabilitada con motivo · `UI:` no abre panel | **⚠️ LLM5** — §9.3 |
| **Cierre** | Los modos disponibles sobre el mismo seed, con LLM y navegador falsos. | `scripts/seed_qa_demo.py` extendido | — |

**El Modo B no está en este plan.** Está en cero (§1.2) y su plan es QA11–QA12 de la
PARTE II. QC1 y QC2 le sirven a los dos, así que hacerlos ahora no lo estorba.

## 8.bis Ajustes aprobados al aprobar cada bloque (A1–A6)

Ajustes al diseño de arriba, acordados al aprobar cada bloque. Los tres primeros
se implementaron en QC3; A4 es una nota de riesgo, A5 está **archivada** con su
disparador escrito, y **A6 es un criterio de QC5** acordado al cerrar QC4.5.

### A1 — El alias es una fuga, y se cierra por estructura

Todo el diseño protege el host: el `anchor_ref` guarda el *path* y la URL completa
solo vive en el `SurfaceAnchor` del artefacto. Pero **el alias sí viajaba al
prompt**, y un alias tipo `tms-prod-urbano-aws` filtra al proveedor del modelo el
mapa de infraestructura que nos esforzamos en no mandar.

Había dos salidas: una regla de nomenclatura con candado, o que el alias no viaje
al prompt. **Se eligió la segunda**, porque una lista negra de palabras ("prod",
"aws", nombres de nube) es una promesa que el nombre nuevo incumple sin que nadie
se entere. Lo implementado:

- **`alcance_para_prompt(target, paths)` es lo único que el modelo llega a saber
  del destino**: `{origen, data_class, paths}`. Ni alias, ni host, ni URL, ni
  credencial. QC5 amplía **esa función** con las anclas observadas, y el candado
  (`test_ni_el_alias_ni_el_host_llegan_al_modelo`) cubre por construcción todo lo
  que se añada después.
- **Un lector único de los destinos.** `settings.QA_EXPLORE_TARGETS` solo se lee
  en `explore/target.py` (candado AST). Un segundo lector es un segundo sitio
  donde una capa puede no aplicarse.
- **Refuerzo de nomenclatura, pero solo el que se puede sostener:** el alias
  coincide con `^[a-z][a-z0-9-]{1,31}$`, así que **no puede *ser*** un host, una
  IP ni una URL. El alias se lee en el plan y en el PDF; el host, no.

### A2 — El alias sintético, con candado de host local

`data_class="real"` sin excepción es correcto para sistemas reales y hacía el
Modo C **imposible de probar de punta a punta** sin saldo del proveedor. Explorar
`localhost:3000` —el entorno de desarrollo propio, con semillas sintéticas— no es
una fuente real.

Un destino **puede** declararse `sintetico`, y solo si su host es local
(`localhost`, `localhost.localdomain`, `127.0.0.1`, `::1`), **verificado por el
validador del modelo y no por confianza**: cualquier host no local con
`data_class: "sintetico"` es un destino inválido que no se explora. No debilita
QA-D22: lo hace ejecutable. Y ser local **habilita** declararlo sintético, no lo
declara por ti (el default sigue siendo `real`).

### A3 — El saneador conserva estructura y rótulos (para QC4)

Borrar `value=`, `<script>` y los dígitos largos: correcto. Borrar `<tbody>`
**completo** se llevaría señal: las opciones de un `<select>`, los mensajes de
error renderizados y los rótulos dentro de una tabla a veces **son** la validación
observable, y son justo el tipo de evidencia que QA-D2 acepta citada verbatim.

Ajuste para QC4: el saneador **conserva la estructura y los rótulos y borra los
datos**. Es decir, dentro de un `<tbody>` se conservan las etiquetas, los atributos
de validación y el texto **rotulado**, y se vacían las celdas de datos —el mismo
criterio que ya se aplica a `value=`—. El candado sobre las fixtures (ninguna
secuencia de 8+ dígitos, ningún `value=` no vacío, ni el host de producción) sigue
siendo el que prueba que la línea quedó en el sitio correcto.

### A4 — Riesgo asumido: QC1 fija el contrato antes de que QC5 sepa qué se observa

QC1 cierra `QaArtifact` **v1.1.0** con `SurfaceAnchor`, `evidence_class` y la
matriz generalizada, y lo hace **antes** de que exista `EXPLORE`. Es el orden
correcto —el contrato no se toca dos veces y el Modo B lo necesita igual— pero
tiene una consecuencia que conviene decir ahora: **puede hacer falta una v1.2.0**
cuando QC5 descubra qué se observa de verdad (un `selector_strategy` más, el
fragmento de DOM que respalda la evidencia, el motivo por el que una página quedó
a medias). No es una desviación: es el precio de fijar un contrato antes de la
primera observación real, y se asume explícitamente.

### A5 — ARCHIVADA: un `<td>` con un control es cromo, no dato

La regla se propuso al diseñar A3, **no aterrizó**, y al ir a implementarla se vio
que **no rescata nada en la pantalla que la motivó**. Queda **archivada, no
pendiente**: se reabre si aparece su disparador, que está escrito abajo.

**El caso, verificado contra el saneador de HEAD.** Dentro de un `<td>` sobrevive
solo el texto *rotulado*, y ni `<button>` ni `<a>` están en `TAGS_ROTULO`. Así que
una **columna de acciones** —el patrón exacto de `/configuracion/usuarios`, con su
kebab por fila— se vacía:

```html
<!-- entra -->  <td><button type="button" id="kebab-1">Editar</button></td>
<!-- sale  -->  <td><button type="button" id="kebab-1"></button></td>
```

Lo que se pierde no es un dato: es el **vocabulario de lo pulsable**. "Editar",
"Eliminar", "Ver ficha" son el rótulo con el que el explorador nombraría un caso y
con el que `SURFACE_MAP` describiría la superficie. Un `<option>` dentro de la misma
tabla sí sobrevive; un `<button>` no, y la asimetría no responde a ningún criterio.

**La forma ingenua de la regla es una fuga, y por eso no se implementa a la ligera.**
"El `<td>` que contiene un control es cromo" concedería la celda **entera**, y una
celda mixta es corriente:

```html
<td>Comercializadora Andina S.A.C. <button type="button">Editar</button></td>
```

Ahí el nombre del cliente sobreviviría por vecindad con un botón. La regla falla
hacia **CONSERVAR** dentro de una celda, que es la dirección mala (§12.5), así que
su forma segura es la estrecha: **es rótulo el texto que está DENTRO del control**
—descendiente de `<button>`, `<a>`, `<summary>`— **no el que comparte celda con
él**. Es decir, no una regla sobre el `<td>`, sino dos tags más en `TAGS_ROTULO`
con su candado de celda mixta.

**Por qué se archiva: el caso en contra.** El ejemplo de arriba —un `<button>` con
la palabra "Editar" dentro— **no es nuestra pantalla**. En
`/configuracion/usuarios` el disparador de la fila es un kebab con un **icono** (sin
texto) cuyo nombre viaja en un `aria-label`, y los ítems del menú ("Editar",
"Eliminar", "Restablecer contraseña") se renderizan en un **Portal**, fuera de la
tabla, donde el saneador ya los conserva porque no están en ninguna celda. Es decir:
A5 rescata **cero** rótulos en la pantalla que la motivó. Y el `aria-label` del
kebab tampoco es el rótulo que A5 quería salvar —es el **nombre del sujeto de la
fila**, un dato— así que desde **F1** (§12.7) se vacía por regla, en la dirección
contraria a la que A5 empujaba.

**Su disparador, para cuando aparezca.** A5 vuelve a estar sobre la mesa el día que
se explore un sistema **legado** que rotule con **texto dentro del control**
(`<button>Editar</button>`, `<a>Ver ficha</a>` dentro de la celda) — el patrón de
ExtJS y del PHP de la casa, que es exactamente lo que el Modo C existe para
explorar. Entonces se implementa en su forma estrecha: **dos tags más en
`TAGS_ROTULO`**, no una regla sobre el `<td>`, con su candado de celda mixta.

### A6 — El tope de tamaño de la evidencia de un enum es un CRITERIO de QC5

QC4.5 emite el ancla `@enum` con dos campos que crecen con el catálogo: `value`
(los valores aceptados unidos por `" | "`) y `evidence` (el fragmento **literal**
del `<select>`, de `<select` a `</select>`). En una pantalla de la casa eso no es
una lista corta. Medido con el extractor de HEAD, sobre un `<select>` con la forma
del maestro real:

| Catálogo | opciones | `value` | `evidence` |
|---|---:|---:|---:|
| motor de BD (enum de dominio) | 4 | 33 car. | 373 car. |
| provincias | 196 | 1.761 car. | 15.541 car. |
| agencias | 400 | 3.597 car. | 31.657 car. |
| **distritos del Perú (ubigeo)** | **1.874** | **16.863 car.** | **148.103 car.** |

Tres sitios donde ese número duele, y **ninguno es hipotético**:

1. **El prompt.** `alcance_para_prompt` es lo único que el modelo sabe del destino
   (A1) y QC5 le añade las anclas. UN ancla de ubigeo son **~37.000 tokens**.
2. **El artefacto.** Se persiste en JSONB y se exporta a PDF.
3. **El CSV.** `evidence` **ya es una columna** (`export.py:44`, «Evidencia
   (verbatim)»). El límite de una celda de Excel son **32.767 caracteres**: el
   `value` de ubigeo cabe, el `evidence` **no**, y el fichero que abre el analista
   se rompe por una celda.

**El tope NO puede ser un recorte del conjunto.** Un enum a medias produce un caso
que afirma que un valor legítimo debe rechazarse, y ese caso **pasa la ejecución
certificando una mentira** (§13.4). Recortar la lista es exactamente el error que
el módulo se prohíbe.

**Lo que sí, porque el caso no necesita el conjunto entero.** El `invalid_value` de
un caso de enum ya es un **centinela** en el Modo A (`VALOR_FUERA_DEL_CATALOGO`,
`edge_cases.py:180`), no un valor derivado del conjunto; y el `valid_value` sale del
**primero**. Lo único que el conjunto completo aportaba es responder *«¿cambió el
catálogo?»*, y para eso una **huella** es estrictamente mejor que el catálogo:
detecta el cambio sin transportarlo. Por encima del tope, el ancla **sigue
existiendo** y lleva `enum_digest` —cardinalidad + hash estable del conjunto
ordenado + los primeros valores— en vez del conjunto literal.

**Y de paso cierra una fuga que no es de tamaño.** Un `<select>` de clientes, de
colaboradores o de jobs es un volcado de datos de producción con forma de enum: en
**nuestro propio frontend**, 4 de 16 `<select>` tienen identificadores de usuario o
nombres completos como valores. El `evidence` verbatim de uno de ésos lleva la
plantilla de personal a un PDF exportable — el mismo riesgo que el guard evita con
las capturas de pantalla (capa 4). La huella no lo lleva.

**El criterio de QC5, explícito:**

1. `ENUM_MAX_OPCIONES` y `ENUM_MAX_CHARS` son constantes del módulo, cada una **con
   su motivo escrito al lado**, como el vocabulario de :data:`ATRIBUTOS_ANCLA`.
2. Por encima del tope se emite `enum_digest`, **nunca** un conjunto recortado. El
   `evidence` del ancla es entonces la etiqueta de apertura del `<select>`, no su
   contenido.
3. Ningún `evidence` de ningún ancla supera los **32.767** caracteres de una celda
   de Excel. Es un test, no una recomendación.
4. Un `<select>` de 1.874 opciones **no** mete el catálogo ni en el prompt ni en el
   artefacto, y **sí** deja el ancla en pie: el hueco no se abre.
5. **Aplica también al Modo A.** `api_field_boundaries` hace
   `", ".join(campo["enum"])` sin tope (`edge_cases.py:178`), y un catálogo del
   `DatabaseArtifact` puede ser igual de largo. El tope se escribe una vez y lo
   comparten los dos modos, o se arregla la mitad del problema.

---

## 9. Colisiones

### 9.1 QC2 ⇄ LLM2 — real, hay que ordenarla

LLM2 hace `data_class` obligatorio en los tres puntos de ingesta e instala
`ProviderPolicyError` en la fábrica. QC2 añade un **cuarto** punto —derivado, no
declarado— y depende de esa excepción para que "sin excepción posible" sea cierto.

**Recomendación: QC2 después de LLM2.** Al revés, QC2 tendría que dejar el test que
importa (proveedor no-Anthropic + `real` ⇒ excepción antes de la llamada) marcado
como pendiente, y un candado de seguridad aplazado es un candado que no existe.
QC0, QC1, QC3 y QC4 **no dependen de LLM2** y pueden ir antes.

### 9.2 QC5/QC6 ⇄ LLM1 — no es colisión, es una laguna que hay que tapar

LLM1 ya está en `main` y su capa 4 **no cubre** el navegador (§6.1): es otro
proceso. No hay conflicto de código; hay una **garantía que se cree existente y no
lo es**. QC3 la tapa con `sin_navegador_real` **antes** de que QC5 instale
Playwright, que es el orden correcto: la valla antes del animal.

### 9.3 QC8 ⇄ LLM5 — conflicto de ficheros, no de diseño

LLM5 ("Frontend" del multiproveedor) toca **la barra superior duplicada en las seis
vistas de artefacto**, `qa-result-view.tsx` incluida, para insertar el sello de
procedencia. QC8 toca ese mismo fichero. **No hacerlos en paralelo**; en secuencia,
en cualquier orden.

### 9.4 QC5 ⇄ LLM3 — solo un candado

Cuando exista Gemini, el candado de §5.3.1 (override de rol + exploración ⇒
`ProviderPolicyError`) pasa de hipotético a ejercitable con un proveedor de verdad.
Si LLM3 aterriza antes que QC2, ese test entra con LLM3.

## 10. Lo que este plan no resuelve, dicho aquí

- **Chromium no arranca** en este host (`libnspr4`, sin `sudo`). QC3, QC4 y toda la
  suite viven sin él; QC5/QC6 lo necesitan para **una** verificación manual.
- **DNS rebinding** entre la comprobación de allowlist y la conexión: documentado,
  no mitigado (§13.2 de la PARTE II).
- **WebSockets** posiblemente fuera del alcance de `page.route` (§3.4).
- **Marcar un sistema del inventario como sintético** (§5.4): necesita columna y
  migración propias, y depende del Modo B.
- **Teclear para observar validaciones nativas** (§3.2, nivel 2): fuera de v1 con
  motivo escrito, no olvidado.

---

# PARTE 4 — Lo implementado

## 11. QC3 — el guard, antes del navegador (cerrado)

`backend/ai/agents/qa/explore/` con **cero líneas de Playwright** y cero
dependencias nuevas (el DOM mínimo es `html.parser`, de la biblioteca estándar).

| Fichero | Qué sostiene |
|---|---|
| `target.py` | Capas 1, 2 y 4 + A1 + A2 + la precondición `readonly_verified` (409). `ExploreTarget` con `extra="forbid"`, `available_targets()`, `assert_target_authorized()`, `redact_url()`, `alcance_para_prompt()` |
| `navigation.py` | Capa 5: `evaluar_navegacion()` (veredicto, para registrar) y `assert_navigation_allowed()` (excepción, para la entrada) |
| `dom.py` | DOM mínimo de biblioteca estándar + `selector_de()` (`[name]` › `#id` › `[data-testid]`) |
| `clicking.py` | Política de pulsado del nivel 1, con el `type="button"` **explícito** |
| `driver.py` | El protocolo estrecho (`goto`/`click`/`close`) y `build_driver()`, que hoy falla explicando que QC5 trae el driver |
| `limits.py` | Topes validados: `0` es inválido, no infinito (QA-D25.4) |
| `session.py` | `ExploreSession`: única dueña del contexto, capa 5 en cada navegación, presupuestos de páginas/profundidad/tiempo/clics |

**Cinco decisiones de implementación que conviene no perder:**

1. **La capa 5 revalida cuatro cosas, no una.** La URL pedida, la `location` de una
   redirección, **la URL final con la que vuelve el driver** (por si la siguió él:
   un DOM traído de otro host no es observación del sistema explorado) y el destino
   de un clic. Lo que cae fuera no se sigue y queda en `salidas_bloqueadas` con su
   motivo y la página de origen.
2. **El clic tiene un único dueño.** `click` solo aparece dentro de
   `ExploreSession.pulsar_si_procede`, comprobado por AST; el driver se guarda con
   nombre mangled y ningún método público lo devuelve. Los métodos que escriben o
   capturan (`fill`, `type`, `press`, `select_option`, `check`, `evaluate`,
   `screenshot`…) no existen en ninguna parte de `app/` ni `ai/`, y el único
   permitido en el futuro será el CLI de login de QC6.
3. **`build_driver` se llama por el módulo, no por un nombre importado.** Un
   `from … import build_driver` resolvería el enlace al importar y el parche del
   cortafuegos —que sustituye el atributo del módulo— no lo alcanzaría. Es la misma
   lección que la capa 1 del cortafuegos del LLM, y tiene su propio candado.
4. **Sin selector estable no se pulsa.** Sin `[name]`, `#id` ni `[data-testid]`,
   `selector_de()` devuelve `None` y el elemento no se pulsa: un clic que no se
   puede describir no se puede repetir, y comparar dos corridas es lo único que
   hace útil a una suite de caracterización. **El selector estructural
   (`nth-of-type`) se aplaza a QC5**, donde llega junto a su `selector_strategy`
   —el campo que avisa de que el ancla es frágil—. Coste declarado: hoy una pestaña
   sin atributos identificables no se pulsa.
5. **`sin_navegador_real` es la capa 5 del cortafuegos de tests**, autouse, y **no
   es una hermana de conveniencia de `sin_api_real`**: la capa 4 (el guard de
   `socket.socket.connect`) parchea *este* proceso y el navegador es otro, así que
   para ese riesgo es la única capa que existe. Parchea la fábrica del driver —y
   los dos entrypoints de Playwright si algún día están instalados—, nunca
   `ExploreSession`: la garantía no puede depender de que el código de mañana pase
   por la sesión.

**Suite:** 1250 → 1395 (+145), toda la de los Modos A y el resto del proyecto
intacta. Sin red, sin LLM, sin navegador y sin dependencias del sistema.

**Lo que QC3 NO trae, dicho aquí:** la intercepción de red que aborta todo método
≠ `GET`/`HEAD`, la neutralización del `submit` con `add_init_script` y el
`storage_state` del login. Las tres necesitan el driver real y son de QC5/QC6. La
mitad de la capa 3 que sí está puesta es la que se decide leyendo el DOM.

---

## 12. QC4 — fixtures y saneador (cerrado)

`backend/tests/fixtures/qa_explore/` con tres escenarios,
`ai/agents/qa/explore/sanitize.py` y `scripts/capture_explore_fixture.py`. Sigue
sin haber una línea de Playwright, y `test_qc3_no_introduce_playwright` sigue vivo.

| Pieza | Qué sostiene |
|---|---|
| `tms_guias/` | Una aplicación observada de punta a punta: entrada con `302`, acceso, listado con tabla y alta con `required`/`maxlength`/`pattern` |
| `spa_router/` | El motivo entero del nivel 1: el formulario **no existe** en el HTML servido y aparece al pulsar la pestaña |
| `trampas/` | `button` sin `type`, redirección fuera de host, `POST` en el clic, `href` `javascript:` (más una descarga y un `<button form="otro">`) |
| `manifest.json` | **Lo que sustituye al navegador**: `status`, `location`, URL final, resultado y `method` de cada clic |
| `sanitize.py` | `sanear_html()` (A3), `violaciones()` (el candado) y `escenario_saneado()` (que aplica el candado **antes** de escribir) |
| `capture_explore_fixture.py` | La captura manual, con autorización explícita. Hoy falla en `build_driver` diciendo que QC5 trae el driver: no finge que exploró |

**Seis decisiones que conviene no perder:**

1. **El manifiesto ejerce la capa 5 sin navegar.** Con `status`, `location` y la
   URL final, la revalidación en cada salto —incluida la de la URL con la que
   *vuelve* el driver— se prueba entera contra HTML congelado. Sin ello, la capa 5
   solo estaría probada con dobles escritos a mano en cada test, que es lo mismo que
   decir que está probada contra sí misma.
2. **A3 en una regla ejecutable**: dentro de un `<tbody>`, el texto sobrevive solo
   si está **rotulado** —`<label>`, `<option>`, `<th>`, `<legend>`, `<caption>`, un
   `role` de mensaje, un `aria-live` o una `class`/`id` de error o ayuda—. Todo lo
   demás se vacía. Es lo que deja pasar un mensaje de error renderizado y las
   opciones de un `<select>` dentro de una celda —la evidencia verbatim de QA-D2— y
   deja fuera el nombre del cliente de la fila de al lado.

   **La frontera exacta de la marca es «en la fila, en la celda o por debajo».** Un
   `<tr class="fila-error">` cuenta —la fila es la unidad que una aplicación marca
   cuando rechaza un registro— y con ella se conserva el texto de todas sus celdas.
   Un `<tbody class="mensaje-error">` **no** cuenta, ni `<table>`, ni `<thead>`, ni
   `<tfoot>`: tienen la misma forma de falso positivo que el
   `<div class="error-boundary">` de React —envuelven la tabla entera— así que se
   les aplica el corte igual que a cualquier ancestro. Los dos lados están fijados
   con test.
3. **Los manejadores en línea se borran, por el mismo motivo que `<script>`**: son
   código, no estructura ni rótulo, y arrastran rutas con identificadores reales.
   Consecuencia declarada: la trampa del `POST` **no** sobrevive a una captura, así
   que las trampas se escriben a mano. Es el sitio correcto para escribirlas.
4. **El candado se prueba introduciendo la violación.** Un candado que solo se ha
   visto pasar es indistinguible de una función que devuelve la lista vacía. Y por
   el otro lado: se comprueba que **no** muerde lo que debe conservarse (el atributo
   de valor vacío, un `pattern` con dígitos, un `data-value`), porque si lo hiciera,
   la salida del propio saneador no pasaría su propio candado.
5. **El saneador no es un oráculo de PII sobre texto libre.** Un dominio de la casa
   o un nombre propio dentro de un párrafo sobrevive —el texto es la evidencia— y lo
   para el candado. Por eso el candado corre **antes de escribir**
   (`escenario_saneado()` lanza `CapturaSuciaError`) y no solo en la suite: un aviso
   por consola se lee cuando ya está comiteado.

6. **NOTA DE DISEÑO — el vocabulario está afinado contra NUESTRO frontend, y el
   Modo C no existe para explorar nuestro frontend.** Es la limitación estructural
   de `PIEZAS_DE_MENSAJE`, y conviene que esté escrita antes de que alguien la
   descubra ampliando la lista.

   Las 17 piezas se auditaron contra lo único que podíamos mirar de verdad: el HTML
   que renderiza `frontend/`. El resultado de esa auditoría es incómodo y por eso
   vale la pena: **una sola pieza tiene un caso observado** (`destructive`, del
   `<p role="alert" class="… text-destructive">` de `ui/field.tsx`). Nuestro
   frontend **no** marca sus errores con una `class` que contenga `error`, y su
   `hint` se rotula `text-meta-foreground`. Es decir: el vocabulario no se derivó
   de observaciones, se heredó.

   Y el objetivo real es otro sistema. El legado de Urbano es **PHP/ExtJS**, cuyo
   vocabulario es `x-form-invalid-field`, `x-form-error-msg` y compañía. De esos
   dos ejemplos, los dos caen dentro de la lista —troceados dan `invalid` y
   `error`—, pero eso es **suerte del troceo, no cobertura**: no hemos explorado
   ese sistema, así que no sabemos cuáles de sus marcas reconocemos ni cuántas se
   nos escapan. Contra un objetivo no observado, una lista de literales solo puede
   quedarse corta.

   **Consecuencia de diseño, no una advertencia:** el peso recae en las señales
   **estructurales**, que no dependen del vocabulario de nadie —`role` de mensaje,
   `aria-live`, `TAGS_ROTULO` (`<label>`, `<option>`, `<th>`, `<legend>`,
   `<caption>`, `<summary>`, encabezados)—. `PIEZAS_DE_MENSAJE` es **red
   secundaria**, y se amplía **solo con evidencia de un sistema explorado**: una
   pieza = un caso verificado, con su origen anotado en el docstring del módulo
   (`observado` / `prospectivo` / `heredado sin caso`).

   **Completar la lista «por simetría» está PROHIBIDO.** Ni el plural de una pieza
   que ya está, ni el resto del enum de sufijos de Bootstrap porque `danger` esté
   dentro, ni la traducción al español de una pieza inglesa. El motivo es la
   asimetría rectora del bloque leída en esta dirección concreta: casar de menos
   **vacía el texto de una celda** —se pierde señal, se ve, se arregla—, mientras
   casar de más **conserva un dato de producción en una fixture comiteada para
   siempre**. Una pieza añadida por simetría ensancha la dirección irreversible sin
   un caso que la respalde, que es exactamente la fuga que este bloque cerró: por
   eso salieron `errors`, `errores` y `mensajes` (20 → 17) y por eso `messages`
   —canónico de Django— se queda **anotado como candidato y fuera de la lista**
   hasta que se explore un sistema que lo emita.

**El residual, con fixture y test esperando a QC5.** `<button type="button">` con
un manejador que manda un `POST` **es pulsable** para la lista blanca del DOM, y
hace bien: leyendo el DOM no hay forma de saber qué dispara. Quien lo para es la
mitad de red de la capa 3. El doble *modela* ese aborto —devuelve la página sin
cambios, y la página "aprobada" existe en el escenario y no se llega a ver— para
dejar escrita la expectativa contra la que QC5 tendrá que quedar verde. El test
dice explícitamente que eso es una especificación ejecutable, no una demostración.

**Suite:** 1395 → 1477 (+82; 77 de QC4 y 5 del candado de la regla R1), sin red,
sin LLM, sin navegador y sin dependencias nuevas. Frontend intacto (120).

**Tres afinamientos posteriores al cierre, sobre el mismo saneador** (1477 → 1533):
el reconocimiento de un mensaje pasó de subcadena a **piezas exactas** con corte de
herencia en la tabla (la fuga que fallaba hacia conservar); después la frontera de
la marca quedó fijada en **«en la fila, en la celda o por debajo»** más la auditoría
del vocabulario que dejó la lista en 17 piezas, con su candado (decisión 6); y por
último **F1** (§12.7), la fuga que se escondía en los atributos. No abren bloque:
QC4 sigue cerrado y QC5 sigue siendo el siguiente.

### 12.7 F1 — el texto que se escondía en un atributo

**La fuga.** El saneador vaciaba el **cuerpo** de una celda de datos y no miraba sus
**atributos**. La pasada de accesibilidad de nuestro propio panel de usuarios pone
el nombre del sujeto de la fila justo ahí:

```html
<td><button type="button" aria-label="Acciones de Juan Perez Quispe">⋮</button></td>
```

El nombre sobrevivía al saneado —ningún patrón de dígitos lo toca— y el candado
tampoco lo buscaba: sus tres comprobaciones eran RUC, dominio de la casa y `value`.
Un volcado del panel con usuarios reales habría comiteado los nombres del equipo. Es
una fuga **activa en la dirección irreversible**, así que se arregló antes de
capturar nada.

**La regla, y por qué no es una lista de nombres de atributo.** La pregunta no es
«¿está `aria-label` en mi lista?» sino **«¿renderiza el navegador este valor?»**. Si
sí, es texto que lee un usuario y se gobierna **exactamente como el texto de una
celda**: dentro de un `<td>` se vacía salvo rótulo, con el mismo corte de frontera
tabular; fuera, se conserva enmascarado. Una sola función
(`_Saneador._gobernar_texto`) decide, y la llaman el cuerpo y los atributos, de modo
que lo que se añada mañana hereda el régimen sin repetir la decisión.

**Lo que hace estructural la identificación.** En el espacio `aria-` la
especificación declara el tipo de valor de cada estado y propiedad, así que se
enumera la mitad **cerrada** —tokens, booleanos, números e IDREF (`ARIA_SIN_PROSA`)—
y **todo lo demás es prosa por defecto**. La inversión es lo que evita repetir el
error de forma de `PIEZAS_DE_MENSAJE`: `aria-rowindextext` —prosa, y justo dentro de
una celda— queda cubierto sin que nadie lo escribiera, y lo que ARIA añada mañana
entra por el lado **benigno** (se vacía de más, no se comitea de menos). Fuera de
`aria-` HTML no agrupa nada, así que ahí sí hay lista (`title`, `alt`, `placeholder`,
`label`, `abbr`, `download`) — pero decide qué se **borra**, que es la dirección
barata, y cada entrada lleva su caso escrito con su candado, igual que el vocabulario
de mensajes.

**`aria-describedby` no entra en ninguna de las dos, y es correcto:** su valor es una
lista de IDREF. El texto que lee el usuario vive en el elemento apuntado, donde ya lo
gobierna el mismo régimen. Residual declarado: si ese elemento está **fuera** de la
celda, su texto se conserva — como todo el texto fuera de una celda, que es la
evidencia.

**El candado gana una cuarta comprobación, y es la única que necesita saber DÓNDE
está lo que mira.** Hace falta porque **las trampas se escriben a mano y nunca pasan
por el saneador**, y no puede ser global porque un `aria-label` con contenido fuera
de una celda es legítimo — prohibirlo en todas partes dejaría a QC4.5 sin fixture con
la que ejercer su cuarta estrategia de ancla. Se implementa con lo más tonto que
sirve: una **ventana de subcadena** entre `<td` y `</td>`, sin árbol, sin ancestros y
sin anidamiento, con la **misma** función de rótulo que usa el saneador —no una
copia— aplicada a la etiqueta que lleva el atributo.

> **REGLA (no criterio de esta vez): el candado puede mirar una VENTANA DE TEXTO;
> nunca construir un árbol ni consultar ancestros.** Tiene que valer igual para un
> `.html`, un `manifest.json` y un README, y tiene que poder entenderlo entero quien
> lo lee. El corolario es la parte útil: **si una comprobación necesita el padre de
> algo, la señal no es «hazla mejor», es que esa comprobación no va en el candado**
> — va en el saneador, que sí parsea, y cuya salida vuelve a pasar por el candado
> antes de tocar el disco. Así queda **F2** (§13.4) y así quedará la siguiente.
> Escrita en el docstring de `sanitize.py`, que es donde la lee quien la necesita. **Residual declarado:** mira esa
etiqueta y no sus ancestros, así que un `<td class="mensaje-error">` con un botón
dentro salta en el candado y no en el saneador. Es la dirección segura —el candado
puede ser más estricto que el saneador, nunca al revés— y se arregla a mano.

**Segundo residual declarado, y ahora con dueño:** un `placeholder` de formato
**dentro** de una celda (una edición en línea) se pierde. Es la dirección barata
—se pierde señal, no se comitea un dato— y el descarte queda anotado, así que quien
captura lo ve. Lo que arreglaría ese caso es la mitad **pendiente** de (b) —`aria-`
y sus vecinos como **fuente de rótulo**, no solo como texto que se lee— y este es
**su primer test** el día que se abra: un `placeholder` de formato es un límite
citable verbatim, exactamente el estatus que QA-D2 exige para un caso de borde.
Queda anotado en `sanitize.py`, junto al atributo.

**Suite:** 1495 → 1533 (+38), ningún test existente reescrito; en
`test_fixtures_candado.py` se añaden casos a las dos listas parametrizadas porque el
candado pasó de tres comprobaciones a cuatro. El caso F1 exacto está fijado con
nombre y **comprobado contra el código anterior**, donde falla.

---

## 13. QC4.5 — el extractor determinista de anclas (cerrado)

`ai/agents/qa/explore/extract.py` + `scripts/anclas_de_html.py`. Sigue sin haber
una línea de Playwright. **Entra `html: str` y `path: str`, sale una lista de
anclas con evidencia literal. Nada más**: sin red, sin LLM, sin navegador, sin clic
y sin tocar el disco.

Es la mitad barata del Modo C y la que decide si el resto sirve de algo:
`SURFACE_MAP` (QC5) es el cortafuegos anti-invención del modo —el gemelo de
`CRITERION_MAP`, `MODEL_MAP` y `RESOURCE_MAP`— y **un cortafuegos vale lo que valga
la lista cerrada que le dan de comer**. Esa lista se fabrica aquí, en Python, antes
de gastar un token: el modelo no elige *qué* hay, solo redacta *cómo* se prueba.

### 13.1 El vocabulario es cerrado y un atributo es un ancla

Once atributos —`required`, `maxlength`, `minlength`, `pattern`, `min`, `max`,
`step`, `type`, `readonly`, `accept`, `multiple`— más `@enum`, que no es un
atributo sino el conjunto de valores que acepta un `<select>`. **Cada entrada lleva
su caso escrito al lado**, y un test exige que ampliarla obligue a escribir ese
caso: una lista de atributos sin su caso es indistinguible de una lista copiada de
la especificación de HTML, y entonces nadie sabe por qué falta el que falta. Es la
misma regla que gobierna `PIEZAS_DE_MENSAJE`.

Que `required` y `maxlength` del mismo campo sean **dos** anclas y no una no es
burocracia (§2.1): habilitan casos distintos y se pueden romper por separado, así
que fundirlas escondería media rotura.

**Tres candidatos anotados y deliberadamente fuera**, por la misma razón por la que
`messages` está anotado fuera del vocabulario de mensajes: `value` es el dato y no
el límite —es justo lo que el saneador vacía—; `disabled` no valida nada, porque un
campo deshabilitado no se envía; y `placeholder` puede llevar el formato y por tanto
un límite citable, pero es **texto**, no una restricción que el navegador imponga —
anclarlo mezclaría lo observado con lo insinuado, y su arreglo tiene dueño: la mitad
pendiente de (b), `aria-` y sus vecinos como **fuente de rótulo** (§12.7).

**`type` ancla solo cuando restringe la forma del dato** (`number`, `email`, `date`,
`file`…). Un caso «escribe texto en un campo de texto» es ruido que entierra al que
importa —el mismo motivo por el que las preguntas al DBA se agrupan por clase de
vacío— y no se pierde nada: el límite real de esos campos vive en
`maxlength`/`pattern`/`required`, que sí se anclan.

### 13.2 Cinco estrategias de selector, y la unicidad sustituye al prefijo de §2.1

`[name]` › `#id` › `[data-testid]` › `[aria-label]` › ruta estructural
`nth-of-type`. Las dos últimas **no** se añaden a la lista de pulsar
(`dom.ESTRATEGIAS`), y la asimetría es deliberada: un selector que una traducción
rompe o que un envoltorio nuevo rompe basta para **anclar** un caso que una persona
va a leer, y no basta para **pulsar** contra una aplicación viva, donde equivocarse
de elemento es una acción y no una nota. La lista de anclas **extiende** la de
pulsar en vez de copiarla, con test: dos listas copiadas se separan.

**Desviación declarada respecto del ejemplo de §2.1.** Aquel ejemplo escribe el ref
con un prefijo de ancestro (`form[name=guia] input[name=ruc]`) para desambiguar. El
prefijo **no desambigua el caso que de verdad ocurre**: dos radios del mismo grupo
comparten `name` *y* comparten formulario. Aquí se exige lo que el prefijo
insinuaba —que el selector case con **un** elemento— y se comprueba de verdad
(`veces_por_selector`), lo que es estrictamente más fuerte y además más corto. Un
candidato ambiguo cae a la estrategia siguiente; en el ejemplo de los radios, a
`#id`.

**El structural nace marcado** (`fragil`), para que `CRITIQUE` pueda emitir su
`Risk` con el porcentaje. `aria-label` **no** se marca, y conviene decir por qué:
frágil no es «puede cambiar», es «puede romperse sin que haya cambiado nada que
importe». Un `<div>` de maquetación rompe el structural sin cambiar nada
observable; un `aria-label` que cambia es un cambio en lo que el usuario lee, y una
suite de caracterización **debe** enterarse de eso.

### 13.3 Fail-closed: sin selector no se emite ancla

Y la rama es real, no decorativa: **una etiqueta que no se puede escribir en CSS no
ancla**. El legado de WebForms sirve `<asp:TextBox name="ruc" required>`, y
`asp:textbox[name="ruc"]` no selecciona nada —los dos puntos abren una
pseudo-clase—. Emitir ese ancla daría un ref que no resuelve nunca, es decir un caso
condenado a fallar por el motivo equivocado, que es ruido con aspecto de hallazgo.
Se prefiere el hueco, que **sí se ve en la cobertura**.

El `path` se comprueba en la única fábrica de refs: una URL, un `//host` o un path
relativo se **rechazan**, no se recortan. Recortar en silencio acepta la
equivocación de quien llama y la repite en la siguiente; y lo que se coló sería el
host del destino dentro de un CSV que se exporta (capa 4 / A1).

### 13.4 F2: visible, fijada con un test, y NO resuelta

El saneador vacía **todo** atributo `value` porque un `value` es un dato de
producción. Pero el `value` de un `<option>` no es un dato: es el **conjunto de lo
aceptado**, es decir un límite citable.

**Corrección del motivo, al cerrar QC4.5.** La primera redacción decía que
distinguirlos exige árbol y ancestros, y que el candado de fixtures tiene prohibido
construirlo (§12.7). Es falso: saber que se está dentro de un `<select>` es un
contador sobre el mismo recorrido lineal, igual que `TAGS_ROTULO` ya distingue lo
que hay dentro de un `<tbody>`. La justificación escrita era **más fuerte que el
obstáculo real**, y eso es peor que no haber escrito ninguna: cierra la puerta con
un candado que no existe, y el que la lea mañana ni siquiera intentará abrirla.

**El obstáculo real es el discriminador.** Conservar el `value` de un `<option>`
conserva **cualquier** lista, y un `<select>` de clientes, de colaboradores o de
jobs es un volcado de datos de producción con forma de catálogo. Sin una regla que
separe **catálogo de dominio** de **lista de datos**, "conserva los `value` de
dentro de un `<select>`" mete en la fixture exactamente lo que el saneador existe
para sacar. Es la misma distinción que necesita **C4 de QC5** —los *enums falsos*,
cuyos valores son ULIDs o nombres de personas—, así que F2 no se resuelve antes que
ella: se resuelven juntas o no se resuelve ninguna.

**Y no abre bloque, porque no está en el camino vivo.** El saneador está entre
*capturar* y *comitear*, no entre *explorar* y *extraer*: el Modo C real extrae del
DOM que devuelve el navegador, con sus `value` intactos. F2 no le quita un ancla a
ninguna exploración; le quita cobertura a las **fixtures**, que es exactamente donde
se ve.

Consecuencia, fijada con dos tests y no con una nota: **sobre HTML crudo el
extractor ve el enum de un `<select>`; sobre la fixture saneada del mismo `<select>`
no ve ninguno** —incluido el `<select name="ubigeo">` que ya está comiteado, que
conserva su `required` y pierde su enum—. No se parchea aquí: un enum reconstruido a
partir de valores vacíos sería el error que este agente no puede cometer. Un enum a
medias tampoco se emite, por lo mismo: un hueco se ve en la cobertura, mientras que
un conjunto incompleto produce un caso que afirma que un valor legítimo debe
rechazarse, y ese caso **pasa la ejecución certificando una mentira**.

### 13.5 Lo que se añadió a `dom.py`, y por qué ahí

Tres datos del parse: `origen` (el texto **literal** de la etiqueta de apertura, que
es lo que hace citable una observación), `ruta` (el camino `nth-of-type`) e `inicio`
(el desplazamiento, para recortar el fragmento literal de un `<select>`).
Reconstruirlos después obligaría a recorrer el HTML con un segundo mecanismo, y dos
parsers del mismo documento se separan el día que uno tropieza con etiquetas mal
cerradas.

### 13.6 Los candados del bloque, y verlos fallar

- **Cero navegador**, por lista de imports **cerrada**: el extractor solo puede
  importar `re`, `dataclasses`, `typing` y el `dom` del propio paquete. Ni
  Playwright, ni red, ni disco, ni los módulos hermanos que conducen el navegador.
- **Nada que abra un fichero**, ni un literal que nombre uno del repositorio (los
  docstrings quedan fuera: hablan de las fixtures precisamente para decir que no las
  tocan). Más un test de comportamiento: con `open` inutilizado, extraer funciona.
- **Síncrono a propósito**: lo que no puede esperar no puede esperar a la red.
- **Idempotente y estable**: dos pasadas dan los mismos refs en el mismo orden, y
  dentro de un control manda el vocabulario y **no** el orden en que la aplicación
  escribió los atributos —ese orden cambia entre despliegues sin que cambie nada, y
  con él cambiarían los refs de una corrida a otra—.
- Y como en QC4, **los candados se ven fallar**: seis fuentes sintéticas
  (`import playwright`, `from …driver import build_driver`, `open("tests/…")`…)
  comprueban que saltan. Un candado que solo se ha visto pasar es indistinguible de
  una función que devuelve la lista vacía.

### 13.7 Un lector para mirarlo con los ojos

`scripts/anclas_de_html.py <fichero.html> --path /guias/nueva [--evidencia]` imprime
la tabla: línea, estrategia (con `⚠` en las frágiles), atributo, valor y selector,
más el recuento y **los controles que se quedaron sin selector**. Ese último bloque
es la mitad del valor de mirar: enseña la decisión fail-closed en vez de dejarla
implícita en una ausencia. No forma parte de la suite y no escribe nada.

**Suite:** 1533 → 1607 (+74), **ningún test existente modificado**. Sin red, sin
LLM, sin navegador y sin dependencias nuevas.
