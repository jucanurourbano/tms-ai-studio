# Diseño — Agente Scrum (segundo agente del ISDF)

> Documento de arquitectura aprobado. Fuente de verdad para la implementación del
> Agente Scrum. Ver también `CLAUDE.md` (memoria del proyecto) y el Agente EF ya
> construido, cuyo patrón se reutiliza.

---

## 0. Principio rector

El Agente Scrum es **el mismo patrón del EF aplicado a un dominio distinto**: un
pipeline LangGraph de nodos con *structured output*, ciclo de afinamiento,
trazabilidad total y métricas reales. Consigna arquitectónica: **maximizar
reutilización, generalizar lo mínimo imprescindible**, dado que el ISDF tiene 9
agentes por delante. No se re-implementa infraestructura; se eleva a "plataforma
multi-agente".

El Agente Scrum **consume un `EFArtifact` v1.2.0 listo** (`ready_for_next_stage=true`)
y produce los insumos de planificación ágil del equipo de Sistemas: épicas,
historias de usuario, criterios de aceptación, estimaciones, backlog priorizado,
plan de sprints y preguntas al Product Owner.

---

## 1. Arquitectura general y reutilización

### Se reaprovecha **tal cual** (cero cambios)

| Pieza | Ubicación | Uso en Scrum |
|---|---|---|
| Checkpointer Redis (`thread_id=job_id`) | `ai/orchestrator/checkpointer.py` | idéntico |
| Cliente Claude (`get_claude_client`, `call_with_retry` con retry-after, `estimate_cost`, `ClaudeLLMClient`) | `app/dependencies/claude.py`, `ai/agents/ef/extract.py` | idéntico (`LLMClient` protocol es agnóstico) |
| Envelope `ApiResponse` + middleware `AgentError` | `shared/`, `app/middlewares/` | idéntico |
| Métricas (`TokenMetrics`, `SkippedItem`, cuarentena, coste real en `BackgroundTasks`) | esquemas EF | reutilizadas en `ScrumArtifact` |
| Glosario logístico | `ai/knowledge/glossary.yaml` + loader | inyectado en nodos generativos (EPICS/STORIES/CRITERIA) |
| Patrón de nodo con *repair loop* + cuarentena (`extract_dimension`/`run_extract`) | `ai/agents/ef/extract.py` | **se extrae a base compartida** |
| Base de tests con mocks, black/isort | — | idéntico |

### Requiere **generalizarse** (una vez, ahora)

**(a) Base de agentes compartida** — `ai/agents/base/`:
- `structured.py`: `LLMClient` protocol + `run_map(...)` genérico (concurrencia
  configurable + reparación de schema + cuarentena en `metrics.skipped`), hoy
  embebido en `extract.py`. EF y Scrum lo consumen.
- `graph.py`: helper de compilación lineal de grafos (factoriza el patrón
  `_NODES` → compile con checkpointer).
- `refine.py`: constructor de "contexto autoritativo" desde validaciones (hoy en
  `ef_service.create_refine`).
- `pipeline.py`: runner genérico de `BackgroundTasks` (hoy `run_ef_pipeline`),
  parametrizado por `agent_type`, builder de grafo y `persist`.

**(b) Persistencia multi-agente — DECISIÓN CLAVE (aprobada).**

Se **unifican** las tablas `ef_*` en tablas multi-agente con discriminador
`agent_type`. No hay tablas propias por agente.

```
agent_jobs        (reemplaza ef_jobs)
  id, agent_type (ef|scrum|arquitectura|…), status,
  parent_job_id (self-FK: refine del MISMO agente),
  input_job_id  (self-FK NULLABLE: entrada CROSS-agente → Scrum.input_job_id = EF job.id),
  source_doc_id (NULLABLE: solo familia EF),
  error, metrics (JSONB), timestamps

agent_artifacts   (reemplaza ef_artifacts)
  id, job_id FK, schema_version, data (JSONB)   # ya es agnóstico

agent_validations (reemplaza ef_validations)
  id, job_id FK, target_type, target_id, status, respuesta   # target_type extensible
```

