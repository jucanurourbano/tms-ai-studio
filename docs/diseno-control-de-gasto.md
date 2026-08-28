# Control de gasto — libro mayor de llamadas y tope duro mensual

> **Estado:** **GAS1 IMPLEMENTADO** (libro mayor + freno + H2) y **GAS2
> IMPLEMENTADO** (el endpoint del mes, la vista y la documentación; desviaciones
> declaradas al final de §10). Los añadidos A y B que pidió el usuario al
> aprobar están resueltos en §4.11 (GAS-D11) y §6.bis.
> **Prioridad:** primera. Va **antes** de OLL0…OLL4 y antes de los recortes de
> `EDGE_CASES` / `PRIORITIZE` / `ESTIMATE`, por decisión del usuario y porque —como
> se argumenta en §8— este bloque es el **instrumento con el que se miden** esos
> recortes. Sin él, "110 llamadas → 1" es una afirmación; con él, una medición.

---

## 0. El encargo, y el número que manda

Tres cosas, en una sola unidad de trabajo:

1. **Tope duro mensual fail-closed.** Configurable, arranca en **100 USD/mes**.
2. **Leer el `usage` real** del proveedor en vez de estimar tokens.
3. **Que los jobs `FAILED` registren lo que gastaron.**

Y un objetivo que **no** es el tope: el gasto real debe quedar en **25–30 USD/mes**.
Los 100 son techo de seguridad. Toda cifra de este documento se compara contra
**25–30**, nunca contra 100. Esa distinción tiene una consecuencia de diseño
directa (GAS-D6): un tope que solo se conoce cuando bloquea es un tope que se
descubre la última semana del mes. Hacen falta **tres** números —freno del job,
techo del mes y objetivo del mes— y solo dos de ellos bloquean.

---

## 1. Lo que hay hoy, verificado

### 1.1 El costo se calcula en el ensamblador, a partir de estimaciones

Los seis `assemble.py` hacen, literalmente, lo mismo:

```python
# ai/agents/{ef,scrum,arquitectura,bd,api,qa}/assemble.py
cost=estimate_cost(tokens.get("input", 0), tokens.get("output", 0)),
```

y ese `tokens` viene acumulado por `merge_metrics(state, tokens, skipped)` desde
cada nodo, que lo produce con:

```python
# ai/tools/chunker/chunker.py:14
def estimate_tokens(text: str) -> int:
    """Estimación simple de tokens (~4 caracteres por token)."""
    return max(1, len(text) // 4)
```

Tres consecuencias, y las tres son el problema:

| Consecuencia | Por qué importa |
|---|---|
| Es una **estimación**, no una medición | El proveedor devuelve el `usage` exacto en cada respuesta y lo estamos tirando. |
| Solo existe si el pipeline **llega a `ASSEMBLE`** | Un job que muere en `EXTRACT` reporta 0 habiendo gastado. |
| Es **por job y al final** | Ningún tope puede aplicarse a mitad de corrida, que es cuando se gasta. |

### 1.2 El `usage` real está ahí y se descarta

```python
# ai/llm/providers/anthropic.py:118
async def _call() -> str:
    msg = await client.ainvoke([("system", system), ("user", user)])
    return message_text(msg.content)      # <- msg.usage_metadata se descarta
```

`AIMessage.usage_metadata` (langchain-core 1.4.9) trae `input_tokens`,
`output_tokens`, `input_token_details.{cache_read, cache_creation}` y
`output_token_details.reasoning`. Está a una línea.

### 1.3 El punto de estrangulamiento existe y es estrecho

`complete_json` tiene **tres** apariciones en todo el árbol fuera del propio
cliente:

- `ai/agents/base/structured.py:115` — `complete_structured`, por donde pasan los
  ~30 nodos generativos;
- `ai/agents/ef/critique.py:114` — el `CRITIQUE` del EF, el único que llama suelto;
- `ai/agents/base/structured.py:26` — la definición del protocolo.

Y `get_llm` tiene **16** sitios de llamada. Es decir: **el sitio correcto para
contabilizar y frenar es el cliente**, y está a mano.

### 1.4 El `FAILED` no escribe métricas

```python
# ai/agents/base/pipeline.py
except Exception as exc:
    async with session_scope() as session:
        await AgentJobRepository(session).update_job_status(
            job_id, JobStatus.FAILED, error=str(exc)[:500]
        )
    raise PipelineError(str(exc)) from exc
```

Ni `update_job_metrics`, ni duración. El job fallido no tiene columna donde decir
lo que quemó.

---

## 2. Dos hallazgos que salieron de mirar los datos reales

Consulta directa a `agent_jobs` (28 filas, 2026-07-20 → 2026-08-27):

### H1 — Los jobs `FAILED` reportan cero, y son la cuarta parte del historial

**7 de 28 jobs están en `FAILED`. Seis reportan exactamente `0` tokens y `0.0`
de costo.** El séptimo (`ef`, 2026-07-20) reporta 4 956 / 0 / \$0.0149 solo porque
alcanzó a persistir métricas parciales antes de caer. Es decir: el encargo #3 no
es una precaución hipotética, es un agujero medido de un cuarto del historial.

### H2 — `qa_nodes` nunca fija `started_at`, y la duración de QA es de 56 años

Las dos corridas reales de QA reportan `duration = 1786990494.418` y
`1786995586.803` segundos. La causa:

```python
# ai/agents/qa/assemble.py:178  (idéntico en los otros cinco)
duration = max(0.0, time.time() - state.get("started_at", time.time()))
```

`QaState` **declara** `started_at: float` (`ai/agents/qa/state.py:31`), y los otros
cinco agentes lo fijan en su primer nodo (`nodes.py:31`, `scrum_nodes.py:51`,
`arquitectura_nodes.py:84`, `bd_nodes.py:114`, `api_nodes.py:110`). **`qa_nodes.py`
no lo fija en ninguno.** El `.get(..., time.time())` no salva nada porque la clave
llega presente con `0.0`, así que el default nunca entra: el fallback está escrito
para el caso que no ocurre.

Entra en este bloque —una línea— porque la duración es el otro eje de "qué me
costó esto", y porque las corridas de QA son justamente las que los puntos 2 y 3
del plan van a optimizar: medir el antes y el después con un reloj roto no sirve.

---

## 3. Por qué la estimación subcuenta: el mecanismo, no el factor

Que `metrics` subcuenta por un factor de 2,4–3,1x era folclore del proyecto. El
mecanismo es concreto y son tres causas acumulativas:

