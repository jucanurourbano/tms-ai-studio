# Diseño — Agente BD (cuarto agente del ISDF)

> Documento de arquitectura **aprobado e implementado** (bloques BD0→BD8). Fuente
> de verdad del Agente BD. Ver también `CLAUDE.md`, `docs/diseno-agente-scrum.md`
> y `docs/diseno-agente-arquitectura.md`, cuyo patrón se reutiliza.

---

## 0. Principio rector

Cuarta instancia del mismo patrón, con **una diferencia de naturaleza**: su salida
es **ejecutable**. Un ADR mal redactado se discute; un `CREATE TABLE` mal generado
falla. De ahí la regla que gobierna todo el agente:

> **El LLM no escribe SQL nunca.** Decide semántica (qué tipo lógico, qué
> constraint, qué índice se justifica) y **Python renderiza** el DDL de forma
> determinista y lo **valida sin LLM**.

Consume el `ArchitectureArtifact` (gate: `ready_for_next_stage=true`) y,
transitivamente, el `EFArtifact` —su materia prima principal, la única validada con
runs reales—. Produce el `DatabaseArtifact v1.0.0`, que habilita al **Agente API**.

---

## 1. Reutilización

### Tal cual (cero cambios)

Tablas `agent_*` + `AgentJobRepository` (`AgentType.BD` ya existía), grafo lineal +
checkpointer Redis, `run_agent_pipeline`, `run_structured_map`, `create_refine`,
`GateError`/`ApiResponse`/middleware, `TokenMetrics`/`SkippedItem`/`Observation`,
glosario logístico, y **todo el centro de comando del frontend** (hub, panel
universal, deep-linking, buscador, preguntas enfocadas, PDF, `<MermaidDiagram>`).

**Cero migraciones de base de datos.**

### Lo nuevo

| Pieza | Para qué |
|---|---|
| `ai/knowledge/db_conventions.yaml` + loader | naming, claves, auditoría, catálogos y el **mapa `logical_type` → tipo por motor** |
| `ai/agents/bd/naming.py` | identificadores reproducibles (plural/singular castellano, truncado por motor) |
| `ai/agents/bd/types.py` | `data_type` libre del EF → `LogicalType`, con certeza explícita |
| `ai/agents/bd/expressions.py` | portero de expresiones `CHECK` con sqlglot |
| `ai/agents/bd/ddl/` | render por dialecto + validación en capas + prueba de humo |
| `ai/agents/base/lineage.py` | recorrido transitivo de `input_job_id` (BD da 2 saltos; API dará 3) |
| `sqlglot==30.15.0` | parseo/transpilación SQL sin motor ni red |

### Permisos

`arquitecto` → **FULL** `bd` (diseña los datos, misma fase DISEÑAR).
`developer` → **READ** (sus módulos van *después* de `bd` y lo consumen).
`analista` **no entra**: sus módulos van *antes*, y leer hacia adelante rompería la
regla de forma de la matriz. Un caso puntual se cubre con **grant** (suma: un
developer con grant de `bd` obtiene FULL). Sin migración.

### Entrada triple transitiva (DB1)

```
bd_job.input_job_id = arquitectura_job_id
     → arquitectura_job.input_job_id = scrum_job_id
          → scrum_job.input_job_id = ef_job_id
```

El `source` guarda los tres ids + hashes. El **Scrum no alimenta el modelo**: solo
completa la trazabilidad, y si faltara no se bloquea el modelado. El **EF sí** es
materia prima: su ausencia es un error de dominio.

---

## 2. Pipeline (15 nodos, 6 con LLM)

```
LOAD_SOURCES → MODEL_MAP → TABLES → RELATIONS → CONSTRAINTS → INDEXES → CATALOGS
             → DDL_GEN → VALIDATE → DICTIONARY → ER_DIAGRAM
             → CRITIQUE → QUESTION_GEN → ASSEMBLE → PERSIST
```

