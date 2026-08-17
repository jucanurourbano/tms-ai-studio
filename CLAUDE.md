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
ver §5.5 y `docs/diseno-agente-qa.md`). Siguiente eslabón: **Agente Backend**.

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
- **REGLA DE RESPALDO:** hacer **push al remoto después de CADA fase commiteada**.

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
│   └── diseno-agente-scrum.md
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
    │   ├── api/v1/{router,health,auth,ef,scrum,arquitectura,bd,apis,qa}.py
    │   ├── dependencies/         # current_user (401) + permissions (403)
    │   ├── middlewares/  models/    # models: agent, user (+ grants)
    │   ├── repositories/         # + story_assignment_repository
    │   ├── services/  schemas/  utils/
    ├── scripts/create_admin.py    # bootstrap del primer admin (CLI)
    ├── scripts/seed_qa_demo.py     # cadena EF→…→QA sembrada, sin gastar tokens
    ├── scripts/reset_password.py  # recuperación de acceso (CLI, sin eco)
    ├── shared/responses/api_response.py
    └── ai/
        ├── orchestrator/
        ├── inventory/            # INVENTARIO: ddl_import, doc_import, matching,
        │                         # reconcile, promote, loader, nodes, contract
        ├── agents/ef/            # (+ scrum/, arquitectura/, bd/, api/, qa/, base/)
        │                         # bd/ddl/:      render + validación del DDL (sin LLM)
        │                         # api/openapi/: render + validación del spec (sin LLM)
        ├── memory/
        ├── knowledge/            # glosario, tech_stack.yaml, db_conventions.yaml,
        │                         # api_conventions.yaml
        ├── tools/{parsers,chunker,validation}/
        └── prompts/ef/           # (+ scrum/, arquitectura/, bd/, api/, qa/)
```
