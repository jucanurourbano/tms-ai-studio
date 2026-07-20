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
multi-agente (D1). Siguiente eslabón: **Agente Arquitectura**.

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

## 5. Ciclo de afinamiento

- Las **validaciones** (`pendiente` | `confirmado` | `corregido` + respuesta) se
  persisten **aparte, sin mutar el artefacto**.
- `POST /refine` crea un **job hijo** (`parent_job_id`) que inyecta las respuestas
  como **contexto autoritativo**.
- `ready_for_next_stage = true` cuando **no hay preguntas `blocking` pendientes**
  (gate del EF hacia el Agente Scrum; el Scrum tiene su propio gate compuesto, §4).

---

## 6. Lecciones obligatorias

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

## 7. Reglas de proceso

- **Modelo Claude por defecto:** `claude-sonnet-5` (`CLAUDE_MODEL` en `.env`).
  Tarifas para cálculo de costos: **$3 / MTok input**, **$15 / MTok output**
  (`CLAUDE_PRICE_INPUT/OUTPUT_PER_MTOK`). Timeout **180s** (`CLAUDE_TIMEOUT`).
- **REGLA DE PRESUPUESTO:** nunca ejecutar análisis contra la **API real de
  Anthropic** sin autorización explícita del usuario. Desarrollo y tests
  **siempre con mocks**. Tampoco escrituras reales a ClickUp sin autorización.
- **REGLA DE RESPALDO:** hacer **push al remoto después de CADA fase commiteada**.

---

## 8. Alcance v1

- **Sin OCR.**
- **Sin RAG pgvector** (la extensión está disponible en la imagen, pero no se usa
  en v1).
- **Sin pausa human-in-the-loop.**

---

## 9. Estructura del repositorio

```
tms-ai-studio/
├── docker-compose.yml        # PostgreSQL 16 (pgvector) + Redis 7
├── .env.example
├── CLAUDE.md                 # este archivo
├── docs/
│   ├── setup-entorno.md
│   └── diseno-agente-scrum.md
├── frontend/                 # Next.js (cliente puro de la API)
└── backend/
    ├── main.py               # FastAPI
    ├── requirements.txt
    ├── app/
    │   ├── config/settings.py    # pydantic-settings
    │   ├── core/logger.py
    │   ├── api/v1/{router,health,ef}.py
    │   ├── dependencies/  middlewares/  models/
    │   ├── repositories/  services/  schemas/  utils/
    ├── shared/responses/api_response.py
    └── ai/
        ├── orchestrator/
        ├── agents/ef/            # (Scrum: ai/agents/scrum/ + ai/agents/base/)
        ├── memory/
        ├── knowledge/            # glosario logístico
        ├── tools/{parsers,chunker,validation}/
        └── prompts/ef/           # (Scrum: ai/prompts/scrum/)
```
