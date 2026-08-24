# Diseño — Soporte multiproveedor de LLM (banco de pruebas con Gemini)

> **Estado: APROBADO.** **LLM0 implementado** (la fábrica, con un solo
> proveedor); LLM1→LLM6 pendientes. Los bloques se ejecutan **uno a uno, con
> aprobación explícita** entre ellos.

---

## 0. Principio rector

El propósito no es "soportar varios modelos". Es **poder ejercitar el pipeline
sin saldo de Anthropic**, y hacerlo sin que el resultado de ese ejercicio pueda
confundirse jamás con un resultado válido.

De ahí que el diseño se ordene por una asimetría, la misma que gobierna al Agente
QA y al Agente API:

> **Un run que falla por falta de proveedor se ve. Un artefacto generado con
> Gemini que nadie distingue de uno validado se despliega.**

Todo lo demás —la fábrica, el parseo, los rate limits— es fontanería. Las dos
cosas que este diseño tiene que hacer *estructuralmente imposibles* son:

1. que un dato real de Urbano salga hacia un proveedor que no sea Anthropic;
2. que un artefacto producido por un proveedor de pruebas circule sin sello.

Ninguna de las dos puede depender de que alguien se acuerde.

---

## 1. Inventario del acoplamiento actual (verificado)

La noticia buena: **la abstracción correcta ya existe**. `LLMClient`
(`ai/agents/base/structured.py:23`) es un protocolo de dos líneas —`complete_json(system, user) -> str`—
y los **~30 nodos generativos de los seis agentes ya lo consumen**. Ni un solo
nodo menciona a Anthropic.

La noticia mala: **la abstracción cubre la llamada, no la política**. Lo que está
cableado a Anthropic es precisamente lo que Gemini rompe.

### 1.1 Puntos que instancian o nombran al proveedor

| # | Archivo | Qué hay | Riesgo al añadir proveedor |
|---|---|---|---|
| 1 | `app/dependencies/claude.py:29-41` | `get_claude_client()` → `ChatAnthropic` | **Único constructor.** Se sustituye por la fábrica. |
| 2 | `ai/agents/base/structured.py:179-199` | `ClaudeLLMClient.complete_json` | **Único adaptador** protocolo↔SDK. |
| 3 | `app/dependencies/claude.py:9,15` | `_RETRYABLE = (RateLimitError, InternalServerError, APIConnectionError)` importadas de `anthropic` | **El más peligroso.** Con otro proveedor esas excepciones no se lanzan nunca: `call_with_retry` deja de reintentar **en silencio**. Y el free tier de Gemini es 429 casi por definición. |
| 4 | `app/dependencies/claude.py:44-56` | `retry_after_seconds` lee `exc.response.headers["retry-after"]` | Gemini señala la espera en el cuerpo del error (`RetryInfo`), no siempre en cabecera. Devolvería `None` y caería al backoff exponencial genérico. |
| 5 | `app/dependencies/claude.py:84-91` | `estimate_cost` sobre `CLAUDE_PRICE_*` globales | Llamado desde los **seis** `assemble.py`. Con Gemini free el costo real es 0; reportar "$0,42" es una métrica **falsa**, no imprecisa. |
| 6 | `ai/agents/base/structured.py:29-56` | `message_text()` documenta la forma de `langchain-anthropic` 1.x (lista de bloques `thinking`+`text`) | Tolerante por construcción; sirve tal cual si el cliente nuevo devuelve `str`. |

### 1.2 Sitios que construyen el cliente (los que hay que redirigir)

- **Servicios (8 construcciones):** `ef_service.py:65` y `:70` (`critique_llm`),
  `scrum_service.py:61` y `:63`, `arquitectura_service.py:66`, `bd_service.py:78`,
  `api_service.py:85`, `qa_service.py:84`.
- **Fallback de nodos (5):** `_llm_of()` en `api_nodes.py:52`,
  `arquitectura_nodes.py:37`, `bd_nodes.py:48`, `qa_nodes.py:39`,
  `scrum_nodes.py:32`; más `ai/orchestrator/nodes.py:85` (EF).
- **Fuera del pipeline (1):** `app/api/v1/inventario.py:282` llama a
  `get_claude_client()` **directamente**, sin pasar por `run_agent_pipeline`. Es
  INV3, la ingesta de **documentos que describen sistemas reales de Urbano**.
  Es decir: el único punto que hoy se salta el runner es también el que maneja el
  material más sensible. No es coincidencia que sea el que más cuidado exige.

