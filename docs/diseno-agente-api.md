# Diseño — Agente API (quinto agente del ISDF)

> Documento de arquitectura **aprobado**. Fuente de verdad del Agente API, **en
> construcción** (ver §9 para el estado por bloques). Leer junto a `CLAUDE.md`,
> `docs/diseno-agente-arquitectura.md` y `docs/diseno-agente-bd.md`, cuyo patrón se
> reutiliza casi por completo.

---

## 0. Principio rector

Quinta instancia del mismo patrón. Comparte con el Agente BD la propiedad que lo
distingue de EF/Scrum/Arquitectura: **su salida es ejecutable**. Un ADR mal
redactado se discute; un OpenAPI mal generado rompe el generador de código del
Agente Backend, el cliente del Agente Frontend y los tests del Agente QA a la vez.
De ahí la regla que gobierna todo el agente, calcada de la del BD:

> **El LLM no escribe OpenAPI nunca.** Decide semántica (qué recurso, qué
> operaciones, qué campos se exponen, quién puede llamar). **Python renderiza** el
> documento YAML de forma determinista y lo **valida sin LLM**.

Y una segunda regla, propia de este agente, que conviene enunciar antes que
cualquier otra cosa:

> **El peor error posible de este agente no es un endpoint de más: es una regla de
> autorización más ancha que la realidad.** Un endpoint sobrante se borra en
> revisión. Una autorización permisiva por silencio se despliega, y expone datos de
> personas a quien no debía verlos. Por eso la matriz de autorización es
> **fail-closed**: lo que nadie autorizó explícitamente queda **denegado**, y la
> ambigüedad no se resuelve por defecto sino con una **pregunta bloqueante**.

Consume el `DatabaseArtifact` (gate: `ready_for_next_stage=true`) y,
transitivamente, `ArchitectureArtifact`, `ScrumArtifact` y `EFArtifact`. Produce el
`ApiArtifact v1.0.0`, que habilita a los Agentes **Backend** y **Frontend**.

---

## 1. Reutilización

A estas alturas la reutilización es prácticamente total. Lo listo aquí para dejar
constancia de que **no hay infraestructura nueva**, y luego lo verdaderamente nuevo.

### Tal cual (cero cambios)

Tablas `agent_*` + `AgentJobRepository` (**`AgentType.API` ya existe**,
`app/models/agent.py:47`), grafo lineal + checkpointer Redis (`thread_id=job_id`),
`run_agent_pipeline` (métricas reales, FAILED, BackgroundTasks), `run_map`
(concurrencia + repair loop + cuarentena → `metrics.skipped`), `create_refine` +
contexto autoritativo, `GateError`/`ApiResponse`/middleware de errores,
`TokenMetrics`/`SkippedItem`/`Observation`, glosario logístico, `resolve_lineage`
—que **ya anticipa este agente**: *"El Agente Arquitectura daba un salto […]. El
Agente BD da dos y el Agente API dará tres"* (`ai/agents/base/lineage.py:12`)— y
**todo el centro de comando del frontend** (hub, panel universal, deep-linking,
buscador local, preguntas enfocadas, export PDF, `RefChip`/`artifact-refs`).

**Cero migraciones de base de datos. Cero cambios en la matriz de permisos.**

### Lo nuevo (cuatro piezas)

| Pieza | Para qué |
|---|---|
| `ai/knowledge/api_conventions.yaml` + loader (`api_conventions_block()`) | rutas, plurales, caso de las propiedades, envelope, catálogo de errores, paginación, filtrado y orden. Mismo rol que `db_conventions.yaml`: el LLM decide **dentro** de estas reglas, no improvisa. |
| `ai/agents/api/openapi/` | `render.py` (documento 3.1 determinista), `validate.py` (L1 estructural + L2 spec), `smoke.py` (L3a runtime, tests) |
| `openapi-spec-validator==0.8.5` | valida el documento contra el JSON Schema de OpenAPI 3.1 en Python puro, **sin red ni tooling externo**. Es el `sqlglot` de este agente. (0.8.5 y no 0.9.0: ver §5.) |
| Frontend: `<AuthorizationMatrix>` + visor/descarga del YAML | la matriz es la visual insignia de este artefacto, como el diagrama ER lo fue del BD |

`openapi-core` se añade **solo como dependencia de test** para la capa L3a (§5).
No entra en `requirements.txt` de runtime.

### Entrada cuádruple transitiva (API1)

```
api_job.input_job_id = bd_job_id
   → bd_job.input_job_id = arquitectura_job_id
        → arquitectura_job.input_job_id = scrum_job_id
             → scrum_job.input_job_id = ef_job_id
```

Tres saltos, resueltos por `resolve_lineage` sin columna nueva. El `source` guarda
los cuatro ids + hashes. Reparto de responsabilidades entre las fuentes:

| Fuente | Aporta | Si falta |
|---|---|---|
| **BD** | tablas, columnas (`logical_type`, nullable, default, length, enum de los CHECK, `example`, `pii`), PK/FK/unique, **índices** (→ qué es filtrable/ordenable), semillas de catálogo (→ ejemplos), `rule_mappings` (→ qué reglas quedaron para la aplicación) | error de dominio: no hay API sin modelo |
| **EF** | `apis[]` (método/ruta/propósito preliminares), **`crud[]`** (base determinista de la autorización), `actors[]`, `business_rules[]`/`validations[]`, `processes[]` (evidencia para endpoints de acción) | error de dominio |
| **Arquitectura** | `components[]` (→ `tags` de OpenAPI y agrupación por módulo), `stack[].auth` y `api_style` (→ esquema de seguridad), `cross_cutting[]` (auth/auditoría), `integrations[]` (lo que **no** es nuestra API) | degradado: se usan defaults + preguntas |
| **Scrum** | solo trazabilidad de la cadena | no bloquea |