**Justificación:**
- Las tablas EF **ya son agnósticas**: `ef_jobs` no tiene columnas específicas de
  EF; `ef_artifacts` guarda `data` JSONB + `schema_version`. Solo faltan
  `agent_type` (discriminador) e `input_job_id` (encadenado cross-agente).
- El ISDF tiene **9 agentes**. Tablas por agente ⇒ ~36 tablas y 9 repositorios
  casi idénticos: insostenible.
- **Costo del refactor = bajo**: datos de desarrollo (hay `seed_demo.py` y
  migraciones; sin datos de producción). Migración `0002_generalizar_agentes`
  renombra tablas, agrega `agent_type`/`input_job_id`, y `EFRepository` →
  `AgentJobRepository` genérico.
- `target_type` de validaciones pasa de `question|assumption` a un enum
  extensible; Scrum usa `question` (preguntas al PO) desde v1.

Alternativa rechazada (**tablas `scrum_*` separadas**): duplica esquema,
repositorio, servicio y migraciones; multiplica por 9 el mantenimiento; sin
ganancia (el `data` ya es JSONB).

### Flujo (Clean Architecture, sin cambios)

```
api/v1/scrum.py → services/scrum_service.py → repositories/agent_job_repository.py → models/agent.py
                        │
                        └→ ai/orchestrator/scrum_graph.py → ai/agents/scrum/* (+ ai/agents/base/*)
```

---

## 2. Pipeline de nodos del grafo Scrum

```
LOAD_EF → EPICS → STORIES → CRITERIA → ESTIMATE → PRIORITIZE
        → SPRINT_PLAN → CRITIQUE → QUESTION_GEN → ASSEMBLE → PERSIST
```

| Nodo | Tipo | Qué hace | Orden |
|---|---|---|---|
| **LOAD_EF** | determinista | Carga el `EFArtifact` + su *validation summary*; **verifica `ready_for_next_stage=true`**; expone RF/procesos/reglas/entidades. Reinyecta respuestas del PO si es refine. | Única fuente; primero. |
| **EPICS** | LLM (structured) | Deriva épicas de **módulos y procesos** del EF. | Las historias cuelgan de épicas. |
| **STORIES** | LLM *map* (concurrencia N) | Una pasada por **requisito funcional** → historias "Como/quiero/para" con `source_refs` a RF/proceso/regla. Detecta `dependencies`. | Necesita épicas; patrón EXTRACT. |
| **CRITERIA** | LLM *map* por historia | Criterios de aceptación (Gherkin) derivados de **reglas + validaciones** ligadas a los refs de la historia. | Requiere historias. |
| **ESTIMATE** | LLM por historia | Story points (Fibonacci) + `estimation_rationale` + `confidence`, `origin=derived`. | Los criterios informan el esfuerzo. |
| **PRIORITIZE** | híbrido | LLM propone MoSCoW + valor/esfuerzo; **Python** arma el `product_backlog` ordenado (bucket MoSCoW → ratio valor/esfuerzo). | Necesita puntos. |
| **SPRINT_PLAN** | **determinista** | *Bin-packing* voraz por capacidad configurable, respetando **dependencias** y el orden del backlog; lo que no cabe → `unassigned`. | Reproducible/testeable. |
| **CRITIQUE** | híbrido | Chequeos deterministas en Python (refs huérfanas al EF, **cobertura** RF, ciclos de dependencias, capacidad excedida) + pase LLM (riesgos). | Determinista primero. |
| **QUESTION_GEN** | determinista | Preguntas al **PO** (RF sin cobertura, estimaciones de baja confianza, historias ambiguas, dependencias circulares). Técnico interno → observaciones. | Igual patrón EF. |
| **ASSEMBLE / PERSIST** | determinista | Ensambla `ScrumArtifact`, métricas reales, descartes → `Observation` (nunca silenciosos); valida esquema; persiste; marca `COMPLETED[_WITH_WARNINGS]`. | Igual que EF. |

Regla dura heredada: **prohibido inventar requisitos**. Si una historia no tiene
base en el EF, no se crea: se emite una pregunta al PO.

---

## 3. Contrato `ScrumArtifact v1.0.0`