> **Recuento corregido en LLM0: son 15, no 13.** 8 en servicios + 6 en nodos + la
> ingesta del inventario. El número queda fijado con un test candado
> (`tests/llm/test_construcciones.py`) para que añadir un agente sin pasar por la
> fábrica no pase inadvertido.

> **Hallazgo de LLM0 en esa misma línea 282:** no solo evadía la política — le
> pasaba a `extract_knowledge` (que espera un `LLMClient`) el **chat crudo**, que
> no tiene `complete_json`. La ingesta de documentos del inventario estaba
> **rota en producción**, y el test la tapaba porque inyectaba un doble con
> `complete_json` donde la ruta real pone un `ChatAnthropic`. Al entrar por la
> fábrica queda arreglada, y el test pasa a doblar el chat.

### 1.3 Consumo de `estimate_cost` (6 sitios)

`ef/assemble.py:183`, `scrum/assemble.py:91`, `arquitectura/assemble.py:128`,
`bd/assemble.py:168`, `api/assemble.py:151`, `qa/assemble.py:184`.

### 1.4 Cortafuegos de tests

`tests/conftest.py:44` parchea **una función por su ruta de importación**
(`app.dependencies.claude.get_claude_client`). `tests/test_budget_guard.py` lo
verifica. Cobertura real: exactamente un proveedor, exactamente un símbolo.

### 1.5 Conclusión del inventario

El refactor **no toca ningún nodo, ningún prompt y ningún contrato**. Toca dos
archivos de infraestructura (`app/dependencies/claude.py`,
`ai/agents/base/structured.py`), redirige 13 construcciones a una fábrica y
generaliza el conftest. Es un cambio pequeño en superficie y grande en
consecuencias, que es la forma que suele tener un cambio que sale mal.

---

## 2. La fábrica — `ai/llm/`

### LLM-D1 — La fábrica devuelve un `LLMClient` completo, no un cliente crudo

Un proveedor **no es un modelo**: es un modelo *más* su política de reintentos,
*más* su límite de tasa, *más* su tabla de precios, *más* su sello de procedencia.
Si `get_llm()` devolviera un `ChatAnthropic` o un `ChatGoogleGenerativeAI`, el
punto 3 de §1.1 volvería a reproducirse: alguien envolvería el nuevo cliente con
la política del viejo.

Por eso el módulo nuevo es un paquete, no un archivo:

```
backend/ai/llm/
├── __init__.py        # get_llm() — única puerta pública
├── base.py            # LLMClient (re-export), ProviderSpec, RunProvenance
├── factory.py         # resolución proveedor/modelo por rol + política de datos
├── registry.py        # PROVIDERS: dict[str, ProviderSpec]
├── retry.py           # política de reintentos POR PROVEEDOR
├── ratelimit.py       # token bucket asyncio compartido por proceso
├── pricing.py         # estimate_cost(provider, model, in, out)
└── providers/
    ├── anthropic.py   # el actual, movido y registrado
    └── gemini.py      # nuevo (LLM3)
```

`ai/agents/base/structured.py` conserva `LLMClient` (es su protocolo y ya lo
importan 30 módulos) y **`ClaudeLLMClient` sobrevive como alias delgado** sobre el
proveedor `anthropic`, para no romper `tests/orchestrator/test_full_pipeline.py`
ni `tests/agents/base/test_structured_content.py`, que lo instancian con un chat
falso inyectado.

### LLM-D2 — Configuración: global **y** por rol, con precedencia explícita

Las tres opciones y por qué la mixta:

- **Solo global** (`LLM_PROVIDER=gemini`): simple, pero inútil para el caso real.
  Durante el banco de pruebas se querrá casi siempre "todo Gemini **menos** el
  nodo que estoy depurando", o al revés.
- **Solo por agente**: verboso (nueve agentes) y sin default sensato; cada agente
  nuevo obliga a tocar el `.env`.
- **Ambas, con el rol ganando** ← **recomendada.**

```python
# settings.py
LLM_PROVIDER: str = "anthropic"          # default de TODO el sistema
LLM_ROLE_OVERRIDES: dict[str, str] = {}  # {"qa": "gemini", "ef": "anthropic"}
```

Resolución en `get_llm(agent_role)`, de mayor a menor precedencia:

1. `LLM_ROLE_OVERRIDES[agent_role]`
2. `LLM_PROVIDER`
3. `"anthropic"` (fail-safe: **el default nunca es el proveedor de pruebas**)

El `agent_role` es una cadena del enum `AgentType` más `"inventory_doc"` para
INV3. Se pasa **explícitamente** desde cada servicio: `get_llm("qa", ...)`. No se
infiere del stack ni de un contextvar, porque un valor por defecto invisible es
justo lo que hace que un guardarraíl no se dispare.