### Permisos (sin cambios, y una consecuencia de nombre)

`developer` ya tiene **FULL** en `api`; `arquitecto` **no lo alcanza** por la regla
de forma de la matriz (`api` va *después* de sus módulos). Se respeta: un caso
puntual se cubre con **grant**, como en BD.

Consecuencia honesta: el bloque de preguntas se llama **`questions_for_tech_lead`**,
no "para el Arquitecto". Quien puede responderlas en la plataforma es quien tiene
`api` FULL — el developer / líder técnico. Nombrar el bloque por su audiencia real
evita el absurdo de dirigir preguntas a un rol que no puede abrir el panel.

---

## 2. Pipeline (14 nodos, 6 tocan el LLM)

```
LOAD_SOURCES → RESOURCE_MAP → RESOURCES → ENDPOINTS → SCHEMAS
             → AUTHORIZATION → RULE_MAPPING → ERRORS
             → OPENAPI_GEN → VALIDATE → CRITIQUE → QUESTION_GEN
             → ASSEMBLE → PERSIST
```

Respecto al pipeline propuesto, **dos inserciones deliberadas**:

- **`RESOURCE_MAP`** (antes de `RESOURCES`) — el cortafuegos anti-invención, el
  equivalente exacto de `MODEL_MAP`. Sin él, `RESOURCES` sería un nodo LLM con
  licencia para inventar recursos.
- **`ERRORS`** (después de `AUTHORIZATION`, antes de `OPENAPI_GEN`) — los códigos de
  estado no se inventan por endpoint: se derivan del catálogo y de las constraints
  del BD. Va después de la autorización, pero **no** por el `403` (con seguridad
  global, todo endpoint autenticado puede devolverlo): por el **`404`**. Cuando un
  actor tiene alcance por filas, un registro fuera de su alcance debe responder
  `404` y no `403` — decir "existe pero no puedes verlo" revela justo lo que el
  alcance pretendía ocultar. Saber si un endpoint está en ese caso exige mirar la
  matriz, y por eso se mira aquí.

| Nodo | Tipo | Qué hace |
|---|---|---|
| **LOAD_SOURCES** | det | Gate defensivo (BD listo). Consolida las cuatro fuentes. Resuelve **estilo de API** (`api_style` del stack), **esquema de seguridad** (capa `auth` del stack → `bearer_jwt`/`oauth2_oidc`) y **convenciones efectivas**, declarando de dónde salió cada uno. Reinyecta respuestas si es refine. |
| **RESOURCE_MAP** | **det** | **Cortafuegos**. Fija en Python qué recursos existen y qué operaciones son candidatas: una por tabla `kind=entity` (CRUD según la matriz del EF), catálogos → solo lectura, tablas puente → **anidadas** bajo su padre (no recurso propio), tablas de auditoría → **sin exposición**. Toda exclusión queda escrita con su motivo. También fija rutas, nombres y qué columnas son filtrables/ordenables (solo PK/FK/indexadas/enum). |
| **RESOURCES** | LLM *map* | Solo describe y clasifica lo que ya existe: nombre para humanos, descripción, agrupación por componente de Arquitectura. **No puede añadir un recurso.** |
| **ENDPOINTS** | híbrido | **Det:** los endpoints CRUD del mapa, con `operation_id`, parámetros de ruta y de paginación. **LLM:** la **única ampliación permitida** — *endpoints de acción* (`POST /siniestros/{id}/cerrar`) derivados de `processes[]`/`business_rules[]`, y **exigen evidencia textual citada**, igual que los valores de catálogo en el BD. Un endpoint del EF (`API-…`) que coincide se marca `origin: "stated"`; el resto, `derived`. |
| **SCHEMAS** | híbrido *map* por recurso | **Det:** esqueleto por operación (`Create`/`Update`/`Read`/`ListItem`) desde las columnas: `required` = NOT NULL sin default, `read_only` = PK/generada/auditoría, `enum` desde el CHECK, `max_length`/`format` desde el tipo lógico, `example` desde `column.example` o la semilla. **LLM:** exposición (qué columna interna **no** sale), campos embebidos (¿el detalle incluye el cliente anidado?) y descripciones. **Ningún campo sin `column_ref`**, salvo `computed=true`, que exige `source_refs` a una `BR-`. |
| **AUTHORIZATION** | híbrido | **Det:** base desde `crud[]` del EF — `create`→POST, `read`→GET lista+detalle, `update`→PATCH, `delete`→DELETE. **LLM:** las **condiciones de alcance** ("los jefes solo ven las solicitudes de su equipo"), que solo pueden nacer de una `BR-`/`ACT-` citada, y deben aterrizar en una **columna real** (`scope_column_refs`). Sin columna que materialice el filtro → `ambiguous=true` → **pregunta bloqueante**. Endpoint sin ninguna regla → **`deny` por defecto** + pregunta. |
| **RULE_MAPPING** | híbrido | Toda `BR-`/`VAL-` del EF con su destino: `endpoint` \| `schema` \| `authorization` \| `database` \| `not_applicable` (con motivo). **Cierra el círculo que abrió el BD:** una regla que el BD clasificó `application` y que aquí no encuentra endpoint que la haga cumplir es una regla que desaparecería del sistema → **pregunta bloqueante**. |
| **ERRORS** | **det** | Catálogo estándar desde `api_conventions.yaml` + estampado por endpoint: `409` donde hay unique constraint, `422` donde hay CHECK o validación de esquema, `404` en detalle/anidados, `401`/`403` donde hay autenticación/alcance, `201`+`Location` en creación, `204` en borrado. Nada de esto lo decide el modelo. |
| **OPENAPI_GEN** | **det** | Renderiza el documento **3.1.0** completo: `info`, `servers`, `tags` (por componente), `paths`, `components.schemas` (incluido el **envelope** de la casa), `components.parameters` (paginación/orden), `components.responses` (catálogo de errores), `securitySchemes` + `security` global. Ordenación estable (rutas y claves ordenadas) para que **dos corridas del mismo modelo produzcan el mismo YAML byte a byte**. |
| **VALIDATE** | **det** | L1 estructural + L2 spec (§5). Un error **no tumba el pipeline**: entra en `validation.errors`, el job cierra `COMPLETED_WITH_WARNINGS` y el semáforo se queda en rojo. |
| **CRITIQUE** | híbrido | **Det:** cobertura que **enumera lo que falta** (tablas sin exponer, `API-` del EF sin endpoint, celdas CRUD sin ruta, actores sin ningún acceso), endpoints que exponen columnas `pii` con alcance ambiguo, explosión de superficie. **LLM:** riesgos de diseño de API. |
| **QUESTION_GEN** | det | Preguntas al líder técnico **agrupadas por clase de vacío** (patrón DB14). |
| **ASSEMBLE / PERSIST** | det | Igual patrón; descartes → `Observation`, nunca silenciosos. |