1. **El loop de reparación factura hasta 3 veces y se cuenta 1.**
   `complete_structured` llama al modelo `max_repairs + 1 = 3` veces cuando el
   esquema falla (`structured.py:107-118`), y `run_structured_map` suma
   `estimate_tokens(system + user)` **una sola vez** por ítem
   (`structured.py:154`). Un ítem que repara dos veces se cobra tres veces y se
   apunta una.
2. **Los tokens de razonamiento no se ven.** `claude-sonnet-5` devuelve bloques
   `thinking` en cada respuesta —es la razón por la que existe `message_text`— y
   el `output` se estima sobre el **JSON ya volcado**, que los excluye por
   completo. Anthropic los cobra dentro de `output_tokens`.
3. **`len // 4` es tosco sobre JSON en español.** Los signos de puntuación y las
   claves cortas tokenizan peor que 4 caracteres por token.

Las tres desaparecen leyendo el `usage`. Y la primera, además, **se convierte en
una métrica**: con una fila de libro mayor por llamada, la tasa de reparación es
`filas / ítems - 1`, que es exactamente el número que OLL-D1 declara como métrica
principal del experimento local.

---

## 4. Decisiones

### GAS-D1 — El punto de medición es el CLIENTE, no el ensamblador

Toda la contabilidad se muda de los seis `assemble.py` al `complete_json` del
cliente: el único sitio por el que pasa cada token, y el único que ya sabe
proveedor, modelo y tarifa (`ProviderSpec.price_per_mtok`).

Resuelve los tres problemas de §1.1 de una vez: la cifra es real, existe aunque
el job muera en el primer nodo, y hay un punto donde comprobar un tope **antes**
de gastar. El inventario de §1.3 dice que el cambio es estrecho: tres sitios
llaman a `complete_json` y ninguno de los ~30 nodos ve el SDK.

### GAS-D11 — El mensaje del freno dice cuánto llevaba y cuánto pedía lo que lo cruzó

*Añadido por el usuario al aprobar GAS1.* El tope por job de \$5 puede frenar
justo cuando importa: los \$1,6–2,0 del job más caro del historial salen de un EF
de 16–22 RF, y un documento de Procesos normal (10–20 KB → 80–150 historias) va a
ser bastante mayor. Dos requisitos, y el segundo es el que tiene contenido:

1. **Configurable por entorno.** `LLM_JOB_CAP_USD`, como los otros dos. Ya estaba
   en el diseño; se hace explícito porque es el número que va a moverse.
2. **Cuando frene, el mensaje tiene que permitir subirlo A CONCIENCIA.** Un
   "se alcanzó el tope" no distingue frenar por poco de frenar por mucho, ni dice
   cuánto habría hecho falta. El mensaje lleva las cuatro cifras:

```
Freno de gasto: se alcanzó el tope del job (LLM_JOB_CAP_USD = 5,0000 USD).
El job 01J… lleva gastados 4,5000 USD y la llamada que lo cruzó puede costar
hasta 0,4229 USD, más un margen reservado de 1,2686 USD (3 llamadas en vuelo
x 0,4229). Si el gasto es esperado, sube LLM_JOB_CAP_USD en el entorno.
```

Se dice **"puede costar hasta"** y no "costó": antes de hacer la llamada nadie
sabe lo que va a costar, y lo que el freno reserva es el techo declarado de
GAS-D5. Decir un número exacto ahí sería inventarlo.

El **orden de los dos frenos también es del mensaje**: primero el del job,
después el del mes. Un job desbocado anunciado como "se acabó el mes" mandaría a
revisar el sitio equivocado.


### GAS-D2 — El protocolo público NO cambia; se añade uno interno

`LLMClient.complete_json(system, user) -> str` se queda **exactamente igual**: lo
importan los ~30 nodos generativos y todos los mocks de la suite.

Debajo:

```python
# ai/llm/metering.py
@dataclass(frozen=True)
class Usage:
    input_tokens: int          # TOTAL, caché incluida (ver GAS-D3)
    output_tokens: int
    cache_read: int = 0
    cache_write: int = 0
    reasoning: int = 0         # SUBCONJUNTO de output_tokens, informativo

@dataclass(frozen=True)
class Completion:
    text: str
    usage: Optional[Usage]     # None = el proveedor no lo reportó (GAS-D4)

class UsageReportingClient(Protocol):        # protocolo INTERNO
    async def complete(self, *, system: str, user: str) -> Completion: ...

class MeteredLLMClient:                      # lo que ve el mundo
    """Comprueba el tope, delega, y anota la fila. En ese orden."""
    async def complete_json(self, *, system: str, user: str) -> str: ...
```

El envoltorio lo aplica **`get_llm`**, no cada proveedor: mismo patrón que la
capa 1 del cortafuegos de tests (`_amordazar` sobre `build_client`), y por la
misma razón —registrar un proveedor nuevo hereda la medición sin que nadie se
acuerde—. Con **candado parametrizado sobre `PROVIDERS`**: si un `ProviderSpec`
devuelve un cliente que no sale medido, la suite rompe.

**Alternativa descartada: `client.last_usage`.** El cliente es **compartido** por
los 3 workers concurrentes de `EXTRACT` (`get_llm` se llama una vez por job y se
inyecta por `config`), así que un atributo mutable atribuiría el `usage` de una
llamada a otra. No es una imprecisión, es una mentira con forma de dato.

### GAS-D3 — La aritmética del `usage` real: los tokens de caché ya vienen sumados

Verificado en `langchain_anthropic/chat_models.py:2384-2392`:

```
input_tokens = base + cache_read + cache_creation
```

