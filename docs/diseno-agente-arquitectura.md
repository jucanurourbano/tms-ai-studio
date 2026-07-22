# Diseño — Agente Arquitectura (tercer agente del ISDF)

> Documento de arquitectura **aprobado**. Fuente de verdad para la implementación
> del Agente Arquitectura. Ver también `CLAUDE.md` (memoria del proyecto),
> `docs/diseno-agente-scrum.md` y los Agentes EF/Scrum ya construidos, cuyo patrón
> se reutiliza.

---

## 0. Principio rector

El Agente Arquitectura es **el mismo patrón EF/Scrum aplicado al dominio "diseño
técnico"**: pipeline LangGraph con *structured output*, trazabilidad total, ciclo
de afinamiento, métricas reales y **prohibido inventar** (si falta base en
EF/Scrum → pregunta al Arquitecto/Líder Técnico). Consigna: **maximizar
reutilización, generalizar lo mínimo**. La infraestructura B0 ya es multi-agente,
así que este agente es sobre todo una **tercera instancia** del patrón.

Consume el **par EF + Scrum de un mismo flujo** (gate: Scrum
`ready_for_next_stage=true`) y produce el `ArchitectureArtifact v1.0.0`: estilo
arquitectónico justificado, componentes/módulos, stack recomendado, ADRs ligeros,
integraciones externas, contratos entre componentes, requisitos transversales,
diagramas (Mermaid), riesgos y preguntas al Arquitecto. Ese artefacto alimentará
a los Agentes **BD** y **API**.

---

## 1. Arquitectura general y reutilización

### Se reaprovecha **tal cual** (cero cambios)

| Pieza | Ubicación | Uso |
|---|---|---|
| Tablas `agent_*` (jobs/artifacts/validations) | `app/models/agent.py` | idéntico; `AgentType.ARQUITECTURA` **ya existe** |
| `AgentJobRepository` genérico | `app/repositories/agent_job_repository.py` | idéntico |
| Grafo lineal + checkpointer Redis (`thread_id=job_id`) | `ai/agents/base/graph.py`, `ai/orchestrator/checkpointer.py` | idéntico |
| `run_agent_pipeline` (BackgroundTasks, métricas reales, FAILED) | `ai/agents/base/pipeline.py` | idéntico |
| `run_map` (concurrencia + repair loop + cuarentena → `metrics.skipped`) | `ai/agents/base/structured.py` | idéntico (COMPONENTS/ADRS *map*) |
| `create_refine` / contexto autoritativo | `ai/agents/base/refine.py` | idéntico (refine del Arquitecto) |
| Cliente Claude, `ApiResponse`/`AgentError`, `GateError` (409) | `app/dependencies/claude.py`, `shared/`, `ai/errors.py` | idéntico |
| `TokenMetrics`/`SkippedItem`/`Observation` | esquemas EF | reutilizados |
| Loader de conocimiento (`load_glossary`/`glossary_block`) | `ai/knowledge/__init__.py` | patrón reutilizado (ver stack) |
| UI: `ArtifactShell`, `badges`, `ValidationControls`, `RefChip`, primitivas, sistema PDF/print | `frontend/src/components/artifact/*`, `.../ef/*` | idéntico |

### Se generaliza **adicionalmente** (mínimo, una vez)

1. **Conocimiento de casa** — `ai/knowledge/tech_stack.yaml` + loader
   (`load_tech_stack()` / `tech_stack_block()`), análogo al glosario. Es el
   mecanismo para que el agente **no proponga exotismos**: allow-list por capa +
   defaults + alternativas. **Refleja el stack con el que Urbano construye sus
   sistemas de negocio** (no el de TMS AI Studio). Nace marcado
   `PENDIENTE DE VALIDACIÓN` por el equipo.
2. **Carga de fuentes doble** — `LOAD_SOURCES` carga Scrum (directo) + EF
   (transitivo). Helper de nodo, no infraestructura nueva.
3. **Frontend `<MermaidDiagram>`** — componente cliente reutilizable con
   **import dinámico client-only y lazy SOLO en la vista del artefacto de
   Arquitectura** (no entra al bundle global). Servirá a futuros agentes de diseño.

**No hace falta:** migración de BD, cambios en grafo/pipeline/checkpointer, ni
repositorio nuevo. Dividendo de la generalización B0.

### Entrada doble EF + Scrum (D1 aprobada: transitiva, sin migración)

`agent_jobs.input_job_id = scrum_job_id` (predecesor directo). El **EF se resuelve
transitivamente** por `scrum_job.input_job_id`. El job de Arquitectura queda
enlazado a Scrum (directo) y a EF (transitivo) **sin columna nueva**. El artefacto
guarda ambos ids + hashes en `source` para reproducibilidad.