### LLM-D3 — El modelo se elige por proveedor, no por rol

`ProviderSpec` fija `default_model`; se puede sobreescribir con
`LLM_MODEL_OVERRIDES: dict[str, str]` **por proveedor** (`{"gemini": "gemini-2.5-flash"}`),
no por rol. Motivo: elegir modelo por rol es una decisión de calidad/costo de
producción, y la producción es Anthropic con un solo modelo. Añadir esa matriz
ahora sería configurar para un problema que no tenemos.

**Alternativa descartada:** `LLM_ROLE_OVERRIDES` con valor `"proveedor:modelo"`.
Más expresivo y más fácil de escribir mal; el parseo de una cadena con
dos puntos no pertenece a un `.env`.

---

## 3. Parseo — ¿una ruta o dos?

Hoy hay una sola ruta y es tolerante: `loads_json()`
(`ai/agents/base/structured.py:59-88`) intenta parseo directo → extrae de un
*fence* markdown → recorta entre la primera llave y su cierre; y si nada vale,
`complete_structured` reinyecta el error de validación al prompt (hasta 2
reparaciones) antes de mandar el ítem a cuarentena.

Gemini ofrece `responseSchema` nativo: el modelo emite JSON que **ya cumple** el
esquema, sin fences y sin reparación.

### LLM-D4 — Se mantiene UNA sola ruta de parseo: la tolerante. `responseSchema` NO se usa. **(APROBADA)**

Suena a desaprovechar la mejor característica del proveedor. Es al revés, y es
la decisión más importante de este documento después del guardarraíl:

> **El banco de pruebas deja de serlo en cuanto ejecuta un código distinto del de
> producción.**

Si Gemini valida por esquema nativo y Claude por reparación, entonces:

- un prompt que solo produce JSON válido **gracias** a `responseSchema` pasa
  verde en el banco y falla en producción;
- el loop de reparación —el código que más veces ha roto este repo (la
  cuarentena masiva de EXTRACT, commit `5066e9f`)— **nunca se ejercita** durante
  las pruebas;
- las cuarentenas de la corrida de prueba dejan de ser comparables con las
  reales, y la métrica `chunks_skipped` pierde sentido como señal.

Lo que se gana con la ruta única: cuando el banco de pruebas señala un problema
de parseo, ese problema **existe** en producción. Que es exactamente para lo que
sirve un banco de pruebas.

**Coste aceptado:** más tokens de reparación con Gemini. Irrelevante — el free
tier no cobra tokens, cobra *llamadas* (§6), y la reparación es como mucho una
llamada extra sobre un ítem que en producción también la habría necesitado.

**Alternativa B (descartada, documentada):** activar `responseSchema` tras una
bandera `LLM_NATIVE_JSON=false`. Se descarta incluso como opción apagada: una
bandera que existe se acaba encendiendo, y el día que se encienda nadie recordará
que invalida la comparabilidad. Si en el futuro hace falta, será una decisión
consciente con su propio bloque.

**Consecuencia menor:** `message_text()` sigue tal cual. El cliente Gemini
devuelve `str` y la función lo pasa por su primera rama sin tocarlo. Cero cambios.

---

## 4. Marcado de procedencia

### LLM-D5 — Se guarda en LOS DOS sitios, con papeles distintos

No es redundancia; son dos preguntas distintas y ninguna de las dos ubicaciones
responde la otra:

| Ubicación | Responde | Sin ella |
|---|---|---|
| `agent_jobs.metrics.provenance` (JSONB) | "¿con qué se generó este job?" **sin abrir el artefacto** | El historial y los listados no pueden marcar ni filtrar los runs de prueba. |
| `artifact.metrics.provenance` (contrato) | "¿con qué se generó **este documento**?" | El artefacto **exportado** (PDF, CSV, promoción al inventario INV6) sale del sistema **sin sello**. |

La segunda es la que importa de verdad. Un PDF impreso no lleva la fila de
`agent_jobs` pegada detrás; acaba en una reunión, y allí un plan de pruebas
generado con Gemini es indistinguible de uno bueno.

**Ninguna requiere migración:**

- `agent_jobs.metrics` ya es `JSONVariant` nullable, ya se rellena vía
  `update_job_metrics` (`agent_job_repository.py:145`) y **ya se expone** en los
  seis `GET /jobs/{id}` (`ef.py:91`, `scrum.py:90`, `arquitectura.py:93`,
  `bd.py:96`, `apis.py:100`, `qa.py:129`). Llega al frontend hoy mismo.