### Qué bloquea y qué no

**Bloquea** (haría inservible o **peligrosa** la API): endpoint sin autorización
resuelta; alcance ambiguo en un endpoint que expone columnas `pii`; regla
`application` del BD sin endpoint que la aplique; tabla de entidad sin exposición ni
motivo; `API-` del EF declarado y no cubierto; OpenAPI inválido; esquema de
seguridad no decidido.

**No bloquea** (solo lo hace mejorable): campo sin descripción, ejemplo ausente,
filtro sobre columna no indexada, paginación por cursor no disponible, endpoint de
acción de baja confianza.

---

## 3. Contrato `ApiArtifact v1.0.0`

Claves en inglés, valores en español. Todo ítem con `id`/`source_refs`/
`confidence`/`origin`. Reutiliza `TokenMetrics`/`SkippedItem`/`Observation` del EF,
`RiskSeverity` de Arquitectura y `LogicalType` del BD (**no se redefine el sistema
de tipos**: el del modelo de datos es el mismo que viaja por la API).

```jsonc
{
  "schema_version": "1.0.0",

  "source": {
    "bd_job_id": "…", "bd_artifact_hash": "…", "bd_schema_version": "1.0.0",
    "architecture_job_id": "…", "architecture_artifact_hash": "…",
    "scrum_job_id": "…", "scrum_artifact_hash": "…",
    "ef_job_id": "…", "ef_artifact_hash": "…", "ef_schema_version": "1.2.0",
    "ready_snapshot": true
  },

  "target": {
    "api_style": "rest",                 // v1: solo REST; otro → pregunta bloqueante
    "spec_version": "3.1.0",
    "base_path": "/api/v1", "api_version": "v1", "versioning": "path",
    "auth": { "scheme": "bearer_jwt", "provider": "Keycloak",
              "source_ref": "STK-007", "decided": true },
    "conventions": {                     // efectivas, persistidas para auditar
      "path_case": "kebab-case", "path_language": "es", "resource_number": "plural",
      "property_case": "snake_case", "envelope": "api_response",
      "update_verb": "PATCH",
      "pagination": { "style": "offset", "limit_param": "limit",
                      "offset_param": "offset", "default_limit": 20, "max_limit": 100 },
      "sort_param": "sort", "date_format": "rfc3339", "decimal_as_string": true
    },
    "conventions_source": "api_conventions.yaml@v0"
  },

  "resources": [{
    "id": "RES-001", "name": "siniestros", "singular": "siniestro",
    "display_name": "Siniestros", "description": "…",
    "table_ref": "TBL-003", "entity_ref": "ENT-003", "component_ref": "CMP-001",
    "base_path": "/siniestros",
    "exposure": "crud",                  // crud | read_only | nested_only | none
    "exposure_reason": null,             // OBLIGATORIO si exposure != crud
    "parent_resource_ref": null,         // recursos anidados (profundidad máx. 1)
    "source_refs": ["ENT-003", "TBL-003", "CRUD-002"],
    "confidence": 0.9, "origin": "derived"
  }],

  "schemas": [{
    "id": "SCH-004", "name": "SiniestroCreate", "resource_ref": "RES-001",
    "kind": "create",                    // create|update|read|list_item|action_input|error|envelope
    "description": "…",
    "fields": [{
      "id": "SF-021", "name": "numero_guia",
      "logical_type": "string", "format": null,
      "required": true, "nullable": false, "read_only": false, "write_only": false,
      "max_length": 20, "enum": null, "example": "G-0001234",
      "column_ref": "COL-014",           // ← firma anti-invención
      "table_ref": "TBL-003",
      "computed": false,                 // true exige source_refs a una BR-
      "pii": false,                      // heredado del BD; gobierna la exigencia de alcance
      "source_refs": ["FLD-012"], "confidence": 0.9, "origin": "derived"
    }],
    "source_refs": ["TBL-003"]
  }],

  "endpoints": [{
    "id": "EP-007", "resource_ref": "RES-001",
    "method": "GET", "path": "/api/v1/siniestros/{siniestro_id}",
    "operation_id": "obtenerSiniestro", "kind": "read_item",
    "purpose": "Obtiene el detalle de un siniestro.",
    "parameters": [{ "id": "PRM-003", "name": "siniestro_id", "location": "path",
                     "logical_type": "bigint", "required": true,
                     "description": "…", "column_ref": "COL-013" }],
    "request_schema_ref": null, "response_schema_ref": "SCH-006",
    "response_kind": "item",             // item | page | none
    "status_codes": [{ "code": 200, "description": "…", "schema_ref": "SCH-006" },
                     { "code": 401, "error_ref": "ERR-401" },
                     { "code": 403, "error_ref": "ERR-403" },
                     { "code": 404, "error_ref": "ERR-404" }],
    "pagination": null,                  // objeto solo si kind == "list"
    "filters": [], "sortable": [],       // solo columnas indexadas (regla dura)
    "idempotent": true, "deprecated": false,
    "auth_rule_refs": ["AUTH-011"],      // ≥1 SIEMPRE (fail-closed)
    "rule_refs": ["BR-004"],
    "ef_api_ref": "API-002",
    "source_refs": ["API-002", "CRUD-002", "TBL-003"],
    "confidence": 0.85, "origin": "stated"
  }],

  "authorization_matrix": [{
    "id": "AUTH-011", "endpoint_ref": "EP-007",
    "actor_ref": "ACT-002", "actor_name": "Jefe de Operaciones",
    "effect": "allow",                   // allow | deny (default global: deny)
    "scope": "own_team",                 // all | own | own_team | own_branch | custom | none
    "scope_expression": "siniestro.equipo_id = usuario.equipo_id",
    "scope_column_refs": ["COL-019"],    // vacío con scope != all → ambiguous
    "basis": "business_rule",            // crud_matrix | business_rule | inferred | default_deny
    "ambiguous": false,                  // true → pregunta BLOQUEANTE
    "source_refs": ["CRUD-004", "BR-007"], "confidence": 0.7, "origin": "derived"
  }],

  "error_catalog": [{
    "id": "ERR-409", "status": 409, "code": "recurso_duplicado",
    "message": "Ya existe un registro con esos datos.",
    "when": "Violación de una restricción de unicidad del modelo.",
    "source_refs": ["UQ-003"]
  }],

  "rule_mappings": [{
    "id": "ARM-005", "rule_ref": "BR-007",
    "enforcement": "authorization",      // endpoint|schema|authorization|database|not_applicable
    "endpoint_refs": ["EP-007"], "schema_field_refs": [], "auth_rule_refs": ["AUTH-011"],
    "bd_enforcement": "application",     // lo que dijo el Agente BD → cierre del círculo
    "note": "…", "confidence": 0.8, "origin": "derived"
  }],

  "openapi": {
    "format": "yaml", "spec_version": "3.1.0",
    "content": "openapi: 3.1.0\n…",      // documento completo, descargable
    "operations_total": 37, "byte_size": 48213, "checksum": "sha256:…"
  },

  "validation": {
    "spec_valid": true,
    "validator": "estructural+openapi-spec-validator",
    "validator_version": "0.9.0",
    "runtime_checked": false,            // análogo de validation.executed del BD
    "checks": { "refs_resolve": true, "no_path_collisions": true,
                "all_endpoints_authorized": true, "http_semantics": true,
                "spec_schema": true, "round_trip": true },
    "errors": [], "warnings": []
  },

  "analysis": {
    "risks": [{ "id": "RISK-001", "description": "…", "severity": "alta",
                "mitigation": "…", "source_ref": "AUTH-014" }],
    "observations": [{ "id": "OBS-001", "description": "…", "reason": "…" }],
    "coverage": {
      "tables_total": 12, "tables_exposed": 10, "unexposed_table_refs": ["TBL-011"],
      "ef_apis_total": 6, "ef_apis_covered": 6, "uncovered_api_refs": [],
      "crud_cells_total": 34, "crud_cells_covered": 31, "uncovered_crud_refs": ["CRUD-009"],
      "rules_total": 18, "rules_enforced": 15, "unenforced_rule_refs": ["BR-012"],
      "actors_total": 4, "actors_with_access": 4, "actors_without_access": []
    }
  },

  "questions_for_tech_lead": [{
    "id": "Q-001",
    "question": "¿Un Jefe de Operaciones ve todos los siniestros o solo los de su equipo?",
    "reason": "BR-007 limita la visibilidad por equipo pero ninguna columna de siniestros identifica al equipo responsable. Afecta a EP-006 y EP-007, que exponen datos personales del conductor.",
    "audience": "tecnico", "blocking": true, "linked_to_ref": "AUTH-011",
    "status": "pendiente", "confidence": 0.6, "origin": "derived"
  }],

  "metrics": {
    "tokens": { "input": 0, "output": 0, "total": 0 }, "cost": 0.0, "duration": 0.0,
    "resources_total": 10, "endpoints_total": 37, "schemas_total": 28,
    "auth_rules_total": 62, "coverage": 0.92, "spec_valid": true, "skipped": []
  }
}
```