### Flujo (Clean Architecture, sin cambios)

```
api/v1/arquitectura.py → services/arquitectura_service.py
    → repositories/agent_job_repository.py → models/agent.py
          └→ ai/orchestrator/arquitectura_graph.py → ai/agents/arquitectura/* (+ ai/agents/base/*)
```

---

## 2. Pipeline de nodos del grafo

```
LOAD_SOURCES → CONTEXT → COMPONENTS → STACK → ADRS → CONTRACTS → DIAGRAMS
             → CRITIQUE → QUESTION_GEN → ASSEMBLE → PERSIST
```

Se añade **DIAGRAMS** (determinista): el Mermaid se genera **desde el grafo
estructurado** (componentes + contratos), no por LLM → sintaxis siempre válida y
reproducible.

| Nodo | Tipo | Qué hace |
|---|---|---|
| **LOAD_SOURCES** | determinista | Carga Scrum + su validation summary; **verifica Scrum `ready_for_next_stage=true`**; resuelve/carga el EF (transitivo); expone contexto consolidado (EF: entidades/relaciones/APIs/reglas/validaciones/RNF/módulos/procesos; Scrum: épicas/historias/puntos/sprints). Reinyecta respuestas del Arquitecto si es refine. |
| **CONTEXT** | híbrido | **Determinista:** *scope profile* (conteos) → `size_class` S/M/L con umbrales configurables (base del estilo, reproducible). **LLM (structured):** detecta **integraciones externas** citadas en el EF (p. ej. planillas ← *papeleta*) y propone *bounded contexts*. |
| **COMPONENTS** | LLM *map* | Componentes/módulos con responsabilidad, capa, `depends_on` y `source_refs` a EF (módulos/entidades/APIs/procesos) y Scrum (épicas/historias). Cada componente cita ≥1 ref real. |
| **STACK** | LLM (structured) sembrado con `tech_stack.yaml` | Stack **por capa** desde el allow-list de la casa + justificación + alternativas. Necesidad fuera del allow-list → **pregunta** (no exotismo). |
| **ADRS** | LLM (structured) | ADRs ligeros de las decisiones significativas (estilo, stack clave, integración, transversales). Cada ADR referencia sus decisiones. |
| **CONTRACTS** | híbrido | **Determinista:** contratos componente↔componente desde `depends_on`. **LLM:** clasifica `kind`, contratos con integraciones externas y **requisitos transversales** (auth/auditoría/notificaciones) desde RNF/reglas. Eventos/colas **solo si se justifican**. |
| **DIAGRAMS** | **determinista** | Mermaid desde componentes+contratos: `flowchart` de componentes por capa + diagrama de contexto (sistema ↔ integraciones). Reproducible/testeable. |
| **CRITIQUE** | híbrido | **Determinista:** componentes sin refs, épicas/entidades no cubiertas, ciclos de dependencia, integración sin contrato, **RNF sin transversal**. **LLM:** riesgos técnicos. |
| **QUESTION_GEN** | determinista | Preguntas al **Arquitecto** desde los vacíos: contrato de integración desconocido, estilo en zona límite, cobertura incompleta, **RNF sin atender (bloqueante)**, decisiones de baja confianza. Técnico interno → observaciones. |
| **ASSEMBLE / PERSIST** | determinista | Ensambla el artefacto, métricas reales, descartes → `Observation` (nunca silenciosos), valida esquema, persiste, marca `COMPLETED[_WITH_WARNINGS]`. |

**Recomendación de estilo (determinista + configurable).** El *scope profile*
pondera entidades, relaciones, historias, `points_total`, nº de integraciones y
procesos distintos → `size_class`:

- **S / M → monolito modular** (recomendación por defecto). Justificación:
  "Sistemas" es un solo equipo, simplicidad operativa, y la plataforma ya es un
  monolito modular.
- **L** (múltiples *bounded contexts* / escalado independiente / muchas
  integraciones) → considerar **microservicios**.
- **Serverless** solo si el perfil es event-driven / picos y stateless.

El LLM **justifica**; la clasificación la fija Python (reproducible). Sesgo
explícito hacia monolito modular salvo señales fuertes.

Regla dura heredada: **prohibido inventar**. Componente/integración/decisión sin
base en EF/Scrum → no se crea: se emite pregunta al Arquitecto (u observación).

---

## 3. Contrato `ArchitectureArtifact v1.0.0`