(el propio comentario del paquete lo dice: *"Anthropic's `input_tokens` excludes
cached tokens, so we manually add them back"*). Aplicar la tarifa de entrada a
ese total cobra **10x de más** las lecturas de caché (valen 0,1x) y **20% de
menos** las escrituras (valen 1,25x). Luego:

```
base  = input_tokens - cache_read - cache_write
costo = base*tin + cache_read*tin*0.10 + cache_write*tin*1.25 + output*tout
```

Hoy el caching **no está activado** en ninguna parte del árbol, así que los cuatro
contadores de caché vienen en 0 y la fórmula se reduce byte a byte a la actual.
Se escribe igual, y se guardan los cuatro contadores, porque el día que alguien
active `cache_control` para abaratar el `CRITIQUE` sin techo, el tope no puede
empezar a mentir en silencio.

`output_token_details.reasoning` es un **subconjunto** de `output_tokens`, ya
cobrado: se guarda como información y **nunca se suma**. Es el número que explica
la causa 2 de §3.

**Guarda:** si `base < 0` (no debería), se cae a `base = input_tokens` y la fila
se marca. Se yerra hacia **cobrar de más**, nunca de menos.

### GAS-D4 — `usage` ausente no es `usage` cero

Tercera vez que el proyecto se topa con la misma forma: *`sqlglot` degradando a
`Command`* (INV2), *redactar en vez de rechazar* (A7), *Ollama truncando en
silencio* (§5.6). **La ausencia de un dato no es el valor 0 de ese dato.**

Si la respuesta no trae `usage_metadata`, anotar 0 dejaría el tope **ciego**: el
peor resultado posible, porque el sistema seguiría gastando creyendo que no gasta.
La fila se anota con la **estimación** y `usage_source = "estimado"`, y el total
del mes informa **qué fracción es estimada**. Un mes con 40% de gasto estimado es
un mes cuyo tope no es de fiar, y eso tiene que verse.

**Candados:** un `ChatAnthropic` falso que devuelve un `AIMessage` realista
produce `usage_source = "real"`; uno sin `usage_metadata` produce una fila, un
`warning` en el log y **jamás** un cero.

### GAS-D5 — El tope se comprueba con MARGEN, no al filo

Con `EXTRACT_CONCURRENCY = 3` hay tres llamadas en vuelo que leen "por debajo del
tope" y lo cruzan juntas. En vez de un protocolo de reserva (dos escrituras por
llamada, y una fuga cada vez que un proceso muere entre ellas), se niega cuando:

```
gastado + margen > tope
margen = llamadas_en_vuelo × costo_máximo_de_una_llamada
```

Así el tope duro **no se cruza nunca**; el precio es un pedazo de techo
inutilizable, y se declara en vez de descubrirse.

La aritmética, con `CLAUDE_MAX_TOKENS = 8192` y \$3/\$15 por MTok:

```
costo_máximo_llamada = 100 000/1e6 × 3  +  8 192/1e6 × 15  =  0,300 + 0,123  =  0,423 USD
margen del MES   (8 llamadas en vuelo: dos jobs a concurrencia 3, más holgura) ≈ 3,4 USD  → 3,4% de 100
margen del JOB   (3 llamadas: la concurrencia dentro de un job)                ≈ 1,3 USD
```

Los **100 000 tokens de entrada son un supuesto declarado**, no un límite
aplicado: hoy no existe ninguno, porque **nada acota `CRITIQUE`** (§5.6 de
`CLAUDE.md`; `critique.py:110` recibe el modelo consolidado entero). Ese techo lo
pone el canario de truncamiento de OLL2, no este bloque. Aquí solo se usa para
dimensionar el margen, y `LLM_MAX_INPUT_TOKENS_ASSUMED` es configurable
precisamente para que el supuesto sea auditable.

### GAS-D6 — Tres números, y el que de verdad protege es el del JOB

Datos reales (`agent_jobs`, consultado 2026-08-28, 28 filas):

| | Estimado | Real (×2,4–3,1) |
|---|---|---|
| Job más caro de la historia (`scrum`, 107 181 in / 22 110 out) | \$0,653 | ~\$1,6–2,0 |
| Corrida EF real típica (5 061 / 6 133) | \$0,107 | ~\$0,26–0,33 |
| Corrida QA real (53 930 / 4 389) | \$0,228 | ~\$0,55–0,71 |
| **Todo el historial del proyecto, sumado** | **~\$1,8** | **~\$4,5–5,6** |

Lo que esa última fila dice es incómodo y útil: **el objetivo de 25–30 USD/mes es
entre 5 y 10 veces todo lo que el proyecto ha gastado en su vida.** El tope no
está protegiendo de lo que se gasta hoy; está protegiendo del volumen que llega
cuando la cadena se valide y se use con requerimientos reales. Y un techo mensual
de 100 no impide que **un solo job** se coma el mes en una tarde: el `CRITIQUE`
sin acotar y las 110 llamadas de `EDGE_CASES` tienen exactamente esa forma.

- **`LLM_JOB_CAP_USD = 5.0`** — freno del job. ~2,5x el job más caro jamás
  observado. Cruzarlo hace fallar **ese** job con un motivo legible, no el mes.
  Es el tope que más veces va a salvar el objetivo de 25–30.
- **`LLM_MONTHLY_CAP_USD = 100.0`** — el techo que pidió el usuario. Fail-closed.
- **`LLM_MONTHLY_TARGET_USD = 30.0`** — **no bloquea**. Es el número que se
  reporta (§7.2) para que 25–30 sea gobernable y no una aspiración. Un objetivo
  que solo se manifiesta cuando el freno actúa se cumple por accidente.

Los dos topes se **calibran con los datos del libro mayor** después de las
primeras semanas, **no ahora**. Mismo criterio con el que el usuario prohibió
afinar el umbral de `TEST_DESIGN` contra los 110 criterios que existen: no se
calibra contra los datos que uno tiene a mano.

### GAS-D7 — Fail-closed significa que un libro mayor ilegible NIEGA la llamada

Es lo más fácil de dejar al revés. Si el libro mayor no se puede leer —base caída,
sumidero sin instalar— la llamada **se rechaza**. Consecuencia declarada y
buscada: **sin libro mayor no hay gasto**, así que un despliegue mal configurado
deja de funcionar en vez de gastar sin medir.

El sumidero es un asiento explícito:

```python
# ai/llm/budget.py
def current_sink() -> SpendSink: ...        # default: NegarTodo("sin libro mayor")
def install_sink(sink: SpendSink) -> None:  # lo instala el lifespan de main.py
```

`ai/llm/` **no importa `app.repositories`**: la implementación con base de datos
vive en `app/` y se instala al arrancar. Así el paquete de proveedores no crece
una dependencia hacia la capa de persistencia, y la suite instala un sumidero
falso sin tocar nada más.

Y el freno vive **dentro de `MeteredLLMClient.complete_json`, antes de delegar** —
no en el servicio ni en el nodo. Un freno en el servicio es un freno que un nodo
se salta; ya nos pasó con `app/api/v1/inventario.py`, que se saltaba incluso el
runner (§1 del diseño multiproveedor).