**Tres decisiones del contrato que conviene tener presentes:**

1. **`column_ref` obligatorio en cada campo de esquema.** Es al Agente API lo que
   `logical_type` es al BD: la propiedad estructural que hace imposible la
   invención. Un campo sin columna detrás solo existe si es `computed=true` y cita
   la regla que lo calcula.
2. **`authorization_matrix` es una lista, no un mapa.** Cada fila es
   `(endpoint × actor)` con su `basis` y sus `source_refs`, así que se puede
   auditar de dónde salió cada permiso. Un mapa denso sería más compacto y menos
   trazable — y en autorización, la trazabilidad es el producto.
3. **`bd_enforcement` dentro de `rule_mappings`.** Copia el veredicto del Agente BD
   junto al propio. Es lo que permite detectar, sin LLM, la regla que ambos dieron
   por hecho que aplicaba el otro.

---

## 4. Prompts (`ai/prompts/api/`)

`_base.md` + un rol estrecho por dimensión. Reglas heredadas: derivar **solo** de
BD/EF/Arquitectura, structured output (nunca JSON libre), `source_refs`
obligatorios, razonar en español / claves en inglés, y **si falta base → pregunta**.

Reglas propias del `_base.md`:

- **Prohibido escribir YAML, JSON Schema u OpenAPI.** Igual que en BD se prohíbe el
  SQL. El bloque de convenciones inyectado entrega vocabulario (tipos lógicos,
  formatos, nombres de operación) y **nunca sintaxis del documento**, para que el
  modelo no pueda copiarla.