- El contrato crece con un modelo nuevo en `ai/agents/ef/schemas/artifact.py`
  (donde ya viven `TokenMetrics`/`SkippedItem`/`Observation`, importados por los
  otros cinco) y un campo **opcional con default** en los seis `*Metrics`
  (`Metrics`, `ScrumMetrics`, `ArchitectureMetrics`, `DatabaseMetrics`,
  `ApiMetrics`, `QaMetrics`). Opcional ⇒ **los artefactos ya persistidos siguen
  validando**, mismo truco que QA10 con `mode`.

```python
class RunProvenance(_Strict):
    """Con qué se generó este artefacto. Sello inmutable, no metadato."""
    provider: str                    # "anthropic" | "gemini"
    model: str                       # id EXACTO del modelo, no la familia
    validation_grade: ValidationGrade  # "produccion" | "banco_de_pruebas"
    generated_at: str                # ISO-8601 UTC
    data_class: DataClass            # "real" | "sintetico"  (§5)
```

### LLM-D6 — El sello es obligatorio y su ausencia se lee como "no confiable"

Si el pipeline no puede determinar proveedor y modelo, **el job falla**. No se
escribe `"desconocido"`, no se omite el campo. Un artefacto sin sello se pinta en
la UI como no verificado, **nunca** como bueno: la ausencia de prueba no es prueba
de ausencia, y el modo de fallo por defecto tiene que ser el conservador.

`validation_grade` es un enum derivado del proveedor, no un campo libre: hoy
`anthropic → produccion`, cualquier otro → `banco_de_pruebas`. Se guarda **derivado
y materializado** a propósito, para que un artefacto exportado siga siendo legible
si mañana cambia el mapa de proveedores.

### LLM-D7 — `estimate_cost` pasa a ser por proveedor

`ai/llm/pricing.py` con una tabla `(provider, model) → (in, out) USD/MTok`, y
precio **0.0 explícito** para los modelos del free tier de Gemini. Los seis
`assemble.py` cambian de `estimate_cost(in, out)` a
`estimate_cost(provenance, in, out)`. `CLAUDE_PRICE_*` se conservan como fuente de
la fila de Anthropic (retrocompatible con el `.env` actual).

Que una corrida de prueba diga "$0.00" **es** el dato correcto, y además hace
visible en el propio dashboard qué parte del gasto histórico fue real.

### LLM-D8 — Frontend: un componente, seis inserciones idénticas, y una marca de agua

El obstáculo real: la barra superior del artefacto está **duplicada en las seis
result views** (p. ej. `qa-result-view.tsx:829-860`). No hay un `<ArtifactHeader>`
compartido que factorizar —y factorizarlo *ahora*, dentro de este bloque, sería
meter un refactor de la UI congelada dentro de un cambio de backend.

Propuesta, en orden de intrusión:

1. **`components/artifact/provenance-badge.tsx`** — un componente nuevo, archivo
   nuevo, que recibe `job.metrics?.provenance` y **no renderiza nada cuando el
   proveedor es Anthropic**. El caso normal no añade ni un píxel ni una
   regresión visual. Cuando no lo es, pinta un badge ámbar con el modelo exacto:
   `banco de pruebas · gemini-2.5-flash-lite`.
2. **Seis inserciones de una línea** (`<ProvenanceBadge metrics={job.metrics} />`)
   junto al badge `v1 · original` de cada vista, más su import. Es el cambio
   mínimo que existe.
3. **Marca de agua en `artifact-print-doc.tsx`** — un solo archivo, y el que de
   verdad cierra el agujero: el badge del header es `print:hidden` por vivir en la
   barra sticky, así que sin este paso **el PDF sale limpio**, que es el peor
   resultado posible.

**Alternativa considerada y descartada:** meterlo dentro de `JobStatusBadge`
(`components/ef/badges.tsx`), ya importado por las seis vistas → cero líneas
nuevas en ellas. Se descarta porque acopla dos conceptos ortogonales (estado del
job vs procedencia del contenido) y porque el badge de estado aparece también en
listados donde no hay `metrics` cargadas.

---

## 5. Guardarraíl de datos sintéticos

Es el requisito duro. Un `.env` mal puesto no puede acabar mandando un DDL de
producción de Urbano a un endpoint de Google.

### LLM-D9 — Clasificación en la ingesta, cumplimiento en la fábrica

Un flag por proyecto no sirve: no existe entidad "proyecto" en este modelo, y
aunque existiera, la clasificación pertenece a **la fuente**, no al contenedor.
El diseño tiene cuatro capas, y cada una falla cerrada.