Claves en inglés, valores en español; todo ítem con
`id`/`source_refs`/`confidence`/`origin`. Reusa `TokenMetrics`/`SkippedItem`/
`Observation`.

```jsonc
{
  "schema_version": "1.0.0",
  "source": {
    "scrum_job_id": "…", "scrum_artifact_hash": "…", "scrum_schema_version": "1.0.0",
    "ef_job_id": "…",    "ef_artifact_hash": "…",    "ef_schema_version": "1.2.0",
    "ready_snapshot": true            // gate Scrum verificado al generar
  },
  "context": {
    "scope_profile": { "entities": 8, "relationships": 6, "modules": 4, "processes": 5,
                       "stories": 12, "points_total": 84, "integrations_detected": 1, "nfr_count": 3 },
    "size_class": "M",                // S | M | L (determinista)
    "bounded_contexts": [{ "id":"BC-001","name":"Siniestros","source_refs":["MOD-001","PRO-001"],
                           "origin":"derived","confidence":0.7 }]
  },
  "architecture_style": {
    "chosen": "modular_monolith",     // modular_monolith | microservices | serverless
    "rationale": "…", "adr_ref": "ADR-001", "confidence": 0.8, "origin": "derived"
  },
  "components": [{
    "id": "CMP-001", "name": "Módulo Siniestros", "type": "domain",   // ui|api|service|domain|integration|datastore|worker
    "layer": "dominio", "responsibility": "…",
    "source_refs": { "epic_refs":["EPIC-001"], "story_refs":["US-001"],
                     "entity_refs":["ENT-001"], "api_refs":["API-001"],
                     "module_refs":["MOD-001"], "process_refs":["PRO-001"] },
    "depends_on": ["CMP-005"], "confidence": 0.75, "origin": "derived"
  }],
  "stack": [{
    "id": "STK-001", "layer": "framework_backend", "technology": "…", "version": "…",
    "rationale": "…", "alternatives": ["…"], "source_refs": ["RNF-001"],
    "confidence": 0.9, "origin": "derived"
  }],
  "adrs": [{
    "id": "ADR-001", "title": "Estilo arquitectónico: monolito modular",
    "decision": "…", "context": "…",
    "alternatives_considered": ["microservicios","serverless"],
    "consequences": ["+ simplicidad operativa","- escalado por módulo limitado"],
    "status": "proposed", "source_refs": ["RNF-001","EPIC-001"],
    "confidence": 0.8, "origin": "derived"
  }],
  "integrations": [{
    "id": "INT-001", "name": "Sistema de Planillas", "system": "planillas",
    "direction": "outbound", "protocol": "unknown",   // rest|soap|file|db|queue|unknown
    "purpose": "Registrar descuentos a personal (papeleta).",
    "data_exchanged": "…", "source_refs": ["PRO-003","BR-005"],
    "contract_known": false, "confidence": 0.6, "origin": "derived"
  }],
  "contracts": [{
    "id": "CON-001", "from_ref": "CMP-002", "to_ref": "CMP-001",
    "kind": "sync_api",             // sync_api | event | shared_module | file | external
    "description": "…", "source_refs": ["API-001"], "confidence": 0.7, "origin": "derived"
  }],
  "cross_cutting": [{
    "id": "XC-001", "concern": "auth",   // auth|authorization|audit|notifications|logging|config|error_handling|i18n
    "requirement": "…", "approach": "…", "source_refs": ["RNF-002","BR-001"],
    "confidence": 0.7, "origin": "derived"
  }],
  "diagrams": {
    "component": { "format": "mermaid", "code": "flowchart LR\n …" },
    "context":   { "format": "mermaid", "code": "flowchart LR\n …" }
  },
  "analysis": {
    "risks": [{ "id":"RISK-001","description":"Contrato de Planillas desconocido",
                "severity":"alta","mitigation":"…","source_ref":"INT-001",
                "confidence":0.7,"origin":"derived" }],
    "observations": [{ "id":"OBS-001","description":"…","reason":"…" }],
    "coverage": {
      "epics_total": 3, "epics_mapped": 3, "uncovered_epic_refs": [],
      "entities_total": 8, "entities_mapped": 7, "uncovered_entity_refs": ["ENT-008"],
      "nfr_total": 3, "nfr_addressed": 2, "uncovered_nfr_refs": ["RNF-003"]
    }
  },
  "questions_for_architect": [{
    "id": "Q-001", "question": "¿Qué protocolo expone el sistema de Planillas (REST/archivo)?",
    "reason": "El contrato de la integración no está en el EF.",
    "audience": "tecnico", "blocking": true, "linked_to_ref": "INT-001", "status": "pendiente",
    "confidence": 0.6, "origin": "derived"
  }],
  "metrics": {
    "tokens": {"input":0,"output":0,"total":0}, "cost":0.0, "duration":0.0,
    "components_total": 0, "adrs_total": 0, "integrations_total": 0,
    "coverage": 0.9, "skipped": []
  }
}
```

