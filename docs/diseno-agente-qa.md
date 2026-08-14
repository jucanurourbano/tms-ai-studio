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