- **Prohibido inventar endpoints, recursos y campos.** El conjunto llega cerrado.
- **Prohibido ampliar una autorización sin regla citada.** Ante la duda: `deny` y
  pregunta. Esta frase va en negrita en el prompt: es la que evita el peor error.

| Prompt | Rol | Entrada → Salida | Anti-alucinación |
|---|---|---|---|
| `resources.md` | Diseñador de recursos | mapa cerrado → nombres/descripciones/agrupación | no puede añadir ni quitar recursos; solo describir |
| `endpoints.md` | Diseñador REST | procesos + reglas → endpoints de **acción** | exige **cita verbatim** del proceso/regla que justifica la acción; sin cita, no se crea |
| `schemas.md` | Diseñador de contratos | columnas del recurso → exposición/embebidos/descripciones | el conjunto de campos es cerrado; ocultar sí, añadir no; `computed` exige `BR-` |
| `authorization.md` | Analista de control de acceso | actores + CRUD + reglas → condiciones de alcance | alcance solo con `BR-`/`ACT-` citada **y** columna real; si no, `ambiguous=true` |
| `rule_mapping.md` | Auditor de reglas | `BR-`/`VAL-` + endpoints → destino | ninguna regla sin destino; `not_applicable` exige motivo |
| `critique.md` | Crítico de API | especificación consolidada → riesgos/vacíos | señala; no propone implementación |

Inyecciones: **glosario logístico** (recursos y rutas en el vocabulario de la casa:
*guía*, *siniestro*, *ubigeo*…), **`api_conventions_block()`** y, en `SCHEMAS`, el
**extracto del diccionario de datos del recurso** (solo sus columnas: acota tokens
y hace estructuralmente imposible citar una columna de otra tabla).

### `ai/knowledge/api_conventions.yaml` (propuesto)

Nace `status: pendiente_de_validacion`, `version: 0`, con `# REVISAR:` por bloque —
mismo patrón que `db_conventions.yaml`. Bloques: `paths` (caso, idioma, número,
profundidad máx. de anidamiento, verbo de actualización), `properties` (caso,
formatos de fecha/decimal), `envelope`, `errors` (catálogo + mapa constraint →
código), `pagination`, `filtering` (regla: solo columnas indexadas), `sorting`,
`security`, `operation_id` (patrón de nombre). Los valores concretos que propongo
están en §8 como decisiones abiertas.

---

## 5. Validación determinista (sin LLM)

| Capa | Qué comprueba | Dónde corre |
|---|---|---|
| **L0** Generado, no escrito | elimina de raíz el error de redacción del documento | OPENAPI_GEN |
| **L1** Estructural (Python) | sobre el artefacto, antes de renderizar (lista abajo) | pipeline |
| **L2** Spec (`openapi-spec-validator`) | el YAML contra el JSON Schema de **OpenAPI 3.1** + chequeos semánticos, sin red | pipeline |
| **L2b** Round-trip | re-parsea el YAML renderizado y compara el conjunto `(método, ruta, operationId)` con `endpoints[]` | pipeline |
| **L3a** Runtime (`openapi-core`) | construye el objeto `Spec` y valida **peticiones/respuestas sintéticas** hechas con los `example` de cada campo: prueba que un runtime real puede usar el documento | tests |
| **L3b** Herramienta externa (Swagger UI / mock server) | certificación | manual, opt-in |

**L1 — comprobaciones estructurales** (todas con código estable y accionable, como
`fk_target_missing` en BD):

1. `request_schema_ref`/`response_schema_ref`/`error_ref` resuelven a un ítem existente.
2. Todo campo de esquema tiene `column_ref` que resuelve a una columna del BD, **o**
   `computed=true` con ≥1 `source_refs`.
3. **Sin colisiones de ruta**: normalizando `{param}`→`{}`, la pareja
   `(método, ruta)` es única. Además, ruta estática que colisiona con una
   paramétrica hermana (`/siniestros/activos` vs `/siniestros/{id}`) → *warning* con
   la regla de precedencia declarada.
4. Parámetros de ruta declarados == parámetros que aparecen en el `path`.
5. `operation_id` único y conforme al patrón.
6. Nomenclatura conforme a `api_conventions.yaml` (caso, número, prefijo `/api/v1`).
7. **Todo endpoint tiene ≥1 regla de autorización** (fail-closed).
8. Semántica HTTP: GET/DELETE sin cuerpo; POST de colección → `201` + `Location`;
   DELETE → `204`; PATCH → `200`; toda colección → parámetros de paginación.
9. Códigos de estado obligatorios presentes según método y autorización.
   **Esta comprobación no se puede delegar en L2:** OpenAPI 3.0 exigía `responses`
   en toda operación, pero **3.1 lo hizo opcional**, así que un endpoint que no
   declara qué devuelve —inservible para Backend y Frontend— pasa la validación de
   la librería sin una queja. Verificado en `tests/agents/api/test_openapi_dependency.py`.
10. `filters`/`sortable` ⊆ columnas indexadas del BD (fuera → *warning* con el
    coste declarado: un filtro sin índice es un table-scan en producción).
