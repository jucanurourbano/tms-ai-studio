# TMS AI Studio — Memoria del proyecto

> Fuente de verdad para **todas** las sesiones de trabajo. Leer completo antes de
> tocar código. Si una decisión cambia, se actualiza aquí primero.

---

## 1. Qué es

**TMS AI Studio** es una plataforma interna de **Urbano TI** que asiste al ciclo de
vida del desarrollo de software mediante **agentes de IA** — el *Intelligent
Software Delivery Framework (ISDF)*.

**Agentes previstos:** EF, Scrum, Arquitectura, BD, API, Backend, Frontend, QA,
DevOps + un **Orquestador** que coordina el flujo entre ellos.

**Estado:** Agente EF **completo** (backend + frontend). Agente Scrum **completo**
(backend + frontend; bloques B0→B8 implementados, ver §4 y
`docs/diseno-agente-scrum.md`). Persistencia **generalizada** a tablas `agent_*`
multi-agente (D1). **Autenticación real** (JWT + usuarios con roles) y **permisos
por fase ISDF** (matriz rol → módulo/nivel + accesos adicionales) protegiendo
toda la API de agentes y el frontend (ver §6 y §6.1). Agente **Arquitectura** **completo**
(backend + frontend; bloques A0→A7 implementados, ver §5 y
`docs/diseno-agente-arquitectura.md`). Agente **BD** **completo** (backend +
frontend; bloques BD0→BD8 implementados, ver §5.2 y `docs/diseno-agente-bd.md`).
Agente **API** **completo** (backend + frontend; bloques API0→API9
implementados, ver §5.3 y `docs/diseno-agente-api.md`). **MÓDULO INVENTARIO DE
SISTEMAS + fase RECONCILE** **completo** (bloques INV0→INV6, ver §5.4): el ISDF
deja de ser greenfield y reconcilia lo que propone contra lo que ya existe.
Agente **QA** **completo** (backend + frontend; bloques QA0→QA8 implementados,
ver §5.5 y `docs/diseno-agente-qa.md`). Del **QA9** —modos de entrada B (sistema
del inventario) y C (exploración solo-lectura de una URL viva)— están implementados
el **guard del Modo C** (bloque **QC3**: `ai/agents/qa/explore/`), sus **fixtures y
saneador** (bloque **QC4**: `tests/fixtures/qa_explore/` + `sanitize.py`), el
**extractor determinista de anclas** (bloque **QC4.5**: `extract.py`) y el
**navegador con su capa 3 de red** (bloque **QC5**: `driver.py` + `network.py`,
Playwright pinneado); **ninguna exploración real todavía**, la suite entera corre
contra HTML de fixtures y sintético. El resto sigue **diseñado y sin implementar**: ver §5.5 *in fine*, la
PARTE II de `docs/diseno-agente-qa.md` y `docs/diseno-qa-modo-c.md`.

**💰 CONTROL DE GASTO (GAS1+GAS2) implementado (2026-08-28).** Toda llamada al
modelo pasa ahora por un libro mayor (`llm_spend`, migración `0011`) y un **freno
duro** que comprueba el tope **antes** de gastar; sin libro mayor legible **no se
llama**. Es el instrumento con el que se van a medir el proveedor local y los
recortes de nodos, y de paso cierra dos agujeros medidos: los jobs `FAILED`
reportaban \$0 habiendo gastado (un cuarto del historial) y QA reportaba
duraciones de **56 años**. **GAS2** le pone la ventana:
`GET /api/v1/gasto/mensual` con desglose **por nodo del grafo** —el antes/después
con el que se demuestra un recorte— y la fracción de la cifra que es estimación,
porque un tope que no se mira se conoce bloqueando. Ver §5.7 y
`docs/diseno-control-de-gasto.md`.

**⏸️ CAMBIO DE PRIORIDAD (2026-08-27).** Los bloques restantes del Modo C
(**QC1, QC2, QC6, QC7, QC8**) quedan **APLAZADOS, no cancelados**: pegar un link
y sacar casos ya es producto de mercado (TestCollab, CoTester, CloudQA) y encima
por visión, no por DOM — es la parte más *commodity* del proyecto. La ventaja
real es la **cadena ISDF completa** trazada a las `BR-`/`VAL-` de Procesos, y
lleva semanas congelada por falta de saldo de API. Prioridad nueva: un
**proveedor LLM local (Ollama)** que permita validarla con corridas reales, sin
gastar y sin que ningún dato de Urbano salga de la máquina — ver §5.6 y
`docs/diseno-llm-local-ollama.md`. Lo ya construido del Modo C **no se toca**.
Siguiente eslabón del ISDF, cuando la cadena esté validada: **Agente Backend**.

---

## 2. Convenciones (obligatorias)

- **Clean Architecture**, flujo de dependencias en un solo sentido:
  `api → services → repositories → models`.
- **`ApiResponse` en TODO endpoint** — envelope uniforme `{success, message, data}`
  (`backend/shared/responses/api_response.py`).
- **Código y docstrings en español.**
- **Claves JSON de los artefactos en inglés, valores en español.**
- **Prefijo `/api/v1`** para toda ruta.
- **Formato:** `black` + `isort`.
- **Tests:** `pytest` con **mocks** (nunca API real).

---

## 3. Agente EF (diseño validado)

Pipeline **LangGraph**:

```
INGEST → PARSE → SEGMENT → EXTRACT → CONSOLIDATE → INFER → INTERPRET
       → CRITIQUE → QUESTION_GEN → ASSEMBLE → PERSIST
```

- **EXTRACT** hace *map* por dimensiones, con **structured output** —
  **NUNCA** parsear JSON libre.
- **Entrada dual:**
  - Documento `.docx` / `.pdf` → **CIR**.
  - Texto libre → **TextToCIRAdapter** (single-shot bajo umbral **4K tokens**).
- **Todo ítem** lleva: `id`, `source_ref`, `evidence` (verbatim), `confidence`,
  `origin` (`stated` | `derived`).
- **EFArtifact v1.2.0** incluye:
  - `systems_interpretation`: `what_process_requests`, `scope_for_systems`,
    `apparent_out_of_scope`, `interpretation_assumptions`.
  - **Preguntas** con: `audience` (`negocio` | `tecnico`), `reason`, `blocking`,
    `linked_to_ref`.

---

## 4. Agente Scrum (diseño validado)

> Diseño completo en **`docs/diseno-agente-scrum.md`**. Consume un `EFArtifact`
> v1.2.0 **listo** (`ready_for_next_stage=true`) y produce los insumos de
> planificación ágil del equipo de Sistemas. Reutiliza el patrón del EF.

Pipeline **LangGraph**:

```
LOAD_EF → EPICS → STORIES → CRITERIA → ESTIMATE → PRIORITIZE
        → SPRINT_PLAN → CRITIQUE → QUESTION_GEN → ASSEMBLE → PERSIST
```

- **STORIES**/**CRITERIA**/**ESTIMATE** son *map* con **structured output**.
  **SPRINT_PLAN** es **determinista** (bin-packing por capacidad, respeta
  dependencias). **Prohibido inventar requisitos**: si falta base en el EF →
  pregunta al PO (no se crea la historia).
- **Contrato `ScrumArtifact v1.0.0`** (claves inglés / valores español; todo ítem
  con `id`/`source_ref(s)`/`confidence`/`origin`): `source` (referencia al job EF
  de origen + `ef_artifact_hash`), `epics[]`, `stories[]` (formato
  "Como/quiero/para", `source_refs` a RF/procesos/reglas, `acceptance_criteria`
  Gherkin, `story_points` Fibonacci + `estimation_rationale`/`confidence`,
  `priority` MoSCoW, `dependencies`, `tags`/`external_key` compatibles ClickUp),
  `product_backlog` (orden), `sprints[]` (capacidad/puntos), `unassigned_story_ids`,
  `questions_for_po[]` (`audience`/`reason`/`blocking`/`linked_to_ref`),
  `analysis` (riesgos/observaciones/cobertura), `metrics`.
- **Gate de entrada:** el servicio verifica `ready_for_next_stage=true` del EF
  **antes de crear el job**; si no está listo → rechazo `4xx` con mensaje claro
  (completar preguntas bloqueantes o generar EF afinada). Re-verificado en
  `LOAD_EF`.
- **`ready_for_next_stage` del Scrum (compuesto):** sin preguntas bloqueantes al
  PO pendientes **y** cobertura de RF ≥ umbral (default 100%) **y** historias
  `must`/`should` estimadas **y** ninguna `must` sin asignar. Habilita al
  **Agente Arquitectura** (siguiente eslabón ISDF).

### Decisiones acordadas (D1–D9)

- **D1** Persistencia: **generalizar** `ef_*` → tablas multi-agente `agent_jobs` /
  `agent_artifacts` / `agent_validations` con `agent_type` e `input_job_id`
  (enlace cross-agente); `AgentJobRepository` genérico. No tablas por agente.
- **D2** Siguiente eslabón: **Arquitectura**.
- **D3** Priorización: **MoSCoW** primario + valor/esfuerzo como desempate.
- **D4** Capacidad de sprint: **20 puntos/sprint** por defecto (configurable).
- **D5** Semáforo compuesto (ver arriba).
- **D6** Validaciones v1: solo `question` (PO); corregir estimaciones (`estimate`)
  en v1.1.
- **D7** ClickUp: **Sprint→Lista, Historia→Tarea, Épica→tag/custom field**; sin
  Sprints nativos.
- **D8** Dependencias: campo `dependencies` en la historia (detección LLM +
  validación de ciclos en CRITIQUE); sin nodo dedicado.
- **D9** Estimación: **LLM** con enum Fibonacci cerrado + `confidence`;
  re-estimación en refine.

### Asignación de historias al equipo (fuera del artefacto)

- Tabla **`story_assignments`** (`job_id`, `story_id`, `user_id`, `assigned_at`,
  `assigned_by`; migración `0008`), **única por `(job_id, story_id)`**: una
  historia tiene como máximo un responsable y reasignar actualiza la fila.
- Tabla **`sprint_assignments`** (migración `0009`, única por
  `(job_id, sprint_id)`): responsable de un **sprint completo**.
- **Cascada `historia > sprint`, DERIVADA no materializada.** Asignar un sprint
  hace que sus historias sin responsable propio se muestren a su nombre, pero NO
  se escriben filas en `story_assignments`: se resuelve al leer, y cada historia
  informa en `source` si su responsable es explícito (`story`) o heredado
  (`sprint`). Así retirar la asignación del sprint deshace la cascada sin dejar
  filas huérfanas, y una asignación por historia sigue siendo una **excepción**
  que ni reasignar ni desasignar el sprint puede pisar.
- Vive **FUERA del `ScrumArtifact`**, igual que las validaciones: el artefacto es
  la salida del agente y **no se muta**; quién ejecuta cada historia es una
  decisión del equipo, posterior e independiente, revisable sin regenerar el plan.
- Endpoints: `GET /scrum/team` (colaboradores asignables: activos, vigentes y
  `available_for_assignment`), `GET /scrum/jobs/{id}/assignments` (devuelve
  `{items, sprints}` con las asignaciones **efectivas**),
  `PATCH /scrum/jobs/{id}/assignments` y
  `PATCH /scrum/jobs/{id}/sprint-assignments` (`user_id: null` desasigna). El equipo vive
  bajo `/scrum` (nivel READ) y no bajo `/auth` para no abrir el panel de usuarios
  a quien no tiene `config`. **Asignar exige Scrum FULL** → `analista` y `admin`.
- Al asignar se valida que el plan exista, que la historia pertenezca a su
  artefacto y que el destinatario sea asignable.
- **Export ClickUp**: columna `Assignee` (CSV) / `assignee_email` (JSON) con el
  correo institucional del responsable **efectivo** (incluidas las historias que
  lo heredan del sprint; fallback al correo de acceso). Las asignaciones se
  inyectan en el mapeo (`story_rows(artifact, assignees=…)`), no en el artefacto.
- **UI preparada para la fase (b), sin implementar:** el plan tiene el botón
  "Enviar a ClickUp" *visible pero deshabilitado* con tooltip, para comunicar que
  la asignación de hoy quedará vinculada. Lo que falta para (b) está en
  `docs/diseno-agente-scrum.md` §7 (resolver correo → id de miembro del
  workspace, dentro del guard fail-closed del espacio de Sistemas).

### Restricción de seguridad ClickUp (crítica)

La cuenta de ClickUp es **compartida** por la organización. El agente **solo**
opera dentro del espacio de **Sistemas**, nunca en otros. Garantizado
estructuralmente:
- `CLICKUP_WORKSPACE_ID` / `CLICKUP_SPACE_ID` / `CLICKUP_ALLOWED_LIST_IDS` /
  `CLICKUP_API_TOKEN` fijados en `settings`/`.env` (nunca hardcode).
- **Guard fail-closed**: toda escritura pasa por `assert_target_authorized(list_id)`
  que resuelve `list → folder → space` y exige `space_id == CLICKUP_SPACE_ID` y
  `list_id ∈ allowlist`; fuera de ello → rechazo explícito. Sin allowlist ⇒ no
  escribe nada.
- **Auditoría** de cada tarea creada (historia origen, cuándo, lista) en
  `agent_external_links`.
- Dos fases: (a) export CSV/JSON compatible (sin token, sin riesgo); (b) API con
  `dry_run` por defecto + creación **idempotente** por `external_key`.

### Plan de implementación por bloques (método EF; tests mockeados, commit+push por bloque)

- **B0** Generalización de persistencia (`agent_*` + `AgentJobRepository` +
  migración `0002`) y base compartida `ai/agents/base/`. EF sigue verde.