**Trazabilidad** (bidireccional): `components[].source_refs` codifica
módulo→épicas/historias (hacia Scrum) y módulo→entidades/APIs (hacia EF); se
resume en `analysis.coverage`. **Eventos/colas** se representan como
`contracts[].kind == "event"` (sin lista redundante). Todo lo inferido lleva
`origin="derived"` + `confidence`.

---

## 4. Estrategia de prompts (`ai/prompts/arquitectura/`)

Base común (`_base.md`) + rol estrecho por dimensión. Reglas heredadas: derivar
**solo** de EF/Scrum, structured output (nunca JSON libre), `origin=derived`,
`source_refs` obligatorios, razonar en español / claves en inglés, y **si falta
base → pregunta al Arquitecto**.

| Prompt | Rol | Entrada → Salida | Anti-alucinación |
|---|---|---|---|
| `context.md` | Analista de alcance | EF+Scrum → integraciones + bounded contexts | integración citada solo con evidencia (proceso/regla) |
| `components.md` | Arquitecto de componentes | módulos/procesos/entidades + épicas → componentes | cada componente cita ≥1 ref real |
| `stack.md` | Arquitecto técnico (**`tech_stack.yaml` inyectado**) | capas + RNF → stack por capa | **enum cerrado** por capa (allow-list); exótico → pregunta |
| `adrs.md` | Redactor de ADRs | decisiones → ADRs (contexto/alternativas/consecuencias) | ADR ancla a `source_refs`; sin decisión inventada |
| `contracts.md` | Integrador | procesos/reglas/`depends_on` → contratos + transversales | integración sin base → no se crea; contrato desconocido → `contract_known=false` + pregunta |
| `critique.md` | Crítico de arquitectura | modelo consolidado → riesgos/vacíos | no propone implementación; solo señala |

Inyecciones: **glosario logístico** en CONTEXT/COMPONENTS/CONTRACTS;
**`tech_stack_block()`** en STACK; vocabulario arquitectónico (capas, ADR, bounded
context) vive en los prompts.

---

## 5. Gate, semáforo y persistencia

**Gate de entrada.** `POST /api/v1/arquitectura/designs {scrum_job_id}` → el
servicio **falla rápido** (`GateError` 409) si el Scrum no está listo
(`ready_for_next_stage=true`), con mensaje claro (completar preguntas al PO o
generar plan afinado). Re-verificado en `LOAD_SOURCES`. El EF ya estaba listo
transitivamente (invariante del Scrum); se snapshotea igual.

**Semáforo de salida — `ready_for_next_stage` (misma semántica que EF/Scrum:
sin bloqueantes + contenido mínimo):**
1. **No hay preguntas bloqueantes al Arquitecto pendientes** (primaria), **y**
2. **Contenido mínimo:** estilo arquitectónico decidido (ADR presente) **y** ≥1
   componente **y** cobertura de épicas/entidades ≥ umbral configurable.

Los **RNF sin atender** y los **contratos de integración desconocidos** **no** son
condiciones extra del gate: se convierten en **preguntas bloqueantes** al
Arquitecto (así entran por la condición primaria). Un único `ready` habilita al
**Agente BD** (siguiente eslabón) y al **Agente API**.

**Persistencia / refine.** `agent_jobs(agent_type='arquitectura',
input_job_id=scrum_job_id)`; artefacto en `agent_artifacts`; métricas en
`agent_jobs.metrics`. Refine del Arquitecto: `POST /arquitectura/jobs/{id}/refine`
→ `parent_job_id=<arch original>, input_job_id=<mismo scrum>`, reinyecta
validaciones `confirmado|corregido` como contexto autoritativo en
COMPONENTS/STACK/ADRS/CONTRACTS. Mismo `create_refine` generalizado.

Cadena ISDF: `EF → Scrum → Arquitectura → BD → API → Backend/Frontend → QA → DevOps`.

---

## 6. Reutilización de UI

- **Nav:** activar **"Arquitectura"** en el grupo **DISEÑAR** (`ISDF_NAV`, hoy
  `enabled:false`).