| Nodo | Tipo | Qué hace |
|---|---|---|
| **LOAD_SOURCES** | det | Gate defensivo; contexto consolidado (EF: entidades, relaciones, campos, validaciones, reglas, CRUD, APIs; Arquitectura: stack, componentes, transversales); **resuelve el motor** y declara de dónde salió. |
| **MODEL_MAP** | det | **Cortafuegos anti-invención**: fija en Python qué tablas y columnas existen. 1:N → FK en el lado N; N:M → tabla puente; 1:1 → *no se decide aquí*; relación huérfana → se reporta. |
| **TABLES** | LLM *map* por tabla | Completa lo que exige juicio: longitud, precisión, descripción, ejemplo, PK. Reconciliación en Python: descarta columnas inventadas, conserva las omitidas y **hace ganar al EF** si contradice un tipo declarado. La ambigüedad se puede añadir, nunca borrar. |
| **RELATIONS** | híbrido | Det: FK de 1:N y de puentes. LLM: dueño de una 1:1 y acciones referenciales. **`cascade` sin regla citada → `restrict`** con observación. |
| **CONSTRAINTS** | LLM *map* por tabla | Reglas del EF → unique/check/not null + **clasificación** (`declarative`/`application`/`trigger`). Toda `BR-`/`VAL-` acaba en `rule_mappings`. |
| **INDEXES** | híbrido | Det: uno por FK. LLM: los justificados por patrón de acceso real. Tres filtros anti sobre-indexado, **todos con observación**. |
| **CATALOGS** | híbrido | Única ampliación de tablas permitida, con refs reales y **evidencia textual** para los valores. Sin valores citados → tabla vacía + pregunta. |
| **DDL_GEN** | **det** | Render por dialecto en orden topológico. FK en script aparte; rollback marcado destructivo. |
| **VALIDATE** | **det** | L1 estructural + L2 sqlglot (ver §5). |
| **DICTIONARY / ER_DIAGRAM** | **det** | Proyecciones del modelo; sin segunda pasada al LLM. |
| **CRITIQUE** | híbrido | Cobertura que **enumera lo que falta**, tablas aisladas, PII, y riesgos (LLM). |
| **QUESTION_GEN** | det | Preguntas al DBA **agrupadas por clase de vacío**. |
| **ASSEMBLE / PERSIST** | det | Igual patrón; descartes → `Observation`. |

---

## 3. Contrato `DatabaseArtifact v1.0.0`

Bloques: `source` · `target` (motor + convenciones efectivas) · `tables[]` ·
`ddl_scripts[]` · `seed_data[]` · `data_dictionary[]` · `er_diagram` ·
`design_decisions[]` · `rule_mappings[]` · `validation` · `analysis`
(risks/observations/coverage) · `questions_for_dba[]` · `metrics`.

Ver `backend/ai/agents/bd/schemas/artifact.py` (contrato) y `examples.py` (ejemplo
completo del dominio de siniestros).

**Tres decisiones del contrato que conviene tener presentes:**

1. **Doble nivel de tipo (DB2)** — cada columna lleva `logical_type` (enum cerrado,
   lo elige el LLM) y `type` (sintaxis del motor, la escribe DDL_GEN). Hace el DDL
   válido por construcción y **regenerarlo para otro motor cuesta cero llamadas**.
2. **`rule_mappings[]`** — toda regla del EF con su destino, aunque no quepa en el
   esquema. Sin este bloque, una regla no expresable desaparecería sin rastro.
3. **`validation.executed`** — distingue *parseado* de *ejecutado*: el artefacto no
   presenta como certificación lo que no lo es.

---

## 4. Prompts (`ai/prompts/bd/`)

`_base.md` (prohibido escribir SQL, prohibido inventar, ante la duda marcar
ambiguo) + `tables.md`, `relations.md`, `constraints.md`, `indexes.md`,
`catalogs.md`, `critique.md`. Inyecciones: glosario logístico +
`db_conventions_block(engine)`, que entrega los **tipos lógicos** y nunca sintaxis
SQL, para que el modelo no pueda copiarla.

---

## 5. Validación del DDL, en capas

| Capa | Qué comprueba | Dónde corre |
|---|---|---|
| **L0** Generado, no escrito | elimina el error de redacción de raíz | DDL_GEN |
| **L1** Estructural (Python) | FK que resuelven y con tipos compatibles, PK obligatoria, duplicados, límite de identificador, semilla coherente | pipeline |
| **L2** sqlglot en el dialecto | sintaxis real del motor, sin BD ni red; caza bugs **del renderizador** | pipeline |
| **L3a** Ejecución en SQLite | que el esquema **se crea** y la semilla entra | tests |
| **L3b** Motor real (PostgreSQL 16) | certificación | opt-in, fuera de la suite |

L3a no es decorativa: **encontró un bug que L1 no veía** — el catálogo listaba todas
sus columnas en el `INSERT`, así que `activo` (NOT NULL DEFAULT true) recibía NULL
explícito, y un NULL explícito no activa el DEFAULT. Se corrigió el generador y se
afinó L1 para distinguir *omitir* una columna con default de *pasarle NULL*.

Limitaciones declaradas de L3a (identidad, esquemas y `NULLS LAST` no sobreviven a
la transpilación): por eso es prueba de humo y el artefacto dice `executed=false`.

---

## 6. Gate, semáforo y persistencia