Claves en inglés, valores en español; todo ítem trazable con
`id`/`source_ref(s)`/`confidence`/`origin`. Reusa `TokenMetrics`/`SkippedItem`/
`Observation` del EF.

```jsonc
{
  "schema_version": "1.0.0",
  "source": {
    "ef_job_id": "…",              // job EF de origen (agent_jobs.id)
    "ef_artifact_hash": "…",       // hash del contenido EF consumido
    "ef_schema_version": "1.2.0",
    "ready_snapshot": true         // gate verificado al generar
  },
  "epics": [{
    "id": "EPIC-001", "title": "…", "description": "…",
    "source_refs": ["MOD-001","PRO-001"],   // módulos/procesos del EF
    "story_ids": ["US-001","US-002"],
    "confidence": 0.8, "origin": "derived"
  }],
  "stories": [{
    "id": "US-001",
    "role": "…", "goal": "…", "benefit": "…",
    "statement": "Como <rol> quiero <objetivo> para <beneficio>",
    "epic_ref": "EPIC-001",
    "source_refs": { "requirement_refs":["REQ-F-001"], "process_refs":["PRO-001"], "rule_refs":["BR-001"] },
    "acceptance_criteria": [{
      "id": "AC-001", "format": "gherkin",
      "given": "…", "when": "…", "then": "…",   // o "text" si no aplica Gherkin
      "source_refs": ["BR-001","VAL-001"], "origin": "derived"
    }],
    "story_points": 5,                         // Fibonacci: 1,2,3,5,8,13,21
    "estimation_rationale": "…", "estimation_confidence": 0.6,
    "priority": "must",                        // MoSCoW: must|should|could|wont
    "value": 4, "effort": 3,                   // 1–5, desempate valor/esfuerzo
    "dependencies": ["US-002"],
    "confidence": 0.7, "origin": "derived",
    // --- Campos nacidos compatibles con ClickUp (§7) ---
    "tags": ["ef:JOB123","REQ-F-001","EPIC-001"],
    "external_key": "JOB123:US-001"            // clave idempotente estable
  }],
  "product_backlog": {
    "method": "moscow",                        // moscow | value_effort
    "ordered_story_ids": ["US-001","US-002","…"],
    "rationale": "…"
  },
  "sprints": [{
    "id": "SPRINT-1", "goal": "…",
    "capacity_points": 20, "total_points": 18,
    "story_ids": ["US-001","US-003"]
  }],
  "unassigned_story_ids": ["US-009"],          // no cupieron (visible, nunca oculto)
  "questions_for_po": [{
    "id": "Q-001", "question": "…", "reason": "…",
    "audience": "negocio",                     // negocio | tecnico
    "blocking": true, "linked_to_ref": "US-004", "status": "pendiente"
  }],
  "analysis": {
    "risks": [{ "id":"RISK-001","description":"…","severity":"alta","source_ref":"…" }],
    "observations": [{ "id":"OBS-001","description":"…","reason":"…" }],
    "coverage": {
      "requirements_total": 12, "requirements_covered": 11,
      "coverage_ratio": 0.92, "uncovered_requirement_refs": ["REQ-F-007"]
    }
  },
  "metrics": {
    "tokens": {"input":0,"output":0,"total":0}, "cost":0.0, "duration":0.0,
    "stories_total": 0, "points_total": 0, "sprints_total": 0,
    "coverage": 0.92, "skipped": []
  }
}
```

**Compatibilidad ClickUp desde v1:** `stories[].tags`, `external_key`, `priority`
(mapeable), `acceptance_criteria` estructurados, `sprints[].id/goal`, `epics[]`
— todo lo necesario para construir el payload de ClickUp **ya vive aquí**. Los
IDs de ClickUp *creados* NO se guardan en el artefacto (se persisten en una tabla
de auditoría, §7), para que el artefacto siga siendo una salida de planificación
pura.

---

## 4. Estrategia de prompts (`ai/prompts/scrum/`)

Base común (`_base.md`) + rol estrecho por dimensión. Reglas heredadas del EF:
derivar **solo** de lo presente en el EF, structured output (nunca JSON libre),
marcar `origin=derived`, `source_refs` obligatorios, glosario inyectado,
**razonar en español / claves en inglés**, y si falta base → **pregunta al PO**
(no inventar).

