# Diseño — Agente QA (sexto agente del ISDF, fase VERIFICAR)

> Consume el **plan Scrum listo** (gate `ready_for_next_stage=true`) y,
> transitivamente, el **EF** —de donde salen reglas `BR-`, validaciones `VAL-` y
> campos `FLD-`—. El **ApiArtifact es una dependencia OPCIONAL**: con él se diseñan
> los casos de autorización; sin él se omiten **con una `Observation` que dice por
> qué**, nunca en silencio. Produce el diseño de pruebas completo: casos, matriz de
> trazabilidad, datasets y plan de ejecución.

---

## 0. Principio rector

**El peor error de este agente es un caso de prueba con un dato inventado.**

Un endpoint sobrante se borra en revisión. Una autorización permisiva se despliega
—esa es la doctrina del Agente API—. Aquí el daño es de otra clase: un caso que
verifica un límite falso ("el saldo máximo es 5000" cuando nadie lo dijo) **no
falla: pasa**. Y al pasar certifica una mentira. Es peor que la ausencia del caso,
porque la ausencia se ve en la cobertura y la mentira genera confianza.

De ahí las dos reglas duras, ambas **impuestas en Python, no en el prompt**:

1. **Todo `TC-` ancla a un `AC-` que existe.** `CRITERION_MAP` enumera antes de
   llamar al LLM qué pares (historia, criterio) hay; un caso que referencie un
   criterio inexistente **se descarta con `Observation`**. Es el cortafuegos
   anti-invención del agente QA, gemelo de `MODEL_MAP` (BD) y `RESOURCE_MAP` (API).
2. **Todo límite de borde ancla a evidencia.** O una **cita verbatim** del texto de
   una `VAL-`/`BR-` del EF, o un **campo estructurado** del ApiArtifact
   (`max_length`, `enum`, `required`, `nullable`). Sin ancla **no hay caso: hay
   pregunta** al QA lead.

Y una tercera, que es la razón de ser de la fase: **este agente puede decir que un
criterio no se puede probar.** "El sistema debe ser rápido" no se convierte en un
caso vago —que alguien ejecutará a mano y marcará "pasa" sin saber qué comprobó—:
se convierte en **pregunta bloqueante**. Un caso vago es deuda disfrazada de
cobertura.

---

## 1. Reutilización

### Tal cual (cero cambios)

- Persistencia `agent_*` + `AgentJobRepository` (`agent_type=QA`, `input_job_id`).
- Grafo LangGraph + checkpointer Redis por `job_id` (reintentos no re-facturan).
- Ciclo de afinamiento: validaciones aparte **sin mutar el artefacto** + `/refine`
  con job hijo (`parent_job_id`) e inyección de respuestas como contexto
  autoritativo.
- `ApiResponse`, errores de app (`GateError` 409), `require_module`.
- Centro de comando del frontend (§5.1 de `CLAUDE.md`): hub + panel + `printSkip`.
- Cortafuegos autouse de tests (`sin_api_real`): todo con mocks.

### Lo nuevo

| Pieza | Qué es |
|---|---|
| `ai/agents/qa/` | grafo, nodos, `criterion_map.py` (cortafuegos), payloads |
| `ai/agents/qa/schemas/` | `QaArtifact v1.0.0` + enums + extracción |
| `ai/agents/qa/export/` | CSV de casos y de matriz (sin dependencia nueva) |
| `ai/prompts/qa/` | `test_design`, `edge_cases`, `dataset`, `critique`, `questions` |
| `app/services/qa_service.py` + `api/v1/qa.py` | gate, semáforo, `/qa/*` |
| `frontend .../qa/` | nav **Verificar** activa + `QaResultView` |

### Permisos (sin cambios en la matriz)

`qa` es **FULL del rol `qa`**, que ya tiene **READ en `scrum`** (§6.1). Encaja sin
tocar `permissions.py`: produce lo suyo y lee hacia atrás. El acento ámbar del
módulo ya existe en `lib/module-accent.ts`, y la fase **Verificar** ya está en
`ISDF_NAV` con `enabled: false` — QA8 solo la enciende.

Ojo con el alcance real: el rol `qa` **no** tiene READ en `ef`, `bd` ni `api`. Lee
esos artefactos **a través de su propio job de QA** (el servicio los resuelve por
la cadena), no por sus endpoints. Eso es correcto y deliberado: ver el EF citado
dentro de un caso de prueba no es lo mismo que poder listar los jobs del EF.

---

## 2. Entradas: la cadena, y el problema del ApiArtifact

`input_job_id = scrum_job_id`. El EF se resuelve **hacia atrás** con
`resolve_lineage`, igual que Arquitectura/BD/API.

**Pero el ApiArtifact no está hacia atrás: está hacia delante.** La cadena real es
`EF → Scrum → Arquitectura → BD → API`, y `resolve_lineage` sube por
`input_job_id`. Desde un job de Scrum **el contrato de API es inalcanzable**: no
hay enlace que lo apunte. Es un hecho de la infraestructura, no un detalle de
implementación, y obliga a decidir cómo entra (**QA-D1**).

Propuesta: **`api_job_id` opcional y explícito en el request**, validado contra la
misma cadena — `resolve_lineage(api_job)` debe contener **este** `scrum_job_id`; si
no, `GateError`. La UI ofrece la lista de contratos compatibles, así que el
descubrimiento existe como **ayuda al humano**, y la **elección** es del QA lead.
El artefacto registra `api_job_id` + hash, o `api_available=false` con
`api_absent_reason` y una `Observation`.

Lo que aporta cada fuente:

| Fuente | Qué se usa | Nodo |
|---|---|---|
| Scrum | `stories[]`, `acceptance_criteria[]` (Gherkin), `priority` MoSCoW, `dependencies`, `epics[]` | CRITERION_MAP, TEST_DESIGN, EXEC_PLAN |
| EF | `BR-`, `VAL-` (texto + `field_ref`), `FLD-` (`data_type`, `required`), `REQ-F-`, `actors[]` | EDGE_CASES, DATASET, TRACE_MATRIX |
| API *(opcional)* | `authorization_matrix[]` (`effect`, `scope`, `scope_column_refs`, `ambiguous`), `endpoints[]`, `SchemaField` (`max_length`, `enum`, `required`) | AUTH_CASES, EDGE_CASES |