**Capa 1 — toda fuente nace clasificada, sin default.**
`data_class: Literal["real", "sintetico"]` **obligatorio** en los tres puntos de
entrada: `POST /ef/analyze` (documento y texto), `POST /inventario/.../ddl`
(`inventario.py:186`) y `POST /inventario/.../documento` (`inventario.py:251`).
Sin el campo → **422**. Que sea obligatorio y no `default="real"` es deliberado:
un default correcto entrena a la gente a no pensar, y el día que alguien lo
cambie a `"sintetico"` por comodidad nadie se entera. Se persiste en
`ef_source_docs.doc_metadata` (JSONB, existente) y en `inventory_systems`.

**Capa 2 — la clasificación es pegajosa y monótona.**
Se hereda por `input_job_id` con `resolve_lineage` (`ai/agents/base/lineage.py`,
ya existe). Regla: **si UNA fuente de la cadena es `real`, todo el descendiente es
`real`.** Nunca al revés. Un plan Scrum derivado de un EF real es real aunque
nadie vuelva a subir nada; un plan de pruebas derivado de él, también.

**Capa 3 — el cumplimiento vive en la fábrica, y la firma obliga a pasar por él.**

```python
def get_llm(agent_role: str, *, data_class: DataClass) -> LLMClient:
    ...
```

`data_class` es **keyword-only y sin default**. Omitirlo es un `TypeError` en el
arranque del job —ruidoso, inmediato, imposible de ignorar— y no una fuga
silenciosa. Esta línea es la que convierte el requisito de "difícil de violar por
error" en algo estructural en vez de documental. Si el proveedor resuelto no es
`anthropic` y `data_class != "sintetico"` → `ProviderPolicyError` **antes de la
primera llamada**.

**Capa 4 — el cliente re-verifica en cada llamada.**
El `LLMClient` no-Anthropic guarda el `data_class` con el que se construyó y lo
comprueba en cada `complete_json`. Cubre el caso de un cliente construido bien y
reutilizado después en otro job — improbable hoy, trivial de introducir mañana
con una caché de clientes.

**Capa 5 — el entorno.** `LLM_PROVIDER != "anthropic"` con `APP_ENV=production`
→ la aplicación **no arranca**. Es la misma forma que el guard de ClickUp: la
decisión peligrosa la toma el despliegue, no una petición.

### LLM-D10 — Lo que el guardarraíl NO cubre, y hay que decidir

Honestidad sobre el alcance: el guardarraíl protege las **fuentes**, pero cada
llamada al LLM lleva además contexto de la casa que ninguna fuente clasifica:

- **`ai/knowledge/` glosario logístico** (8 términos: *checkpoint*, *guía*,
  *shipper*, *siniestro*, *papeleta*, *recupero*, *ubigeo*, *DEO*). **Propuesta:
  se envía.** Es vocabulario de dominio, no datos de negocio; su valor competitivo
  es nulo y sin él los prompts no representan el caso real.
- **`ai/knowledge/tech_stack.yaml`.** **Propuesta: NO se envía a un proveedor
  no-Anthropic.** Nombra proveedor cloud, servicios gestionados, versiones y
  decisiones de despliegue **reales** de Urbano (INV0). Mandarlo a Google mientras
  se bloquea el DDL sería un guardarraíl cosmético: se protege la puerta y se deja
  la ventana. Requiere un `tech_stack.sintetico.yaml` de sustitución, cargado por
  el loader cuando el proveedor no es Anthropic.
- **Los prompts del sistema** (`ai/prompts/*/`). Describen el método ISDF, no
  datos de Urbano. **Propuesta: se envían.**

**DECISIÓN DEL USUARIO (aprobada y generalizada):**

- `data_class` se aplica a **TODOS** los archivos de `ai/knowledge/`, no solo al
  glosario y a `tech_stack.yaml`: incluye `db_conventions.yaml`,
  `api_conventions.yaml` y cualquiera que se añada.
- **Sin default**, igual que en las fuentes de ingesta: olvidar clasificar un
  archivo de conocimiento debe ser un **`TypeError`**, no una fuga.
- `tech_stack.sintetico.yaml` tendrá **claves y estructura IDÉNTICAS** a las del
  real; solo cambian los valores. Si cambia la forma, el banco deja de probar el
  mismo ensamblado de prompt que producción — y entonces no es un banco de
  pruebas, es otro sistema.

Se implementa en **LLM2**.

---

## 6. Rate limits del free tier

### 6.1 La aritmética del problema