| Prompt | Rol estrecho | Entrada → Salida | Anti-alucinación |
|---|---|---|---|
| `epics.md` | Agrupador de épicas | módulos+procesos EF → épicas | cada épica cita ≥1 `source_ref` real |
| `stories.md` | Redactor de historias | 1 RF (+contexto proceso/regla) → historias | prohibido crear historia sin `requirement_ref` |
| `criteria.md` | Analista de aceptación | historia + reglas/validaciones → Gherkin | criterios anclados a `rule_refs`/`validation_refs` |
| `estimate.md` | Estimador ágil | historia + criterios → puntos Fibonacci + razón + confidence | escala Fibonacci cerrada (enum); confidence obligatorio |
| `prioritize.md` | Product analyst | historias + valor/esfuerzo → MoSCoW + justificación | solo clasifica; el orden lo arma Python |
| `critique.md` | Crítico de plan | modelo consolidado → riesgos/vacíos | no propone soluciones técnicas |

Glosario: el logístico (dominio) se inyecta en EPICS/STORIES/CRITERIA. La
terminología ágil (épica, story point, sprint) vive en los prompts (vocabulario
propio del agente); no requiere nuevo glosario.

---

## 5. Persistencia y relación con el job EF + refine

- **Generación**: `POST /api/v1/scrum/plans {ef_job_id, capacity_points?}` → el
  servicio **falla rápido** si el EF no está listo (ver gate); si ok, crea
  `agent_jobs(agent_type='scrum', input_job_id=ef_job_id, status=PENDING)` y
  encola el pipeline (`BackgroundTasks`).
- **Enlace al EF**: `agent_jobs.input_job_id` → EF `agent_jobs.id`. El artefacto
  guarda además `source.ef_artifact_hash` para reproducibilidad.
- **Persistencia del artefacto**: `agent_artifacts(job_id, schema_version='1.0.0',
  data=<ScrumArtifact>)`. Métricas reales en `agent_jobs.metrics`.
- **Refine (PO)**: `POST /api/v1/scrum/jobs/{id}/refine` → crea
  `agent_jobs(agent_type='scrum', parent_job_id=<scrum original>, input_job_id=<mismo EF>)`,
  reinyecta las validaciones `confirmado|corregido` del PO como **contexto
  autoritativo** en STORIES/CRITERIA/ESTIMATE. Nueva versión del `ScrumArtifact`.
  Idéntico patrón al EF (`create_refine` generalizado en `ai/agents/base/refine.py`).

### Gate de entrada — "¿y si el EF no está listo?"

`ready_for_next_stage` del EF se computa de su *validation summary* (sin
preguntas bloqueantes pendientes). El servicio Scrum lo verifica **antes de crear
el job**:
- Si no está listo → **rechazo `409/400`** con `ApiResponse.fail`:
  `"El artefacto EF <id> no está listo para planificación: quedan N preguntas
  bloqueantes sin responder. Complétalas o genera una versión afinada
  (POST /ef/jobs/<id>/refine)."`
- Re-verificado defensivamente en `LOAD_EF`.

---

## 6. `ready_for_next_stage` del Scrum y siguiente eslabón

**Verde cuando** (condición compuesta, gate del PO como primaria):
1. **No hay preguntas bloqueantes al PO pendientes** (primaria, espejo del EF), y
2. Toda historia `must`/`should` tiene estimación, y
3. **Cobertura** ≥ umbral configurable (default 100% de RF cubiertos por ≥1
   historia; RF sin cobertura genera pregunta bloqueante), y
4. Ninguna historia `must` quedó `unassigned` en el sprint plan.

**Siguiente eslabón: Agente Arquitectura** (fase DISEÑAR). Tras el "qué + plan"
(EF→Scrum) sigue el "cómo técnico": Arquitectura toma `stories[]` +
`entities[]`/`relationships[]` del EF → diseño de componentes/capas; luego BD,
API, Backend, Frontend. Cadena:
`EF → Scrum → Arquitectura → BD → API → Backend/Frontend → QA → DevOps`.