**Hallazgo que corrige el enunciado:** los límites estructurados **no están en el
EF**. `FieldDef` solo tiene `name`/`entity_ref`/`data_type`/`required`, y
`ValidationRule` es **texto libre** (`rule` + `field_ref`). Los límites duros
(`length`, `precision`, `scale`, `nullable`, `CheckConstraint.expression`) viven en
el **BD**, y su reflejo (`max_length`, `enum`) en el **API** — ambos hacia delante.
Por eso EDGE_CASES extrae el límite **del texto** de la `VAL-` con structured
output (valor + operador + **cita verbatim**), y **cuando hay ApiArtifact, el campo
estructurado prevalece** sobre lo extraído. Funciona sin él y mejora con él
(**QA-D2**).

---

## 3. Pipeline (12 nodos, 5 tocan el LLM)

```
LOAD_SOURCES (gate) → CRITERION_MAP (det.) → TEST_DESIGN (map, LLM)
  → EDGE_CASES (LLM anclado) → AUTH_CASES (det., condicional)
  → DATASET (LLM + poda det.) → TRACE_MATRIX (det.) → EXEC_PLAN (det.)
  → CRITIQUE (LLM) → QUESTION_GEN (LLM) → ASSEMBLE → PERSIST
```

Dos ajustes sobre el pipeline propuesto, con su razón:

- **`CRITERION_MAP` es nuevo** (entre LOAD y TEST_DESIGN). Fija en Python el
  universo de pares (historia, criterio) y reparte el *map* por historia. Sin él,
  "todo TC referencia un AC existente" sería una validación *a posteriori* que
  descarta trabajo ya pagado al modelo; con él, el LLM recibe los ids que puede
  usar y la matriz de trazabilidad sale **gratis y completa**, incluidos los
  criterios que se quedaron sin caso.