11. **Toda tabla del BD** tiene endpoints **o** `exposure != "crud"` con motivo.
12. **Toda regla `application` del BD** aparece en `rule_mappings` con al menos un
    `endpoint_refs`/`auth_rule_refs`.
13. Ninguna columna `pii` viaja en un endpoint cuya regla de alcance sea `ambiguous`.

Como en BD, **un fallo no cae el pipeline**: se reporta, el job termina
`COMPLETED_WITH_WARNINGS` y el semáforo queda en rojo. Entregar una especificación
con un defecto señalado es útil; caerse, no.

**Notas sobre `openapi-spec-validator`** (todas verificadas en API0,
`tests/agents/api/test_openapi_dependency.py`):

- El documento generado es **autocontenido** (`$ref` solo a `#/components/…`), así
  que la validación no resuelve referencias remotas y **no hay salida a red**.
- **Versión pinneada `0.8.5`, no `0.9.0`**: `openapi-core` (capa L3a) exige
  `<0.9.0`, y dejar runtime y validación en ramas incompatibles no compensa. Se
  pinnea por la misma razón que `sqlglot`: un cambio de versión puede alterar la
  validación en silencio.
- **Un `$ref` colgante lanza excepción en vez de reportarse** por `iter_errors()`.
  L2 debe envolver la llamada y convertirla en un `validation.errors`, o una
  referencia rota tumbaría el pipeline en lugar de reportarse — justo lo contrario
  de lo que exige este diseño. La comprobación L1 nº 1 existe para que ese caso no
  llegue nunca a L2, pero un bug del renderizador podría colarlo.

---

## 6. Gate, semáforo, persistencia y API

**Gate de entrada.** `POST /api/v1/apis/specs {bd_job_id, style_override?}` →
`GateError` **409** si el modelo de datos no está listo, con mensaje accionable
(responder las preguntas al DBA o generar un modelo afinado). Re-verificado en
`LOAD_SOURCES`.

**Esquema de seguridad no decidido** — no es gate. Se usa el default de la casa
(capa `auth` de `tech_stack.yaml`) con `auth.decided=false` + **pregunta
bloqueante**: el job corre y produce valor, el semáforo se queda en rojo.

**Semáforo de salida (habilita a Backend y Frontend):**

1. Sin preguntas bloqueantes pendientes, **y**
2. ≥1 endpoint, **y**
3. **todos los endpoints con autorización resuelta** (ninguno en `default_deny` sin
   pregunta respondida), **y**
4. cobertura de tablas expuestas y de `API-` del EF ≥ umbral configurable
   (`API_COVERAGE_THRESHOLD`, default 1.0), **y**
5. `validation.spec_valid` sin errores.

La cobertura de celdas CRUD y de reglas **no** entra al gate: genera preguntas
(mismo criterio que los campos/validaciones en BD y los RNF en Arquitectura).

**Endpoints `/api/v1/apis/*`** (`READ` a nivel de router, `FULL` en escritura):

- `POST /apis/specs` — crear (gate 409)
- `GET /apis/available-bd-jobs` — modelos de datos y si están listos
- `GET /apis/jobs[/{id}][/artifact]`
- **`GET /apis/jobs/{id}/openapi?format=yaml|json&spec_version=3.1|3.0`** — descarga.
  **Dividendo DB2 aplicado a las APIs:** el documento se **re-renderiza** desde el
  artefacto estructurado, así que servirlo en JSON, o degradarlo a 3.0.3 para
  tooling que aún no soporta 3.1, **cuesta cero llamadas al modelo**.
- `PATCH|GET /apis/jobs/{id}/validations` · `POST /apis/jobs/{id}/refine`

El **refine conserva las convenciones y el esquema de seguridad** del job original,
por la misma razón que el refine de BD conserva el motor: afinar el contrato no
cambia la plataforma sobre la que se construye.

*(Colección Postman/Insomnia y cliente TypeScript generado: fuera de v1, mismo
tratamiento que la fase (b) de ClickUp — se anota, no se implementa.)*

---

## 7. Frontend (centro de comando, §5.1 de `CLAUDE.md`)

Nav: activar **API** en el grupo **CONSTRUIR** (`ISDF_NAV`, hoy `enabled:false`,
`frontend/src/lib/isdf.ts:95`). Flujo idéntico: `/agents/api` → `/new` (elegir un
job de BD listo) → `/jobs/[jobId]` (Progreso ↔ Resultado).

`ApiResultView` define sus `HubSection[]`; el hub, el panel, el buscador, el
deep-linking y el PDF salen gratis.