---

## 7. Integración ClickUp (diseño ahora, implementación posterior)

### Restricción de seguridad — garantizada **estructuralmente**

- **Config fija** (`settings`/`.env`, nunca hardcode): `CLICKUP_API_TOKEN`,
  `CLICKUP_WORKSPACE_ID` (team), `CLICKUP_SPACE_ID` (**Sistemas**),
  `CLICKUP_ALLOWED_LIST_IDS` (allowlist explícita), opcional `CLICKUP_FOLDER_ID`.
- **Guard obligatorio** (`ai/integrations/clickup/guard.py`): **toda** operación
  de escritura pasa por `assert_target_authorized(list_id)` que (a) resuelve
  `list → folder → space` vía API y (b) exige `space_id == CLICKUP_SPACE_ID` **y**
  `list_id ∈ allowlist`. Destino fuera → `ClickUpForbiddenError` (rechazo
  explícito). **Fail-closed**: sin allowlist configurada, el módulo no escribe nada.
- **Auditoría**: tabla `agent_external_links`
  `{id, scrum_job_id, story_id, external_key, clickup_task_id, list_id, action, created_at}`.
  Cada tarea creada queda registrada (qué historia la originó, cuándo, en qué lista).
- **Nunca** borrado/movimiento fuera del espacio; el token se usa solo tras pasar
  el guard.

### Mapeo conceptual (recomendado + alternativas)

| Concepto Scrum | ClickUp (recomendado) | Alternativa |
|---|---|---|
| Sprint | **Lista** (`Sprint 1`, `Sprint 2`, `Backlog`) en carpeta `TMS · Sistemas · <EF job>` | Sprint nativo de ClickUp (a nivel space — más riesgo en cuenta compartida; **evitar en v1**) |
| Historia | **Tarea** en la lista del sprint (descripción = statement + criterios; puntos = custom field; prioridad; tags de trazabilidad) | subtarea de una tarea-épica |
| Épica | **Tag + custom field "Épica"** en la tarea (opcional tarea-padre) | Lista por épica (choca con lista=sprint) |
| Criterios | **Checklist/markdown** en la descripción | custom field |
| Estimación | custom field de puntos (o `points` nativo) | tag |
| Prioridad | ClickUp priority: must→urgent, should→high, could→normal, wont→low | custom field |
| Trazabilidad EF | tags `ef:<job>`, `REQ-F-…` + custom field "EF ref" | solo descripción |

**Elegido:** Sprint→Lista, Historia→Tarea, Épica→tag/custom field (más una carpeta
por corrida). Mantiene todo dentro de una carpeta acotada del space de Sistemas
(auditable y borrable en conjunto) y usa el tablero por sprint del equipo. Se
evita la feature nativa de Sprints por ser a nivel space (mayor superficie de
riesgo en cuenta compartida).

### Dos fases

- **(a) Export compatible — primera entrega, cero riesgo, sin token**: CSV/JSON
  con el formato de importación de ClickUp (Task Name, Description, Status,
  Priority, Tags, Custom Field puntos, List=Sprint). Solo lectura del artefacto →
  archivo; importación manual por el usuario.
- **(b) API directa — fase posterior**: cliente ClickUp con token en settings;
  **`dry_run` por defecto** que devuelve el plan de creación (QUÉ tareas/listas y
  en qué destino) **antes** de crear; creación **idempotente** por `external_key`
  (consulta `agent_external_links`; si existe, no duplica — *upsert*). Todo tras
  el guard.

El `ScrumArtifact` ya nace con `tags`, `external_key`, `priority`, criterios
estructurados y agrupación sprint/épica ⇒ **sin migración de esquema** al
implementar (b).

---

## 8. Reutilización de UI

- **Nav**: activar **"Agente Scrum"** en el grupo **GESTIONAR** (`ISDF_NAV`); el
  resto sigue "próximamente".
- **Flujo**: `/agents/scrum` (landing) → `/agents/scrum/new` (elegir un **job EF
  listo**: lista de jobs EF con `ready_for_next_stage=true`, o pegar `ef_job_id`,
  + input de **capacidad por sprint**) → `POST /scrum/plans` →
  `/agents/scrum/jobs/[jobId]` (Progreso↔Resultado, idéntico patrón).
