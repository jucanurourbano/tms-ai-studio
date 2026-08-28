# Proveedor LLM LOCAL (Ollama) — viabilidad, diseño y plan

> **Estado:** PARTE I medida el **2026-08-27**. PARTE II y III **diseñadas, sin
> implementar**. Ningún bloque autorizado todavía (REGLA R2).
>
> **Motivo del encargo:** la cadena EF → Scrum → Arquitectura → BD → API → QA
> lleva semanas sin una corrida real por falta de saldo de API. Un proveedor
> local permite validarla sin gastar y **sin que ningún dato de Urbano salga de
> la máquina**. Ver §0.

---

## 0. Por qué este documento existe (y qué se aplazó para escribirlo)

Investigación de mercado del 2026-08-27: el **Modo C** del Agente QA —pegar un
link y sacar casos— ya es producto en **TestCollab QA Copilot**, **CoTester** y
**CloudQA** (este último con tier gratuito), y los tres usan **modelos de visión
sobre la pantalla** en vez de parseo de DOM. Es la parte más *commodity* del
proyecto y se le habían dedicado quince bloques.

Lo que **no** existe en el mercado es la cadena ISDF completa con casos trazados
a `BR-`/`VAL-` de las especificaciones de Procesos, en español, con el glosario
logístico y la gobernanza por fases. Esa es la ventaja real y es la que está
parada.

**Consecuencia:** `QC1`, `QC2`, `QC6`, `QC7` y `QC8` quedan **APLAZADOS, no
cancelados** (anotado en `docs/diseno-qa-modo-c.md` §0.bis). Lo ya construido
—guard, saneador, extractor, candados, cortafuegos— **no se toca**: no es
específico del Modo C, es infraestructura del proyecto.

---

# PARTE I — VIABILIDAD (medida)

> Todo lo de esta parte está **medido en esta máquina** salvo lo que se marca
> explícitamente como **estimado**. La distinción importa: la decisión de la
> §1.6 se toma sobre lo medido, y lo estimado es justamente lo que `OLL0` va a
> comprobar.

## 1.1 ¿Está Ollama instalado?

**NO.** Ni en WSL2 ni en el host Windows.

| Comprobación | Resultado |
|---|---|
| `which ollama` | no está en el `PATH` |
| `/usr/local/bin/ollama`, `/usr/bin/ollama` | no existen |
| `~/.ollama` | no existe (**no hay ningún modelo descargado**) |
| `curl localhost:11434/api/version` | no responde |
| `%LOCALAPPDATA%\Programs\Ollama` (host) | no existe |

Instalarlo y descargar el primer modelo es trabajo de `OLL0`, y es la razón de
que las cifras de velocidad de la §1.4 sean estimaciones y no medidas.

## 1.2 Hardware disponible (medido)

| Recurso | Valor | Cómo se obtuvo |
|---|---|---|
| RAM total WSL2 | **11.19 GiB** (`MemTotal 11738776 kB`) | `/proc/meminfo` |
| RAM disponible ahora | **8.45 GiB** | `MemAvailable` |
| Ya en uso | 2.7 GiB | Postgres + Redis + uvicorn + next-server, **que tienen que seguir corriendo** |
| Swap | 3.0 GiB | irrelevante: hacer *swap* de pesos de un modelo es inutilizarlo |
| RAM host Windows | **23.0 GiB** (24 717 651 968 B) | `Win32_ComputerSystem` |
| `.wslconfig` | **no existe** → WSL toma el 50% por defecto | — |
| CPU | **AMD Ryzen AI 7 350**, 8 núcleos / 16 hilos | `lscpu` |
| SIMD | **AVX-512 completo**: `f`, `vl`, `bw`, `dq`, `cd`, `vnni`, `bf16`, `vbmi`, `vbmi2`, `ifma` | `/proc/cpuinfo` |
| RAM física | **2 × 12 GB DDR5-5600**, dual channel | `Win32_PhysicalMemory` |
| Ancho de banda teórico | **89.6 GB/s** (5600 MT/s × 8 B × 2 canales) | derivado |
| Disco libre | 943 GB | `df -h` |

### GPU: **no hay ninguna utilizable. La inferencia será CPU pura.**

Este es un resultado negativo firme, no una duda:

| Señal | Estado | Qué significa |
|---|---|---|
| `/dev/dxg` | **presente** | paravirtualización DirectX de WSL — sirve a D3D12/DirectML, **no** a Ollama |
| `/dev/kfd` | **ausente** | sin este nodo **no hay cómputo ROCm**. Es el bloqueo duro |
| `/opt/rocm`, `rocminfo` | ausentes | ROCm no instalado (y sin `/dev/kfd` no serviría) |
| `nvidia-smi` | ausente | no hay NVIDIA |
| `vulkaninfo` | ausente | y Ollama oficial **no trae backend Vulkan** |

La iGPU **Radeon 860M** existe (driver 32.0.31019.2002, 512 MB de carve-out) pero
es inalcanzable para Ollama dentro de WSL2. Y aunque se alcanzara desde Windows
nativo —`gfx1150` requiere `HSA_OVERRIDE_GFX_VERSION` y el soporte es
irregular—, **la ganancia sería modesta**: una iGPU comparte el mismo bus de
memoria DDR5 que la CPU, y la generación de tokens está limitada por ancho de
banda, no por cómputo. No es la palanca que parece.