- **B1** Contrato `ScrumArtifact v1.0.0` (Pydantic + fixture + round-trip).
- **B2** Grafo Scrum + `LOAD_EF` (+ gate) + nodos stub.
- **B3** EPICS/STORIES/CRITERIA (LLM mockeado) + trazabilidad.
- **B4** ESTIMATE/PRIORITIZE/SPRINT_PLAN (SPRINT_PLAN determinista).
- **B5** CRITIQUE/QUESTION_GEN + cobertura.
- **B6** ASSEMBLE/VALIDATE/PERSIST + servicio + API (`/scrum/*`) + refine + gate 4xx.
- **B7** Export ClickUp (CSV/JSON) + guard + auditoría (fase (a), sin API).
- **B8** Frontend: nav GESTIONAR, `ArtifactShell` factorizado, `ScrumResultView`,
  flujo new→plan→afinar.

---

## 5. Agente Arquitectura (diseño validado)

> Diseño completo en **`docs/diseno-agente-arquitectura.md`**. Tercer agente del
> ISDF (fase **DISEÑAR**). Consume el **par EF + Scrum** de un mismo flujo y
> produce el diseño técnico que alimentará a los Agentes **BD** y **API**.
> Reutiliza el patrón EF/Scrum; la infraestructura B0 ya es multi-agente.

Pipeline **LangGraph**:

```
LOAD_SOURCES → CONTEXT → COMPONENTS → STACK → ADRS → CONTRACTS → DIAGRAMS
             → CRITIQUE → QUESTION_GEN → ASSEMBLE → PERSIST
```

- **Entrada doble (transitiva, sin migración):** `input_job_id = scrum_job_id`;
  el EF se resuelve por `scrum_job.input_job_id`. El artefacto guarda ambos ids +
  hashes en `source`.
- **COMPONENTS/STACK/ADRS/CONTRACTS** son *map*/structured output.
  **CONTEXT** calcula un *scope profile* **determinista** → `size_class` S/M/L que
  fundamenta la **recomendación de estilo** (default **monolito modular**; el LLM
  justifica). **DIAGRAMS** genera Mermaid **determinista** desde el grafo
  estructurado (nunca por LLM). **Prohibido inventar**: sin base en EF/Scrum →
  pregunta al Arquitecto.
- **Contrato `ArchitectureArtifact v1.0.0`** (claves inglés / valores español;
  todo ítem con `id`/`source_refs`/`confidence`/`origin`): `source` (Scrum + EF de
  origen + hashes), `context` (scope_profile, size_class, bounded_contexts),
  `architecture_style`, `components[]` (con trazabilidad a épicas/historias del
  Scrum y entidades/APIs del EF), `stack[]`, `adrs[]`, `integrations[]`,
  `contracts[]` (eventos = `kind:"event"`), `cross_cutting[]`, `diagrams`
  (Mermaid), `analysis` (riesgos/observaciones/cobertura de épicas/entidades/RNF),
  `questions_for_architect[]` (`audience`/`blocking`/`linked_to_ref`), `metrics`.
- **Stack de la casa:** `ai/knowledge/tech_stack.yaml` (allow-list por capa +
  defaults) inyectado en STACK para **no proponer exotismos**. Refleja el stack
  con el que Urbano construye sus **sistemas de negocio** (no el de TMS AI Studio);
  nace **PENDIENTE DE VALIDACIÓN** por el equipo.
- **Gate de entrada:** el servicio verifica Scrum `ready_for_next_stage=true`
  antes de crear el job (`GateError` 409); re-verificado en `LOAD_SOURCES`.
- **`ready_for_next_stage` (misma semántica que EF/Scrum):** sin preguntas
  bloqueantes al Arquitecto pendientes **y** contenido mínimo (estilo decidido +
  ≥1 componente + cobertura de épicas/entidades ≥ umbral). **RNF sin atender** y
  **contratos de integración desconocidos** → **preguntas bloqueantes** (no
  condiciones extra del gate). Un único `ready` habilita a **BD** y **API**.

### Decisiones acordadas (A1–A8)

- **A1** Entrada doble EF+Scrum: **transitiva** vía `scrum_job_id` (sin migración).
- **A2** Recomendación de estilo: *scope profile* **determinista** + heurística
  (LLM justifica); default **monolito modular**.
- **A3** Diagramas **deterministas** desde el grafo (Mermaid válido); nodo `DIAGRAMS`.
- **A4** `mermaid` en frontend con **import dinámico client-only y lazy SOLO en la
  vista del artefacto de Arquitectura** (no en el bundle global).
- **A5** Stack desde allow-list **cerrada** (`tech_stack.yaml`, negocio de Urbano,
  PENDIENTE DE VALIDACIÓN); necesidad exótica → pregunta.
- **A6** Granularidad de componentes: **bounded-context/módulo** (~5–15), no clases.
- **A7** Eventos/colas: **síncrono en monolito por defecto**; eventos solo si se
  justifican; si no → `Observation` "no requerido v1".
- **A8** Semáforo: **único `ready`** (sin bloqueantes + contenido mínimo).

### Plan de implementación por bloques (tests mockeados, commit+push por bloque)

- **A0** `tech_stack.yaml` (borrador PENDIENTE DE VALIDACIÓN) + loader;
  `<MermaidDiagram>` frontend (lazy). EF/Scrum siguen verdes.
- **A1** Contrato `ArchitectureArtifact v1.0.0` (Pydantic + fixture + round-trip).
- **A2** Grafo + `LOAD_SOURCES` (carga doble + gate) + `CONTEXT` (scope determinista) + stubs.
- **A3** `COMPONENTS`/`STACK` (LLM mockeado) + trazabilidad.
- **A4** `ADRS`/`CONTRACTS`/`DIAGRAMS` (Mermaid determinista).
- **A5** `CRITIQUE`/`QUESTION_GEN` + cobertura (RNF/integraciones → bloqueantes).
- **A6** `ASSEMBLE/VALIDATE/PERSIST` + servicio + API (`/arquitectura/*`) + refine + gate 409.
- **A7** Frontend: nav DISEÑAR, `ArchitectureResultView`, Mermaid lazy, flujo
  new→design→afinar, export PDF con diagramas.

---

## 5.1 Vista de artefacto: CENTRO DE COMANDO (patrón único de TODOS los agentes)

La página de un job **no es un documento**: es un **hub**. El mismo patrón sirve
para EF, Scrum, Arquitectura y BD, y es el que debe seguir cualquier agente nuevo
(API, Backend…). Vive en `frontend/src/components/artifact/`.

- **El hub** (`hub-card.tsx`): cabecera (título, versión, semáforo, mini-stats,
  acciones) + **grid de tarjetas-sección** que **ES el índice** — no hay índice
  lateral. Cada tarjeta lleva icono con el **acento del módulo**, conteos, una
  **línea de insight** con el dato que importa y, si reclama acción (bloqueantes
  sin responder, historias fuera de sprint, contratos por definir), **borde rojo
  + badge**. El hub cabe en una pantalla.
- **El panel lateral universal** (`artifact-panel.tsx`): TODO el contenido se
  explora aquí. Media pantalla desde la derecha con el hub atenuado pero visible;
  ancho 50% por defecto, botón a 70%, borde arrastrable (40–85%) y preferencia
  persistida; **pantalla completa en móvil**. Cabecera fija: volver, icono,
  título, conteo, **buscador local**, switcher de sección y cerrar; debajo,
  **sub-pestañas** cuando la sección las tiene; cuerpo con scroll propio.
- **Las secciones son DATOS, no JSX incrustado** (`HubSection[]`): `id` (slug del
  hash), título, icono, conteos, insight, urgencia y un `render(ctx)` — o `tabs`
  con un `render` cada una. Esa misma definición alimenta la tarjeta, el panel y
  el PDF; **no hay dos versiones del contenido**.
- **Navegación entre paneles**: `ArtifactNavProvider` + `RefChip`. Cada vista
  declara sus rutas por prefijo (`artifact-refs.ts`, gana el prefijo más largo):
  pulsar `BR-003` dentro de Preguntas abre Modelo → Reglas con la fila resaltada
  y **"← volver"** en la cabecera (mini-historial dentro del sheet). Un id que
  **pertenece a otro artefacto** (un `REQ-F-…` citado por el Scrum) **no finge un
  destino**: se avisa con un toast.
- **Deep-linking**: la URL sigue al panel (`#requisitos`, `#modelo/reglas`);
  compartir el enlace abre el job con ese panel y esa pestaña.
- **Atajos**: `Esc` cierra; `←`/`→` cambian de sección. El listener de teclado va
  en **fase de captura** (el diálogo detiene la propagación antes de `window`) y
  el foco inicial entra en el panel, **no** en el selector de sección.
- **Buscador local**: filtra la sección abierta (`artifact-search.ts`, sin
  acentos) y las **sub-pestañas muestran las coincidencias** en vez del total,
  apagando las que no tienen ninguna.
- **Preguntas**: el modo enfocado (una a una, progreso, Confirmar/Corregir) vive
  DENTRO del panel (`focused-questions.tsx`) junto a la vista Lista; arranca en
  "una a una" si queda alguna pendiente.
- **EXPORT PDF INTACTO** (`artifact-print-doc.tsx`): el informe **no usa
  paneles**. Portada + índice derivado + todos los capítulos seguidos,
  reutilizando el `render` de cada sección con `forPrint: true`. Reglas:
  - El sheet es `print:hidden`: nunca contamina la exportación.
  - Una pestaña que solo **filtra** otra (Must sobre Todas) lleva `printSkip`, o
    el PDF duplica el contenido.
  - `printNow(isReady)` espera al contenido **asíncrono** antes de abrir el
    diálogo: sin ello el PDF de Arquitectura salía sin los diagramas Mermaid.
- **Motion**: entrada del sheet 200ms ease-out, cambio de sección con fade corto,
  hover de tarjeta con elevación; `prefers-reduced-motion` ya neutraliza todo.

---

---

## 5.2 Agente BD (diseño validado e implementado)

> Diseño completo en **`docs/diseno-agente-bd.md`**. Cuarto agente del ISDF (fase
> **DISEÑAR**). Consume el `ArchitectureArtifact` (gate `ready_for_next_stage`) y,
> transitivamente, el `EFArtifact` —su materia prima— para producir el **modelo de
> datos físico**. Habilita al **Agente API**.

Pipeline **LangGraph** (15 nodos, solo 6 llaman al LLM):

```
LOAD_SOURCES → MODEL_MAP → TABLES → RELATIONS → CONSTRAINTS → INDEXES → CATALOGS
             → DDL_GEN → VALIDATE → DICTIONARY → ER_DIAGRAM
             → CRITIQUE → QUESTION_GEN → ASSEMBLE → PERSIST
```

- **REGLA RECTORA: el LLM NUNCA escribe SQL.** Elige un `logical_type` de un enum
  cerrado y Python renderiza el DDL al dialecto del motor. Por eso el DDL es válido
  por construcción y **regenerarlo para otro motor cuesta cero llamadas al modelo**
  (`GET /bd/jobs/{id}/ddl?engine=`).
- **`MODEL_MAP` es el cortafuegos anti-invención**: fija en Python qué tablas y
  columnas existen (una por entidad/campo del EF + puentes N:M). El LLM solo tipa y
  describe; los **catálogos** son la única ampliación posible, y exigen evidencia
  textual del EF. Un valor de catálogo inventado sería el peor error de este agente:
  un dato falso con aspecto de verdad.
- **Contrato `DatabaseArtifact v1.0.0`**: `target` (motor + convenciones efectivas),
  `tables[]` (columnas con `logical_type`+`type`, PK, FK, unique, check, índices),
  `ddl_scripts[]`, `seed_data[]`, `data_dictionary[]`, `er_diagram` (Mermaid),
  `design_decisions[]`, **`rule_mappings[]`** (toda `BR-`/`VAL-` del EF con su
  destino: `declarative`|`application`|`trigger`), `validation`, `analysis`
  (risks/observations/coverage), `questions_for_dba[]`, `metrics`.
- **Validación del DDL en capas, sin LLM**: L1 estructural + L2 sqlglot en el
  dialecto real (ambas en el pipeline), L3a **ejecución contra SQLite en memoria**
  (tests) y L3b motor real (opt-in). El artefacto declara si se **parseó** o se
  **ejecutó**: no presenta como certificación lo que no lo es.
- **Motor**: `database_relational` de `tech_stack.yaml` está **VALIDADA** →
  **PostgreSQL 16**. Si la arquitectura no decide motor, se usa el default con
  `engine_decided=false` + pregunta bloqueante.
- **Semáforo** (habilita al Agente API): sin bloqueantes **y** ≥1 tabla **y** todas
  con PK **y** cobertura de entidades ≥ umbral **y** DDL válido.
- **Preguntas al DBA agrupadas por clase de vacío**: 40 columnas sin tipo son UNA
  pregunta con los refs enumerados, no 40 que entierran la que importa.
- Sin migraciones de BD. Permisos: `arquitecto` FULL, `developer` READ (§6.1).

---

## 5.3 Agente API (diseño aprobado, en construcción)

> Diseño completo en **`docs/diseno-agente-api.md`**. Quinto agente del ISDF (fase
> **CONSTRUIR**). Consume el `DatabaseArtifact` (gate `ready_for_next_stage`) y,
> transitivamente, Arquitectura, Scrum y EF. Produce el contrato de APIs que
> habilita a los Agentes **Backend** y **Frontend**.

Pipeline **LangGraph** (14 nodos, 6 tocan el LLM):

```
LOAD_SOURCES → RESOURCE_MAP → RESOURCES → ENDPOINTS → SCHEMAS
             → AUTHORIZATION → RULE_MAPPING → ERRORS
             → OPENAPI_GEN → VALIDATE → CRITIQUE → QUESTION_GEN
             → ASSEMBLE → PERSIST
```