Una corrida de QA sobre un plan a escala: `TEST_DESIGN` y `EDGE_CASES` son *map*
sobre criterios (`QA_MAP_CONCURRENCY=3`), más `AUTH_CASES`, `DATASET` y
`CRITIQUE`. Con 40 historias × ~4 criterios son **del orden de 100–150 llamadas**
por run, y cada cuarentena añade hasta 2 reparaciones. El EF con un documento
grande es del mismo orden.

Contra un free tier de decenas de RPM y unos cientos de RPD, eso significa: **un
run completo consume una fracción notable de la cuota diaria**, y la restricción
que muerde primero no es la de minuto sino la **diaria**.

### 6.2 LLM-D11 — Tres capas, y ninguna toca el grafo

Todo vive **debajo** del protocolo `LLMClient`. Los nodos siguen viendo
`complete_json(system, user) -> str` y no se enteran de nada. El grafo no se
ensucia porque el grafo nunca supo de esto.

**(a) Limitador proactivo, no reactivo** (`ai/llm/ratelimit.py`). Un token bucket
`asyncio` por proveedor, compartido por proceso, dentro del cliente. Espacia las
llamadas *antes* de mandarlas en vez de esperar el 429. Reintentar tras el rechazo
es la peor estrategia contra una cuota: gasta la petición **y** el tiempo.

**(b) La concurrencia la manda el proveedor, no el agente.** Hoy
`EXTRACT_CONCURRENCY`, `BD_TABLES_CONCURRENCY`, `API_SCHEMAS_CONCURRENCY` y
`QA_MAP_CONCURRENCY` valen 3 y son constantes de agente. Propuesta: un solo
cambio en `run_structured_map` (`structured.py:124`) —
`efectiva = min(concurrency, getattr(llm, "max_concurrency", concurrency))` — y el
cliente Gemini declara `max_concurrency = 1`. **Una línea**, ningún nodo tocado,
y el `getattr` con default mantiene a los mocks funcionando sin cambios.

**(c) Backoff que distingue los dos 429** (`ai/llm/retry.py`). Es el detalle que
separa una espera de una tortura:

| Señal | Significado | Política |
|---|---|---|
| 429 por **RPM** | te has pasado este minuto | reintentar, respetando `RetryInfo`/`retry-after` |
| 429 por **RPD / cuota diaria** | no hay más hasta mañana | **NO reintentar.** Fallar el job de inmediato con un mensaje que lo diga |

Sin esta distinción, agotar la cuota diaria produce un job que tarda veinte
minutos reintentando contra una pared y acaba con un error genérico. Con ella,
falla en dos segundos diciendo exactamente qué pasó.

`_RETRYABLE` deja de ser una tupla de excepciones de `anthropic` y pasa a ser un
método de `ProviderSpec` (`is_retryable(exc) -> bool`) + `wait_hint(exc)`. Para
Anthropic el comportamiento es **idéntico al actual** y así lo fija un test.

---

## 7. Cortafuegos de tests generalizado

### LLM-D12 — Cuatro capas, y solo la última generaliza de verdad

Hoy `conftest.py:44` parchea un símbolo. Añadir un `_boom` por proveedor es
volver a resolver el mismo problema cada vez, y el fallo llega el día que alguien
añade el tercer proveedor sin leer el conftest.

1. **La fábrica** — parchear `ai.llm.factory.get_llm`. Cubre por construcción
   todo proveedor que pase por la puerta correcta.
2. **Los constructores de cada SDK** — cubre a quien se salte la fábrica con un
   import directo.
3. **`get_claude_client`** — se mantiene, por los tests actuales y por
   `inventario.py:282`.
4. **La red** ← *la que de verdad generaliza.* Un guard autouse que hace fallar
   `socket.socket.connect` hacia cualquier host no-local, con el mensaje de la
   REGLA DE PRESUPUESTO. **No hay que actualizarlo nunca**: cubre a un proveedor
   que nadie ha escrito todavía, un `httpx` suelto en un test nuevo, un webhook.
   Es la única capa cuyo alcance no depende de que alguien la mantenga.

La capa 4 tiene un coste que hay que aceptar de frente: puede romper tests que hoy
salen a la red **sin que nadie lo sepa**. Si aparece alguno, es un hallazgo, no un
inconveniente.

`tests/test_budget_guard.py` crece con un test por capa **más uno parametrizado
sobre `PROVIDERS`**: registrar un proveedor sin cortafuegos rompe la suite. Es el
mismo patrón que `sin_inventario_real` y `sin_navegador_real` (QA13).

---

## 8. Modelo de Gemini recomendado

### LLM-D13 — `gemini-2.5-flash-lite`, y la razón no es la calidad