**Palanca que sí existe y hoy no se usa:** el host tiene 23 GiB y WSL2 se queda
con 11.19 (el 50% por defecto, porque no hay `.wslconfig`). Un
`.wslconfig` con `memory=16GB` deja 7 GiB a Windows y sube el techo de modelo de
8B a 14B. Es un cambio de una línea con consecuencia directa en la §1.4.

## 1.3 El tamaño real de los prompts (medido)

Aquí está el hallazgo del turno. Se midió sobre el código y sobre las **corridas
reales contra Claude que ya están en la base de datos**.

### (a) Los prompts del EF son pequeños

| Pieza | chars | tokens (est. 4 c/t) |
|---|---|---|
| Glosario logístico | 2 043 | 510 |
| `system` por dimensión (base + glosario + rol) | 3 121 – 3 465 | **780 – 866** |
| Esquema JSON de salida (si se usara `format=`) | 1 086 – 1 935 | 271 – 483 |
| Chunk máximo (`chunk_cir(token_threshold=4096)`) | — | **4 096** |
| **EXTRACT: entrada por llamada** | — | **≈ 5 000 máx** |
| **Salida por llamada** | — | hasta **8 192** (`CLAUDE_MAX_TOKENS`) |

`CLAUDE_MAX_TOKENS` vale 8192 y el comentario del `settings.py` dice por qué: el
default de 4096 **truncaba la dimensión mayor de EXTRACT**. Es decir, no es un
margen teórico — hay constancia de una salida real de una sola llamada por encima
de 4 096 tokens.

### (b) Corridas reales contra Claude Sonnet (`agent_jobs.metrics`)

| Job | Fuente | input | output | duración | costo |
|---|---|---|---|---|---|
| Vacaciones (a) | 1 760 B | 5 061 | 6 133 | **103.0 s** | $0.107 |
| Vacaciones (b) | 1 760 B | 5 061 | 5 481 | **100.7 s** | $0.097 |
| Vacaciones (c) | 1 760 B | 4 957 | 3 998 | — | $0.075 |

Artefactos EF persistidos: **50 286**, 29 570, 23 215, 5 733, 4 032 chars
(≈ **12 571**, 7 392, 5 803, 1 433, 1 008 tokens).

**El EF es un pipeline de expansión:** 1 760 bytes de entrada producen un
artefacto de 50 KB. La carga no está en leer, está en **generar** — y generar es
exactamente lo que una CPU hace despacio.

### (c) La llamada más grande del pipeline no es EXTRACT: es CRITIQUE

`ai/agents/ef/critique.py:110` manda **el modelo consolidado entero** en el
`user`:

```python
user = "MODELO CONSOLIDADO:\n" + json.dumps(
    {"consolidated": consolidated, "inferred": inferred}, ensure_ascii=False)
```

Medido sobre el artefacto real más grande que hay en la base:

| Pieza | chars | tokens |
|---|---|---|
| `consolidated` (requirements, actors, modules, menus, processes, business_rules, validations, fields) | 25 763 | 6 441 |
| `inferred` (entities, relationships, crud, apis) | 1 771 | 443 |
| `system` de crítica (base + glosario + `critique.md`) | ~4 912 | 1 228 |
| **TOTAL entrada de UNA llamada** | | **≈ 8 100** |

**Y eso salió de un documento fuente de 1 760 bytes.**

> ### El hallazgo, dicho claro
>
> **El chunker acota EXTRACT (4 096 tokens por trozo). NADA acota CRITIQUE.**
> CRITIQUE recibe todo lo extraído del documento completo, así que su entrada
> **crece con el documento** y no tiene techo.
>
> La proporción medida es de **~4.6 tokens de entrada de CRITIQUE por byte de
> documento fuente**. Aunque la expansión se degrade y no sea lineal (parte del
> artefacto es coste fijo), un documento de Procesos de 10–20 KB —que es un
> documento **normal**, ni grande— sitúa a CRITIQUE en el orden de **20 000 a
> 90 000 tokens de entrada en una sola llamada**.
>
> Contra Claude (200K de contexto) esto es invisible y por eso nunca ha dolido.
> Contra un modelo local es el límite que manda.
>
> **Esto no es un problema de Ollama: es una propiedad del pipeline que Ollama
> hace visible.** Vale la pena aunque el proveedor local se descarte.

### (d) La trampa del contexto silencioso

Ollama **no falla** cuando el prompt excede `num_ctx`: lo **trunca**, y lo
registra en su log. Un CRITIQUE truncado no da error — critica un fragmento y
devuelve hallazgos con toda la apariencia de estar completos.

Es exactamente la clase de fallo que este proyecto ya ha cazado dos veces:
`sqlglot` degradando a `Command` en INV2, y *redactar en vez de rechazar* en A7.
**Redactar no es no tener; truncar no es fallar.** El diseño lo trata como
requisito duro en §2.1(e), no como nota al pie.

## 1.4 Qué modelo entra de verdad (estimado sobre memoria medida)

Presupuesto real: **8.45 GiB disponibles** menos margen para que Postgres, Redis,
uvicorn y Next sigan vivos → **~6.5–7.0 GiB para Ollama**.