| Sección | Contenido | Insight de la tarjeta | Urgencia (borde rojo) |
|---|---|---|---|
| **Contrato** | estilo, `base_path`, versionado, seguridad, convenciones efectivas | "REST · 37 operaciones · Bearer JWT" | seguridad no decidida |
| **Recursos** | tarjetas por recurso: tabla origen, componente, nº de endpoints, exposición | "10 recursos · 2 sin exponer" | tabla de entidad sin exposición |
| **Endpoints** | **agrupados por recurso** (acordeón), chip de método con color, ruta monoespaciada, propósito, refs de esquema y códigos. Pestañas: *Todos* · *Escritura* · *Sin autorizar* (`printSkip` en las dos últimas: solo filtran) | "37 endpoints · 12 de escritura" | alguno sin autorización |
| **Autorización** | **la visual insignia**: matriz endpoints × actores. Celda ✓ (todo) / ◑ (con alcance, tooltip con la expresión) / ✗ / **⚠ ambiguo**. `md+` tabla con cabecera fija y scroll horizontal propio; por debajo, una tarjeta por endpoint con la lista de actores | "4 actores · 3 alcances condicionados" | ≥1 celda ambigua |
| **Esquemas** | por esquema, tabla de campos: nombre, tipo, requerido, solo-lectura, ejemplo y **chip `COL-…`** (ref a otro artefacto → aviso, patrón `bd-refs.ts`) | "28 esquemas · 214 campos" | campo `computed` sin regla |
| **Errores** | catálogo: estado, código, cuándo | "7 códigos estándar" | — |
| **Reglas** | cada `BR-`/`VAL-` con su destino y el veredicto del BD al lado | "15/18 reglas con destino" | regla `application` sin endpoint |
| **OpenAPI** | visor del YAML en `<pre>` monoespaciado con **copiar** y **descargar** (`.yaml`/`.json`), badge de validación y tamaño. Sin dependencia nueva de resaltado: el documento es un entregable de máquina, no una lectura | "3.1.0 · 47 KB · válido" | inválido |
| **Validación** | mapa de `checks` + errores/avisos con su `code` | "6/6 comprobaciones" | errores |
| **Análisis** | pestañas riesgos / cobertura (con los no cubiertos **enumerados**) / observaciones | "cobertura 92%" | riesgo alto |
| **Preguntas** | lista + modo enfocado (`focused-questions.tsx`) | "2 bloqueantes pendientes" | bloqueantes pendientes |

**Export PDF.** Portada "Especificación de API", índice derivado y todos los
capítulos, reutilizando cada `render` con `forPrint: true`. Dos reglas propias:

- La **matriz de autorización** es el capítulo ancho: se imprime **partida por
  recurso** (no una tabla de 37 filas × 4 columnas cortada al margen), y cada bloque
  cabe en una página.
- El **YAML crudo lleva `printSkip`**. Un informe con 1.200 líneas de YAML no lo lee
  nadie y duplica lo que las tablas de endpoints ya cuentan mejor. En su lugar, el
  PDF imprime una ficha del documento (versión, nº de operaciones, checksum,
  validación) y **dice dónde descargarlo**. El YAML es un entregable de máquina y se
  entrega como archivo.

`api-refs.ts` declara las rutas por prefijo: `RES-`→Recursos, `EP-`→Endpoints,
`SCH-`/`SF-`→Esquemas, `AUTH-`→Autorización, `ERR-`→Errores, `ARM-`→Reglas,
`RISK-`/`OBS-`→Análisis, `Q-`→Preguntas. Los ids de otros artefactos (`COL-`,
`TBL-`, `BR-`, `CRUD-`, `ACT-`, `CMP-`) **no fingen destino**: avisan con un toast.

---

## 8. Decisiones y riesgos

### Decisiones propuestas (API1–API14)

| # | Decisión | Recomendación |
|---|---|---|
| API1 | Entrada cuádruple | **Transitiva** (3 saltos) con `resolve_lineage`. Sin migración. |
| API2 | El LLM y el documento | **Nunca escribe OpenAPI**; render determinista + validación sin LLM. |
| API3 | Anti-invención | **`RESOURCE_MAP`** fija recursos, operaciones y columnas; el LLM describe. Única ampliación: endpoints de acción **con cita verbatim**. |
| API4 | Autorización | **Fail-closed**: sin regla → `deny`; alcance sin columna real → `ambiguous` → pregunta **bloqueante**; `pii` + ambiguo → siempre bloqueante. |
| API5 | Validación | `openapi-spec-validator==0.9.0` (runtime) + `openapi-core` (solo tests, L3a). Ambos pinneados. |
| API6 | **Idioma de las rutas** | **ACORDADA: dominio en español, protocolo en inglés.** `GET /api/v1/siniestros/{siniestro_id}?limit=20&sort=-fecha_registro`. Razón: los segmentos de ruta son una proyección de las tablas, que ya son español (`siniestros`, `guias`); traducirlas obliga a un diccionario mental en cada chip de trazabilidad y parte en dos el lenguaje ubicuo del equipo. Lo que **no** es dominio (`/api/v1`, `limit`, `offset`, `sort`, códigos de error) va en inglés porque es protocolo, no negocio. Es exactamente la misma regla que ya gobierna los artefactos: **claves en inglés, valores en español**. |
| API7 | Caso de las propiedades JSON | **ACORDADA: `snake_case`**, espejo 1:1 de las columnas. Hace la trazabilidad verificable a simple vista y le ahorra al Agente Backend una capa de mapeo (y su clase de bugs). |
| API8 | Envelope de respuesta | **ACORDADA: el `ApiResponse` de la casa** (`{success, message, data}`), con la paginación dentro de `data` y el `code` estable del error también en `data`. Coherencia con lo que el Agente Backend va a generar. El envelope lo pone `OPENAPI_GEN`: el LLM ni lo ve. |
| API9 | Formato de error | Dentro del envelope, con **`code` estable** en `data`. Se descarta RFC 9457 (`problem+json`) por incoherencia con el envelope: mezclar dos formatos en la misma API es peor que elegir el menos estándar de los dos. |
| API10 | Paginación | **`offset`/`limit`** con `{items, total, limit, offset}`, default 20 / máx. 100. Es lo que ya usa la plataforma. Cursor: fuera de v1 (se anota para tablas de alto volumen). |
| API11 | Verbo de actualización | **`PATCH`** (parcial). Se omite `PUT`: el reemplazo total invita a borrar campos por accidente desde un formulario incompleto. |
| API12 | Exposición por tipo de tabla | entidad → CRUD según matriz; catálogo → **solo lectura**; puente → **anidado** bajo su padre; auditoría → **sin exposición**. Toda exclusión con motivo escrito. |
| API13 | Anidamiento | **Profundidad máxima 1** (`/siniestros/{id}/documentos`). Más profundo → recurso de primer nivel con filtro. |
| API14 | Audiencia de las preguntas | **`questions_for_tech_lead`** (quien tiene `api` FULL). Sin tocar la matriz de permisos; caso puntual → grant. |