Para este uso la métrica que decide **no es la capacidad del modelo, es la cuota**.
El banco de pruebas ejercita el pipeline —que los nodos encadenen, que el parseo
aguante, que la cuarentena funcione, que el semáforo cierre—, y para eso el techo
de razonamiento es irrelevante. Lo que importa es cuántas llamadas caben en un día.

- **`gemini-2.5-flash-lite`** ← recomendado. El de mayor límite gratuito y menor
  latencia de la familia 2.5. Latencia baja importa más de lo que parece: con
  `max_concurrency = 1` (§6.2b) el run se serializa, y el tiempo total es la suma.
- **`gemini-2.5-flash`** — plan B si Flash-Lite falla demasiado la reparación de
  esquema en los nodos con contratos grandes (`ENDPOINTS`, `TABLES`). Más capaz,
  menos RPM. Se cambia con una variable, sin tocar código.
- **`gemini-2.5-pro`** — descartado: cuota gratuita mínima. Gastaría el día en un
  run.

> ⚠️ **Verificar antes de pinear.** Los ids y las cuotas exactas del free tier los
> cambia Google con frecuencia y mi conocimiento tiene fecha de corte. **El bloque
> LLM3 empieza confirmando id de modelo, RPM y RPD en `ai.google.dev` / la consola
> de AI Studio**, y esos números se escriben en este documento. No se pinea contra
> lo que yo recuerde.

### LLM-D14 — El cliente Gemini se escribe con `httpx`, sin `langchain-google-genai` **(APROBADA)**

> Aprobada por el usuario: **no se instala** `langchain-google-genai`. Cliente
> propio en `httpx` detrás del mismo protocolo `LLMClient`, lo más aburrido
> posible, probado contra un **servidor HTTP falso** y nunca contra Google.

La decisión menos obvia del documento, y hay un riesgo concreto detrás.

`requirements.txt` pinea `langchain==1.3.14`, `langchain-core==1.4.9`,
`langchain-anthropic==1.4.8`, con un comentario que explica por qué: langchain 1.x
cambió la forma de `AIMessage.content` a lista de bloques y **rompió el parseo de
EXTRACT en silencio** (commit `5066e9f`). Instalar `langchain-google-genai`
significa meter en el resolvedor un paquete con su propio rango de
`langchain-core`. Un `pip install` que mueva `langchain-core` **reproduce
exactamente aquel incidente**, y esta vez con menos atención puesta porque el
cambio "es solo añadir un proveedor de pruebas".

Contra eso, lo que necesitamos de una integración LangChain es… nada. El protocolo
`LLMClient` pide **una** función: `complete_json(system, user) -> str`. Eso son
~40 líneas de `httpx` (**ya es dependencia**, se usa en tests) contra
`generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`. Sin
paquete nuevo, sin resolvedor, sin riesgo de arrastrar `langchain-core`, y con el
mapeo de errores 429 (§6.2c) escrito por nosotros en vez de inferido a través de
dos capas de abstracción.

Es el mismo criterio con el que este repo renderiza DDL y OpenAPI en Python en
lugar de añadir tooling: **cuando la superficie que necesitas es diminuta, la
dependencia cuesta más que el código.**

**Alternativa (descartada):** `langchain-google-genai` pinneado con
`pip install --dry-run` verificando que `langchain-core` no se mueve, más un test
candado sobre `langchain_core.__version__`. Funciona, pero paga una dependencia
grande y un riesgo permanente en cada actualización, a cambio de código que no
íbamos a escribir de todos modos.

**Pineado nuevo:** ninguno para Gemini. Solo `httpx` sube de dependencia de tests
a dependencia de aplicación (con su versión fijada).

---

## 9. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | Un artefacto de prueba se toma por bueno | Sello obligatorio (LLM-D5/D6) + badge + **marca de agua en el PDF** |
| R2 | Fuga de datos reales a Google | Cinco capas (§5), `data_class` keyword-only sin default |
| R3 | `tech_stack.yaml` se filtra pese al guardarraíl | LLM-D10 — **decisión pendiente del usuario**, no cerrada aquí |
| R4 | Instalar el proveedor rompe el parseo de Claude | LLM-D14: sin paquete nuevo |
| R5 | Cuota diaria agotada = jobs colgados | LLM-D11c: 429 diario **no** se reintenta |
| R6 | El banco de pruebas valida un camino que producción no recorre | LLM-D4: ruta de parseo única |
| R7 | El socket-guard rompe tests que hoy salen a la red | Es un hallazgo. Se corrige el test, no el guard |
| R8 | Métricas de costo falsas | LLM-D7: precio por proveedor, 0.0 explícito |