Memoria = pesos + caché KV. La caché KV crece con el contexto y **es la mitad
olvidada de la cuenta**:

| Modelo (Q4_K_M) | Pesos | KV @16K (q8_0) | KV @32K (q8_0) | Total @16K | ¿Entra? |
|---|---|---|---|---|---|
| **4B** | ~2.6 GB | ~0.7 GB | ~1.4 GB | **3.3 GB** | sí, con holgura (y 32K también) |
| **8B** | ~4.9 GB | ~1.0 GB | ~2.0 GB | **5.9 GB** | **sí, justo** |
| **14B** | ~9.0 GB | ~1.4 GB | ~2.8 GB | 10.4 GB | **NO** (sí con `.wslconfig memory=16GB`) |
| **30B MoE** | ~18 GB | — | — | — | **NO** en ningún caso |

**Techo hoy: 8B a 16K de contexto.** Con `.wslconfig memory=16GB`: 14B a 16K.

> **Aviso:** con caché KV en `f16` en vez de `q8_0` estas cifras casi se
> duplican y el 8B **deja de entrar a 16K**. Fijar `OLLAMA_KV_CACHE_TYPE=q8_0`
> no es una optimización, es un requisito.

### Velocidad — **ESTIMADA, no medida** (esto lo mide `OLL0`)

Generar es un problema de ancho de banda: `tok/s ≈ BW_efectivo / tamaño_modelo`.
Con 89.6 GB/s teóricos y un rendimiento efectivo típico del 55–65% → **~50 GB/s**.

| Modelo | Generación (est.) | Prefill (est., AVX-512) |
|---|---|---|
| 4B Q4 | ~20 tok/s | ~120 tok/s |
| 8B Q4 | ~10 tok/s | ~60 tok/s |

Aplicado al job real de la §1.3(b) (5 061 in / 6 133 out, **103 s con Claude**):

| Escenario | Prefill | Generación | **Total** | vs Claude |
|---|---|---|---|---|
| 8B Q4 | ~84 s | ~613 s | **≈ 11–12 min** | **7×** más lento |
| 4B Q4 | ~42 s | ~307 s | **≈ 6 min** | ~3.5× |
| 8B con reparaciones (peor caso ×3) | | | **≈ 35 min** | 20× |

Dos advertencias sobre estas cifras:

1. **`concurrency=3` no ayuda y probablemente estorba.** En CPU los tres
   trabajadores compiten por el mismo ancho de banda; además cada petición
   paralela de Ollama reserva **su propia caché KV**, triplicando la memoria. El
   proveedor local debe declarar `max_concurrency = 1` (§2.1c).
2. **Una sola llamada de 8 192 tokens de salida tarda ~14 min a 10 tok/s.** El
   `CLAUDE_TIMEOUT` de 180 s la mataría a mitad. El timeout es por proveedor
   (§2.1d).

## 1.5 La API de Ollama con `httpx` puro (confirmado)

**Sí, sin dependencias nuevas.** Confirmado:

- `httpx` ya está declarado en `backend/requirements.txt` (línea 85) — no es
  transitiva accidental de `anthropic`, es dependencia directa. Instalado:
  **0.28.1**.
- Ollama expone `POST /api/chat` (nativo) y `POST /v1/chat/completions`
  (compatible OpenAI). Ambos son **JSON sobre HTTP sin autenticación**: un
  `httpx.AsyncClient` y nada más. No hace falta el paquete `ollama`, ni
  `openai`, ni `langchain-ollama`.
- Es el **mismo criterio con el que se rechazó `langchain-google-genai`**
  (LLM-D14): un SDK que envuelve una petición JSON añade una capa de
  comportamiento que hay que auditar y parchear, a cambio de nada.

**Se usa `/api/chat` (nativo), no `/v1/`.** El endpoint compatible con OpenAI
existe para no tocar código ajeno; aquí el cliente se escribe de todas formas, y
el nativo expone `options.num_ctx` y `keep_alive` —los dos parámetros que la
§1.3(d) y la §2.1(e) convierten en requisitos— sin tener que colarlos por un
campo que la compatibilidad no garantiza.

## 1.6 VEREDICTO

**VIABLE, con un límite duro que hay que respetar en el diseño.**

**Sí, para el objetivo declarado:**
- El hardware da para un **8B a 16K de contexto** (o 4B a 32K) sin tocar nada, y
  para 14B con una línea de `.wslconfig`.
- `httpx` puro, cero dependencias nuevas.
- La fábrica de LLM0 está construida justo para esto: registrar un
  `ProviderSpec` y nada más.
- Un job de EF costaría **~11 min contra ~103 s**. Para validar una cadena que
  hoy no corre en absoluto, 11 minutos es un precio excelente.
- **El A/B es reproducible byte a byte:** el documento fuente sigue en disco
  (`storage/4741241f….txt`, 1 760 B) y hay **tres artefactos de Claude
  guardados** con sus métricas. Se compara contra verdad registrada, no contra
  una impresión.

**No, como sustituto general de Claude:**
- **CRITIQUE no tiene techo de entrada** (§1.3c). Con documentos del tamaño ya
  probado (~2 KB) cabe en 16K. Con un documento de Procesos real de 10–20 KB, no
  cabe en ningún modelo que entre en esta máquina — y **Ollama lo truncaría en
  silencio**.