- **REGLA RECTORA (gemela de la del BD): el LLM NUNCA escribe OpenAPI.** Decide
  semántica; Python renderiza el YAML 3.1 y lo valida sin LLM. Re-renderizar a JSON
  o degradar a 3.0.3 cuesta cero llamadas al modelo.
- **SEGUNDA REGLA: el peor error de este agente es una autorización más ancha que
  la realidad.** Un endpoint sobrante se borra en revisión; una autorización
  permisiva por silencio se despliega. Por eso la matriz es **fail-closed**: sin
  regla → `deny`; alcance sin columna real → pregunta bloqueante; y si el endpoint
  expone columnas que el BD marcó `pii`, la ambigüedad **siempre** bloquea.
- **`RESOURCE_MAP` es el cortafuegos anti-invención** (equivalente de `MODEL_MAP`):
  fija en Python qué recursos y operaciones existen. Única ampliación: endpoints de
  **acción** desde procesos/reglas, **con cita verbatim**. Ningún campo de esquema
  existe sin `column_ref` a una columna del BD (salvo `computed` con `BR-`).
- **`rule_mappings[]` cierra el círculo que abrió el BD**: copia su veredicto en
  `bd_enforcement`. Una regla que el BD clasificó `application` y que aquí no
  encuentra endpoint es una regla que desaparecería del sistema → bloqueante.
- **Contrato `ApiArtifact v1.0.0`**: `source` · `target` (estilo, base_path,
  seguridad, convenciones efectivas) · `resources[]` · `schemas[]` · `endpoints[]` ·
  `authorization_matrix[]` · `error_catalog[]` · `rule_mappings[]` · `openapi`
  (YAML) · `validation` · `analysis` · `questions_for_tech_lead[]` · `metrics`.
- **Validación en capas sin LLM**: L1 estructural (13 comprobaciones) + L2
  `openapi-spec-validator` **0.8.5** + L2b round-trip; L3a `openapi-core` en tests.
  Dos hallazgos fijados con test en API0: **3.1 hizo `responses` opcional** (así que
  "todo endpoint declara sus códigos" es responsabilidad de L1, no de la librería) y
  un **`$ref` colgante lanza excepción** en vez de reportarse (L2 debe capturar).
- **Decisiones acordadas**: rutas con **dominio en español y protocolo en inglés**,
  propiedades JSON en **`snake_case`** (espejo 1:1 de las columnas), **envelope
  `ApiResponse`** de la casa, paginación **offset/limit**, **PATCH** como verbo de
  actualización. Fijadas en `ai/knowledge/api_conventions.yaml` y con test candado.
- **Semáforo** (habilita a **Backend** y **Frontend**): sin bloqueantes **y** ≥1
  endpoint **y** **todos con decisión de acceso** **y** cobertura ≥ umbral **y**
  especificación válida. Un endpoint que nadie puede llamar es código muerto para
  el Agente Backend, así que no habilita a construir aunque el documento sea válido.
- **Frontend**: nav CONSTRUIR, `ApiResultView` sobre el centro de comando (§5.1).
  Su visual insignia es la **matriz de autorización** (endpoints × actores, con el
  hueco visible); el YAML se copia y se descarga en YAML o JSON, y lleva `printSkip`
  en el PDF —mil líneas que nadie lee y que duplican el catálogo de endpoints—.
- Sin migraciones de BD. Permisos sin tocar: `developer` FULL `api`; las preguntas
  se dirigen a **`questions_for_tech_lead`** (quien puede responderlas). El
  arquitecto participa por **grant**, no por excepción a la matriz.

## 5.4 Módulo INVENTARIO DE SISTEMAS + fase RECONCILE (implementado)

> La evolución **brownfield** del ISDF. Hasta INV0 cada agente diseñaba como si la
> organización partiera de cero; el inventario es la memoria de **lo que ya
> existe** y RECONCILE es la fase que la usa.

**INV0 — conocimiento de la casa.** `tech_stack.yaml` incorpora el destino real
(AWS, PostgreSQL 16 sobre **Aurora Serverless v2**, React 19 + TS + Tailwind,
Kotlin + Compose, Flutter, Python para reportería asíncrona), cada capa validada
**citando su fuente**. Aurora NO entra en `allowed`: esa lista es el contrato de
dialectos del Agente BD (`DB_ENGINES` + `engine_type_map`), y Aurora es un
despliegue de PostgreSQL, no un dialecto — vive en `dialect`/`managed_service`/
`deployment`. `language_backend` sigue SIN validar con candado: el documento fija
Python solo para reportes. El estilo (microservicios) vive FUERA de `layers`, en
el bloque `architecture`, para no duplicar la decisión que ya toma
`architecture_style` + ADR-001. Glosario ampliado con 11 términos operativos.

**INV1 — modelo.** `inventory_systems` (destino|legado|externo) e
`inventory_assets` (db_schema|module|api|document) con `content` JSONB, migración
`0010`. **Versionado sin bandera `is_current`**: recargar inserta `version+1` y la
vigente es el máximo por `(system_id, asset_type, name)`, resuelto al LEER — un
máximo derivado no se desincroniza, una bandera sí. Todo activo nace `importado`,
nunca `validado`: cargar no es revisar.

**INV2 — ingesta de esquemas.** Dump DDL → sqlglot, **sin LLM**. La trampa que
define el módulo: sqlglot NO lanza excepción ante lo que no entiende, lo degrada a
`Command` — un importador ingenuo perdería tablas en silencio y RECONCILE diría
"créala" sobre una tabla de producción. Se trocea con el tokenizador y todo
`Command` se reporta con su línea. Introspección read-only **fail-closed en cuatro
capas**: alias (nunca DSN del cliente, sería SSRF), allowlist de hosts, solo
lectura impuesta por el servidor y credencial siempre redactada. Rol `admin`
estricto.

**INV3 — ingesta de documentos.** Reutiliza el pipeline del EF + pase LLM que
extrae módulos, entidades, funcionalidades y **decisiones**. Las defensas viven en
Python, no en el prompt: se verifica que la `source_ref` sea un `element_id` real
del fragmento y que haya evidencia verbatim; lo demás se descarta y **se informa**.

**INV4 — la fase RECONCILE.** Nodo en Arquitectura, BD y API. Cuatro veredictos:
`reuse` (no se construye) · `extend` (**ALTER, no CREATE**) · `new` · `conflict`
(**pregunta bloqueante**). Entre "claramente lo mismo" y "claramente distinto" hay
una banda de duda donde **no se adivina, se pregunta**: la diferencia entre no
saber y equivocarse. Matching léxico/estructural con umbrales calibrados por test;
gancho para pgvector documentado en `name_similarity`. Consecuencias reales: lo
reutilizado no se crea **ni se dropea en el rollback**, un catálogo reutilizado no
se siembra, y una columna añadida NOT NULL sin DEFAULT se relaja (contra una tabla
con datos ese ALTER reventaría). `reconciliation` es **opcional** en los tres
contratos: retrocompatible. Sin inventario, la fase se declara no ejecutada **con
el motivo escrito** y el diseño sigue como greenfield.

**INV5 — UI.** Sección propia "Conocimiento → Inventario", primera en la nav.
Esquema con tablas plegables y buscador por tabla Y por columna. Badges de
reconciliación (verde/azul/violeta/rojo) con vocabulario único en
`lib/reconciliation.ts` y el activo existente al lado de la propuesta.

**INV6 — promoción.** Un artefacto terminado de BD o API se promueve al
inventario. **Se MEZCLA, no se reemplaza**: reemplazar borraría del inventario lo
que ese diseño no menciona, y el siguiente reconciliaría contra una foto
incompleta.

**Permisos:** módulo `inventario` — excepción consciente a la regla de forma:
FULL para `admin`/`arquitecto` (curarlo es responsabilidad de arquitectura) y READ
para **todos** los demás, incluido `procesos`. No es una fase, es conocimiento
transversal.

**Cortafuegos:** `tests/conftest.py` añade `sin_inventario_real` (hermano del de
la API de Anthropic) para que ningún test abra conexiones al reconciliar.

**Seed de demostración:** `scripts/seed_inventario_demo.py` (TMS Moderno, 15
tablas maestras). ⚠️ **Nombres SINTÉTICOS**: `PROYECTO_MODERNIZACION_v4` NO está
en el repositorio; se reprodujo la FORMA acordada (5 apps, 16 microservicios, 15
maestras), no los nombres reales. Al incorporar el documento, sustituirlos aquí y
en `tests/inventory/fixtures.py`.

---

## 5.5 Agente QA (diseño validado e implementado)

> Diseño completo en **`docs/diseno-agente-qa.md`**. Sexto agente del ISDF (fase
> **VERIFICAR**). Consume el `ScrumArtifact` (gate `ready_for_next_stage`), el
> `EFArtifact` transitivo y —**si se indica**— el `ApiArtifact`. Produce el plan
> de pruebas ejecutable.

Pipeline **LangGraph** (12 nodos, solo 5 tocan el LLM):

```
LOAD_SOURCES → CRITERION_MAP → TEST_DESIGN → EDGE_CASES → AUTH_CASES
             → DATASET → TRACE_MATRIX → EXEC_PLAN
             → CRITIQUE → QUESTION_GEN → ASSEMBLE → PERSIST
```

- **`CRITERION_MAP` es el cortafuegos anti-invención** (gemelo de `MODEL_MAP` y
  `RESOURCE_MAP`): fija en Python qué pares (historia, criterio) existen **antes**
  de gastar un token. El LLM no elige *qué* hay, solo redacta *cómo* se prueba.
- **La asimetría que gobierna el agente**: un caso ausente se ve en la cobertura;
  un caso **falso** pasa la ejecución y certifica una mentira. De ahí que un caso
  de **borde** exija el límite citado **verbatim** (QA-D2) y que los casos de
  **autorización** se deriven por plantilla de la matriz del contrato de API
  (QA-D7) — una regla `ambiguous` produce **pregunta**, nunca caso.
- **La dependencia del `ApiArtifact` es opcional y explícita** (QA-D1): no está en
  la cadena hacia atrás sino hacia delante, así que se indica y se **verifica que
  pertenezca a la misma cadena**. Sin contrato no hay casos de autorización y el
  artefacto **declara el motivo**; el propio contrato Pydantic hace imposible que
  se cuelen por la puerta de atrás.
- **Contrato `QaArtifact v1.0.0`**: `source` · `target` (umbrales y tabla de
  minutos efectivos) · `test_cases[]` · `trace_matrix` (filas + `coverage`) ·
  `datasets[]` · `execution_plan` (suites, orden topológico, esfuerzo) ·
  `questions_for_qa_lead[]` · `analysis` · `metrics`.
- **Determinista** (sin LLM): la matriz, el plan de ejecución con su orden
  topológico, los casos de autorización y los **minutos** —de una tabla por tipo y
  prioridad guardada en `target` (QA-D8), no de una estimación del modelo: dos
  corridas del mismo plan dan el mismo número—.
- **Semáforo**: sin bloqueantes **y** ≥1 caso **y** todo caso anclado a un criterio
  real **y** cobertura de criterios `must`/`should` completa. Los de
  `could`/`wont` sin caso son **advertencia** (QA-D5). QA es hoy el último eslabón:
  su `ready` significa **"el plan se puede ejecutar"**.
- **Exports CSV** (casos y matriz) con **BOM UTF-8** y delimitador `;`: Excel en
  configuración española los abre de un doble clic, sin asistente y sin acentos
  rotos, y sin añadir `openpyxl` (QA-D6).
- **Frontend**: nav VERIFICAR, `QaResultView` sobre el centro de comando (§5.1).
  Su visual insignia es la **matriz de trazabilidad** (criterio × tipo de caso, con
  el hueco visible y separado por si bloquea o solo avisa). Badges por tipo con
  vocabulario único en `lib/test-case-kind.ts`.
- **Seed de demostración**: `scripts/seed_qa_demo.py` siembra la cadena completa
  EF → Scrum (plan **a escala**) → Arquitectura → BD → API → QA, con el plan de
  pruebas generado por el **pipeline real** y LLM falso. ⚠️ Pulsar "Generar" en la
  UI sí llama al modelo real.
- Sin migraciones de BD. Permisos sin tocar: `qa` FULL para el rol `qa`.

### QA9 — modos de entrada B y C (diseñado; **del Modo C existen el guard, las fixtures y el extractor**)

> `docs/diseno-agente-qa.md` **PARTE II** (§11–§17) y `docs/diseno-qa-modo-c.md`
> (QA-D19…QA-D25 + los ajustes A1–A4). Todo lo de arriba describe el **Modo A**
> (desde el plan Scrum). Del resto están implementados **QC3 (el guard)**,
> **QC4 (fixtures y saneador)** y **QC4.5 (el extractor de anclas)**
> —`ai/agents/qa/explore/` y `tests/fixtures/qa_explore/`—; el Modo B sigue en cero
> y el Modo C no explora nada todavía: no hay navegador, y por eso todo se ejerce
> contra HTML congelado.

- **El problema que resuelve el bloque**: el Modo B (desde un sistema del
  **INVENTARIO**) y el Modo C (**exploración Playwright solo-lectura** de una URL
  viva) **no tienen `ScrumArtifact`**, así que amputan `CRITERION_MAP` — el órgano
  que hace confiable al agente. Sin sustituto del ancla serían una fábrica de
  cobertura falsa a escala.