- **`AUTH_CASES` es DETERMINISTA**, no un nodo LLM. La matriz del API ya trae
  `effect`, `scope` y `scope_column_refs`: de `allow` + `scope ∈ {own, own_team,
  own_branch}` se **deriva** el caso negativo cruzado ("actor del equipo B pide un
  recurso del equipo A → 403"), y de `deny` el caso de rechazo. El texto sale de
  plantilla. Es exactamente el ejemplo del enunciado ("un jefe NO puede ver
  solicitudes de otro equipo") y es el terreno donde inventar es más caro: la
  superficie de autorización no se redacta a ojo. Y si `ambiguous=true`, **no se
  emite caso**: se emite pregunta bloqueante, respetando el veredicto del API.

Los 5 nodos con LLM: `TEST_DESIGN`, `EDGE_CASES`, `DATASET` (solo los valores),
`CRITIQUE`, `QUESTION_GEN`. Todos con **structured output**; nunca JSON libre.
Concurrencia del *map* = **3**, como EXTRACT.

---

## 4. Contrato `QaArtifact v1.0.0`

Claves en inglés, valores en español; `id`/`source_refs`/`confidence`/`origin` en
todo ítem.

```
source        SourceRef  scrum_job_id + hash, ef_job_id + hash,
                         api_job_id? + hash?, api_available, api_absent_reason?,
                         ready_snapshot
target        Target     umbrales y política EFECTIVOS (cobertura, minutos por
                         tipo, política de automation_hint) — el cálculo
                         determinista queda auditable
test_cases[]  TestCase   id TC-, title, story_ref, criterion_ref (OBLIGATORIO),
                         type (functional|negative|boundary|authorization),
                         preconditions[], steps[] (numerados: action + expected?),
                         test_data[] (field_ref?, value, kind, anchor),
                         expected_result, priority, automation_hint (ui|api|manual),
                         estimated_minutes, boundary? (BoundaryAnchor),
                         auth_context? (AuthCase), tags[], source_refs[],
                         confidence, origin
              BoundaryAnchor  rule_ref, kind (min|max|length|format|required|
                              conditional|date_order), operator, value,
                              evidence (VERBATIM), anchor_source (ef_text|api_field)
              AuthCase        auth_rule_ref, endpoint_ref, actor_ref, scope,
                              expected_status, negative
trace_matrix  TraceMatrix rows[] (requirement_ref, story_ref, criterion_ref,
                          test_case_ids[], covered), coverage (criteria/
                          requirements/stories total+covered+ratio+uncovered_refs),
                          orphan_criterion_refs[]  ← advertencia
datasets[]    Dataset    id DS-, entity_ref, name, rows[] (kind valid|invalid|
                         boundary, values{}, expectation, field_refs[], anchor)
execution_plan ExecPlan  suites[] (id, epic_ref, test_case_ids[], estimated_minutes,
                         depends_on_suite_ids[]), order[] (topológico),
                         totals (manual_minutes, by_type, by_priority)
questions_for_qa_lead[]  question, reason, audience, blocking, linked_to_ref, status
analysis      risks[] (RF sin caso ← hallazgo), observations[], coverage
metrics       tokens/cost/duration + contadores por tipo y prioridad
```

`api_available=false` ⇒ `test_cases` sin ninguno de tipo `authorization` **y** una
`Observation` explícita. La ausencia se declara; no se disimula.

---

## 5. Lo determinista (sin una sola llamada al LLM)

- **TRACE_MATRIX**: producto de `CRITERION_MAP` × `test_cases`. `criteria_ratio`,
  `uncovered_criterion_refs`, y la cadena `REQ-F- → US- → AC- → TC-` reconstruida
  desde `story.source_refs.requirement_refs`. Criterio sin caso → `orphan` +
  **advertencia**; `REQ-F-` sin ningún caso → **hallazgo** (`Risk`).
- **EXEC_PLAN**: una suite por épica; orden **topológico** por `story.dependencies`
  (mismo detector de ciclos que el Scrum); esfuerzo manual = suma de
  `estimated_minutes`, y esos minutos salen de una **tabla por tipo y prioridad en
  `target`**, no de una estimación del modelo — así dos ejecuciones del mismo plan
  dan el mismo número.
- **DATASET**: las filas y su `kind` los fija Python desde `FLD-`/`VAL-` (y los
  `SchemaField` si hay API); el LLM solo rellena **valores concretos verosímiles**.
- **AUTH_CASES**: descrito en §3.

---

## 6. Gate, semáforo, persistencia y API

- **Gate de entrada**: Scrum `ready_for_next_stage=true` → si no, `GateError` 409
  con mensaje accionable. Re-verificado en `LOAD_SOURCES`. Si se pasó
  `api_job_id`, se exige además que su artefacto exista y pertenezca a la cadena.
- **Semáforo** (`ready_for_next_stage`): sin bloqueantes pendientes **y** ≥1 caso
  **y** todo `TC-` con `criterion_ref` válido **y** cobertura de criterios de
  historias `must`/`should` = **100%** **y** ninguna `must` sin caso.
  QA es hoy el último eslabón: su `ready` significa **"el plan se puede ejecutar"**,
  y queda disponible para un futuro agente de automatización. Los criterios de
  `could`/`won't` sin caso son **advertencia**, no bloqueo — así el enunciado
  ("criterio sin caso = advertencia") y el umbral del 100% dejan de contradecirse
  (**QA-D5**).
- **Endpoints** `/api/v1/qa`: `POST /qa/jobs` (`scrum_job_id`, `api_job_id?`),
  `GET /qa/jobs`, `GET /qa/jobs/{id}`, `GET /qa/jobs/{id}/artifact`,
  `GET /qa/jobs/{id}/summary`, validaciones + `POST /qa/jobs/{id}/refine`,
  `GET /qa/scrum-plans` (planes listos elegibles) y los exports de §7.
  READ a nivel de router, FULL en escrituras.

---

## 7. Exports

- **CSV de casos** y **CSV de la matriz**: UTF-8 **con BOM** y delimitador `;`.
  No es capricho: así Excel en configuración regional española abre el archivo en
  columnas de un doble clic, sin asistente de importación. Cero dependencias
  nuevas (**QA-D6**).
- **PDF**: el informe completo del centro de comando (§5.1), reutilizando el
  `render` de cada sección con `forPrint: true`. El **YAML/CSV crudo lleva
  `printSkip`**; la matriz sí entra, resumida por historia.

---

## 8. Frontend (QA8)

Nav **Verificar** activa (`enabled: true`, icono `shield-check`, acento ámbar).
`QaResultView` sobre hub + panel universal. Secciones: Resumen · Casos (sub-pestañas
por tipo: Funcionales / Negativos / Borde / Autorización) · Trazabilidad · Datasets
· Plan de ejecución · Preguntas.

El **visual insignia es la matriz de trazabilidad**: criterios × casos con el hueco
visible, igual que la matriz de autorización lo es del Agente API. Badges por tipo
de caso con vocabulario único en `lib/test-case-kind.ts`, siguiendo el precedente
de `lib/reconciliation.ts`.

⚠️ El frontend tiene su propio `AGENTS.md`: **este Next.js no es el de la memoria
del modelo**. Antes de escribir código de QA8 hay que leer la guía pertinente en
`node_modules/next/dist/docs/`.

---

## 9. Decisiones (QA-D1…QA-D8) y riesgos

| # | Decisión | Propuesta |
|---|---|---|
| QA-D1 | Cómo entra el ApiArtifact (no es alcanzable hacia atrás) | `api_job_id` **opcional y explícito**, validado a la misma cadena; la UI lista los compatibles |
| QA-D2 | De dónde salen los límites de borde | Cita **verbatim** del texto de `VAL-`/`BR-`; si hay API, **el campo estructurado prevalece**. Sin ancla → pregunta |
| QA-D3 | Cortafuegos anti-invención | Nodo `CRITERION_MAP` determinista antes de TEST_DESIGN |
| QA-D4 | Prioridad del caso | Heredada del MoSCoW de la historia, **con un suelo**: un caso de `authorization` nunca baja de `alta` (un fallo de autorización es de seguridad, no de funcionalidad) |
| QA-D5 | Semáforo | Cobertura **100% en `must`/`should`**; `could`/`won't` sin caso = advertencia |
| QA-D6 | Excel | CSV UTF-8 con BOM y `;` (Excel lo abre nativo). `.xlsx` real exigiría `openpyxl`, dependencia nueva |
| QA-D7 | `AUTH_CASES` sin LLM | Derivado por plantilla de la matriz; `ambiguous=true` → pregunta, nunca caso |
| QA-D8 | Minutos de esfuerzo | Tabla por tipo/prioridad en `target`, no estimación del modelo (reproducible) |

**Riesgos**

- **Explosión combinatoria**: 40 historias × 5 criterios × 4 tipos ≈ 800 casos. Se
  acota con un **techo por criterio** (`target.max_cases_per_criterion`, default 6)
  y, si se poda, **se registra `Observation` con lo dejado fuera** — un tope
  silencioso se leería como cobertura completa.
- **Preguntas en avalancha**: 30 criterios no verificables son **una** pregunta con
  los refs enumerados, como en el Agente BD; no 30 que entierran la importante.
- **Datos de prueba con aspecto real**: los valores los inventa el LLM por
  definición (son ejemplos). Se marcan `origin=derived` y **jamás** se emiten datos
  personales verosímiles para columnas que el BD/API marcaron `pii`; para esas se
  usan valores obviamente sintéticos.

---

## 10. Plan de implementación por bloques

Tests mockeados, commit+push por bloque.

- **QA0** este documento + decisiones abiertas.
- **QA1** contrato `QaArtifact v1.0.0` + fixture + round-trip + candados
  (`criterion_ref` obligatorio, `boundary` sin `evidence` inválido).
- **QA2** gate + grafo + `LOAD_SOURCES` (cadena + `api_job_id` opcional) + stubs.
- **QA3** `CRITERION_MAP` + `TEST_DESIGN` + `EDGE_CASES` + `AUTH_CASES` (LLM
  mockeado; test de que un `criterion_ref` inventado se descarta con `Observation`).
- **QA4** `DATASET` + `TRACE_MATRIX` + `EXEC_PLAN` deterministas (+ ciclos).
- **QA5** `CRITIQUE` + `QUESTION_GEN` (duplicados, huérfanos, no verificables).
- **QA6** `ASSEMBLE`/`PERSIST` + servicio + API `/qa/*` + refine + gate 409.
- **QA7** exports CSV (casos + matriz).
- **QA8** frontend: nav Verificar activa, `QaResultView`, badges, PDF.
- **Cierre** pipeline completo con `ScrumArtifact` sintético rico + LLM fake →
  `QaArtifact` con cobertura verificada + seed de demostración.

> **Continúa en la PARTE II (QA9)**: los modos de entrada B (sistema del
> inventario) y C (exploración de una URL viva). Todo lo anterior describe el
> **Modo A**, único implementado hasta `d99c068`.

---

# PARTE II — QA9: modos de entrada alternativos (B y C)

> Estado: **DISEÑO PROPUESTO, sin implementar.** Nada de esta parte existe en el
> código a fecha de HEAD `d99c068`. Se escribe primero, como QA0, porque los dos
> modos tocan la garantía central del agente y —el Modo C— abren una superficie de
> seguridad nueva.

---

## 11. El problema real: los dos modos amputan el cortafuegos

La PARTE I entera se sostiene sobre una frase: **todo `TC-` ancla a un `AC-` que
existe**. `CRITERION_MAP` puede cerrar el universo de criterios porque hay un
`ScrumArtifact` que los enumera, y el `ScrumArtifact` existe porque alguien acordó
una especificación.

**Los modos B y C no tienen `ScrumArtifact`.** No es un detalle de plomería: es la
amputación del órgano que hace confiable al agente. Un diseño ingenuo —"acepta un
`system_id` o una URL y genera casos"— dejaría al LLM eligiendo *qué* probar, que
es exactamente lo que §0 prohíbe. Sin sustituto del ancla, los modos B y C serían
una máquina de fabricar cobertura falsa a escala.

### 11.1 La distinción que lo ordena todo: especificación vs observación

| | **Modo A** (Scrum) | **Modos B y C** |
|---|---|---|
| El ancla es | **intención**: `AC-042` dice qué *debe* pasar | **observación**: la columna es `NOT NULL`, el input tiene `maxlength=11` |
| El caso afirma | "el sistema **debe** hacer X" | "el sistema **hace** X hoy" |
| Un caso en rojo significa | **el sistema está mal** | **algo cambió** — puede ser regresión o cambio deliberado |
| Su valor | verificar lo acordado | fijar el comportamiento actual antes de tocarlo |
| Nombre clásico | pruebas de aceptación | *characterization tests* / pruebas de caracterización |

Esta distinción **no puede quedarse en la cabeza de quien generó el plan**, porque
determina cómo se lee un fallo. Un QA lead que mezcla una suite de observación con
una de especificación pierde la capacidad de distinguir "hay un bug" de "el sistema
evolucionó", y a partir de ahí la suite entera se degrada a ruido que alguien
acabará marcando como *skip*.

**Por eso `evidence_class` es un campo obligatorio por caso** (`specification` |
`observation`), viaja en el CSV, se muestra como badge en la UI y aparece en el
PDF. Es la aportación más importante de QA9 al contrato, por delante de cualquier
nodo nuevo.

### 11.2 Los modos son excluyentes por job

Un job = un modo. Un `QaArtifact` no mezcla casos de especificación y de
observación. Razón: el semáforo, la cobertura y el denominador de la matriz
significan cosas distintas en cada modo (§12.7, §13.9), y un artefacto con dos
semánticas dentro obligaría a cualificar cada número al leerlo.

**Fuera de alcance, con su motivo:** la combinación *"Modo A + inventario"*
—diseñar desde el plan Scrum y además señalar qué módulos existentes se ven
afectados— es **selección de regresión**, no diseño de pruebas: necesita una suite
previa de la que seleccionar, y hoy no existe ninguna. Se anota como sucesor
natural una vez que los modos B/C hayan poblado esa suite.

---

## 12. Modo B — desde un sistema del inventario

### 12.1 Qué es

Entrada: un `inventory_systems.id` (`destino` | `legado` | `externo`) y una
selección de sus **activos vigentes**. Salida: un plan de pruebas que **fija el
comportamiento observable del sistema tal como está inventariado**, para poder
tocarlo sin romperlo en silencio. Es la pieza que le faltaba al giro brownfield de
INV0→INV6: RECONCILE evita **rediseñar** lo que ya existe; el Modo B evita
**romperlo**.

### 12.2 `ASSET_MAP`: el sustituto del criterio

Gemelo de `CRITERION_MAP`, `MODEL_MAP` y `RESOURCE_MAP`. Enumera **en Python, antes
de gastar un token**, los *elementos anclables* de los activos seleccionados. Cada
entrada del *map* lleva un `anchor_ref` estable y su evidencia; el LLM redacta
*cómo* se prueba, nunca elige *qué* hay.

**Jerarquía de calidad del ancla** — el orden importa, porque decide qué clase de
caso se puede emitir:

| Nivel | Fuente | Qué es | Casos que habilita | `origin` |
|---|---|---|---|---|
| **1** | `db_schema` → constraint | Hecho estructural duro: `NOT NULL`, `CHECK`, `UNIQUE`, FK, longitud del tipo físico | `boundary`, `negative` | `stated` |
| **2** | `document` → `ExtractedFunctionality`/`ExtractedDecision` | Afirmación de comportamiento **con `evidence` verbatim** y `source_ref` a un `element_id` real | `functional`, `negative` | `stated` |
| **3** | `api` → endpoint (`method` + `path`) | Superficie: la operación existe | **solo** alcanzabilidad / *smoke* | `derived` |
| **4** | `module` → nombre de funcionalidad | Una etiqueta sin contenido | **ninguno → pregunta** al QA lead | — |

Sobre el **nivel 1**: la longitud no viene como campo. `_column_from_artifact`
guarda `type` (el tipo **físico** renderizado, `VARCHAR(11)`) y `logical_type`. El
límite se obtiene **parseando el tipo físico en Python** (`VARCHAR(11)` → longitud
11), nunca preguntándoselo al modelo. Misma regla de siempre: el modelo decide
semántica, Python decide la forma.

Sobre el **nivel 4**: un activo `module` promovido trae nombres de funcionalidades
y entidades, sin comportamiento. Un caso construido sobre eso sería redacción pura.
Se declara `not_testable` con su pregunta, exactamente como "el sistema debe ser
rápido" en el Modo A.

### 12.3 Lo que el Modo B NO puede producir (y por qué está probado)

**Un activo `api` del inventario no tiene semántica.** `api_surface_from_artifact`
guarda `method`, `path`, `operation_id`, `kind`, `purpose`, `resource_ref`,
`deprecated`. **No guarda códigos de estado, ni esquemas de petición/respuesta, ni
matriz de autorización** — y es deliberado: "un YAML de mil líneas dentro de un
activo no lo hace más comparable".

Consecuencia dura, impuesta en `ASSET_MAP`: desde un activo `api` **no se emite un
caso que afirme un código de respuesta**. `POST /api/v1/guias → 201` sería
convención disfrazada de evidencia — el error de §0 en su forma más pura, porque
además *parecería* razonable a quien revise. Se emite alcanzabilidad ("la operación
existe en la superficie inventariada") y nada más.

**`AUTH_CASES` se salta siempre en Modo B**, salvo que se indique además un
`api_job_id` real (§12.6). El nodo ya sabe declarar su ausencia con motivo; se
reutiliza tal cual.

### 12.4 `importado` vs `validado`: modula la confianza, no bloquea

Todo activo nace `importado`: cargado, pero **nadie lo ha mirado**. INV lo dice de
lo suyo: *"reutilizar una tabla que un parser dedujo mal es peor que no tener el
dato"*.

Aquí la conclusión es **distinta, y por una razón concreta**: un caso de prueba
generado sobre un constraint mal parseado **falla ruidosamente al ejecutarse**. No
es una mentira silenciosa: es un fallo que alguien investiga. La asimetría de §0
—ausencia visible vs mentira que pasa— no se cumple en esta dirección, así que
bloquear sería desproporcionado.

Decisión: `validation_status` **viaja en el ancla de cada caso**, modula
`confidence` (un ancla `validado` produce un caso con más confianza que uno
`importado`) y, si la suite se apoya mayoritariamente en activos `importado`,
`CRITIQUE` emite un **`Risk`** que lo dice con el porcentaje. Se informa; no se
esconde y no se bloquea.

### 12.5 Alcance: la explosión aquí es peor que en el Modo A

15 tablas × 20 columnas = 300 columnas, casi todas con un `NOT NULL` y poco más.
Generar 300 casos sería convertir el agente en una fábrica de ruido.

Tres frenos, todos deterministas:
1. **Selección explícita de activos** en la petición (`asset_ids`), y opcionalmente
   de tablas/módulos dentro de ellos. El alcance lo fija el QA lead, no el agente.
2. **Techo por elemento** (`target.max_cases_per_anchor`, hermano de
   `max_cases_per_criterion`).
3. **`NOT NULL` sin más no genera caso propio por defecto**: se agrupa en **un**
   caso de obligatoriedad por tabla que enumera las columnas. Un caso por columna
   sería cobertura inflada, que es una forma de mentira sobre el tamaño del plan.

Y la regla de la casa: **lo que se pode se registra con su ref en una
`Observation`**. Un tope silencioso se leería como cobertura completa.

### 12.6 Pipeline B

```
LOAD_INVENTORY (guard) → ASSET_MAP (det.) → TEST_DESIGN (map, LLM)
  → EDGE_CASES (LLM anclado) → AUTH_CASES (det., casi siempre ausente)
  → DATASET → TRACE_MATRIX → EXEC_PLAN → CRITIQUE → QUESTION_GEN
  → ASSEMBLE → PERSIST
```

**La cola es la misma que la del Modo A.** Nueve de los doce nodos operan sobre
"entradas con ancla" y no sobre criterios; lo único que cambia es la cabeza
(`LOAD_INVENTORY` + `ASSET_MAP` en vez de `LOAD_SOURCES` + `CRITERION_MAP`).
Implementación: **tres constructores de grafo que comparten la lista de nodos de
cola**, seleccionados por modo en el servicio. No se toca `build_linear_graph`.

`LOAD_INVENTORY` reutiliza `ai.inventory.loader`, pero **con `system_id`
obligatorio**: la resolución "el único sistema `destino`" es aceptable para
RECONCILE (es una fase auxiliar de un diseño) e inaceptable aquí (es la entrada
completa del job). Sin sistema no hay job: `GateError` 409, no un plan vacío.

`api_job_id` sigue siendo aceptable y opcional también en Modo B: si el sistema
inventariado corresponde a un contrato de API ya diseñado, la matriz de
autorización vuelve a estar disponible y `AUTH_CASES` produce. Se valida que el
artefacto exista y tenga hash, igual que en QA-D1.

### 12.7 Semáforo B: un `ready` que afirma otra cosa

Modo A: *"el plan cubre la especificación acordada"*.
Modo B: **"el plan fija los elementos anclables de los activos en alcance"**.

Condiciones: sin bloqueantes pendientes **y** ≥1 caso **y** todo caso con
`observed_anchor` resoluble a un elemento real del activo **y** cobertura de
elementos de **nivel 1 y 2** ≥ umbral. Los de nivel 3 (superficie) cuentan aparte;
los de nivel 4 son pregunta, no hueco.

El artefacto **escribe la frase**, no solo el booleano: leyendo un `ready=true` hay
que poder saber qué se está certificando.

---

## 13. Modo C — exploración de una URL viva

### 13.1 Qué observa

Un navegador headless recorre en **solo lectura** una aplicación desplegada y
registra su superficie: rutas alcanzables, formularios, campos con sus atributos de
validación, tablas, navegación y textos.

Lo valioso —y la razón de que el modo exista— es que **los atributos de validación
del HTML son hechos estructurales tan duros como un `CHECK` de la BD**:

```html
<input name="ruc" required maxlength="11" pattern="[0-9]{11}">
```

Eso ancla, con la misma solidez que una `VAL-` citada verbatim, casos de
`required`, `length` (11 y 12) y `format`. El ancla es el atributo + el selector +
la URL + el instante de captura. Un rótulo en pantalla ("Monto máximo: 5000") se
cita **verbatim como evidencia de texto**, con exactamente el mismo estatus que el
texto libre de una `VAL-` del EF en QA-D2: es una afirmación citable, no un dato
estructurado, y por tanto de menor precedencia.

### 13.2 Las cinco capas fail-closed

El precedente obligatorio es INV2 (`app/services/introspection_service.py`): cuatro
capas independientes para conectarse a bases de producción. Modo C conduce un
**navegador autenticado contra una aplicación viva**, que es al menos igual de
peligroso, así que hereda las cuatro y añade una quinta que INV2 no necesitaba.

**Capa 1 — El cliente NUNCA envía una URL.** Envía un **alias** que debe existir en
`QA_EXPLORE_TARGETS` (settings/`.env`). Es el argumento literal de INV2: *"si el
alias viniera del cliente como DSN, cualquiera con permiso de escritura podría
apuntar el servidor a un host arbitrario — un SSRF de manual"*. Con alias, el
conjunto de destinos posibles lo fija **quien despliega**, no quien llama. Y hay un
segundo motivo, propio de este modo: el alias transporta también la **credencial de
la cuenta de QA**, que por definición no puede venir del cliente.

**Capa 2 — Allowlist de hosts.** `QA_EXPLORE_ALLOWED_HOSTS`. Lista vacía significa
**"nada autorizado"**, no "todo". Sin allowlist, el módulo no navega a ninguna
parte.

**Capa 3 — Solo lectura impuesta por el navegador, no por la intención.** Esta es
la traducción de `default_transaction_read_only=on`, y su matiz es todo:

> *"No se depende de que las consultas sean SELECT: el propio Postgres rechaza
> cualquier escritura."* — INV2

El equivalente aquí **no** es "solo pulsamos enlaces" (eso es intención, y un
`<a>` puede disparar un `fetch`). Es interceptar la red del contexto y **abortar
toda petición cuyo método no sea `GET`/`HEAD`**, más `route.abort()` de descargas y
del selector de ficheros. Un submit accidental muere **dentro del navegador, antes
de salir**. Además: no se escribe en ningún campo, no se pulsan botones de envío, y
el contexto se crea con `permissions: []`.

**Capa 4 — La credencial nunca sale.** Ni en el artefacto, ni en el `origin_ref`,
ni en un log, ni en la respuesta de la API. Se reutiliza el criterio de
`redact_dsn`. **Corolario propio del navegador: no se guardan capturas de pantalla
en el artefacto.** Una captura de una app autenticada contiene datos reales de
producción y el artefacto se exporta a PDF y a CSV. La evidencia es la **cadena del
atributo y el selector**, no una imagen.

**Capa 5 — La allowlist se re-verifica en CADA navegación.** Una base de datos no
redirige; una aplicación web sí. Un `302` a otro host, un enlace externo, un
`window.location`: cada uno es una salida de la jaula. Toda navegación revalida
host + esquema (`http`/`https` únicamente; `file:`, `data:`, `blob:` y `javascript:`
rechazados), y lo que cae fuera **no se sigue y se registra**. Se anota el riesgo
residual de *DNS rebinding* (el host allowlisted resolviendo a otra IP entre la
comprobación y la conexión) como pendiente conocido: mitigarlo exige fijar la IP
resuelta, y se documenta en vez de fingir que no existe.

### 13.3 Lo que el Modo C NO puede producir

- **Nada que exija cambiar estado.** Es de solo lectura por construcción: no hay
  casos de alta, edición ni borrado *verificados*; puede describir el formulario,
  no su resultado.
- **Nada sobre lo que el sistema *debería* hacer.** Solo lo que muestra.
- **Nada detrás de un flujo que requiera enviar datos.** Si media pantalla vive
  tras un `POST`, esa mitad **no se explora, y el artefacto lo dice** con las rutas
  que quedaron inalcanzables. Un explorador que calla lo que no vio produce una
  cobertura optimista, que es la peor clase.
- **Casos de autorización.** Requieren la matriz del `ApiArtifact`. Explorar con
  dos cuentas y comparar lo visible sería tentador y es exactamente el terreno
  donde inventar es más caro (§3): queda **fuera de v1**.

### 13.4 `SURFACE_MAP`

El tercer cortafuegos. Toma la observación cruda del explorador y fija los
elementos anclables: por página, sus formularios; por formulario, sus campos; por
campo, sus atributos de validación **presentes** (nunca ausentes: que no haya
`maxlength` no significa que no haya límite, significa que no se observó). Lo que
el LLM recibe es esa lista cerrada.

### 13.5 Pipeline C

```
EXPLORE (guard, sin LLM) → SURFACE_MAP (det.) → TEST_DESIGN (map, LLM)
  → EDGE_CASES (LLM anclado) → [AUTH_CASES ausente] → DATASET
  → TRACE_MATRIX → EXEC_PLAN → CRITIQUE → QUESTION_GEN → ASSEMBLE → PERSIST
```

`EXPLORE` **no llama al LLM**: es recorrido y lectura del DOM. El modelo entra en
`TEST_DESIGN` y `EDGE_CASES`, ya con el universo cerrado. Todo caso de Modo C nace
con `automation_hint = ui`: es lo único que se observó.

### 13.6 Presupuesto y radio de acción

Un crawler sin techo contra una aplicación viva es un generador de carga. Topes en
`settings`, efectivos en `target`, y **reportados**: `QA_EXPLORE_MAX_PAGES` (default
50), `QA_EXPLORE_MAX_DEPTH` (3), `QA_EXPLORE_TIMEOUT_MS` por página (15 000),
`QA_EXPLORE_TOTAL_BUDGET_S` (300) y restricción a **mismo origen**. Lo que quede sin
recorrer al agotarse el presupuesto se enumera en una `Observation` con las URLs
pendientes — nunca se trunca en silencio.

### 13.7 Entorno: lo que hoy falta (verificado)

- **Playwright NO es dependencia del backend**: `import playwright` →
  `ModuleNotFoundError` en `backend/.venv`; no aparece en `requirements.txt`.
  QA9 añade `playwright` (pinneado) a los requisitos del backend.
- En `frontend/node_modules` hay `playwright@1.62.1`, pero es **transitiva de
  `vitest`** y no está declarada en `package.json`. No cuenta como dependencia del
  proyecto y no es la del backend.
- Los navegadores están descargados (`~/.cache/ms-playwright/chromium-1234`) pero
  **Chromium no arranca**: falta `libnspr4` y no hay `sudo` sin contraseña. Requiere
  `sudo npx playwright install-deps chromium` en el host.
- **`QA_EXPLORE_ENABLED` nace en `false`**, igual que
  `INVENTORY_INTROSPECTION_ENABLED`. Un módulo que conduce navegadores contra
  producción no se activa por defecto al desplegar.
- **Tests sin navegador**: la suite ejerce `SURFACE_MAP` y el guard contra **HTML
  guardado en fixtures**, nunca contra un navegador vivo. El cortafuegos
  `sin_api_real` tendrá un hermano, `sin_navegador_real`, autouse por el mismo
  motivo: la protección no puede depender de que cada test se acuerde de pedirla.

### 13.8 Permisos: la decisión peligrosa es de despliegue, la segura es de QA

Registrar un alias (elegir **qué** aplicaciones son explorables y con qué cuenta)
es un acto de **despliegue**: vive en `settings`, y por tanto es de `admin`.
Lanzar una exploración contra uno de esos destinos ya acotados es trabajo de
**`qa` FULL**.

No se copia el `admin` estricto de la introspección de BD porque la naturaleza del
riesgo es distinta: allí el cliente elegía una base entera de producción; aquí el
radio ya está cerrado por alias + allowlist + solo-lectura antes de que el QA lead
toque nada. Exigir `admin` para ejecutar convertiría la función en inusable por su
único usuario. **La matriz de `permissions.py` no se toca.**

### 13.9 Semáforo C

*"El plan fija la superficie observada de la aplicación explorada, en el alcance
recorrido."* Con la coletilla obligatoria: **y enumera lo que no pudo recorrer**.
Sin bloqueantes **y** ≥1 caso **y** todo caso con `surface_anchor` (URL + selector +
atributo + instante) **y** exploración terminada por agotar la superficie, no por
agotar el presupuesto — si fue por presupuesto, `ready` sigue siendo posible pero el
artefacto lo declara y `CRITIQUE` emite `Risk`.

---

## 14. Contrato `QaArtifact v1.1.0`

**Retrocompatible.** Todo lo nuevo es opcional o tiene default, así que los
artefactos v1.0.0 ya persistidos siguen validando sin tocarlos — mismo criterio con
el que INV4 metió `reconciliation` en tres contratos sin romper ninguno.

```
mode          QaMode     specification | inventory | exploration
                         DEFAULT specification → los artefactos v1.0.0 existentes
                         se leen como Modo A sin migrar nada
source        union discriminada por `mode`:
                ScrumSource      (v1.0.0 tal cual: scrum/ef/api + ready_snapshot)
                InventorySource  system_id, system_name, system_kind,
                                 asset_refs[] (id + type + name + version +
                                 validation_status), api_job_id?, captured_at
                ExplorationSource target_alias, base_url (SIN credencial),
                                 pages_visited, pages_skipped[] (url + motivo),
                                 budget_exhausted, explored_at, browser_version
target        + max_cases_per_anchor, + exploration_budget{...}
test_cases[]  + evidence_class  specification | observation   ← OBLIGATORIO
              + observed_anchor  Optional[AssetAnchor | SurfaceAnchor]
                                 (discriminado por `kind`)
   AssetAnchor    kind="asset", asset_id, asset_type, system_id, element_path
                  ("guias.numero_guia"), constraint_kind, evidence (verbatim),
                  validation_status
   SurfaceAnchor  kind="surface", url, selector, attribute, value,
                  evidence (verbatim), observed_at
trace_matrix  TraceRow: `story_ref`/`criterion_ref` pasan a Optional; se añaden
              `anchor_ref` + `anchor_kind` (criterion|asset_element|surface_element).
              En Modo A no cambia una coma.
              Coverage: se añaden anchors_total/covered/ratio + uncovered_anchor_refs
```

**Lo que el contrato prohíbe** (mismo criterio que la PARTE I: impide invención y
omisión muda, permite representar defectos reportables):

- `evidence_class=observation` **sin** `observed_anchor` → `ValidationError`.
- `evidence_class=specification` **con** `observed_anchor` → `ValidationError`.
  Son mundos distintos; mezclarlos en un caso lo haría ilegible.
- `mode=inventory|exploration` con `criterion_ref` en cualquier caso → los criterios
  no existen en esos modos. La puerta de atrás queda cerrada **por el tipo**, igual
  que los casos de autorización sin `ApiArtifact` en v1.0.0.
- `SurfaceAnchor` sin `evidence` verbatim, o `AssetAnchor` con `element_path` que no
  resuelve contra los `asset_refs` declarados en `source`.
- `mode=exploration` con casos `type=authorization` (§13.3).

---

## 15. La migración que QA9 sí necesita

Hasta aquí, QA y API se han construido **sin tocar la base**. QA9 rompe esa racha, y
conviene decir por qué en vez de forzar un apaño.

`agent_jobs.input_job_id` es una **FK a `agent_jobs.id`**. La entrada del Modo B es
un `inventory_systems.id` y la del Modo C un alias de configuración: **ninguno es un
job**. Meterlos ahí es imposible; meterlos en `title` (texto de presentación) o en
`source_type` (`String(16)`) sería exactamente el tipo de sobrecarga que este
código no hace. Y guardarlos **solo** dentro del artefacto tiene un fallo concreto:
un job que **falla** no tiene artefacto, y entonces nadie puede saber contra qué
sistema o qué destino se lanzó — justo cuando más falta hace.

**Migración `0011`: `agent_jobs.input_params` JSONB nullable.** "Los parámetros de
entrada que no son un job". La usan Modo B (`system_id`, `asset_ids`), Modo C
(`target_alias`) y —**cerrando de paso el hueco conocido**— el `target_system_id` de
Arquitectura/BD/API, que hoy existe en los tres `state.py`, lo leen los tres
`*_nodes.py` y **nadie lo rellena**, dejando a RECONCILE dependiendo de que haya
exactamente un sistema `destino`.

---

## 16. Decisiones (QA-D9…QA-D18) y riesgos

| # | Decisión | Propuesta |
|---|---|---|
| QA-D9 | Qué sustituye al criterio | `ASSET_MAP` (B) y `SURFACE_MAP` (C), deterministas y previos al LLM. Mismo patrón que `CRITERION_MAP`/`MODEL_MAP`/`RESOURCE_MAP` |
| QA-D10 | Especificación vs observación | `evidence_class` **obligatorio por caso**; visible en UI, CSV y PDF. Un fallo se lee distinto según cuál sea |
| QA-D11 | Mezcla de modos | **Excluyentes por job.** La combinación A+inventario es *selección de regresión* y queda fuera, por falta de suite previa |
| QA-D12 | Semántica desde un activo `api` | **Prohibida**: la superficie inventariada no guarda códigos ni esquemas. Solo alcanzabilidad |
| QA-D13 | `importado` vs `validado` | Modula `confidence` + `Risk` si la suite se apoya en no validados. **No bloquea**: un ancla mal parseada falla ruidosamente, no miente en silencio |
| QA-D14 | Destino del Modo C | **Alias, nunca URL del cliente** (SSRF) + allowlist de hosts + re-verificación en cada navegación |
| QA-D15 | Solo lectura del Modo C | **Abortar en red todo método ≠ GET/HEAD**, no "solo pulsamos enlaces". Traducción de `default_transaction_read_only=on` |
| QA-D16 | Capturas de pantalla | **No se guardan.** Una captura autenticada lleva datos reales de producción a un PDF exportable |
| QA-D17 | Permisos | Registrar alias = `admin` (despliegue); explorar = `qa` FULL (runtime). Matriz sin tocar |
| QA-D18 | Persistencia | Migración `0011` `input_params` JSONB; cierra además el `target_system_id` huérfano de INV |

**Riesgos**

- **Suite de observación tratada como de especificación.** El riesgo de fondo del
  bloque. Mitigación: `evidence_class` obligatorio + badge + columna en el CSV +
  frase explícita del semáforo. Si algo de esto se recorta al implementar, el
  bloque pierde su justificación.
- **Cobertura optimista en Modo C.** Lo que hay tras un `POST` no se ve. Mitigación:
  `pages_skipped[]` con motivo y `Risk` cuando el presupuesto se agota.
- **Ruido a escala en Modo B.** 300 columnas → 300 casos. Mitigación: selección
  explícita de activos, techo por ancla y agrupación de `NOT NULL` por tabla.
- **Chromium en el host.** Hoy no arranca (`libnspr4`). El bloque QA13 se diseña
  para ser verificable **sin navegador** (fixtures HTML); solo QA14 lo necesita.
- **DNS rebinding** entre la comprobación de allowlist y la conexión. Documentado,
  no mitigado en v1: exigiría fijar la IP resuelta.

---

## 17. Plan de bloques (QA9→QA16)

Tests mockeados, `pytest`/`tsc` en verde, commit+push por bloque. **El Modo A debe
seguir verde en todos.**

- **QA9** este documento + decisiones QA-D9…QA-D18.
- **QA10** contrato `QaArtifact v1.1.0`: `mode`, `evidence_class`, `source` como
  unión discriminada, `AssetAnchor`/`SurfaceAnchor`, `TraceRow` generalizado.
  Candados: observación sin ancla inválida, criterio en modo B/C inválido, y
  **round-trip de un artefacto v1.0.0 existente que sigue validando**.
- **QA11** migración `0011` (`input_params`) + repositorio + `LOAD_INVENTORY` con
  `system_id` obligatorio y `GateError` 409.
- **QA12** `ASSET_MAP`: jerarquía de anclas, parseo del tipo físico a longitud,
  agrupación de `NOT NULL`, techo por ancla. Test candado: **un activo `api` no
  produce ningún caso que afirme un código de estado**.
- **QA13** **El guard del Modo C, antes que el navegador.** Alias, allowlist,
  esquemas, redacción, topes de presupuesto y `sin_navegador_real` autouse. Sin una
  línea de Playwright: se construye la valla antes de meter al animal.
- **QA14** `EXPLORE` con Playwright (dependencia nueva, `QA_EXPLORE_ENABLED=false`)
  + `SURFACE_MAP`, ejercidos contra **HTML de fixtures**. Test candado: una petición
  `POST` interceptada se aborta.
- **QA15** cabeceras de grafo B y C sobre la cola compartida + servicio + API
  (`POST /qa/jobs` con `mode`) + semáforos diferenciados + `GET /qa/explore-targets`
  (alias autorizados, **sin credenciales**, hermano de `GET /inventario/sources`).
- **QA16** frontend: selector de modo en `/agents/qa/new`, badge de
  `evidence_class`, ancla visible en cada caso, `pages_skipped` en el hub, columna
  nueva en el CSV.
- **Cierre** los tres modos sobre el mismo seed, con LLM y navegador falsos.