- **Reutilización concreta**: `ProgressView`, `ValidationControls`, `badges`
  (confidence/origin/audience/status), `Mono`, `RefLink` (deep-link + resaltado),
  barra de afinamiento, semáforo, botón Regenerar (con costo estimado), Descargar
  JSON, e índice-lateral + tablas densas — **ya son genéricos**. Se factoriza un
  `ArtifactShell` (cabecera + índice + barra de afinamiento + semáforo) desde
  `result-view.tsx`, y `ScrumResultView` compone sus secciones:
  1. **Backlog** (orden, MoSCoW).
  2. **Sprints** (capacidad/puntos, historias, `unassigned` visible con ⚠).
  3. **Historias** (statement, refs al EF navegables, criterios Gherkin,
     puntos+razón+confidence, prioridad, dependencias).
  4. **Épicas**.
  5. **Preguntas al PO** (validación inline, filtro bloqueantes).
  6. **Análisis** (riesgos, cobertura con RF no cubiertos explícitos).
- Semáforo: **"Listo para el Agente Arquitectura"**.
- `lib/api/scrum.ts` reusa `apiRequest` (envelope centralizado) + tipos TS espejo
  del `ScrumArtifact`.

---

## 9. Decisiones acordadas

| # | Decisión | Acordado |
|---|---|---|
| D1 | Persistencia | **Generalizar** tablas `ef_*` → `agent_*` (agent_type, input_job_id) + `AgentJobRepository` |
| D2 | Siguiente eslabón ISDF | **Arquitectura** |
| D3 | Priorización | **MoSCoW** primario + valor/esfuerzo como desempate |
| D4 | Capacidad de sprint | **20 puntos/sprint** por defecto, configurable (request + settings) |
| D5 | `ready_for_next_stage` Scrum | **Compuesto** (sin bloqueantes + cobertura + estimadas + sin `must` sin asignar) |
| D6 | Objetivos de validación | v1 solo `question` (PO); corregir estimaciones (`estimate`) en v1.1 |
| D7 | Mapeo ClickUp | **Sprint→Lista, Historia→Tarea, Épica→tag/custom field**, sin Sprints nativos |
| D8 | Dependencias | Campo `dependencies` en la historia (detección LLM + validación de ciclos en CRITIQUE); sin nodo dedicado |
| D9 | Estimación | **LLM** con enum Fibonacci cerrado + confidence; re-estimación en refine |

Riesgos gestionados en implementación: cobertura como "silent cap" → siempre
reportar RF no cubiertos; determinismo de `SPRINT_PLAN` para tests; guard de
ClickUp **fail-closed**; idempotencia de refine (checkpointer no re-factura).

---

## 10. Plan de implementación por bloques (método EF)

Cada bloque: `pytest`/`build`/`lint` en verde, **commit + push**, todo con
**mocks** (sin API real de Anthropic ni escrituras reales a ClickUp).

| Bloque | Contenido |
|---|---|
| **B0** | Generalización de persistencia (`agent_*` + `AgentJobRepository` + migración `0002`) y base compartida `ai/agents/base/`. EF sigue verde. |
| **B1** | Contrato `ScrumArtifact v1.0.0` (Pydantic + fixture + round-trip). |
| **B2** | Grafo Scrum + `LOAD_EF` (+ gate) + nodos stub. |
| **B3** | EPICS/STORIES/CRITERIA (LLM mockeado) + trazabilidad. |
| **B4** | ESTIMATE/PRIORITIZE/SPRINT_PLAN (SPRINT_PLAN determinista). |
| **B5** | CRITIQUE/QUESTION_GEN + cobertura. |
| **B6** | ASSEMBLE/VALIDATE/PERSIST + servicio + API (`/scrum/*`) + refine + gate 4xx. |
| **B7** | Export ClickUp (CSV/JSON) + guard + auditoría (fase (a), sin API). |
| **B8** | Frontend: nav GESTIONAR, `ArtifactShell` factorizado, `ScrumResultView`, flujo new→plan→afinar. |