**REGLA R1:** `current_sink` se llama por su módulo (`_budget.current_sink()`),
nunca importado por nombre, y entra en el registro de
`tests/test_costuras_parcheables.py`.

### GAS-D8 — El mes es de calendario en `America/Lima`, y está escrito

No la zona local del servidor: un contenedor en UTC rueda de mes a las 19:00 de
Lima y parte el gasto de un día entre dos meses. `LLM_BUDGET_TZ` con **un único
lector** desde `settings`.

**Residual declarado:** el periodo de facturación de Anthropic no es
necesariamente el mes calendario, así que el mes del libro mayor y el mes de la
factura pueden diferir en hasta un día de gasto. Quien concilie contra la consola
necesita saberlo, así que se escribe aquí y no se descubre allí.

### GAS-D9 — El artefacto conserva su estimación; la verdad vive en el job

La cifra real aterriza en **`job.metrics.real`**, y se escribe en **un solo
sitio**: `AgentJobRepository.update_job_metrics`, que ya recibe el `job_id` y por
tanto puede consultar el libro mayor y fundir el bloque. Un cambio, y lo heredan
los seis agentes **y la ruta de `FAILED`**.

```jsonc
"metrics": {
  "tokens": {"input": 5061, "output": 6133},   // la estimación del ensamblador
  "cost": 0.107178,                            // idem, sin tocar
  "real": {                                    // NUEVO: el libro mayor
    "input_tokens": 14210, "output_tokens": 15980,
    "cost_usd": "0.282330", "calls": 37,
    "usage_source": "real", "estimated_calls": 0,
    "ratio_sobre_estimado": 2.63
  }
}
```

Ese `ratio_sobre_estimado` convierte el 2,4–3,1x de folclore del proyecto en una
columna medida por corrida.

**Lo que este bloque NO hace, y por qué:** `artifact.metrics.cost` sigue siendo la
estimación del ensamblador, y por tanto el **PDF exportado sigue llevando un
número bajo**. Hacerlo verdadero exige que los ~20 nodos dejen de llamar a
`estimate_tokens` y lean el `usage` de cada llamada —una extensión del protocolo
en 20 ficheros—, y eso no es un día. **Dueño escrito: LLM4**, que ya toca los seis
`assemble.py` para volver `estimate_cost` per-proveedor (LLM-D7) y que además
debe **reutilizar la tarifa de `MeteredLLMClient` en vez de escribir una segunda**.
Es una deuda con fecha y dueño, no una mentira silenciosa.

> **Decisión que pido aprobar explícitamente.** La alternativa es que los seis
> nodos `PERSIST` sobreescriban `metrics.tokens`/`cost` del artefacto con la
> verdad del libro mayor justo antes de persistir (~20 líneas, 6 ficheros; todas
> las llamadas al LLM ya ocurrieron cuando corre `PERSIST`). Se gana un artefacto
> honesto hoy; se paga completar la salida del agente **fuera** del agente y
> retocar los seis fixtures de artefacto. **Recomiendo la vía de arriba**
> (artefacto intacto, verdad en el job, deuda a LLM4): este bloque es un freno, y
> meterle dentro un cambio en el contrato de los seis agentes es cómo un bloque de
> un día se convierte en tres.

### GAS-D10 — La atribución por nodo sale gratis de `run_structured_map`

Para decir "`EDGE_CASES` costaba X y ahora cuesta Y" la fila necesita el nodo, y
el cliente solo conoce el `agent_role`. La salida está ya escrita: **`run_structured_map`
recibe `stage` como parámetro** (`structured.py:145`, hoy solo para el motivo de
cuarentena). Un `llm.for_stage(stage)` dentro de esa función —un reenvoltorio
barato que arrastra la etiqueta— cubre **todos los nodos de tipo *map* del
sistema con una sola edición**.

`for_stage` es opcional y se pide con `getattr`: los mocks de la suite no lo
tienen y no deben tenerlo. Es una **etiqueta**, no dinero, así que tolerar su
ausencia no es fail-open. Los nodos que no son *map* (el `CRITIQUE` del EF, los
pases sueltos de BD/API) quedan con `stage = NULL` y se atribuyen al agente: el
hueco **se ve** en la consulta, en vez de adivinarse.

---

## 5. El libro mayor

Migración **`0011_libro_mayor_de_gasto`**. El `0011` estaba nominalmente
apartado para QC2, que quedó **aplazado** (`docs/diseno-qa-modo-c.md` §0.bis); si
QC2 se reanuda, toma el `0012`.

```sql
CREATE TABLE llm_spend (
    id                 VARCHAR(26)  PRIMARY KEY,              -- ULID (IdMixin)
    created_at         TIMESTAMPTZ  NOT NULL,
    updated_at         TIMESTAMPTZ  NOT NULL,
    job_id             VARCHAR(26)  REFERENCES agent_jobs(id) ON DELETE SET NULL,
    agent_role         VARCHAR(32)  NOT NULL,   -- "ef".."qa" | "inventory_doc"
    stage              VARCHAR(32),             -- nodo, cuando se conoce (GAS-D10)
    provider           VARCHAR(32)  NOT NULL,
    model              VARCHAR(64)  NOT NULL,
    usage_source       VARCHAR(16)  NOT NULL,   -- "real" | "estimado"  (GAS-D4)
    input_tokens       INTEGER      NOT NULL,   -- TOTAL, caché incluida (GAS-D3)
    output_tokens      INTEGER      NOT NULL,
    cache_read_tokens  INTEGER      NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER      NOT NULL DEFAULT 0,
    reasoning_tokens   INTEGER      NOT NULL DEFAULT 0,   -- subconjunto de output
    cost_usd           NUMERIC(12,6) NOT NULL,
    duration_ms        INTEGER
);
CREATE INDEX ix_llm_spend_created_at   ON llm_spend (created_at);
CREATE INDEX ix_llm_spend_job_id       ON llm_spend (job_id);
CREATE INDEX ix_llm_spend_agent_stage  ON llm_spend (agent_role, stage);
```

Detalles que no son cosméticos:

- **`cost_usd` es `NUMERIC(12,6)`, no `float`.** Es dinero que se suma miles de
  veces contra un umbral; el error de coma flotante acumulado no tiene por qué
  aparecer en la decisión de bloquear.
- **`job_id` es nullable con `ON DELETE SET NULL`**, mismo criterio que
  `agent_jobs.created_by`: el total del mes **no puede cambiar** porque alguien
  borró un job, y la fila conserva su `agent_role`. La ingesta de documentos del
  inventario (`inventario.py:290`) no tiene job y pasa `job_id=None` **de forma
  explícita** — porque si no contara, el mes tendría una fuga.