**Gate de entrada.** `POST /api/v1/bd/models {architecture_job_id, engine_override?}`
→ `GateError` **409** si la arquitectura no está lista, con mensaje accionable.
Re-verificado en `LOAD_SOURCES`.

**Motor no decidido**: no es gate. Se usa `engine_override` → default validado de la
casa, con `engine_decided=false` y **pregunta bloqueante**. El job corre y produce
valor; el semáforo se queda en rojo.

**Semáforo de salida (DB3)** — habilita al **Agente API**:
sin bloqueantes pendientes **y** ≥1 tabla **y** todas con PK **y** cobertura de
entidades ≥ umbral **y** `validation` sin errores. Cobertura de campos, validaciones
y reglas **no** entra al gate: genera preguntas.

**API `/api/v1/bd/*`**: `POST /models` · `GET /available-architecture-jobs` ·
`GET /jobs[/{id}][/artifact]` · **`GET /jobs/{id}/ddl?engine=&formato=`** ·
`PATCH|GET /jobs/{id}/validations` · `POST /jobs/{id}/refine`.

El **refine conserva el motor** del job original: afinar el modelo no cambia la
plataforma sobre la que se construye.

---

## 7. Decisiones (DB1–DB14)

| # | Decisión | Acordado |
|---|---|---|
| DB1 | Entrada triple | **Transitiva** (2 saltos) + `lineage.py`. Sin migración. |
| DB2 | Tipos | **Doble nivel**: `logical_type` (enum cerrado) + `type` (render por motor). |
| DB3 | Semáforo | Compuesto, incluyendo **DDL válido**. |
| DB4 | Motor | **PostgreSQL 16**, capa `database_relational` **validada** por el equipo. El resto de `tech_stack.yaml` sigue en borrador. |
| DB5 | Anti-invención | `MODEL_MAP` fija las tablas en Python; el LLM solo tipa y describe. |
| DB6 | Reglas no declarativas | Clasificación obligatoria; nunca descarte silencioso. |
| DB7 | Auditoría / soft delete | Solo si la arquitectura declaró el transversal `audit`. Soft delete: no por defecto. |
| DB8 | Índices | Sin patrón de acceso citado no hay índice; tope por tabla **reportado**. Particionado fuera de v1. |
| DB9 | PII | Se **señala** (heurística conservadora) + pregunta no bloqueante. No se cifra nada. |
| DB10 | Alcance | DDL de creación + rollback. **Brownfield (diff contra un esquema existente) fuera de v1.** |
| DB11 | Multi-schema | No en v1: un solo esquema. |
| DB12 | `sqlglot` | Aceptada y pinneada. |
| DB13 | Permisos | `arquitecto` FULL, `developer` READ; el resto por grant. |
| DB14 | Preguntas | **Agrupadas por clase de vacío**, con el recorte declarado. |

---

## 8. Bloques implementados

| Bloque | Contenido | Commit |
|---|---|---|
| **BD0** | `db_conventions.yaml` + loader, `sqlglot`, `lineage.py`, permisos | `81707e9` |
| **BD1** | Contrato `DatabaseArtifact v1.0.0` | `8c73839` |
| **BD2** | Grafo + `LOAD_SOURCES` + `MODEL_MAP` + naming/tipos | `2fed63d` |
| **BD3** | `TABLES` + `RELATIONS` (+ cortafuegos de presupuesto en tests) | `60fe906` |
| **BD4** | `CONSTRAINTS` + `INDEXES` + `CATALOGS` | `2f5a10a` |
| **BD5** | `DDL_GEN` + `VALIDATE` + `DICTIONARY` + `ER_DIAGRAM` (+ PostgreSQL 16) | `40925f2` |
| **BD6** | `CRITIQUE` + `QUESTION_GEN` | `4d8c112` |
| **BD7** | Servicio + API `/bd/*` + refine + export DDL | `695489c` |
| **BD8** | Frontend: nav DISEÑAR, `DatabaseResultView`, ER, DDL descargable | `cee36e2` |

---

## 9. Pendientes conocidos

- **Validar el resto de `tech_stack.yaml`** (lenguaje, framework, nube, CI/CD…).
  Hoy solo `database_relational` está confirmada.
- **Validar `db_conventions.yaml`**: nace `pendiente_de_validacion`. Naming, PK,
  columnas de catálogo y defaults de longitud/precisión los puso el asistente.
- **L3b**: automatizar la certificación contra el contenedor PostgreSQL 16 del
  `docker-compose.yml` como test opt-in.
- **Brownfield**: diff contra un esquema existente (requiere introspección).
- **Sin runs reales**: todo el agente se construyó y probó con mocks.