- **La distinción que lo ordena todo: especificación vs observación.** El Modo A
  ancla a *intención* ("el sistema **debe** hacer X"); B y C a *observación* ("**hace**
  X hoy"). Un caso en rojo significa "el sistema está mal" en A y **"algo cambió"** en
  B/C. De ahí `evidence_class` **obligatorio por caso** (viaja al CSV, al badge y al
  PDF): mezclar ambas suites destruye la capacidad de distinguir bug de evolución y
  degrada la suite a ruido. **Los modos son excluyentes por job.**
- **Sustitutos del cortafuegos**: `ASSET_MAP` (B) y `SURFACE_MAP` (C), deterministas
  y previos al LLM, mismo patrón que `CRITERION_MAP`/`MODEL_MAP`/`RESOURCE_MAP`.
- **Modo B — jerarquía de anclas**: constraint de `db_schema` (nivel 1) · afirmación
  de `document` con evidencia verbatim (2) · endpoint de `api` **solo alcanzabilidad**
  (3) · `module` → pregunta (4). El nivel 3 es regla dura:
  `api_surface_from_artifact` **no guarda códigos de estado ni esquemas**, así que
  afirmar `→ 201` sería convención disfrazada de evidencia. `importado` vs `validado`
  modula `confidence` y emite `Risk` pero **NO bloquea**: un ancla mal parseada falla
  ruidosamente, no miente en silencio — la asimetría rectora no aplica en esa
  dirección.
- **Modo C — cinco capas fail-closed** (hereda las cuatro de INV2): (1) **alias,
  nunca URL del cliente** —sería SSRF, y además el alias transporta la credencial de
  la cuenta de QA—; (2) **allowlist de hosts**, vacía = nada autorizado; (3) **solo
  lectura impuesta en red: abortar todo método ≠ GET/HEAD** — "solo pulsamos enlaces"
  es intención, no *enforcement*, igual que "las consultas son SELECT" no es
  `default_transaction_read_only=on`; (4) la credencial **no se redacta, no se
  acepta** —una URL con *userinfo* no es un destino válido, ni un enlace navegable
  (A7; ver más abajo)— y **no se guardan capturas de pantalla** (una captura
  autenticada lleva datos reales de producción a un PDF exportable); (5) **la
  allowlist se re-verifica en CADA navegación** — una BD no redirige, una
  aplicación web sí. `QA_EXPLORE_ENABLED=false` por defecto.
- **Rompe dos rachas del proyecto, a conciencia**: el contrato sube a **`QaArtifact`
  v1.1.0** (retrocompatible — `mode` con default `specification`, así que los
  artefactos ya persistidos siguen validando) y **exige la migración `0011`**
  (`agent_jobs.input_params` JSONB). `input_job_id` es **FK a `agent_jobs.id`** y un
  sistema del inventario **no es un job**; guardarlo solo dentro del artefacto
  perdería el rastro justo en los jobs que **fallan**, que es cuando más falta hace.
  De paso cierra el `target_system_id` huérfano de INV (existe en los tres
  `state.py`, lo leen los tres `*_nodes.py`, **nadie lo rellena**).
- **Permisos (matriz sin tocar)**: registrar un alias explorable es un acto de
  **despliegue** (`admin`); lanzar una exploración contra un destino ya acotado es
  **`qa` FULL**.
- **Entorno**: desbloqueado en QC5 — `libnspr4`/`libnss3` instalados y
  `playwright==1.62.0` en `requirements.txt`. **El pin incluye la revisión del
  navegador**: 1.62.0 trae `chromium` **1234**, el que ya está descargado, así que
  cambiarlo sin comprobar `playwright/driver/package/browsers.json` obliga a bajar un
  Chromium nuevo. Aun así **la suite no arranca ningún navegador**: el Modo C se
  ejerce contra HTML de fixtures y sintético, y `sin_navegador_real` lo impone.
- **Bloques** (renumerados en `docs/diseno-qa-modo-c.md`): QC0 diseño ✅ →
  **QC3 el guard ✅** → **QC4 fixtures y saneador ✅** → **QC4.5 el extractor de
  anclas ✅** → **QC5 navegador + capa 3 de red + conjuntos cerrados ✅**.
  **⏸️ APLAZADOS** (`docs/diseno-qa-modo-c.md` §0.bis): QC1 contrato v1.1.0 ·
  QC2 migración `0011` + `data_class` · QC6 CLI de login · QC7 grafo C +
  `SURFACE_MAP` + servicio + API · QC8 frontend. El aplazamiento **desactiva la
  colisión QC2 ⇄ LLM2**, que era la que ordenaba los dos frentes. El Modo B
  (`LOAD_INVENTORY`, `ASSET_MAP`) sigue en cero con el plan QA11–QA12 de la
  PARTE II.

#### QC3 — el guard del Modo C (implementado)

`backend/ai/agents/qa/explore/`: `target.py` (capas 1, 2 y 4) · `navigation.py`
(capa 5) · `clicking.py` + `dom.py` (la mitad de la capa 3 que se decide leyendo el
DOM) · `limits.py` · `driver.py` (protocolo estrecho, **cero Playwright**) ·
`session.py` (`ExploreSession`). Lo que no se puede perder de vista:

- **A1 — el alias no viaja al prompt.** El host ya no viajaba; el alias sí, y un
  `tms-prod-urbano-aws` filtraría el mapa de infraestructura al proveedor del
  modelo. Se cerró por **estructura y no por nomenclatura**: `alcance_para_prompt()`
  es lo ÚNICO que el modelo sabe del destino (`origen`, `data_class`, `paths`), y
  QC5 amplía **esa función**, de modo que el candado cubre lo que se añada después.
  Refuerzo: el alias coincide con `^[a-z][a-z0-9-]{1,31}$`, así que no puede *ser*
  un host ni una URL, y `QA_EXPLORE_TARGETS` tiene **un único lector**.
- **A2 — un destino puede declararse `sintetico` SOLO si su host es local**
  (`localhost`/`127.0.0.1`/`::1`), verificado por el validador y no por confianza.
  Sin esa excepción el Modo C era imposible de probar de punta a punta sin saldo del
  proveedor; con ella, cualquier host no local sigue siendo `real` sin excepción.
- **`readonly_verified: true` es obligatorio** por destino (409 si falta): sin una
  cuenta de solo lectura en la aplicación explorada, lo único que separa una
  escritura de producción de nosotros son nuestras propias capas.
- **La capa 5 revalida cuatro cosas**: la URL pedida, la `location` de una
  redirección, **la URL final con la que vuelve el driver** y el destino de un clic.
  Lo que cae fuera no se sigue y queda registrado con su motivo.
- **La trampa del `<button>`**: en HTML un `<button>` sin `type` dentro de un
  `<form>` es `type="submit"`. Se exige el `type="button"` **explícito en el
  atributo**, incluso fuera de un formulario (un `<button form="otro">` envía uno
  ajeno). Lo que sí se permite es pulsar pestañas y acordeones dentro de un `<form>`:
  bloquear "todo lo que esté dentro de un form" dejaría fuera la mayor parte del
  valor. **Teclear (nivel 2) está FUERA de v1** y no por el riesgo de escritura: si
  un `keyup` dispara un autoguardado y la petición muere abortada, el explorador
  **observa que no hubo validación** y emite un caso falso.
- **Candados AST** (precedente `tests/llm/test_construcciones.py`): cero
  `fill`/`type`/`press`/`select_option`/`check`/`evaluate`/`screenshot` en `app/` y
  `ai/`; `click` **solo** dentro de `ExploreSession.pulsar_si_procede`;
  `build_driver` no se importa por nombre en ninguna parte (un `from … import`
  resolvería el enlace al importar y el parche del cortafuegos no lo alcanzaría);
  ningún esquema de request con forma de URL/host.
- **`sin_navegador_real` es la CAPA 5 del cortafuegos de tests** (`tests/firewall.py`,
  autouse). **No es una hermana de conveniencia de `sin_api_real`**: la capa 4
  parchea `socket.socket.connect` en *este* proceso y un navegador es **otro proceso
  del sistema operativo**, así que para ese riesgo es la única capa que existe.
  Parchea la **fábrica del driver**, nunca `ExploreSession`.
- **Sin selector estable (`[name]` › `#id` › `[data-testid]`) no se pulsa.** El
  selector estructural llega en QC5 junto a su `selector_strategy`, el campo que
  avisa de que el ancla es frágil.
- **A7 — la capa 4 se cumple en la ENTRADA.** `redact_url` tapaba la credencial
  embebida en la URL del destino en cada superficie por la que podía asomar; eso la
  deja **dentro** del sistema y hace la garantía proporcional al número de
  superficies que alguien recordó (mismo patrón que F1: *redactar no es no tener*).
  Desde A7 el validador **rechaza** cualquier URL con *userinfo*, mirando el
  `netloc` crudo y no `partes.username` —la forma percent-encoded no se lee como
  usuario—. Dos hallazgos más salieron del arreglo: **la capa 5 aceptaba
  *userinfo*** (el destino ya no puede declararlo, pero **el enlace lo escribe la
  aplicación explorada**, y `urlparse` no cuenta el *userinfo* ni en el esquema, ni
  en el host, ni en el origen), y **el `ValidationError` de Pydantic incluye el
  valor de entrada tal cual**, así que el nuevo rechazo publicaba lo que acababa de
  rechazar — lo cazó el test que ya existía, y `_construir` traduce ahora la
  excepción a un `ValueError` redactado para que la de terceros **no circule**.
  `redact_url` se queda: sobre un destino es un no-op demostrable, y sigue haciendo
  falta para las URLs que no declaramos nosotros.
- **QC3 NO trae** la intercepción de red (abortar todo método ≠ `GET`/`HEAD`), la
  neutralización del `submit` ni el `storage_state`: las tres necesitan el driver
  real y son de QC5/QC6.

#### QC4 — fixtures y saneador (implementado)

`backend/tests/fixtures/qa_explore/` (tres escenarios: `tms_guias`, `spa_router`,
`trampas`) + `ai/agents/qa/explore/sanitize.py` + `scripts/capture_explore_fixture.py`.
Sigue sin haber una línea de Playwright.

- **El `manifest.json` sustituye al navegador.** Da `status`, `location`, la URL
  final y el resultado de cada clic, así que la **capa 5** —revalidar en CADA
  navegación— se ejerce entera sin navegar, sin servidor local y sin red. Es lo que
  permite ejercer el 99% del Modo C en este host, donde Chromium no arranca.
- **El saneador aplica A3: conserva la estructura y los rótulos, borra los datos.**
  La parte que importa es lo que NO se lleva: un mensaje de error renderizado y las
  opciones de un `<select>` **dentro de un `<tbody>`** son la validación observable
  y la evidencia verbatim de QA-D2, así que sobreviven; lo que se vacía es el texto
  suelto de las celdas. Además borra `<script>`/`<style>`, los comentarios, los
  `<meta>` de sesión, los atributos con nombre sensible y **los manejadores en
  línea** (mismo motivo que `<script>`: son código), vacía el atributo de valor sin
  quitarlo, enmascara toda secuencia de 8+ dígitos y reescribe las URLs absolutas
  del host explorado a su *path* — una fixture no lleva escrito el mapa de la
  infraestructura (A1).
- **El candado sobre las fixtures es un test, no una nota en el README**
  (`tests/agents/qa/test_fixtures_candado.py`): recorre **todos** los ficheros del árbol
  —`.html`, `.json` y `.md`— y exige ninguna secuencia de 8+ dígitos, ningún dominio
  de la casa y ningún atributo de valor con contenido. Y se prueba **introduciendo
  la violación**: un candado que solo se ha visto pasar es indistinguible de una
  función que devuelve la lista vacía. `escenario_saneado()` lo aplica **antes** de
  escribir y **revienta**; un aviso por consola se lee cuando ya está comiteado.
- **El saneador no es un oráculo de PII sobre texto libre.** Un dominio de la casa
  o un nombre propio dentro de un párrafo sobrevive al saneado —el texto es la
  evidencia—; lo para el candado, y por eso el candado se ejecuta antes de escribir
  y no después de comitear. Consecuencia declarada: las **trampas se escriben a
  mano**, porque el saneador borra los manejadores en línea y la del `POST` no
  sobreviviría a una captura.
- **La trampa del `POST` fija un residual con test**: `<button type="button">` con
  un manejador que manda un `POST` **es pulsable** para la lista blanca, y hace
  bien — leyendo el DOM no hay forma de saber qué dispara. Quien lo para es la
  **mitad de red de la capa 3**, que llega en QC5. El doble de la suite *modela* ese
  aborto (devuelve la página sin cambios) para dejar el caso escrito: es la
  especificación ejecutable contra la que QC5 tendrá que quedar verde, no su
  demostración.

#### QC4.5 — el extractor determinista de anclas (implementado)

`ai/agents/qa/explore/extract.py` + `scripts/anclas_de_html.py`. **Entra `html` y
`path`, sale la lista de anclas con evidencia literal. Nada más**: sin red, sin
LLM, sin navegador, sin clic y sin tocar el disco. Es la lista cerrada con la que
`SURFACE_MAP` (QC5) será un cortafuegos —un cortafuegos vale lo que valga lo que le
dan de comer— fabricada en Python **antes** de gastar un token.

- **Vocabulario cerrado, un atributo = un ancla**: los once atributos de validación
  más `@enum`, cada entrada **con su caso escrito al lado** y un test que obliga a
  escribirlo al ampliar la lista (misma regla que `PIEZAS_DE_MENSAJE`). Que
  `required` y `maxlength` sean dos anclas y no una es lo que impide esconder media
  rotura. **Fuera, anotados con su motivo**: `value` (el dato, no el límite),
  `disabled` (no valida nada) y `placeholder` (texto, no restricción). `type` ancla
  solo cuando restringe la forma del dato: un caso «escribe texto en un campo de
  texto» entierra al que importa.
- **Cinco estrategias de selector** —`[name]` › `#id` › `[data-testid]` ›
  `[aria-label]` › estructural— y la lista **extiende** la de pulsar en vez de
  copiarla. Las dos últimas no sirven para pulsar: equivocarse de elemento contra
  una aplicación viva es una acción, no una nota. **Desviación declarada de §2.1**:
  el prefijo de ancestro del ejemplo (`form[...] input[...]`) no desambigua el caso
  que ocurre —dos radios del mismo grupo comparten `name` y formulario— así que en
  su lugar se **comprueba la unicidad** del selector y el ambiguo cae a la
  estrategia siguiente. El estructural **nace marcado**; `aria-label` no, porque
  frágil no es «puede cambiar» sino «puede romperse sin que haya cambiado nada que
  importe».
- **Fail-closed con una rama real**: una etiqueta que no se puede escribir en CSS
  (`<asp:TextBox>` de WebForms) **no ancla**, porque el ref no resolvería nunca y el
  caso fallaría por el motivo equivocado. El hueco se ve en la cobertura; el ruido
  con aspecto de hallazgo, no. El `path` de un ref se **rechaza** si es una URL, no
  se recorta: el host viene del alias y no viaja al artefacto (capa 4 / A1).
- **F2 fijada con un test, no resuelta**: el saneador vacía todo `value` porque es un
  dato, pero el `value` de un `<option>` es el **conjunto de lo aceptado**, un límite
  citable. Distinguirlos exige árbol y ancestros, y el candado tiene prohibido
  construirlos. Consecuencia escrita: en crudo se ve el enum, en la fixture saneada
  no —incluido el `<select name="ubigeo">` ya comiteado—. Un enum a medias tampoco se
  emite: un hueco se ve, un conjunto incompleto **pasa la ejecución certificando una
  mentira**.
- **`dom.py` gana tres datos del parse** (`origen` literal, `ruta` `nth-of-type`,
  `inicio`) porque reconstruirlos después exigiría un segundo parser del mismo
  documento, y dos parsers se separan en cuanto una etiqueta cierra mal.
- **Candados del bloque**: lista de imports **cerrada** (solo `re`, `dataclasses`,
  `typing` y `dom`), nada que abra un fichero ni literal que nombre uno del
  repositorio, síncrono a propósito, y extracción idempotente y estable —dentro de un
  control manda el vocabulario, nunca el orden en que la aplicación escribió los
  atributos—. Y **se ven fallar**, como los de QC4.
- **`scripts/anclas_de_html.py`** imprime la tabla de anclas de un `.html` de disco,
  con las frágiles marcadas y **los controles que se quedaron sin selector**: la
  decisión fail-closed se mira, en vez de deducirse de una ausencia.

#### QC5 — el navegador, la capa 3 de red y los conjuntos cerrados (implementado)

`ai/agents/qa/explore/network.py` + `driver.py` reescrito + `extract.py` ampliado.
`playwright==1.62.0` entra en `requirements.txt` y
`test_qc3_no_introduce_playwright` se borra: es su acto visible de muerte.

- **La capa 3 tiene dos mitades en ficheros gemelos**: `clicking.py` decide qué se
  **toca** leyendo el DOM (QC3), `network.py` qué se **envía** (QC5) — se aborta
  toda petición cuyo método no sea `GET`/`HEAD`, por lista **blanca**. La política
  es una función pura y el driver una cáscara que pregunta y obedece: por eso la
  capa entera se ejerce **sin arrancar nada**.
- **El orden es un criterio.** Primero `add_init_script` neutraliza el `submit`
  (evento en captura + `prototype.submit`, que NO dispara el evento, +
  `requestSubmit`), después la intercepción de red. Al revés el navegador formaría
  envíos que mueren abortados, y **un envío que muere se observa como "no hubo
  validación"** — la observación falsa que el agente no puede producir, y el mismo
  motivo por el que teclear está fuera de v1. Lo que NO se toca es la validación:
  el mensaje de error renderizado es la evidencia verbatim de QA-D2.
- **Un subrecurso `GET` a otro origen sí pasa, declarado**: abortar el JS de un CDN
  deja una página rota, y de una página rota salen casos que afirman lo que el
  sistema no hace. Residual escrito (la cabecera `Referer`).
- **`DUENO_DEL_CLIC` pasa a `DUENOS_DEL_CLIC`**, dos: la sesión que **decide** y el
  driver que **ejecuta**. No hay forma de pulsar en Playwright sin llamar a algo
  llamado `click`, y las alternativas están prohibidas por motivos peores. Sigue
  garantizando lo que importaba: ningún nodo pulsa nada.
- **`sin_navegador_real` pasa a proteger de un riesgo presente**: sus dos entradas
  de Playwright ya no se saltan por falta de paquete, y hay test de que el blindaje
  **llegó**. Saltándose la primera entrada (referencia real a `build_driver`) el
  navegador **sigue sin arrancar**. `build_driver` no lanza nada al construir; la
  jaula se instala sobre el contexto **antes** de que exista una página, con
  candado de fuente.
- **C4 — el discriminador catálogo-de-dominio vs lista-de-datos.** Mira **solo los
  `value`, nunca los rótulos**: forma de código · ningún identificador de fila
  (ULID/UUID/hex/token) · si todos son enteros, longitud uniforme ≥4 dígitos.
  Fail-closed: un valor malo descarta el conjunto, y el `<select>` conserva sus
  otras anclas. No mira el texto porque «La Libertad» y «Juan Pérez» son idénticos
  estructuralmente **y** porque leer el texto para decidir mete el texto en el
  camino de la decisión. Cierra la fuga que A6 midió y deja ubigeo en pie.
  **Residual ABIERTO y fijado con test**: una PK entera uniforme de 4 dígitos ancla
  hoy y dejará de anclar cuando la tabla cruce a 10000 — diferido, con dueño
  escrito (`docs/diseno-qa-modo-c.md` §14.6).
- **C2** `radio`/`checkbox` por `name` son un conjunto cerrado (mínimo dos: uno
  suelto declara un sí/no); su selector `[name]` casa con todos **a propósito**.
  **C3** el tope de A6 se **reutiliza** de `common.enum_evidence` —el candado del
  `hashlib` sigue verde— y por encima del tope la evidencia es la etiqueta de
  apertura, que es la razón por la que el tope vive en `extract` y no en
  `SURFACE_MAP`. **C5** un selector que interpola una plantilla o un id de fila se
  salta; cae a la ruta estructural, estable y marcada frágil.
- **Todo descarte dice POR QUÉ** (`Descarte`, vocabulario cerrado con su caso
  escrito). El motivo describe la **regla**, nunca cita un valor: viaja al PDF
  igual que una evidencia. `scripts/anclas_de_html.py` lo imprime **entero**.
- **La lista de imports de `extract.py` se amplía a `ai.agents.qa.common`**, con la
  justificación escrita en el propio candado. Sigue diciendo lo mismo: ni
  navegador, ni red, ni disco. Es **cerrada, no congelada**.

---

## 5.6 Proveedor LLM LOCAL — Ollama (PRIORIDAD ACTUAL; diseñado, sin implementar)

> Viabilidad medida, diseño y plan en **`docs/diseno-llm-local-ollama.md`**.
> Se apoya en la fábrica `ai/llm/` (LLM0 ✅) y en el cortafuegos de 5 capas
> (LLM1 ✅). **Ningún bloque autorizado** (REGLA R2).

**Para qué.** Validar la cadena EF → Scrum → Arquitectura → BD → API → QA con
corridas **reales** sin gastar un centavo y sin que ningún dato de Urbano salga
de la máquina. Es lo que desbloquea la ventaja competitiva del proyecto, hoy
congelada por falta de saldo de API.

**Viabilidad (medida el 2026-08-27): VIABLE con un límite duro.**
- Ollama **NO está instalado** todavía; `OLL0` lo instala y mide.
- WSL2: **11.19 GiB** de RAM (host 23 GiB, sin `.wslconfig` ⇒ 50%), **8 núcleos
  Zen5 con AVX-512 completo**, DDR5-5600 dual channel (89.6 GB/s teóricos).
- **Sin GPU utilizable**: `/dev/kfd` ausente ⇒ no hay ROCm; Ollama no trae
  Vulkan. **Inferencia CPU pura.** La iGPU 860M no es la palanca que parece
  (comparte el mismo bus de memoria). La palanca real es `.wslconfig`.
- **Techo: 8B Q4 a 16K de contexto** (o 4B a 32K). 14B solo con
  `.wslconfig memory=16GB`. `KV_CACHE_TYPE=q8_0` es **requisito**, no ajuste.
- `httpx` puro (ya en `requirements.txt`), **cero dependencias nuevas** — mismo
  criterio con el que se rechazó `langchain-google-genai` (LLM-D14).

**EL HALLAZGO, que vale aunque el proveedor local se descarte:** el chunker acota
`EXTRACT` (4 096 tokens por trozo) pero **NADA acota `CRITIQUE`** — recibe el
modelo consolidado **entero** (`critique.py:110`), así que su entrada crece con
el documento y no tiene techo. Medido: un documento fuente de **1 760 bytes**
produce **~8 100 tokens de entrada en UNA llamada**. Un documento de Procesos
normal (10–20 KB) sitúa a `CRITIQUE` en 20 000–90 000 tokens. Contra Claude
(200K) es invisible; contra un modelo local es el límite que manda. **Y Ollama
trunca en silencio** — misma clase de fallo que `sqlglot` degradando a `Command`
(INV2) y que *redactar en vez de rechazar* (A7): **truncar no es fallar**.

**Decisiones (OLL-D1…D5):**
- **D1** Un `ProviderSpec` y nada más. **`format` (gramática) NO se usa**:
  LLM-D4 se reafirma con argumento más fuerte —si el local decodifica por
  gramática y Claude no, no se compara el modelo, se comparan dos pipelines—. La
  **tasa de reparación pasa a ser la métrica principal** del experimento.
  `max_concurrency=1`, `OLLAMA_TIMEOUT=1200` (una salida de 8 192 tokens a
  ~10 tok/s tarda ~14 min: los 180 s de Anthropic la matarían siempre),
  `num_ctx` explícito **con canario de truncamiento antes de llamar**, precio 0.0.
- **D2 (la que hace útil todo esto)** Un proveedor local **SÍ admite
  `data_class="real"`**. La regla de LLM-D9 está escrita sobre un **nombre**
  (`provider != "anthropic"`) y debe estarlo sobre una **propiedad**:
  `ProviderSpec.data_residency` ∈ `local` | `tercero_confiable` | `tercero`, y
  solo `tercero` exige datos sintéticos. **Es más estricto, no más laxo**:
  registrar un proveedor sin declarar dónde acaban los datos pasa a ser
  imposible. LLM-D10 se relaja **solo** para `local` (el `tech_stack.yaml` real
  se manda; el sintético sigue haciendo falta para Gemini). La capa 5
  (`APP_ENV=production` ⇒ no arranca) **se mantiene intacta**.
- **D3** Cortafuegos: **NO hace falta una capa nueva**. La capa 4 permite todo
  loopback —y Ollama vive en `127.0.0.1:11434`—, pero **no es ciega** como lo era
  con el navegador: la ve y la deja pasar por una regla nuestra que se quedó
  corta. Se **estrecha la capa 4** por puerto (lector único desde `settings`) y
  se declara la costura en la capa 2 (`build_http_client`, llamada por módulo,
  **REGLA R1** — tercer tropiezo con lo mismo). *Apilar una capa sobre una regla
  equivocada deja la regla equivocada debajo.*
- **D4** Procedencia: **mismo régimen que LLM4, sin excepción** →
  `banco_de_pruebas`. Es el contraste exacto de D2 y son **ejes ortogonales**:
  *local* responde **dónde están los datos**, no **si el resultado sirve**.
  `RunProvenance` guarda el id **con tag** y gana `data_residency`.
- **D5** Se prueba primero el **EF**, y no por ser el primero: es el único con
  corridas reales contra Claude registradas (3 artefactos en `agent_artifacts`
  con sus `metrics`) y **el A/B es reproducible byte a byte** —el documento
  fuente sigue en disco—. Se compara por magnitudes deterministas, sin LLM juez;
  la fila que decide es **`evidence` verbatim presente en el fuente**, que es el
  anti-invención y se comprueba con una búsqueda de subcadena.

**Bloques:** **OLL0** banco de medición **fuera del repositorio** (instala, mide
tok/s, RSS real, canario de truncamiento y tasa de reparación; **si el 8B repara
mal, el plan se detiene aquí y esa es la conclusión**) → **OLL1**
`data_residency` + cortafuegos **antes del proveedor** (mismo criterio que LLM1 y
QC3) → **OLL2** el proveedor (`httpx` + `MockTransport`; tapa el hueco del
semáforo propio de `run_extract`, que no pasa por `run_structured_map`) →
**OLL3** procedencia (depende de LLM4) → **OLL4** la corrida real y el veredicto
(**se autoriza aparte**).

**⚠️ El choque que hay que resolver ANTES de construir: LLM2.** Está
especificado sobre `provider != "anthropic"`; **no ha empezado**, así que debe
implementar la regla **ya en su forma final** sobre `data_residency`. Si no, la
política de datos —lo más delicado del diseño— se escribe dos veces. Orden:
**LLM2 (reformado) → OLL1 → OLL2 → OLL4**, con **OLL0 en paralelo desde ya**
porque no toca el repositorio. **LLM3 (Gemini) pierde su justificación
principal** —el *free tier* era para poder probar sin gastar, y el local lo hace
mejor y además admite datos reales—; conserva calidad y velocidad. **No se
decide aquí**: se revisa a la luz de OLL4.

**Candidata de PRODUCTO (no de este plan):** de TestCollab se toma **una** idea —
una **bandeja de propuestas** (`pendiente`/`aceptado`/`rechazado`, edición en
línea, **nada se crea hasta que un humano acepta**), que es la misma forma que
las validaciones y las asignaciones: vive fuera del artefacto y no lo muta. **NO
se copia su entrada por URL libre**: nuestra allowlist de destinos
preautorizados es superior (una URL del cliente es SSRF) y se queda.

---

## 5.7 CONTROL DE GASTO — libro mayor, freno duro y la ventana (GAS1+GAS2)

> Diseño completo en **`docs/diseno-control-de-gasto.md`**. **GAS1 y GAS2
> cerrados**. Va **antes** que OLL0…OLL4 porque es el **instrumento con el que se
> miden**: sin él, "110 llamadas → 1" es una afirmación; con él, una medición.

**Lo que cambia en runtime, y hay que saberlo antes de tocar nada:** desde GAS1
**toda** llamada al modelo pasa por `MeteredLLMClient` —lo aplica `get_llm`, no
cada proveedor, con candado parametrizado sobre `PROVIDERS`—, que **comprueba el
tope, delega y anota la fila, en ese orden**. Sin libro mayor legible, **la
llamada se niega** (GAS-D7): un despliegue que se olvide de `install_db_sink()`
en el `lifespan` deja de funcionar en vez de gastar sin medir.

- **Tres números, y solo dos frenan** (GAS-D6): `LLM_JOB_CAP_USD` = 5 (el que más
  veces va a actuar: un techo mensual no impide que **una** corrida se coma el mes
  en una tarde), `LLM_MONTHLY_CAP_USD` = 100, y `LLM_MONTHLY_TARGET_USD` = 30 que
  **no bloquea nunca**. Toda cifra se compara contra 25–30, no contra 100. **No
  hay bandera para apagar el freno**: es la bandera que alguien deja apagada.
- **El mensaje del freno permite subir el tope a conciencia** (GAS-D11): dice el
  tope, **cuánto llevaba gastado**, **cuánto pedía la llamada que lo cruzó** y el
  margen reservado, y nombra la variable de entorno. Primero frena el del job y
  después el del mes: un job desbocado anunciado como "se acabó el mes" mandaría a
  revisar el sitio equivocado.
- **El tope se comprueba con MARGEN** (GAS-D5), no al filo: con concurrencia hay
  varias llamadas en vuelo que leen "por debajo" y lo cruzan juntas. Se niega
  cuando `gastado + margen > tope`. El precio —~3,4% del techo mensual
  inutilizable— se declara en vez de descubrirse.
- **`usage` ausente NO es `usage` cero** (GAS-D4). Tercera vez que el proyecto se
  topa con la misma forma (`sqlglot` degradando a `Command`, *redactar en vez de
  rechazar*, Ollama truncando en silencio): **la ausencia de un dato no es el
  valor 0 de ese dato**. Anotar 0 dejaría el tope ciego, que es lo único peor que
  pararse. La fila va con la estimación **marcada** y se informa qué fracción del
  mes es estimada.
- **La caché ya viene sumada en `input_tokens`** (GAS-D3), así que aplicarle la
  tarifa plana cobraría 10x de más las lecturas y 20% de menos las escrituras. Hoy
  el caching no está activado y la fórmula se reduce **byte a byte** a la anterior
  —hay test—; se escribe igual para que activar `cache_control` mañana no haga que
  el tope empiece a mentir. `reasoning` es **subconjunto** de `output` y **nunca**
  se suma.
- **A mitad de corrida** (§6.bis del diseño): quedan las filas del gasto real, **no
  queda artefacto** —`persist` solo lo invoca el nodo `PERSIST`, el último— y el
  job queda `FAILED` con el motivo y `metrics.real`. **El semáforo del siguiente
  agente no puede leer mal nada porque no hay nada que leer**: es ausencia de
  dato, no una comprobación que se pueda olvidar. La condición que lo sostiene y
  que hay que proteger: un `BudgetExceededError` **no puede confundirse con un
  ítem en cuarentena** —caería en `ASSEMBLE` produciendo un artefacto que parece
  entero y le faltan 70 casos—. Tres tests lo fijan uno a uno.
- **La verdad vive en `job.metrics.real`** (GAS-D9), fundida en
  `update_job_metrics` —un sitio, seis agentes **y la ruta de `FAILED`**—, con
  `ratio_sobre_estimado` que convierte el 2,4–3,1x de folclore en una columna
  medida. **`artifact.metrics.cost` sigue siendo la estimación**, con dueño
  escrito (**LLM4**) y, desde GAS1, **etiquetada como tal**: `TokenMetrics.source`
  en los seis artefactos y "costo estimado" en las siete vistas del frontend.
- **`get_llm(rol, *, data_class, job_id)`**: `job_id` es keyword-only y **sin
  default**, como `data_class`. La ingesta de documentos del inventario pasa
  `None` **explícito** y su gasto **se anota igual** — si no contara, el mes
  tendría una fuga por el único sitio que ingiere documentos reales de Urbano.
- **H2 arreglado**: `qa_nodes` no fijaba `started_at` en ningún nodo y las dos
  corridas reales de QA reportaban **56 años**. El `state.get(..., time.time())`
  del ensamblador no salvaba nada porque la clave llega presente con `0.0`.
- **Capa 6 del cortafuegos de tests** (`tests/firewall.py`): libro mayor en
  memoria, autouse. Y la **capa 1 pasa a tapar las dos bocas** del cliente
  (`complete_json` **y** `complete`): al envolver, el envoltorio llama al
  protocolo interno, así que la mordaza de LLM1 habría dejado de cubrir sin que
  nada lo dijera.
- Migración **`0011_libro_mayor_de_gasto`** (`llm_spend`; `cost_usd` es
  `NUMERIC(12,6)`, no `float`: es dinero que se suma miles de veces contra un
  umbral). El `0011` estaba apartado para QC2, que quedó aplazado; si QC2 se
  reanuda, toma el `0012`.

**Lo que GAS1 NO hace:** no acota `CRITIQUE` (lo **mide y lo frena**; el techo de
entrada es el canario de OLL2), no arregla el número del artefacto (LLM4) y no
toca la matriz de permisos.

### GAS2 — la ventana (implementado 2026-08-28)

**`GET /api/v1/gasto/mensual`** (`app/api/v1/gasto.py` → `spend_report_service`
→ `LlmSpendRepository.resumen_del_mes`), **`config` READ**, y la vista
*Configuración → Control de gasto*. Un tope que no se mira se conoce
bloqueando, y enterarse del techo porque un job murió a mitad de corrida es la
peor forma de enterarse.

- **`by_stage` es la razón de ser del bloque**: el gasto por nodo del grafo
  (GAS-D10) es el antes/después con el que se demuestra un recorte —"`EDGE_CASES`
  costaba X y ahora cuesta Y"—, y sin él esa frase no se puede sostener. El gasto
  que **ningún nodo reclama** sale como una fila con `stage: null` y su importe:
  un hueco que se ve, no un cero que se confunde con "ese nodo no gasta".
- **La honestidad de GAS-D4 llega hasta arriba, en tres campos que no se repiten:**
  `estimated_calls`, `estimated_cost_usd` y `usage_source`. La `estimated_fraction`
  es del **DINERO y no de las llamadas** —desviación declarada del ejemplo de §7.2
  del diseño—: la de llamadas ya es derivable de los dos contadores, y **una sola
  llamada cara estimada mueve la cifra mucho más que cien baratas**.
- **`usage_source` de un TOTAL tiene cuatro valores, no dos** (`fuente_del_total`
  en `app/models/spend.py`, un solo sitio para el job y para el mes): `real` ·
  `mixto` · `estimado` · **`sin_datos`**. Dos correcciones al vocabulario de GAS1,
  y las dos son la misma regla del proyecto —la ausencia de un dato no es el valor
  0 de ese dato—: un job con **todas** las llamadas estimadas decía `mixto`, que
  afirma que algo se midió; y un mes con **cero** llamadas daría `real` por
  aritmética, presumiendo de medición sobre nada.
- **Los importes viajan con los seis decimales de la columna**, no redondeados a
  céntimos (desviación declarada): una fila de `by_stage` puede valer 0,003 USD y
  a dos decimales se leería 0,00 — justo la fila que tiene que enseñar el recorte.
  Redondear es cosa de la vista, y la vista usa dos precisiones a propósito
  (`lib/gasto.ts`, con test).
- **`top_jobs` excluye las filas sin `job_id`** —la ingesta del inventario y las
  de un job borrado (`ON DELETE SET NULL`)—: agruparlas inventaría un job gigante
  que no existe. Su gasto sigue contando en el total y en `by_agent`, que es donde
  se ve. El agente sale de la propia fila y **no de un `JOIN`** con `agent_jobs`:
  la fila lo conserva aunque el job se borre.
- **Un tope en 0 reporta `null`, no 0%.** Es una configuración legítima, y ahí el
  porcentaje no existe: `0%` diría "no has empezado" justo cuando cualquier gasto
  ya lo ha cruzado.
- **El objetivo se publica aunque no frene** (GAS-D6). Un número que solo se
  manifiesta cuando el freno actúa se cumple por accidente; en la vista tiene su
  propia barra, al lado del techo duro.
- **Sin migración y sin tocar la matriz de permisos.** Es solo lectura: quien
  garantiza el tope sigue siendo `MeteredLLMClient`, antes de cada llamada.

### La LÍNEA BASE del «antes» está fijada y es RECONSTRUIDA (§3.bis del diseño)

Para demostrar un recorte hace falta el «antes», y **el «antes» medido no existe:
ninguna corrida de la historia registró el `usage`** (`TokenMetrics.source` vale
`"estimado"` en los seis agentes), así que todo lo anterior a GAS1 solo admite
reconstrucción. Se reconstruye ejecutando **nuestro propio código** —determinista,
re-medible, 0,00 USD— con `scripts/medir_linea_base.py` (pipeline real de QA +
doble del LLM de la suite, sobre el plan Scrum real de 31 historias y **110
criterios**, `01KY33JDAV21N40N326TCR3JSS`). Lo que hay que saber sin abrir el doc:

- **QA modo A: 221 llamadas · 603 869 tok de entrada · 2,61 USD estimados.**
  `TEST_DESIGN` 110 y `EDGE_CASES` 110, cada nodo con **una sola firma de
  `system`**: 466 738 tokens de preámbulo reenviado = **1,40 USD por corrida, el
  55% de la factura del agente**.
- **El «110 → 1» no es alcanzable, y el límite está en la SALIDA** (~14 700 tok
  estimados, 35–45 k reales, contra los 8 192 que el propio proyecto asume). El
  recorte es **agrupar**: el punto 2 pasa a ser **110 → ~11** (lotes de 10, el
  **91%** del desperdicio). Lotes de 20 añaden un 5% y duplican el riesgo de
  truncar.
- **ARREGLADO al medir: quince nodos LLM caían en `stage = NULL`** (§3.bis.4 del
  diseño). La fila de `CRITIQUE` salió `(sin etiqueta)` y el agujero resultó ser
  mucho mayor: GAS1 etiquetó en `run_structured_map`, que cubre los nodos *map* y
  **deja fuera a los de una sola llamada** — el **Agente Arquitectura entero**
  entre ellos. La etiqueta baja a `complete_structured` y `stage` pasa a ser
  **keyword-only sin default** (como `data_class`/`job_id` en `get_llm`), con
  candado en `tests/llm/test_atribucion_por_nodo.py`. El EF **no** estaba ciego:
  sus dos nodos LLM ya se etiquetaban a mano.
- **Scrum `ESTIMATE`+`PRIORITIZE`: 62 llamadas, 0,178 USD de ahorro** — el punto 2
  vale ~8x el punto 3, así que **el punto 3 BAJA de prioridad** (se hace después o
  se pliega a otro bloque). A cambio, el punto 3 sí se puede hacer entero (62 → 2).
- **El tope del job frena esa corrida**: 3,73 USD utilizables (5,00 − margen)
  contra 6,3–8,1 reales. La primera corrida real de QA hay que autorizarla
  subiendo el tope a conciencia. Y **ese plan no pasa el gate**: cuatro `must` sin
  sprint ⇒ `no_must_unassigned` falso ⇒ 409.
- **Cuando haya saldo, el primer dólar es del EF, no de QA**: 0,107 estimados ⇒
  **0,26–0,33 reales** sobre el documento que sigue en disco, y es el A/B
  reproducible byte a byte que OLL-D5 ya reclama.
- El «después» **no se compara contra esa tabla**: se corre el par antes/después
  **seguido y con el mismo modelo**, y las dos corridas quedan en el libro mayor.
  La tabla dice cuánto costará el par y qué esperar de él.

### Y ese requerimiento era de JUGUETE: la escala por tamaño (§3.ter del diseño)

Las cinco corridas del historial salieron de textos de ~1,7 KB. Un documento de
Procesos real trae 10–20 KB, así que la línea base está en el extremo pequeño de
la escala. `scripts/medir_escala_por_tamano.py` lo mide (mismo método: pipeline
real + doble calibrado contra el artefacto real, 0,00 USD):

- **La cadena real, medida de punta a punta** (documento real → EF real → plan
  real): **9,07 RF/KB · 1,94 historias/RF · 3,55 criterios/historia ⇒ 62,4
  CRITERIOS POR KB.** Un documento de 10 KB produce ~639 criterios.
- **Costo por corrida** (USD estimados; el real es 2,4–3,1x): a 1,76 KB
  EF 0,13 + Scrum 0,46 + QA 2,52 = **3,10**; a 10 KB = **19,54**; a 20 KB =
  **43,23** (era 43,32 antes de arreglar el duplicado, ver más abajo). El objetivo de 25–30 USD/mes **no aguanta un solo requerimiento de
  10 KB**.
- **QA domina y Scrum es el que más rápido crece.** `build_stories_user` y
  `build_criteria_user` meten TODO el contexto del EF en CADA llamada ⇒ x11,6 de
  documento da **x28** de costo. QA no lo sufre porque su payload por criterio
  está **acotado** (`[:20]`, QA-D8).
- **A qué tamaño mata el freno: 1,1 KB, y no es del EF sino de QA** (a x2,4;
  Scrum 4,9 KB; EF **28,6 KB** tras el arreglo del duplicado, antes 26,8). El EF
  ni se acerca a ser el cuello de botella.
- **Antes del freno hay otro techo, y es la SALIDA: 11,1 KB.** Por encima, la
  dimensión mayor de `EXTRACT` pasa de `CLAUDE_MAX_TOKENS`=8 192 y **se trunca**
  → cuarentena con observación (ruidoso, no silencioso) pero el EF **pierde esa
  dimensión entera**. Es el límite real de lo que el sistema procesa completo.
- **✅ El documento se enviaba DOS VECES — ARREGLADO (2026-08-28).** Por encima
  de ~16,4 KB en modo texto el `SECTION` único del `TextToCIRAdapter` acababa en
  `context` **y** en `text` del chunk, y `build_user` manda los dos en el MISMO
  mensaje: **2,00x medido, seis veces por corrida**. Hoy 1,00x. El arreglo tiene
  **dos mitades y las dos hacen falta**:
  1. **El texto de una `SECTION` es un RÓTULO, nunca el cuerpo.** Era el único
     `add_section` del repositorio que pasaba contenido —los otros tres ya pasaban
     un título—, así que el arreglo *restaura* un invariante que el resto del
     código ya asumía (`CIRBuilder` apila ese texto como ancestro del breadcrumb:
     apilar 40 KB era la señal). El cuerpo pasa a un `PARAGRAPH`.
  2. **El elemento que ABRE un chunk aporta su texto al contexto O al cuerpo,
     nunca a los dos.** Sin esto, (1) sería una regla que alguien tiene que
     recordar en el próximo parser; con esto la duplicación es imposible por
     construcción. Un heading ya se duplicaba así, solo que barato.
  **De propina, de (2): un grupo sin cuerpo ya no gasta un chunk.** Un título
  seguido de su subtítulo producía un `FRAGMENTO` con solo el título — 6 llamadas
  por dimensión que no podían extraer nada. Medido en un documento con esa forma:
  **25 → 12 chunks**; a 20 KB estructurado, **114 → 108 llamadas**. Su
  `element_id` se arrastra al chunk siguiente: la partición sigue cubriendo el CIR
  entero y la provenance no cambia.
  **Medido (20,5 KB plano):** `EXTRACT` 66 363 → 35 615 tok de entrada; el EF
  1,19 → 1,10 USD estimados (≈0,22–0,29 reales por corrida). Siete candados, los
  siete **vistos fallar** contra el código anterior. **Efectos secundarios
  declarados:** en `single_shot` el rótulo "Documento" suma ~18 tok por corrida
  —el precio de que el CIR de texto plano tenga la misma forma que el de los demás
  parsers—, y un documento **vacío** no gana rótulo (si no, el nombre del fichero
  se leería como contenido y sería citable como `source_ref`; lo cazó un test del
  inventario). **Sigue abierto:** el chunker **no tiene tope de tamaño** — 40 KB
  planos son UN chunk de 10 000 tokens (ver el techo de salida, punto 3).
- **Los dos modos de entrada son idénticos tras `PARSE`**, pero el modo texto
  **no tiene máximo** (`content` solo declara `min_length=100`; la ruta de fichero
  sí pasa por `MAX_UPLOAD_MB`). Recomendación: distinguir **por tamaño, no por
  modo**, con un pre-flight determinista (bytes → chunks → llamadas → estimación)
  que hable de **la cadena** y no solo del EF.

### El recorte del punto 2, DISEÑADO y sin implementar (`docs/diseno-recorte-qa-lotes.md`)

Agrupar los *map* de QA en lotes. **Ningún bloque autorizado (REGLA R2).** Lo que
hay que saber sin abrir el doc:

- **El lote se arma con HISTORIAS ENTERAS empaquetadas** (mismo FFD que
  `SPRINT_PLAN`), y **no por el ahorro**: el contexto de historia compartido vale
  0,037 USD, el 1,5% del recorte, y los bloques arbitrarios empatan en dinero. Se
  elige por coherencia del encargo y porque **partir una historia** es la forma
  exacta del duplicado de D2. Medido: **110 → 12** lotes con tope 10 (no ~11).
- **Tope POR NODO, no global** (D4): `EDGE_CASES` 10, `TEST_DESIGN` **5**. Su
  salida por llamada es 2,3x (307 contra 133 tok est.), así que un lote de 10 le
  da 7 368–9 517 tokens reales contra los **8 192** de `CLAUDE_MAX_TOKENS`.
  **220 → 36 llamadas, 1,179 USD = 84% del desperdicio**, y los 6 puntos que se
  dejan compran no vivir al borde del truncamiento. El tope es una constante: se
  sube cuando el libro mayor diga que hay holgura.
- **Si un lote trunca: se parte en dos, UNA vez.** No recursivo (converge al
  costo de hoy) y sin distinguir truncamiento de esquema malo (no son
  distinguibles desde fuera; la heurística que se equivoca cuesta llamadas).
  **Precondición dura:** un `BudgetExceededError` NO puede entrar por ahí — misma
  trampa que GAS1 cazó en §6.bis, o una corrida al filo duplica sus llamadas.
- **D2: el lote NO resuelve el duplicado entre criterios, y el orden importa.**
  El detector reporta **0** grupos y **no puede reportar otra cosa**:
  `criterion_ref` está en la clave (es aritmética, no estadística). Quedan 12
  lotes, así que los duplicados entre lotes siguen invisibles — y el lote **empuja
  el riesgo en la dirección mala** (diez criterios juntos invitan a diez casos con
  la misma plantilla). Por eso el arreglo del detector va **antes o con** el
  agrupamiento: si no, el antes/después del bloque no se puede leer.
  El arreglo **no** es quitar `criterion_ref` a secas —faltaría `expected_result`
  y un par de borde se reportaría como duplicado—: la clave pasa a ser
  `(type, steps, test_data, expected_result)`. Y **no se borra nada**: un
  duplicado entre criterios dice que **dos criterios piden lo mismo**, que es un
  hallazgo sobre el plan.
- **D3, el trade-off:** se pierde atención por criterio (real, y **es la única de
  las cuatro preguntas que exige una corrida pagada** — el doble no tiene nada que
  degradar), la cuarentena se vuelve gruesa y `by_stage` pierde granularidad que
  nadie usaba. **Se GANA el proveedor local**: menos llamadas y más largas es
  exactamente lo que prefiere un modelo a 10 tok/s con `max_concurrency=1`, así
  que el agrupamiento **hace más viable a OLL**, no compite con él.
  **Lo que NO se toca es el ancla**: `CRITERION_MAP` sigue fijando qué pares
  existen. Condición de implementación: con lote, el modelo devuelve a qué
  criterio pertenece cada caso y Python lo **busca en el lote y rechaza lo que no
  esté** — si se olvida, el lote es la puerta por la que el modelo reasigna casos,
  que es el peor error posible del agente.
- **🐛 Trampa de código que el bloque resuelve, no descubre:**
  `MAX_CASES_PER_CALL = 4` es hoy *por llamada* = por criterio; con un lote de 5
  recortaría a 4 los 20 casos esperados. Pasa a ser **por criterio dentro del
  lote**, y lo mismo `not_testable`.
- **Bloques: LOT0** detector · **LOT1** empaquetado (aritmética, sin LLM) ·
  **LOT2** el lote en `run_structured_map` (todo el riesgo) · **LOT3** la corrida
  real del par, **se autoriza aparte**.

**Punto 3 (Scrum `ESTIMATE`+`PRIORITIZE` 62 → 2): APLAZADO.** Vale 0,178 USD
contra ~8x del punto 2. Se hace después o se pliega a otro bloque.

---

## 6. Autenticación y usuarios

Autenticación **real** por `email` + contraseña con **JWT**; protege toda la API
de agentes y el frontend. Sigue la misma arquitectura del proyecto
(`api → services → repositories → models`) y el envelope `ApiResponse`.

- **Modelo `User`** (`backend/app/models/user.py`, tabla `users`, migración
  `0005_users`): `id` (ULID), `email` **único**, `full_name`, `password_hash`,
  `role`, `is_active`, timestamps. Más:
  - `deleted_at` (**baja lógica**, migración `0007`).
  - **Perfil de equipo** (migraciones `0008`/`0009`): `institutional_email` (el
    que se exporta a ClickUp; puede diferir del de acceso), `specialty` (**enum
    cerrado**: `backend|frontend|db|qa|fullstack|otro`) y
    `available_for_assignment`.
- **Baja lógica, NO borrado físico ni anonimización.** Los jobs
  (`agent_jobs.created_by`) y las validaciones (`agent_validations.answered_by`)
  referencian a su autor: anonimizar dejaría el historial sin respuesta a "¿quién
  hizo esto?" y de forma irreversible. Un usuario con `deleted_at` no inicia
  sesión ni aparece en los listados, su ficha se conserva y la baja se revierte.
  Su correo **sigue reservado** (la única de la tabla cubre esas filas):
  reutilizarlo exige reactivar, no crear otra cuenta.
- **Salvaguardas de gestión** (todas con test): no eliminarse a sí mismo, no
  dejar la plataforma sin ningún **administrador activo** (aplicada también a
  desactivar, porque `config` FULL es concedible por grant y sin ella un no-admin
  podía desactivar a todos los admins sin poder promover a nadie), y un admin no
  cambia su propio rol ni edita sus propios grants.
- **Roles funcionales por fase ISDF** (migración `0006_roles_por_fase`; sustituyen
  al par binario `admin`|`member`, cuyos usuarios pasaron a `analista`).
- **Hashing:** **bcrypt vía `passlib`** (`bcrypt` pinneado `<4.1` por
  incompatibilidad con `passlib` 1.7.4). El `password_hash` **nunca** se expone en
  la API ni se registra en logs; **jamás** se persiste la contraseña en claro.
- **JWT** (`python-jose`, HS256): el `sub` es el id del usuario. `JWT_SECRET`,
  `JWT_ALGORITHM` y `JWT_EXPIRE_MINUTES` viven en `settings`/`.env`. El
  `JWT_SECRET` **no se commitea**; en producción es único y **se rota**
  periódicamente (rotarlo cierra todas las sesiones vigentes).
- **Endpoints `/api/v1/auth`** (OpenAPI en español, `ApiResponse`):
  - `POST /auth/register` — crea usuario. Exige **`config` FULL**. **Excepción de
    bootstrap:** si no existe ningún usuario, el primer registro se permite **sin
    auth** y nace `admin`. Crear otro `admin` exige **rol** `admin`.
  - `POST /auth/login` — `email` + `password` → `access_token` (JWT) + usuario.
  - `GET /auth/me` — usuario actual + **`modules` efectivos** (rol + grants ya
    resueltos). Es la única fuente de permisos del frontend.
  - `GET /auth/roles` — catálogo de roles/módulos/niveles con la matriz (panel).
  - `GET /auth/users` — listado (**`config` READ**).
  - `PATCH /auth/users/{id}` — activar/desactivar (**`config` FULL**; un admin no
    puede desactivarse a sí mismo).
  - `PATCH /auth/users/{id}/profile` — nombre, correo de acceso y **perfil de
    equipo** (**`config` FULL**; aplica solo lo informado, 409 si el correo está
    tomado).
  - `POST /auth/users/{id}/password` — **restablecer** contraseña (**`config`
    FULL**; operación administrativa: no pide la anterior).
  - `GET /auth/users/{id}/activity` — huella del usuario (jobs + validaciones) y
    `recommend_deactivate` (**`config` READ**).
  - `DELETE /auth/users/{id}` — **baja lógica** (**`config` FULL**).
  - `PATCH /auth/users/{id}/role` — cambia el rol (**rol `admin` estricto**; un
    admin no puede cambiar su propio rol).
  - `PUT /auth/users/{id}/grants` — reemplaza los accesos adicionales
    (**rol `admin` estricto**; semántica de *replace*).
- **Protección:** `get_current_user`
  (`backend/app/dependencies/current_user.py`) valida el JWT → **401** sin token.
  La **autorización** vive aparte en `app/dependencies/permissions.py`:
  `require_module(module, level)` protege EF, Scrum, Arquitectura y configuración
  (READ a nivel de router, FULL por endpoint de escritura) y devuelve **403** con
  un mensaje que distingue "sin acceso al módulo" de "solo lectura".
  Errores de app (`app/errors.py`: `AuthError` 401 / `ForbiddenError` 403 /
  `NotFoundError` 404 / `ConflictError` 409) se traducen al envelope uniforme por
  el middleware.
- **Bootstrap del primer admin** (dos vías; **sin credenciales en el repo**):
  1. CLI: `backend/scripts/create_admin.py --email <correo> --name "<nombre>"`
     (pide la contraseña sin eco; idempotente).
  2. Endpoint `POST /auth/register` mientras la tabla `users` esté vacía.
- **Recuperación de acceso (tercera herramienta de operación):**
  `backend/scripts/reset_password.py --email <correo>` [`--reactivar`]. Existe
  porque `create_admin.py` es idempotente pero **no** toca la contraseña del
  usuario existente, y `POST /auth/users/{id}/password` exige `config` FULL —es
  decir un token— y **quien no puede iniciar sesión no tiene token**. El script
  rompe ese círculo desde el servidor. La contraseña se pide **sin eco y con
  confirmación**, y **no** se acepta por argumento: así no queda en el historial
  del shell ni en la lista de procesos; solo se persiste el hash. Si la cuenta está
  desactivada o dada de baja, **se niega** salvo `--reactivar`: resetear sin
  reactivar dejaría el acceso igual de cerrado, porque esos usuarios no inician
  sesión por diseño.
- **Frontend:** `AuthProvider` guarda el token (memoria + `localStorage`), el
  cliente API adjunta el `Bearer` y un handler global de **401** cierra sesión y
  redirige a `/login`. Guarda de rutas (`AppGate`): sin sesión → `/login`; con
  sesión, `/login` → dashboard; **sin permiso para la ruta → dashboard con aviso**
  (`lib/route-permissions.ts`; las rutas `/new` exigen FULL). Pantalla `/login` con
  identidad Urbano; sidebar con **badge del rol** y **cerrar sesión**.
  **Panel de usuarios** (`/configuracion/usuarios`, módulo `config`): alta,
  búsqueda por nombre/correo, filtros por rol y estado, contador, y por usuario
  un menú **kebab (⋮)** con Editar (identidad + rol + perfil de equipo), Accesos
  adicionales (**checkboxes múltiples** + atajo **Full stack** =
  Backend+Frontend+BD+API), Restablecer contraseña, Activar/Desactivar y Eliminar
  — las tres últimas con confirmación, y la baja exigiendo escribir el nombre y
  avisando de la actividad registrada. **Responsive**: tabla en `md+`, una card por usuario
  por debajo. Todos los campos de contraseña de la app (login, bootstrap, alta y
  restablecimiento) usan `PasswordInput`, con toggle mostrar/ocultar.

### 6.1 Permisos por fase ISDF (matriz)

**Fuente de verdad única: `backend/app/core/permissions.py`.** No duplicar la
matriz en ningún otro sitio — el frontend consume los `modules` ya resueltos que
devuelve `GET /auth/me` (`lib/permissions.ts` solo interpreta ese mapa).

- **Módulos** (`Module`): un agente del ISDF (`ef`, `scrum`, `arquitectura`, `bd`,
  `api`, `backend`, `frontend`, `qa`, `devops`) o `config`. Los agentes aún no
  implementados ya tienen módulo, para no tocar el enum al asignar permisos.
- **Niveles** (`AccessLevel`): `READ` (consultar) y `FULL` (crear/editar/afinar).
  **`FULL` implica `READ`.**

| Rol | FULL | READ |
|---|---|---|
| `admin` | todo (+ `config`) | — |
| `procesos` | `ef` | — |
| `analista` | `ef`, `scrum` | — |
| `arquitecto` | `arquitectura`, `bd` | `ef`, `scrum` |
| `developer` | `api`, `backend`, `frontend` | `arquitectura`, `bd`, `scrum` |
| `qa` | `qa` | `scrum` |

- La matriz sigue una regla de forma: **FULL en lo que el rol produce, READ en lo
  que queda hacia atrás en la cadena**. Por eso `bd` es FULL del `arquitecto` (misma
  fase DISEÑAR) y READ del `developer` (sus módulos van después y lo consumen), y
  `analista` no lo alcanza: los suyos van antes.
- **`devops` NO tiene rol asignado** (solo `admin`): el modelo acordado no lo
  menciona y no se le inventó dueño. Añadirlo a la matriz cuando el equipo decida a
  quién pertenece.
- **Grants** (`user_module_grants`, única por `(user_id, module)`): accesos extra
  por usuario que **SUMAN** sobre el rol y **nunca restan** — si el rol da `FULL`
  y el grant dice `READ`, gana `FULL`. `User.grants` usa `lazy="selectin"`.
- **Anti-escalada (crítico):** cambiar roles, editar grants y crear un `admin`
  exigen **rol `admin` estricto**, no `config` FULL. Si bastara el módulo,
  conceder un grant de `config` equivaldría a regalar el rol admin, porque el
  beneficiario podría auto-asignarse cualquier permiso. Fail-closed.
- **El JWT identifica, no autoriza:** el `sub` es el id del usuario y los permisos
  se resuelven en cada petición. Cambiar un rol surte efecto **con el mismo
  token**, sin cerrar sesión (y por eso la migración `0006` no rompe sesiones).
- **Navegación:** los módulos sin acceso son **invisibles**, no deshabilitados
  (una fase sin agentes visibles desaparece). Con acceso `READ` la vista del
  artefacto se muestra completa pero **sin acciones de escritura**, con un badge
  "Modo lectura" que explica la ausencia.

---

## 7. Ciclo de afinamiento

- Las **validaciones** (`pendiente` | `confirmado` | `corregido` + respuesta) se
  persisten **aparte, sin mutar el artefacto**.
- `POST /refine` crea un **job hijo** (`parent_job_id`) que inyecta las respuestas
  como **contexto autoritativo**.
- `ready_for_next_stage = true` cuando **no hay preguntas `blocking` pendientes**
  (gate del EF hacia el Agente Scrum; el Scrum tiene su propio gate compuesto, §4).

---

## 8. Lecciones obligatorias

- **Timeout 180s** en llamadas al modelo.
- **Backoff respetando `retry-after`.**
- **Concurrencia EXTRACT** por defecto **3**.
- **Checkpointing por `job_id`** — los reintentos **no re-facturan** fases ya
  completadas.
- **Métricas reales** (tokens / costo / duración) también en la ruta de
  `BackgroundTasks`.
- Los **descartes del assembler NUNCA son silenciosos** — siempre generan una
  `Observation`.
- **Redis Stack requerido (no Redis plano).** El checkpointer
  `langgraph-checkpoint-redis` usa comandos de **RedisJSON** (`JSON.SET` /
  `JSON.GET`); Redis plano (`redis:7`) falla con `unknown command 'JSON.SET'`.
  El servicio `redis` de `docker-compose.yml` usa **`redis/redis-stack-server:latest`**
  (carga el módulo `ReJSON` por defecto), mismo puerto `6379` y volumen
  `tms_redis_data`. Verificar con `docker exec tms_redis redis-cli MODULE LIST`
  (debe listar `ReJSON`).
- **REGLA R1 — una costura parcheable se llama por su MÓDULO, nunca por el
  símbolo importado.** Un `from modulo import simbolo` a nivel de módulo resuelve
  el enlace **al importar**, y a partir de ahí ningún `monkeypatch` sobre el
  atributo del módulo de origen lo alcanza: el importador se queda con la
  referencia vieja y el cortafuegos no ve nada. Todo lo que deba poder parchearse
  en tests se llama `_mod.func(...)`. Un import **dentro de una función** sí vale
  —resuelve en cada llamada— y es la escapatoria legítima. Nos mordió dos veces:
  `tests/orchestrator/test_claude.py` construía el `ChatAnthropic` REAL sin que
  ninguna capa lo viera (hallado en LLM1), y `_driver.build_driver` en QC3.
  **Candado:** `backend/tests/test_costuras_parcheables.py` (registro de costuras
  + comprobación de que el símbolo sigue existiendo donde dice su dueño). La
  desviación de §7.1 del diseño multiproveedor —la capa 1 envuelve `build_client`
  de cada `ProviderSpec` en vez de sustituir `get_llm`— tiene esta misma raíz.
- **Glosario logístico** en `backend/ai/knowledge/`, inyectado en
  `EXTRACT` / `INTERPRET` / `CRITIQUE` (y en EPICS/STORIES/CRITERIA del Scrum):
  - `checkpoint` = estado
  - `guía` = documento de envío
  - `shipper` = cliente
  - `siniestro` = evento logístico (no de seguros)
  - `papeleta` = descuento a personal
  - `recupero` = recuperación económica
  - `ubigeo` = departamento-provincia-distrito
  - `DEO` = depuración operativa

---

## 9. Reglas de proceso

- **Modelo Claude por defecto:** `claude-sonnet-5` (`CLAUDE_MODEL` en `.env`).
  Tarifas para cálculo de costos: **$3 / MTok input**, **$15 / MTok output**
  (`CLAUDE_PRICE_INPUT/OUTPUT_PER_MTOK`). Timeout **180s** (`CLAUDE_TIMEOUT`).
- **REGLA DE PRESUPUESTO:** nunca ejecutar análisis contra la **API real de
  Anthropic** sin autorización explícita del usuario. Desarrollo y tests
  **siempre con mocks**. Tampoco escrituras reales a ClickUp sin autorización.
  La regla está **protegida por un cortafuegos autouse** en `tests/conftest.py`:
  un test que caiga en el cliente real falla con un mensaje que dice cómo
  arreglarlo, en vez de salir a la red (`tests/test_budget_guard.py` lo cubre).
  **Desde GAS1 la regla tiene además un freno en runtime** (§5.7): todo lo que
  sale de `get_llm` comprueba el tope antes de gastar y anota la fila después, y
  sin libro mayor legible **no llama**. La regla decía qué no hacer; el freno lo
  impide.
- **REGLA DE RESPALDO:** hacer **push al remoto después de CADA fase commiteada**.
- **REGLA R2 — protocolo de cierre de bloque: cerrar → reportar → esperar
  aprobación del siguiente.** Ningún bloque arranca sin visto bueno explícito y
  ninguno se encadena con el siguiente sin reportar antes. LLM1 se cerró sin
  reporte; no volvió a pasar por suerte, no por diseño, y escrito aquí deja de
  depender de la suerte.

---

## 10. Alcance v1

- **Sin OCR.**
- **Sin RAG pgvector** (la extensión está disponible en la imagen, pero no se usa
  en v1).
- **Sin pausa human-in-the-loop.**

---

## 11. Estructura del repositorio

```
tms-ai-studio/
├── docker-compose.yml        # PostgreSQL 16 (pgvector) + Redis 7
├── .env.example
├── CLAUDE.md                 # este archivo
├── docs/
│   ├── setup-entorno.md
│   ├── diseno-agente-{scrum,arquitectura,bd,api,qa}.md
│   ├── diseno-qa-modo-c.md          # ⏸️ QC1/2/6/7/8 APLAZADOS (§0.bis)
│   ├── diseno-control-de-gasto.md   # 💰 GAS1 ✅ · GAS2 ✅ (§5.7) · §3.bis/§3.ter
│   ├── diseno-recorte-qa-lotes.md   # el punto 2: lotes en QA (diseñado, sin implementar)
│   ├── diseno-multiproveedor-llm.md # LLM0 ✅ LLM1 ✅ · LLM2 a reformar (§5.6)
│   └── diseno-llm-local-ollama.md   # ⭐ PRIORIDAD ACTUAL (§5.6)
├── frontend/                 # Next.js (cliente puro de la API)
│   └── src/components/artifact/   # centro de comando: hub-card, artifact-panel,
│                                  # artifact-print-doc, artifact-nav, primitives
└── backend/
    ├── main.py               # FastAPI
    ├── requirements.txt
    ├── app/
    │   ├── config/settings.py    # pydantic-settings
    │   ├── core/{logger,security}.py    # security: hashing bcrypt + JWT
    │   ├── core/permissions.py   # MATRIZ rol → módulo/nivel (fuente única)
    │   ├── errors.py             # errores de app (auth/permisos → ApiResponse)
    │   ├── api/v1/{router,health,auth,ef,scrum,arquitectura,bd,apis,qa,
    │   │           gasto}.py
    │   ├── dependencies/         # current_user (401) + permissions (403)
    │   ├── middlewares/  models/    # models: agent, user (+ grants), spend
    │   ├── services/spend_sink.py # libro mayor real + preflight del mes (GAS1)
    │   ├── services/spend_report_service.py  # el mes que se mira (GAS2)
    │   ├── repositories/         # + story_assignment, llm_spend (libro mayor)
    │   ├── services/  schemas/  utils/
    ├── scripts/create_admin.py    # bootstrap del primer admin (CLI)
    ├── scripts/capture_explore_fixture.py  # captura fixtures del Modo C (manual)
    ├── scripts/anclas_de_html.py   # imprime la tabla de anclas de un .html (manual)
    ├── scripts/seed_qa_demo.py     # cadena EF→…→QA sembrada, sin gastar tokens
    ├── scripts/medir_linea_base.py # el «antes» de los recortes, reconstruido (0 USD)
    ├── scripts/medir_escala_por_tamano.py  # cómo escala la cadena con el documento
    ├── scripts/reset_password.py  # recuperación de acceso (CLI, sin eco)
    ├── shared/responses/api_response.py
    └── ai/
        ├── orchestrator/
        ├── inventory/            # INVENTARIO: ddl_import, doc_import, matching,
        │                         # reconcile, promote, loader, nodes, contract
        ├── agents/ef/            # (+ scrum/, arquitectura/, bd/, api/, qa/, base/)
        │                         # bd/ddl/:      render + validación del DDL (sin LLM)
        │                         # api/openapi/: render + validación del spec (sin LLM)
        │                         # qa/explore/:  guard del Modo C (5 capas) + navegador
        │                         #               + sanitize.py: saneador de capturas (A3)
        │                         #               + extract.py:  anclas deterministas (QC4.5+QC5)
        │                         #               + network.py:  capa 3 en red (QC5)
        │                         #               + driver.py:   Playwright, la única cáscara
        ├── llm/                  # fábrica multiproveedor + metering.py (medición)
        │                         # + budget.py (el freno y el sumidero, GAS1)
        ├── memory/
        ├── knowledge/            # glosario, tech_stack.yaml, db_conventions.yaml,
        │                         # api_conventions.yaml
        ├── tools/{parsers,chunker,validation}/
        └── prompts/ef/           # (+ scrum/, arquitectura/, bd/, api/, qa/)
```