- **No hay columnas `attempt` ni `outcome`.** Son derivables: una fila por llamada
  significa que la tasa de reparación es `filas / ítems − 1`, y ése es justo el
  número que OLL-D1 declara métrica principal. Una columna que se puede contar no
  se guarda.
- **No hay columna `data_residency`.** Se deriva de `provider` vía el registro, y
  OLL1 la introduce como propiedad del `ProviderSpec` (§5.6). Guardarla aquí sería
  desnormalizar una decisión que aún no existe.

---

## 6. El freno, en orden de ejecución

```
MeteredLLMClient.complete_json(system, user)
  │
  1. sumidero = _budget.current_sink()            # sin sumidero ⇒ NIEGA (GAS-D7)
  2. gastado_mes, gastado_job = await sumidero.totales(mes(tz), job_id)
  3. si gastado_job + margen_job  > LLM_JOB_CAP_USD      → BudgetExceededError(job)
     si gastado_mes + margen_mes  > LLM_MONTHLY_CAP_USD  → BudgetExceededError(mes)
  4. completion = await interno.complete(system=..., user=...)     # el gasto
  5. usage = completion.usage o estimación marcada (GAS-D4)
  6. await sumidero.anotar(fila)                  # se anota SIEMPRE, gaste o falle
  7. return completion.text
```

Una consulta por llamada (paso 2). Una llamada al modelo tarda entre 5 y 60
segundos; una consulta indexada de 1 ms es gratis, y elegir eso antes que un
acumulador en memoria evita el error real: el EF construye **dos** clientes por
job (`llm` y `critique_llm`, `ef_service.py:69,74`), así que un contador dentro
del cliente subcontaría el job justamente en el agente cuyo `CRITIQUE` no tiene
techo.

**El `BudgetExceededError` es un error de dominio, no una excepción cualquiera.**
Sube por `run_agent_pipeline`, que lo traduce a `FAILED` con un `error` legible
—"tope del job (5,00 USD) alcanzado en `EDGE_CASES`; gastado 5,02"— y, gracias a
GAS-D9, **con las métricas reales ya escritas**. El job fallido dice cuánto
costó fallar. Ese era el encargo #3.

**Preflight en el servicio.** Antes de encolar el `BackgroundTask`, los seis
servicios comprueban el techo del mes y devuelven **409** (`ConflictError`, ya
existe en `app/errors.py`) con el número. Es redundante con el paso 3 —a
propósito—: sin él, el usuario ve un job que arranca, corre y muere; con él, ve un
mensaje antes de esperar. El que **garantiza** es el paso 3; el preflight es
cortesía, y se declara como tal.

---

## 6.bis. Qué pasa A MITAD DE RUN (el escenario más probable de todos)

*Añadido por el usuario al aprobar GAS1, y tiene razón en que faltaba: el tope no
se cruza al empezar un job, se cruza en la llamada 40 de 110.*

La pregunta era cuádruple: **¿qué queda en la base? ¿artefacto parcial? ¿en qué
estado queda el job? ¿puede `ready_for_next_stage` leer mal un artefacto
incompleto?**

### 6.bis.1 El reparto, y por qué es estructural

| Dónde | Qué queda | Por qué |
|---|---|---|
| `llm_spend` | **Las 39 filas** de las llamadas que sí ocurrieron | Se escriben una a una, antes del fallo. El gasto está completo aunque la corrida no lo esté. |
| `agent_artifacts` | **Nada** | `save_artifact` se llama **solo** desde `persist`, y `persist` lo invoca **solo** el nodo `PERSIST`, el último del grafo. No hay artefacto parcial porque no existe ninguna escritura intermedia que pudiera dejarlo. |
| `agent_jobs` | `status=FAILED`, `error` con el mensaje de GAS-D11, `metrics.duration` y `metrics.real` | La rama `except` del runner escribe métricas **antes** de marcar el estado. |

**El semáforo del siguiente agente no puede leer mal nada, y no porque se
compruebe: porque no hay nada que leer.** El gate consulta el artefacto del job de
entrada; un job `FAILED` no tiene fila en `agent_artifacts`, así que la pregunta
"¿está listo?" no encuentra un artefacto incompleto que interpretar — encuentra
ausencia. Es una garantía por construcción, no una comprobación que alguien pueda
olvidarse de escribir.

### 6.bis.2 La condición que de verdad hay que proteger

Todo lo anterior se sostiene sobre **una** propiedad: que un `BudgetExceededError`
**no se pueda confundir con un ítem en cuarentena**.

La cuarentena de `run_structured_map` existe para "el modelo contestó mal": el
ítem se marca, se deja una `Observation` y el job **sigue**. Si el freno cayera
ahí, los 70 ítems restantes quedarían "en cuarentena", el pipeline llegaría a
`ASSEMBLE` y produciría **un artefacto que parece entero y le faltan 70 casos**,
con su cobertura recalculada tan tranquila y el semáforo opinando sobre él. Es la
forma exacta del error que este proyecto no puede cometer —el mismo de `sqlglot`
degradando a `Command`, el mismo de un enum a medias— y aquí llegaría hasta el
artefacto.

Hoy se cumple: `complete_structured` captura solo `JSONDecodeError`/`ValidationError`,
y el `_llm_pass` del `CRITIQUE` del EF también. Pero *se cumple*, no *está
garantizado*: bastaría un `except Exception` en el camino del LLM. Por eso hay
tres tests que lo fijan uno por uno (`tests/llm/test_gasto_a_mitad_de_corrida.py`),
y no uno solo de extremo a extremo.

### 6.bis.3 Las llamadas hermanas que estaban en vuelo

`asyncio.gather` propaga la primera excepción **sin cancelar** a las demás. Las 2
llamadas que ya estaban en vuelo terminan, y **sus filas se anotan**, que es lo
correcto: ese dinero se gastó. No es una fuga del tope — es exactamente lo que el
margen de GAS-D5 reserva, y el motivo de que exista.

**Residual declarado:** si una hermana en vuelo es *denegada* por el freno en vez
de completarse, su excepción no la recoge nadie y `asyncio` registra un
`Task exception was never retrieved`. Es ruido en el log, no gasto ni pérdida de
datos, y no se arregla aquí: cancelar las hermanas cambiaría la semántica de la
cuarentena para todos los agentes, que es un cambio mucho mayor que el problema.