- **Flujo:** `/agents/arquitectura` (landing) → `/new` (elegir un **job Scrum
  listo**: lista con `ready_for_next_stage=true` o pegar `scrum_job_id`) →
  `POST /arquitectura/designs` → `/jobs/[jobId]` (Progreso↔Resultado, patrón
  idéntico).
- **`ArchitectureResultView`** dentro del `ArtifactShell` reutilizado, secciones:
  **Resumen + Estilo** (ADR-001) · **Componentes** (+ diagrama) · **Diagrama de
  contexto** · **Stack** (tabla) · **ADRs** · **Integraciones** · **Contratos** ·
  **Transversales** · **Análisis** (riesgos + cobertura con no-cubiertos
  explícitos) · **Preguntas al Arquitecto** (validación inline, filtro
  bloqueantes). Reusa `RefChip` (deep-link EF/Scrum), badges, mini-stats,
  semáforo "Listo para el Agente BD".
- **Mermaid:** `<MermaidDiagram code>` cliente con **import dinámico
  (`ssr:false`) y lazy solo en esta vista** (no en el bundle global),
  `securityLevel:'strict'`, tema claro/oscuro; *fallback* a bloque de código si
  falla el parseo.
- **Export PDF:** sistema editorial existente + **página(s) de diagramas** (el SVG
  de Mermaid imprime nativo, a ancho completo), **ADRs** como fichas y **stack**
  como tabla. Portada "Diseño de Arquitectura", versión y ficha de métricas
  (componentes, ADRs, integraciones, cobertura).
- `lib/api/arquitectura.ts` + tipos TS espejo del artefacto.

---

## 7. Decisiones acordadas (A1–A8)

| # | Decisión | Acordado |
|---|---|---|
| A1 | Entrada doble EF+Scrum | **Transitiva** (`input_job_id=scrum`, EF vía `scrum.input_job_id`). **Sin migración.** |
| A2 | Recomendación de estilo | **Scope profile determinista + heurística**; LLM justifica. Default **monolito modular**. |
| A3 | Diagramas | **Deterministas** desde el grafo estructurado (Mermaid válido). Nodo `DIAGRAMS`. |
| A4 | Mermaid en frontend | Añadir `mermaid`; **import dinámico client-only y lazy SOLO en la vista de Arquitectura** (no bundle global). |
| A5 | Stack | Allow-list **cerrada** por capa desde `tech_stack.yaml` (stack **de negocio de Urbano**, PENDIENTE DE VALIDACIÓN); exótico → pregunta. |
| A6 | Granularidad de componentes | Nivel **bounded-context/módulo** (~5–15), no clases. |
| A7 | Eventos/colas | **Síncrono en monolito por defecto**; eventos solo si se justifican; si no → `Observation` "no requerido v1". |
| A8 | Semáforo | **Único `ready`** (sin bloqueantes + contenido mínimo). RNF sin atender e integraciones sin contrato → **preguntas bloqueantes**, no condiciones extra. |

Riesgos gestionados: contratos de integración desconocidos → pregunta bloqueante;
sobre-ingeniería (mitigada por sesgo a monolito + "no inventar"); Mermaid inválido
(mitigado por generación determinista); cobertura como *silent cap* (siempre
reportar épicas/entidades/RNF no cubiertos).

---

## 8. Plan de implementación por bloques (método EF/Scrum)

Cada bloque: `pytest`/`build`/`lint` en verde, **todo con mocks** (sin API real de
Anthropic), **commit + push**.

| Bloque | Contenido |
|---|---|
| **A0** | `tech_stack.yaml` (borrador, PENDIENTE DE VALIDACIÓN) + loader; `<MermaidDiagram>` (frontend, lazy). Generalización mínima. EF/Scrum siguen verdes. |
| **A1** | Contrato `ArchitectureArtifact v1.0.0` (Pydantic + fixture + round-trip). |
| **A2** | Grafo + `LOAD_SOURCES` (carga doble + gate) + `CONTEXT` (scope profile determinista) + nodos stub. |
| **A3** | `COMPONENTS` + `STACK` (LLM mockeado) + trazabilidad a EF/Scrum. |
| **A4** | `ADRS` + `CONTRACTS` (contratos, integraciones, transversales) + `DIAGRAMS` (Mermaid determinista). |
| **A5** | `CRITIQUE` + `QUESTION_GEN` + cobertura (épicas/entidades/RNF → bloqueantes). |
| **A6** | `ASSEMBLE/VALIDATE/PERSIST` + servicio + API `/arquitectura/*` + refine + gate 409. |
| **A7** | Frontend: nav DISEÑAR, `ArchitectureResultView`, render Mermaid lazy, flujo new→design→afinar, export PDF con diagramas. |