- Un 8B es sustancialmente más débil que Sonnet redactando JSON contra un
  esquema por prosa. **Esto no se tapa** (§2.1b): se mide como tasa de
  reparación, y esa tasa **es** el resultado del experimento.

**Qué decide `OLL0`, antes de escribir una línea en el repositorio:** las tres
cifras estimadas (tok/s de generación, tok/s de prefill, tasa de reparación) y
la comprobación del truncamiento silencioso. Si la tasa de reparación es alta,
la conclusión útil es "este modelo no sirve" y se entrega **eso**.

---

# PARTE II — DISEÑO

> Se implementa **sobre** el diseño multiproveedor
> (`docs/diseno-multiproveedor-llm.md`), no al lado. Todo lo que sigue son
> decisiones nuevas o modificaciones explícitas de las que ya están aprobadas.

## 2.1 OLL-D1 — Cómo entra `ollama` en la fábrica de LLM0

**(a) Registro: un `ProviderSpec` y nada más.** `ai/llm/providers/ollama.py` con
su `SPEC`, y una línea en `PROVIDERS`. Es literalmente lo que el registro
prometía: *«añadir un proveedor es registrar un `ProviderSpec` y nada más»*.

```
name           = "ollama"
default_model  = lambda: settings.OLLAMA_MODEL          # id EXACTO con tag
build_client   = _build_client                          # httpx puro
is_retryable   = errores de conexión y 5xx; NUNCA un 4xx
wait_hint      = None  →  backoff exponencial de ai/llm/retry.py
price_per_mtok = lambda _m: (0.0, 0.0)                  # ver (f)
data_residency = "local"                                # campo NUEVO, ver OLL-D2
```

**(b) Ruta de parseo: se mantiene la tolerante. `format` NO se usa.**

Ollama admite `format: <json schema>`, que fuerza el JSON por gramática y haría
imposible una violación de esquema. **Se rechaza**, por la misma razón que
LLM-D4 rechazó `responseSchema` de Gemini, y aquí el argumento es **más fuerte**:

> El objetivo del proveedor local es **comparar** su salida con la de Claude. Si
> el local decodifica con gramática y Claude no, no se compara el modelo: se
> comparan dos pipelines distintos. Un prompt que solo produce JSON válido
> *gracias* a la gramática pasaría verde en local y fallaría en producción, y el
> loop de reparación —el código que más veces ha roto este repositorio— **nunca
> se ejercitaría**.

Consecuencia deliberada: **la tasa de reparación se convierte en la métrica
principal del experimento.** Es también la respuesta a la incógnita nº 2 que
LLM3 dejó abierta (*«qué tasa de reparación significa modelo insuficiente y no
bug del pipeline»*), y se responde antes y más barato con Ollama que con Gemini,
porque aquí no hay cuota que gastar.

*Si algún día se quiere `format`, será una decisión consciente con su propio
bloque y su propia justificación — no una bandera apagada que alguien encienda.*

**(c) Concurrencia: la manda el proveedor.** `max_concurrency = 1`, por el
mecanismo que LLM-D11(b) ya dejó especificado
(`min(concurrency, getattr(llm, "max_concurrency", concurrency))` en
`run_structured_map`). Motivo distinto al de Gemini —no es cuota, es que en CPU
el paralelismo reparte el mismo ancho de banda y **triplica la caché KV**— pero
el mecanismo es el mismo y no hay que inventar nada.

⚠️ `ai/agents/ef/extract.py:run_extract` tiene su **propio** semáforo y **no**
pasa por `run_structured_map`. Es un hueco real del mecanismo de LLM-D11(b), y
como el EF es el primer agente que se va a probar (OLL-D5), hay que taparlo en
`OLL2`. Anotado aquí para que no se descubra corriendo.

**(d) Timeout por proveedor.** `CLAUDE_TIMEOUT=180` es de Anthropic. Una llamada
local de 8 192 tokens de salida a ~10 tok/s tarda **~14 minutos**: con 180 s
moriría siempre, y el fallo parecería del modelo. `OLLAMA_TIMEOUT`, default
**1200 s**. El timeout deja de ser global el mismo día que deja de haber un solo
proveedor, exactamente igual que pasó con el precio en LLM-D7.

**(e) `num_ctx` explícito y verificado — requisito, no ajuste.** Por §1.3(d):

1. `options.num_ctx` se manda **siempre** y de forma explícita
   (`OLLAMA_NUM_CTX`, default 16384). Nunca se confía en el default del modelo.
2. **Canario de truncamiento:** antes de la primera llamada real de un job, el
   cliente estima los tokens del par `system+user` con la **misma**
   `estimate_tokens` que ya usa el pipeline para sus métricas, y si supera
   `num_ctx` menos el margen de salida → **`ProviderError` que dice el número**.
   Falla ruidosamente en vez de criticar medio documento.
3. `keep_alive` configurable: recargar 5 GB de pesos entre nodos añadiría
   minutos por job.

Es la misma forma que `assert_target_authorized` en ClickUp o el guard del Modo
C: **la comprobación va antes de la acción, no después del daño**.