### 6.bis.4 Por qué `FAILED` y no un estado nuevo

Se consideró un `STOPPED_BY_BUDGET`. Se descarta: el job **no produjo nada
utilizable**, que es exactamente lo que `FAILED` significa en el historial y en
los cuatro grupos del filtro. Un estado propio obligaría a migrar el tipo enum de
Postgres y a repartirlo por los grupos del frontend para distinguir algo que el
`error` ya distingue —y que ahora, además, viene con las cifras de GAS-D11—.

### 6.bis.5 Reintentar es barato, y eso ya estaba

El checkpointer indexa por `thread_id = job_id`, así que **relanzar tras subir el
tope no re-factura las fases completadas**: la corrida retoma en el nodo donde la
pararon. Es la propiedad que convierte "el freno cortó a mitad" de un desastre en
una interrupción. No es nueva, pero es la que hace que este diseño sea aceptable.


---

## 7. Lo que se ve

### 7.1 `job.metrics.real` — vía `update_job_metrics`, un solo sitio (GAS-D9)

Ya se expone en los seis `GET /jobs/{id}` sin tocar nada
(`ef.py:91`, `scrum.py:90`, `arquitectura.py:93`, `bd.py:96`, `apis.py:100`,
`qa.py:129`). Llega al frontend el mismo día.

### 7.2 `GET /api/v1/gasto/mensual` — porque un tope que no se mira se conoce bloqueando

```jsonc
{ "success": true, "data": {
  "month": "2026-08", "timezone": "America/Lima",
  "spent_usd": "22.41", "target_usd": "30.00", "cap_usd": "100.00",
  "target_pct": 74.7, "cap_pct": 22.4,
  "calls": 1843, "estimated_calls": 0, "estimated_fraction": 0.0,
  "by_agent":   [{"agent_role": "qa", "cost_usd": "11.02", "calls": 1210}, …],
  "by_stage":   [{"agent_role": "qa", "stage": "EDGE_CASES", "cost_usd": "8.90", "calls": 1101}, …],
  "top_jobs":   [{"job_id": "…", "agent_type": "qa", "cost_usd": "1.94"}, …]
}}
```

`by_stage` es la fila que va a demostrar los puntos 2 y 3 del plan. `estimated_fraction`
es la honestidad de GAS-D4: si no es 0, el resto de la respuesta es aproximado y
lo dice.

**Permiso: `config` READ** (hoy, `admin`). Es dato de costo. Un `analista`
bloqueado no necesita el desglose de la organización: necesita saber por qué se le
negó su job, y eso va en el mensaje del 409 y en el `error` del `FAILED`.

### 7.3 Configuración nueva (`settings` + `.env.example`)

```python
LLM_MONTHLY_CAP_USD: float = 100.0        # techo duro, fail-closed
LLM_MONTHLY_TARGET_USD: float = 30.0      # objetivo: NO bloquea, se reporta
LLM_JOB_CAP_USD: float = 5.0             # freno del job (GAS-D6)
LLM_BUDGET_TZ: str = "America/Lima"       # lector único (GAS-D8)
LLM_MAX_INPUT_TOKENS_ASSUMED: int = 100_000   # solo para el margen (GAS-D5)
LLM_BUDGET_HEADROOM_CALLS: int = 8        # llamadas en vuelo del margen mensual
LLM_CACHE_READ_FACTOR: float = 0.10       # tarifas de caché (GAS-D3)
LLM_CACHE_WRITE_FACTOR: float = 1.25
```

**No hay `LLM_BUDGET_ENABLED`.** Una bandera para apagar el freno es la bandera
que alguien deja apagada; lo que se configura es el *número*, y quien quiera
trabajar sin freno pone un techo alto y queda escrito en el `.env`.

---

## 8. Cómo encaja con lo que ya estaba planificado

| Plan | Relación |
|---|---|
| **Puntos 2 y 3 del plan** (`EDGE_CASES` 110→1, `PRIORITIZE`+`ESTIMATE` 62→2) | `by_stage` **es** el antes/después que se pidió. Construir esto primero no retrasa esos bloques: los vuelve medibles en vez de argumentables. |
| **OLL0…OLL4** (proveedor local) | El libro mayor es su **instrumento**: tokens y duración por llamada dan los tok/s, y `filas / ítems − 1` da la **tasa de reparación**, que OLL-D1 declara métrica principal del experimento. El A/B de OLL-D5 se consulta, no se reconstruye. |
| **LLM2** (`data_class` → `data_residency`) | **Sin colisión.** El libro mayor guarda `provider`; la residencia se deriva del registro (GAS-D10, §5). |
| **LLM4** (procedencia, `estimate_cost` per-proveedor, muerte del shim) | **Colisión declarada y asignada.** LLM4 hereda la deuda de GAS-D9 (el artefacto) y debe **reutilizar** la tarifa de `MeteredLLMClient` en lugar de escribir una segunda. |
| **`CRITIQUE` sin techo** (§5.6) | Este bloque **lo mide y lo frena** (el freno del job es lo que impide que se coma el mes), pero **no lo acota**. Acotarlo es el canario de OLL2. Se dice para que no se lea como resuelto. |

---

## 9. Riesgos y residuales declarados

1. **El margen de GAS-D5 inutiliza ~3,4% del techo mensual y ~25% del freno del
   job.** Es el precio de no cruzar el tope nunca. Ambos márgenes son
   configurables y la aritmética está escrita para poder discutirla.
2. **El mes del libro mayor puede no ser el mes de la factura** (GAS-D8). Hasta un
   día de gasto de diferencia al conciliar contra la consola.
3. **El `usage` estimado contamina el total.** Se acota informándolo
   (`estimated_fraction`), no ocultándolo. Si aparece por encima de 0 con
   Anthropic, es un bug del cliente y hay candado que lo caza.
4. **Una llamada que muere por red no deja fila** — no hubo tokens facturados, así
   que es correcto; pero significa que el libro mayor cuenta *gasto*, no *intentos*.
   Los intentos se ven en el log.
5. **El PDF exportado sigue llevando la estimación** hasta LLM4 (GAS-D9). Con
   fecha y dueño.
6. **Los topes iniciales (5 / 100 / 30) están dimensionados sobre 28 filas**, de
   las cuales solo ~8 son corridas reales. Se recalibran con datos, no antes
   (GAS-D6).

---

## 10. Plan de implementación por bloques