### Riesgos

| Riesgo | Mitigación |
|---|---|
| **Autorización más ancha que la realidad** (el peor) | fail-closed + `basis` auditable por fila + `pii` como agravante + bloqueante por ambigüedad |
| **Explosión de superficie** (30 tablas × 5 = 150 endpoints) | exclusiones por tipo de tabla (API12), CRUD solo donde la matriz del EF lo pide, y `metrics.endpoints_total` con aviso al superar un tope configurable — **reportado, nunca recortado en silencio** |
| Coste de tokens en `SCHEMAS` (map por recurso) | concurrencia 3 (`API_SCHEMAS_CONCURRENCY`) y contexto acotado al diccionario del recurso |
| Tooling que aún no digiere OpenAPI 3.1 | render 3.0.3 a coste cero desde el mismo artefacto (§6) |
| Tamaño del artefacto (YAML embebido, ~50–150 KB) | aceptado: mismo criterio que el DDL completo en BD; `checksum` + `byte_size` declarados |
| Regla que el BD y la API se pasan mutuamente | comprobación L1 nº 12 sobre `bd_enforcement`: es el motivo de que ese campo exista |
| `db_conventions.yaml` sigue sin validar, y ahora también `api_conventions.yaml` | nace `pendiente_de_validacion`; las convenciones efectivas se persisten en `target` para que el artefacto sea auditable aunque el YAML cambie |

---

## 9. Plan de implementación por bloques

Cada bloque: `pytest`/`build`/`lint` en verde, **todo con mocks** (cortafuegos
autouse de `tests/conftest.py` activo), **commit + push**.

| Bloque | Contenido |
|---|---|
| **API0** | `api_conventions.yaml` (borrador) + loader; `openapi-spec-validator` pinneado; `openapi-core` en dependencias de test. EF/Scrum/Arquitectura/BD siguen verdes. |
| **API1** | Contrato `ApiArtifact v1.0.0` (Pydantic + enums + fixture del dominio de siniestros + round-trip). El contrato **impide** lo que sería invención u omisión muda (campo sin columna, exclusión sin motivo, alcance sin columna, descarte sin explicación, acción sin evidencia) y **permite** representar los defectos reportables (endpoint sin autorizar, spec inválida): negarse a construirlos impediría al agente reportarlos. |
| **API2** | Grafo + `LOAD_SOURCES` (carga cuádruple + gate + resolución de estilo/seguridad) + `RESOURCE_MAP` + naming + nodos stub. Dos consecuencias del cortafuegos que se confirmaron al implementarlo: **sin celda en la matriz CRUD no se generan endpoints** para esa entidad (se enumera y acabará en pregunta), y una tabla puente necesita `nested_delete` además de `nested_list`/`nested_create`, o una relación N:M se podría crear y nunca deshacer. |
| **API3** | `RESOURCES` + `ENDPOINTS` (CRUD determinista + acciones con evidencia). La **cita de la acción se verifica en Python** contra el texto del `PRO-`/`BR-`/`VAL-` citado: una paráfrasis convincente no pasa. El modelo entrega un **verbo**, nunca una ruta. |
| **API4** | `SCHEMAS` (esqueleto determinista + exposición por LLM) + `ERRORS`. Tres salvaguardas de exposición: no se puede ocultar la PK (sin ella no hay detalle), ni una columna obligatoria al crear (sin ella no hay alta), ni una que no exista. El `404` cambia de redacción cuando el endpoint tiene alcance por filas: responder `403` revelaría que el registro existe. |
| **API5** | `AUTHORIZATION` (base CRUD + alcances) + `RULE_MAPPING` (cierre del círculo con el BD). El esquema de salida del modelo **no admite `all`**: no hay sitio donde escribir "este actor lo ve todo", así que una alucinación solo puede restringir. Un endpoint sin autorizar lleva una fila `deny` explícita: el hueco se ve en la matriz, no en una ausencia. |
| **API6** | `OPENAPI_GEN` determinista + `VALIDATE` L1/L2/L2b (+ L3a `openapi-core` en tests). **L3a encontró un fallo que L1 y L2 no podían ver**: declarar `servers: /api/v1` con rutas que ya llevan el prefijo duplica la base (`/api/v1/api/v1/…`). Es un error semántico, no de esquema. El servidor pasa a ser la raíz y las rutas conservan el prefijo completo, que es como viajan en el artefacto y como se ven en el hub. |
| **API7** | `CRITIQUE` + `QUESTION_GEN` (agrupadas por clase de vacío) + cobertura. |
| **API8** | `ASSEMBLE/VALIDATE/PERSIST` + servicio + API `/apis/*` + refine + gate 409 + descarga del OpenAPI. |
| **API9** | Frontend: nav CONSTRUIR, `ApiResultView`, matriz de autorización, visor/descarga del YAML, flujo new→spec→afinar, export PDF. |

---

## 10. Pendientes conocidos (heredados y nuevos)

- Validar `tech_stack.yaml` más allá de `database_relational` — aquí pesan las capas
  **`auth`** y **`api_style`**, que fijan el esquema de seguridad.
- Validar `api_conventions.yaml` (nace en borrador, igual que `db_conventions.yaml`).
- Colección Postman/Insomnia y cliente TypeScript generado: fuera de v1.
- Paginación por cursor, `Idempotency-Key`, rate limiting y webhooks: fuera de v1.
- Sin runs reales: como el resto de la cadena, se construirá y probará con mocks.