**(f) Precio 0.0, y el campo existe a propósito.** `price_per_mtok → (0.0, 0.0)`,
igual que los modelos del free tier de Gemini en LLM-D7. Que una corrida local
diga **$0.00** *es* el dato correcto, y hace visible en el propio panel qué parte
del gasto histórico fue real. El coste que un run local sí tiene —11 minutos de
CPU— se lee en `metrics.duration`, que ya se registra.

## 2.2 OLL-D2 — `data_class="real"`: la excepción que hace útil todo esto

**Es la decisión central del documento.** LLM-D9 (capa 3) dice hoy:

> Si el proveedor resuelto no es `anthropic` y `data_class != "sintetico"` →
> `ProviderPolicyError`.

Aplicada literalmente, esa regla **inutiliza el proveedor local**: obligaría a
inventar documentos de Procesos sintéticos para probar la cadena, que es
precisamente lo que no queremos hacer.

### El diagnóstico: la regla está escrita sobre un NOMBRE, no sobre una PROPIEDAD

`anthropic` no puede recibir datos reales *por llamarse Anthropic*. Puede porque
existe una relación con un tercero al que la organización decidió confiarle esos
datos. Gemini no puede porque **manda los datos a un tercero al que nadie se los
confió**.

**Ollama no manda nada a ningún sitio.** El proceso corre en la máquina del
usuario, sobre `localhost`. No hay tercero. La regla escrita como
`provider != "anthropic"` prohíbe un flujo que **no tiene el riesgo que la regla
existe para evitar**.

### La decisión

`ProviderSpec` gana un campo obligatorio:

```python
DataResidency = Literal["local", "tercero_confiable", "tercero"]
```

| Proveedor | `data_residency` | Admite `real` | Por qué |
|---|---|---|---|
| `anthropic` | `tercero_confiable` | **sí** | relación establecida; es producción |
| `ollama` | `local` | **sí** | **no sale un byte de la máquina** |
| `gemini` (futuro) | `tercero` | **no** | destino no autorizado para datos de Urbano |

Y la capa 3 de LLM-D9 se reescribe **sobre la propiedad**:

```python
if spec.data_residency == "tercero" and data_class != "sintetico":
    raise ProviderPolicyError(...)
```

**Esto es más estricto que lo de hoy, no más laxo.** Hoy la regla es una lista
negra implícita de un elemento: registrar mañana un cuarto proveedor sin tocar
nada lo dejaría *prohibido por accidente* — y el día que alguien "arregle" esa
condición para desbloquearse, la arreglará en la dirección equivocada. Con el
campo obligatorio en el `ProviderSpec`, **registrar un proveedor sin declarar
dónde acaban los datos es imposible**: es un `TypeError` en el constructor del
`dataclass`. Misma forma que `data_class` sin default en `get_llm`.

### Las tres consecuencias que hay que sostener

1. **`data_residency` no se lee de settings.** Es una propiedad del proveedor,
   no de la configuración. Un `.env` no puede declarar que Gemini es local.
2. **LLM-D10 se relaja SOLO para `local`.** LLM-D10 decidió que
   `ai/knowledge/tech_stack.yaml` no se manda a un proveedor no-Anthropic porque
   nombra proveedor cloud, servicios y versiones reales de Urbano. Con
   `residency == "local"` esa razón **desaparece por completo**: no hay
   destinatario. Se manda el `tech_stack.yaml` **real**, y el
   `tech_stack.sintetico.yaml` que LLM2 tiene que crear **sigue haciendo falta**
   para Gemini. La regla del loader pasa a ser la misma: *`local` y
   `tercero_confiable` reciben el real; `tercero` recibe el sintético*.
3. **La capa 5 de LLM-D9 (`APP_ENV=production` ⇒ no arranca) se mantiene
   INTACTA para `ollama`.** Aquí no hay excepción y la razón no es la privacidad
   sino la calidad: un artefacto de producción generado por un 8B local sería
   malo aunque fuera perfectamente privado. **Local resuelve dónde están los
   datos; no resuelve si el resultado sirve.** Son dos ejes ortogonales, y
   confundirlos es el error que OLL-D4 existe para impedir.

### Encaje con LLM2 (que no ha empezado)

**LLM2 debe implementar la regla YA en su forma final**, sobre
`data_residency`, no sobre `provider == "anthropic"`. Si LLM2 la fija sobre el
nombre y `OLL1` la reescribe después, la política de datos —la parte más
delicada del diseño— se habrá escrito dos veces en dos bloques distintos. Ver
§3.2.

## 2.3 OLL-D3 — El cortafuegos: **no hace falta una capa nueva**

**El agujero es real y está confirmado leyendo `tests/firewall.py`:**

La capa 4 (`es_destino_local`) permite **todo** destino de loopback —
correctamente, porque Postgres (5432) y Redis (6379) viven ahí. **Ollama también
vive ahí (11434).** Un test que construya el cliente local y lo llame saldría a
Ollama de verdad y **ninguna de las cinco capas lo vería**:

| Capa | ¿Cubre a Ollama? | Por qué |
|---|---|---|
| 1 · la fábrica | **sí**, si se pasa por `get_llm` | envuelve `build_client` de **todo** `ProviderSpec` registrado |
| 2 · constructores de SDK | **no** | no hay SDK que parchear: es `httpx` genérico |
| 3 · `get_claude_client` | no | es de Anthropic (y muere en LLM4) |
| 4 · la red | **NO — es el agujero** | `127.0.0.1:11434` es loopback ⇒ permitido |
| 5 · el navegador | no aplica | — |