Tests mockeados siempre. Commit + push por bloque (REGLA DE RESPALDO).
**Aprobación explícita entre bloques** (REGLA R2).

### GAS1 — El libro mayor y el freno, juntos ✅ IMPLEMENTADO

Van en el mismo bloque a propósito. El principio del proyecto es *el guard antes
de lo que protege* (QC3 antes del navegador, LLM1 antes del proveedor), pero aquí
**lo que hay que proteger ya existe** y el freno no puede construirse sin el libro
mayor que le dice cuánto se lleva gastado. Partirlo en dos deja una ventana en la
que hay instrumento y no hay freno, que es lo contrario del encargo.

Contenido:

- `app/models/spend.py` + migración `0011_libro_mayor_de_gasto` (§5).
- `app/repositories/llm_spend_repository.py` — `anotar()` y `totales(mes, job_id)`
  en una consulta.
- `ai/llm/metering.py` — `Usage`, `Completion`, `UsageReportingClient`,
  `MeteredLLMClient` (GAS-D2), aritmética de caché (GAS-D3), caída a estimación
  marcada (GAS-D4).
- `ai/llm/budget.py` — `SpendSink`, `current_sink`/`install_sink` con default que
  **niega** (GAS-D7), cálculo del mes en `LLM_BUDGET_TZ` (GAS-D8), márgenes
  (GAS-D5), `BudgetExceededError`.
- `ai/llm/providers/anthropic.py` — `complete()` devolviendo `Completion` con el
  `usage_metadata`; `complete_json` pasa a ser la cara del envoltorio.
- `ai/llm/factory.py` — `get_llm(rol, *, data_class, job_id)`; `job_id`
  **keyword-only y sin default** (mismo criterio que `data_class`: olvidarlo es un
  `TypeError` ruidoso). Los 16 sitios lo pasan; `inventario.py` pasa `None`
  **explícito**.
- `ai/agents/base/structured.py` — `run_structured_map` etiqueta con `for_stage`
  (GAS-D10). El protocolo público **no se toca**.
- `ai/agents/base/pipeline.py` — la rama `except` escribe métricas y duración
  antes de marcar `FAILED` (§1.4).
- Los seis servicios — preflight 409 (§6).
- `ai/orchestrator/qa_nodes.py` — **H2**: `"started_at": time.time()` en
  `node_load_sources`, con su test.
- `tests/firewall.py` — candado de que el sumidero por defecto niega, y de que
  ningún test escribe filas de gasto reales.
- `tests/test_costuras_parcheables.py` — alta de `current_sink` (REGLA R1).

**Tests:**
- Parametrizado sobre `PROVIDERS`: **todo** proveedor registrado sale de `get_llm`
  envuelto en `MeteredLLMClient` (candado de GAS-D2).
- `AIMessage` realista ⇒ `usage_source="real"` y los cinco contadores en la fila.
- `AIMessage` **sin** `usage_metadata` ⇒ fila con `usage_source="estimado"`,
  `warning` en el log, **nunca** un cero (GAS-D4). Se prueba **quitando** el
  `usage`, no asumiéndolo.
- Aritmética de caché: con `cache_read`/`cache_write` en 0 el costo es **byte a
  byte** el actual; con valores no nulos, la tarifa correcta y `reasoning` **no
  sumado** (GAS-D3). `base < 0` cae al lado de cobrar de más.
- Tope del mes y tope del job: la llamada se niega **antes** de tocar el cliente
  interno —verificado con un interno que explota al invocarse, mismo truco que
  LLM2— y el margen se respeta.
- Sumidero ausente ⇒ la llamada se niega (GAS-D7). **Se ve fallar**: con el
  sumidero instalado, la misma llamada pasa.