---

## 10. Plan de implementación por bloques

Tests mockeados siempre. Commit + push por bloque (REGLA DE RESPALDO).
**Aprobación explícita entre bloques.**

### LLM0 — La fábrica, con un solo proveedor ✅ **IMPLEMENTADO**
`ai/llm/` completo (registro, `ProviderSpec`, retry por proveedor, pricing) con
**únicamente** `anthropic` registrado. Las 13 construcciones redirigidas a
`get_llm(role, data_class=...)`. `ClaudeLLMClient` sobrevive como alias.
*Nada de comportamiento cambia.*
**Tests:** la suite entera sigue verde sin tocarse · el default resuelve a
`anthropic` · la política de reintentos de Anthropic es byte a byte la de hoy
(candado sobre `_RETRYABLE` y `retry_after_seconds`) · `get_llm` sin `data_class`
lanza `TypeError`.

### LLM1 — Cortafuegos generalizado, **antes** del proveedor nuevo
Las cuatro capas de §7. Mismo criterio que QA13 (el guard antes del navegador):
la protección se construye **antes** de que exista lo que hay que proteger, o se
construye tarde.
**Tests:** `test_budget_guard.py` con un test por capa + parametrizado sobre
`PROVIDERS` · un `httpx.get` a un host externo dentro de un test falla con el
mensaje de la REGLA DE PRESUPUESTO.

### LLM2 — Clasificación de datos y política de proveedor
`data_class` obligatorio en los tres puntos de ingesta · herencia monótona por
`resolve_lineage` · `ProviderPolicyError` en la fábrica · guard de `APP_ENV` ·
decisión de LLM-D10 aplicada al loader de `knowledge/`.
Se prueba con un **proveedor falso registrado solo en tests**: el guardarraíl se
demuestra antes de que exista la puerta que protege.
**Tests:** 422 sin `data_class` · cadena con una fuente `real` ⇒ descendiente
`real` · proveedor no-Anthropic + `real` ⇒ `ProviderPolicyError` **antes de la
primera llamada** (verificado con un cliente que explota al invocarse) · arranque
rechazado en `production`.

### LLM3 — Proveedor Gemini
**Pendiente de especificar ANTES de abrir el bloque** (encargo del usuario):

1. **Cuota agotada a mitad de run.** Un run de QA tiene 5 nodos LLM: qué pasa con
   el artefacto parcial, en qué estado queda el job, y si el semáforo
   `ready_for_next_stage` puede leer como bueno un artefacto incompleto. Se
   diseña explícitamente, no se descubre en la primera corrida.
2. **Umbral del loop de reparación.** Qué tasa de reparación significa "modelo
   insuficiente, escalar" y no "bug del pipeline". Sin ese número, un modelo
   débil genera falsos positivos y se van días depurando ruido.
3. **Cuotas reales por familia**, comparadas en la consola. No se asume la 2.5:
   hay familias más nuevas con free tier. Se confirma antes de pinear.

Confirmación previa de id/cuotas en la consola (LLM-D13) · cliente `httpx` ·
token bucket · `max_concurrency=1` · mapeo 429 RPM vs RPD · `pricing` a 0.0.
**Tests:** todo con `httpx.MockTransport` · 429-RPM reintenta y respeta la espera
· 429-RPD **no** reintenta · `run_structured_map` respeta `max_concurrency` ·
respuesta con fence markdown se parsea por la ruta tolerante.

### LLM4 — Procedencia
`RunProvenance` + campo opcional en los seis `*Metrics` + `provenance` en
`agent_jobs.metrics` + `estimate_cost` por proveedor.
**Tests:** round-trip de los **fixtures de artefacto existentes** sin
`provenance` (retrocompatibilidad) · un run sin proveedor determinable falla en
vez de sellar `"desconocido"` · costo 0.0 con Gemini y el actual con Anthropic.

### LLM5 — Frontend
`<ProvenanceBadge>` (nulo con Anthropic) · seis inserciones de una línea · marca
de agua en `artifact-print-doc.tsx`.
**Tests:** el componente no renderiza nada con `provider="anthropic"` · renderiza
modelo y grado con Gemini · **la marca de agua aparece en el doc de impresión**.

### LLM6 — Cierre
Corrida real contra Gemini con `scripts/seed_qa_demo.py` adaptado a fuentes
sintéticas · números reales de cuota consumida por run · `.env.example` ·
actualización de `CLAUDE.md` (§9 REGLA DE PRESUPUESTO y §11 estructura).
**Esta es la única autorización de red del plan, y se pide explícitamente.**