### Por qué **no** se añade `sin_llm_local`

`sin_navegador_real` mereció ser una capa nueva porque la capa 4 es
**estructuralmente ciega** al navegador: Chromium es *otro proceso del sistema
operativo* y sus sockets no pasan por el parche de este proceso. Ahí no había
nada que arreglar, había que construir algo que no existía.

**Aquí no es así.** Ollama se alcanza con un socket de **este mismo proceso**: la
capa 4 lo ve perfectamente y lo **deja pasar porque una regla que escribimos
nosotros dice que loopback es seguro**. Esa regla se quedó corta el día que
apareció un servicio de inferencia en localhost.

> **Apilar una capa sobre una regla equivocada deja la regla equivocada
> debajo.** La siguiente cosa que escuche en un puerto local volverá a pasar.

### Lo que sí se hace: **estrechar la capa 4 y declarar la costura en la capa 2**

**(a) Capa 4 — loopback deja de ser un salvoconducto.** `es_destino_local` pasa
a rechazar el **puerto de inferencia local**, leído del **mismo** `settings` que
lee el proveedor (un único lector, como `QA_EXPLORE_TARGETS`), con su propio
mensaje:

> «Un test intentó llamar al LLM local REAL en `127.0.0.1:11434`. Inyecta un
> doble (`httpx.MockTransport`). REGLA DE PRESUPUESTO: nunca se llama a un
> modelo real en tests.»

Postgres, Redis, `::1` y los sockets unix siguen pasando sin fricción — lo cubre
el test que LLM1 ya escribió.

**(b) Capa 2 — la costura se declara aunque no haya SDK.** `SDK_CONSTRUCTORS`
exige una entrada por cada proveedor de `PROVIDERS` (hay un test parametrizado
que rompe la suite si falta). Para `ollama` la entrada no puede ser
`httpx.AsyncClient` —parcharlo tumbaría a FastAPI, a `starlette` y a media
suite—, así que es **nuestra propia fábrica de transporte**:
`ai.llm.providers.ollama.build_http_client`.

Y por **REGLA R1** se llama por su módulo (`_mod.build_http_client(...)`),
**nunca** por el símbolo importado. Es la tercera vez que este proyecto tropieza
con lo mismo: `test_claude.py` en LLM1 y `_driver.build_driver` en QC3. Va con
su entrada en `tests/test_costuras_parcheables.py`.

**(c) Y la capa 4 se ve fallar.** Como los candados de QC4 y QC4.5: un test que
**introduce la violación** —un `httpx` suelto contra el puerto de inferencia— y
comprueba que la capa lo para. *Un candado que solo se ha visto pasar es
indistinguible de una función que devuelve la lista vacía.*

## 2.4 OLL-D4 — Procedencia: **mismo régimen que LLM4, sin excepción**

LLM-D6 ya deja `validation_grade` derivado del proveedor: `anthropic →
produccion`, **cualquier otro → `banco_de_pruebas`**. `ollama` cae en el segundo
grupo y **no se toca nada**.

Merece decirse explícitamente porque es el contraste exacto con OLL-D2:

| Eje | Pregunta | `ollama` |
|---|---|---|
| `data_class` / `data_residency` | ¿puede ver datos reales? | **SÍ** — no sale de la máquina |
| `validation_grade` | ¿el resultado está validado? | **NO** — `banco_de_pruebas` |

**Son ortogonales, y el diseño los mantiene separados a propósito.** El error
fácil —y caro— sería que "local y privado" se leyera como "de confianza": un
artefacto hecho por un 8B es exactamente igual de no validado que uno hecho por
Gemini, aunque sea infinitamente más privado.

Lo que hay que sostener:

- `RunProvenance` guarda el **id exacto con tag** (`qwen3:8b-q4_K_M`), nunca la
  familia. Dos tags del mismo modelo no dan la misma salida, y sin el tag el A/B
  de OLL-D5 no es reproducible.
- El sello **debe entrar en la marca de agua del PDF** (LLM-D8 paso 3). Es el
  paso que de verdad cierra el agujero: el badge de la cabecera es
  `print:hidden`, así que sin él **el PDF sale limpio**, que es el peor
  resultado posible. Un plan de pruebas generado por un 8B local, impreso y
  llevado a una reunión, es indistinguible de uno bueno.
- `RunProvenance` gana `data_residency`. Sin él, un artefacto exportado dice con
  qué se generó pero **no dice si los datos salieron de la organización** — que
  es justamente la pregunta que este proveedor existe para poder responder que
  no.

## 2.5 OLL-D5 — Se prueba primero el **EF**

Confirmado, y por una razón más fuerte que "es el primero de la cadena":

1. **Es el único con corridas reales contra Claude registradas** — tres
   artefactos EF en `agent_artifacts` con sus `metrics`.
2. **El A/B es reproducible byte a byte:** el documento fuente sigue en disco
   (`storage/4741241f….txt`, 1 760 B) y su hash está en `ef_source_docs`. Mismo
   texto, mismo pipeline, cambia el proveedor y **nada más**.