- `BudgetExceededError` en mitad de un grafo ⇒ job `FAILED` **con** `metrics.real`
  escritas y el motivo en `error` (encargo #3, y H1 deja de reproducirse).
- Concurrencia: 3 workers de `run_structured_map` producen 3 filas con el `stage`
  correcto y ninguna atribución cruzada (el caso que mata a `last_usage`).
- Tasa de reparación: un ítem que repara dos veces deja **3** filas.
- `job_id=None` (ingesta del inventario) anota fila y **cuenta** para el mes.
- El mes se corta en `America/Lima`: una fila a las 19:30 del último día del mes
  en UTC pertenece al mes de Lima que le toca (GAS-D8).
- **H2**: la duración de un job QA es un número de segundos plausible.

#### Lo que GAS1 hizo distinto de lo escrito arriba (desviaciones declaradas)

1. **Diez ajustes de configuración, no ocho.** Se añaden
   `LLM_MAX_OUTPUT_TOKENS_ASSUMED` —el diseño usaba `CLAUDE_MAX_TOKENS`, que es
   específico de Anthropic y no tiene por qué asomar en un módulo genérico— y
   `LLM_JOB_HEADROOM_CALLS`, porque la aritmética del margen del job usa "3
   llamadas en vuelo" y dejarlo cableado haría **no auditable el número que más
   veces va a frenar**, justo el que GAS-D11 obliga a explicar en el mensaje.

2. **`metrics.real` entra en GAS1, no en GAS2.** El propio plan pedía como test
   de GAS1 "job `FAILED` **con** `metrics.real` escritas", y eso exige la fusión
   de GAS-D9. Está donde decía el diseño —`update_job_metrics`, un solo sitio— y
   GAS2 se queda con el endpoint, la vista y la documentación.

3. **Se etiqueta la estimación en el artefacto y en el PDF** (condición
   innegociable del usuario al aprobar el aplazamiento de GAS-D9 a LLM4). No se
   corrige el número —eso sigue siendo LLM4—, se **marca**: `TokenMetrics.source`
   (`"estimado"` | `"medido"`, default `"estimado"`) alcanza a los **seis**
   artefactos con una sola edición, porque los seis reutilizan el `TokenMetrics`
   del EF y el `cost` es una función pura de él. En el frontend, las siete
   etiquetas "costo" pasan a "costo estimado". Un número etiquetado como estimado
   es honesto; un número bajo sin marca que llega a gerencia, no.

4. **Se etiquetan dos nodos que no pasan por `run_structured_map`**: el `EXTRACT`
   del EF (tiene su propio *map* y es el nodo que más llamadas hace) y su
   `CRITIQUE` (el único llamador suelto de `complete_json`, y el de la entrada
   sin techo). Dos líneas, y son justamente las dos filas que el experimento
   local va a necesitar leer. El resto de pases sueltos quedan con `stage = NULL`,
   como estaba previsto.

5. **La capa 1 del cortafuegos tapaba una sola boca.** Al envolver el cliente,
   `MeteredLLMClient` llama al protocolo interno `complete(...)`, así que la
   mordaza sobre `complete_json` habría dejado pasar de largo a cualquier
   proveedor que no cayera además en `get_claude_client`. Se tapan las dos, con
   un candado **estructural**: comprobarlo llamando no distinguía nada, porque
   con Anthropic la llamada choca igual contra la capa 3 y el test pasaba con la
   capa 1 rota. Se vio fallar antes de darlo por bueno.

6. **Capa 6 del cortafuegos de tests**: un libro mayor en memoria, autouse. Hace
   dos cosas —que ningún test escriba gasto real y que el resto de la suite pueda
   seguir llamando al doble del LLM pese al fail-closed—, y hay un test que **lo
   quita** para comprobar que sin él la llamada se niega.

7. **El preflight es la primera sentencia del método**, no una línea antes de
   `add_task` como decía §6: después de crear el job, un 409 dejaría una fila
   `PENDING` que nunca va a correr. Hay candado AST sobre los seis servicios.

8. **Si `anotar` falla, se falla.** No estaba decidido. El dinero ya está gastado
   y devolver el texto sería gratis, pero una fila que no se escribe es gasto que
   el tope no ve, y a partir de ahí el freno protege un número que no es el real.
   Se falla ruidosamente y la siguiente llamada se niega igual, porque el
   sumidero sigue roto.


### GAS2 — Lo que se ve ✅ IMPLEMENTADO

- `AgentJobRepository.update_job_metrics` funde `metrics.real` desde el libro
  mayor (GAS-D9) — un sitio, seis agentes, más la ruta de `FAILED`.
- `app/api/v1/gasto.py` — `GET /gasto/mensual` (§7.2) con `config` READ, en el
  router `v1`.
- `.env.example` con los ocho ajustes (§7.3) y su comentario.
- `CLAUDE.md`: §9 (la REGLA DE PRESUPUESTO gana un freno además de una regla),
  §11 (estructura) y una sección de estado para este plan.

**Tests:**
- `metrics.real` aparece en un job `COMPLETED` **y** en uno `FAILED`.
- `ratio_sobre_estimado` calcula bien y **no** divide por cero cuando la
  estimación es 0 (que es el caso de los seis `FAILED` de H1).
- `GET /gasto/mensual` con `config` READ responde; sin él, **403**.
- `estimated_fraction` refleja las filas estimadas.
- `by_stage` agrupa y `stage = NULL` aparece como no atribuido, no como 0
  (GAS-D10).

#### Lo que GAS2 hizo distinto de lo escrito arriba (desviaciones declaradas)

1. **`metrics.real` ya estaba** (desviación 2 de GAS1). GAS2 se quedó con el
   endpoint, la vista y la documentación, como allí se anunció.

2. **`estimated_fraction` es fracción del DINERO, no de las llamadas.** El
   ejemplo de §7.2 la pone junto a `estimated_calls`, lo que sugiere
   `estimadas / total`; pero eso ya es derivable de los dos contadores que van al
   lado, así que el campo no añadiría nada. Se calcula sobre el importe, que sí es
   información nueva y es la que decide: **una sola llamada cara estimada mueve la
   cifra mucho más que cien baratas**. Se publica también `estimated_cost_usd`
   para que sea auditable.

3. **Cuatro valores de `usage_source` para un total, no dos.** `fuente_del_total`
   (`app/models/spend.py`) es ahora el único sitio donde se decide, y lo usan el
   job y el mes. Corrige dos casos en los que GAS1 afirmaba de más: **todas las
   llamadas estimadas** decía `mixto` —que afirma que algo se midió— y ahora dice
   `estimado`; y **cero llamadas** daría `real` por aritmética, presumiendo de
   medición sobre nada, así que dice `sin_datos`. Es la regla de GAS-D4 aplicada al
   agregado: la ausencia de un dato no es el valor 0 de ese dato.

4. **Los importes salen con los seis decimales de la columna**, no redondeados a
   céntimos como en el ejemplo. Una fila de `by_stage` puede valer 0,003 USD y a
   dos decimales se leería 0,00 — y `by_stage` es justamente la fila que tiene que
   enseñar el antes/después de un recorte. Redondear es cosa de la vista, que usa
   dos precisiones a propósito (`lib/gasto.ts`, con test).

5. **`top_jobs` lleva `agent_role` y no `agent_type`, y sale de la propia fila.**
   Un `JOIN` con `agent_jobs` daría el tipo "oficial" pero perdería el job borrado
   (`ON DELETE SET NULL`); la fila del libro mayor conserva su `agent_role` pase lo
   que pase, y es el mismo vocabulario que `by_agent`. Las filas **sin** `job_id` se
   excluyen: agruparlas inventaría un job gigante que no existe. Su gasto sigue en
   el total y en `by_agent`.

6. **Un tope en 0 reporta `null`, no 0%.** No estaba decidido. Es una
   configuración legítima —quien no quiere gastar nada la usa— y ahí el porcentaje
   no existe: `0%` diría "no has empezado" justo cuando cualquier gasto ya lo cruzó.

7. **Cuatro consultas y no una.** Agrupar por tres criterios en una sola exigiría
   `GROUPING SETS`, que SQLite —el motor de la suite— no tiene, o traerse el libro
   mayor entero a Python. Es una pantalla que se mira a mano, no el freno: aquí
   manda la claridad.

8. **`.env.example` no gana ningún ajuste** (GAS2 no introduce configuración) pero
   sí un puntero al endpoint: quien lee los topes tiene que saber dónde se mira lo
   que están conteniendo.

---

## 11. Lo que este bloque NO hace

- **No acota `CRITIQUE`.** Lo mide y lo frena; el techo de entrada es OLL2.
- **No arregla el número del artefacto ni del PDF.** GAS-D9, dueño LLM4.
- **No toca la matriz de permisos.** El endpoint reutiliza `config` READ.
- **No toca el frontend.** `metrics.real` ya llega por los seis `GET /jobs/{id}`;
  pintarlo es un bloque aparte, y `<ProvenanceBadge>` de LLM5 es donde vive ese
  tipo de trabajo.
- **No calibra los topes.** Los pone en un número justificado y los deja para
  recalibrar con datos (GAS-D6).