3. **Es el único agente que no depende de un `ready_for_next_stage` ajeno**: no
   hay que sembrar una cadena para llegar a él.
4. Ejercita las dos formas de llamada del sistema: *map* con esquema pequeño
   (EXTRACT ×6) y **pase único con el modelo entero** (CRITIQUE) — que es
   precisamente la llamada que la §1.3(c) señaló como límite.

**Qué se compara, y cómo.** Comparar dos JSON con `diff` no dice nada útil: los
ids se renumeran y el orden puede variar. La comparación es **determinista y
sobre magnitudes**, sin LLM juez:

| Métrica | Qué revela |
|---|---|
| **Tasa de reparación** por dimensión | *la* métrica: ¿sabe el modelo producir el esquema? |
| Cuarentenas (`chunks_skipped`) | irreparables |
| Conteo por sección (reqs, reglas, validaciones, actores…) | ¿extrae lo mismo o alucina de más? |
| **`evidence` verbatim: ¿está literalmente en el fuente?** | **el anti-invención.** Comprobable en Python, sin modelo |
| Cobertura y nº de preguntas bloqueantes | ¿el semáforo daría el mismo veredicto? |
| `duration` | el coste real del proveedor local |

La cuarta fila es la importante y sale gratis: **una `evidence` que no aparece
literalmente en el documento fuente es una invención**, y eso se comprueba con
una búsqueda de subcadena. Es el mismo criterio que ya sostiene QA-D2 y el
verificador de INV3. Si el modelo local inventa evidencias, no sirve — y se sabrá
sin discutir estilos de redacción.

---

# PARTE III — PLAN POR BLOQUES

> Tests mockeados, `commit` + `push` por bloque, **REGLA R2**: cerrar → reportar
> → esperar aprobación. Ninguno autorizado todavía.

## 3.1 Bloques

### OLL0 — Banco de medición · **FUERA del repositorio** · *no autorizado*
El único bloque que no escribe código de producción, y el que decide si los
demás existen. Instalar Ollama en WSL2, descargar **dos** modelos (un 4B y un
8B), y medir en el *scratchpad*:

- tok/s de **generación** y de **prefill** por modelo (el dato estimado en §1.4);
- **RSS real** con `num_ctx=16384` y `KV_CACHE_TYPE=q8_0` — confirmar que el 8B
  entra en 6.5 GB **con Postgres, Redis y el frontend corriendo**;
- **el canario de truncamiento**: mandar un prompt mayor que `num_ctx` y
  comprobar de primera mano que responde sin error (§1.3d). Si no trunca en
  silencio, se anota y §2.1(e) se relaja;
- **tasa de reparación**: los seis `system` reales del EF + un chunk real,
  contados a mano sobre cuántas respuestas validan contra el `schema` Pydantic.

**Entregable:** una tabla de cifras y un veredicto **modelo por modelo**.
**Si la tasa de reparación del 8B es mala, el plan se detiene aquí** y esa es la
conclusión: barata, rápida y correcta.

### OLL1 — `data_residency` + cortafuegos, **antes del proveedor**
`data_residency` obligatorio en `ProviderSpec` · política de OLL-D2 · capa 4
estrechada por puerto · entrada de la capa 2 · costura en
`test_costuras_parcheables.py`.

Mismo criterio que LLM1 (*el cortafuegos antes del proveedor*) y que QC3 (*el
guard antes del navegador*): **la protección se construye antes de que exista lo
que hay que proteger, o se construye tarde.**

**Depende de LLM2** (§3.2). **Tests:** proveedor falso `residency="tercero"` +
`real` ⇒ `ProviderPolicyError` antes de la primera llamada · falso
`residency="local"` + `real` ⇒ **pasa** · registrar un `ProviderSpec` sin
`data_residency` ⇒ `TypeError` · la capa 4 **se ve fallar** contra el puerto de
inferencia · Postgres y Redis siguen pasando.

### OLL2 — El proveedor `ollama`
`ai/llm/providers/ollama.py` con `httpx` puro · `num_ctx` explícito + canario ·
`max_concurrency=1` · `OLLAMA_TIMEOUT` · precio 0.0 · `is_retryable` (conexión y
5xx; **nunca** un 4xx) · **y el hueco del semáforo propio de
`run_extract`** (§2.1c).

**Tests:** todo con `httpx.MockTransport`, cero red · `num_ctx` viaja en cada
petición · prompt mayor que el contexto ⇒ `ProviderError` **antes** de llamar ·
respuesta con *fence* markdown se parsea por la ruta tolerante · `run_extract`
respeta `max_concurrency=1` · **candado: `format` no aparece en el payload**
(OLL-D1b se defiende con un test, no con un párrafo).

### OLL3 — Procedencia
Depende de **LLM4**. `data_residency` en `RunProvenance` · `ollama →
banco_de_pruebas` · marca de agua en el PDF.
**Tests:** artefactos existentes sin `provenance` siguen validando · el grado es
`banco_de_pruebas` · **la marca de agua aparece en el documento de impresión**.

### OLL4 — La corrida real, y el veredicto
**El único bloque que ejecuta un modelo de verdad, y se autoriza aparte.**
Correr el EF sobre `storage/4741241f….txt` con el proveedor local, comparar
contra los tres artefactos de Claude por la tabla de OLL-D5, y **medir dónde
revienta CRITIQUE** subiendo el tamaño del documento hasta agotar `num_ctx`
(§1.3c) — ese número es el que decide si el proveedor local sirve para
documentos reales o solo para los de prueba.

**Entregable:** informe A/B con cifras + decisión de seguir con Scrum o parar.
No consume presupuesto de API, pero **sí** es una corrida real y por eso se pide.

## 3.2 Choques con LLM2 y con el resto del frente LLM

### ⚠️ El choque real: **LLM2 debe cambiar de forma antes de construirse**

LLM2 está especificado para implementar `provider != "anthropic" && real ⇒
error`. OLL-D2 lo reescribe sobre `data_residency`. **LLM2 no ha empezado**, así
que hay una sola decisión correcta y hay que tomarla ahora:

> **LLM2 implementa la regla directamente en su forma final** (sobre
> `data_residency`), con su proveedor falso de tests parametrizado sobre los
> **tres** valores.

Si no, la política de datos —la parte más delicada del diseño— se escribe dos
veces, en dos bloques distintos, y la segunda vez es un *cambio* sobre algo ya
probado. Coste de hacerlo ahora: un campo más en el `dataclass` y un caso más en
la parametrización. Coste de hacerlo después: reabrir el guardarraíl.

**Consecuencia de orden:** `OLL1` **no puede ir antes que LLM2**. El camino es
**LLM2 (reformado) → OLL1 → OLL2 → OLL0 ya medido → OLL4**, con `OLL0` corriendo
**en paralelo desde ya** porque no toca el repositorio.

### LLM3 (Gemini) — pierde su justificación principal

Gemini entró al plan por el *free tier*, es decir para **poder probar sin
gastar**. El proveedor local hace eso mismo **mejor**: sin cuota diaria, sin
rate limit, sin 429 de dos sabores, sin token bucket, y —lo decisivo— **admite
datos reales**.

Lo que Gemini sigue teniendo es **calidad y velocidad**: un modelo de frontera
gratuito produce JSON estructurado mucho mejor que un 8B local.

**No se decide aquí.** Se señala que el orden `LLM3 → LLM4` merece revisarse a
la luz de OLL4: si el modelo local aguanta la cadena, LLM3 pasa de "siguiente"
a "quizá innecesario", y toda su maquinaria de cuotas (LLM-D11 a, c) se aplaza
con él. **Es del usuario.**

### Choques menores

| Con | Qué pasa |
|---|---|
| **LLM-D4** (ruta única de parseo) | **Se reafirma**, con argumento más fuerte (§2.1b). Sin cambios |
| **LLM-D11(b)** (concurrencia del proveedor) | Se **usa** tal cual, y `OLL2` tapa el hueco de `run_extract` |
| **LLM4** | `OLL3` depende de él. Sin choque: `ollama` cae solo en `banco_de_pruebas` |
| **LLM5** (frontend) | El `<ProvenanceBadge>` sirve sin tocarse. Solo cambia el texto: `banco de pruebas · qwen3:8b` |
| **LLM1** | Se **modifica** la capa 4 que LLM1 escribió. Sus tests de loopback deben seguir verdes |
| **QC1/2/6/7/8** | **Ninguno.** Están aplazados (§0) |
| **QC2 ⇄ LLM2** | La colisión de `docs/diseno-qa-modo-c.md` §9.1 **se desactiva** al aplazarse QC2 |

## 3.3 Configuración nueva (`.env.example`)

```
LLM_PROVIDER=anthropic          # el default NUNCA es el proveedor de pruebas
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=                   # id EXACTO con tag; sin default: elegirlo es una decisión
OLLAMA_NUM_CTX=16384
OLLAMA_TIMEOUT=1200
OLLAMA_KEEP_ALIVE=30m
```

`OLLAMA_MODEL` **sin default a propósito**: qué modelo se usa determina el
resultado del A/B, y un default invisible convierte esa decisión en un accidente.
`OLLAMA_KV_CACHE_TYPE=q8_0` y `OLLAMA_NUM_PARALLEL=1` son del **servidor**, no de
la aplicación: van en la documentación de arranque de `OLL0`, no en `settings`.

---

## 4. Candidata de PRODUCTO (no de este plan) — la bandeja de propuestas

De **TestCollab** se toma **una** idea, y se anota aquí para no perderla:

> Una **bandeja de propuestas** con estados `pendiente` / `aceptado` / `rechazado`
> y **edición en línea**, donde **nada se crea hasta que un humano acepta**.

Encaja bien con lo que ya existe: es la misma forma que las **validaciones**
(§7 de `CLAUDE.md`) y que las **asignaciones de historias** — algo que vive
**fuera del artefacto**, que no lo muta y que es revisable sin regenerar nada. Y
extiende el modo enfocado de Preguntas del centro de comando (§5.1) de
*responder* a *aceptar o corregir*.

**Se evalúa cuando la cadena esté validada, no antes.**

**Lo que NO se copia:** su entrada por **URL libre**. Nuestra **allowlist de
destinos preautorizados** (capas 1 y 2 del guard del Modo C) es estrictamente
superior —una URL del cliente es SSRF— y **se queda**, aplazada pero intacta.
