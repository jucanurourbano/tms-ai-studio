# Punto 2 — La cota de Scrum: acotar lo que cada llamada arrastra

> **Estado: DISEÑADO, SIN IMPLEMENTAR.** Ningún bloque autorizado (REGLA R2).
> Instrumento: `backend/scripts/medir_los_cuatro_puntos.py` §1 y §2 (0,00 USD,
> re-medible). Contexto: `diseno-control-de-gasto.md` §3.ter.2 y §3.quater.

---

## 0. El encargo, y las tres preguntas

§3.ter midió que **Scrum es el que más rápido crece de los tres agentes**: x11,6
de documento produce **x28 de costo**, contra x11,6 en QA. La causa nombrada allí:
`build_stories_user` mete **todo** el contexto del EF en **cada una** de sus N
llamadas y `build_criteria_user` mete **todas** las validaciones en cada una de
las suyas. El término es `N x contexto(N)` — cuadrático.

Este documento contesta las tres preguntas con las que se encargó el diseño:

1. **Qué necesita DE VERDAD cada llamada, campo por campo** (§1–§2).
2. **Si aplica la forma de QA-D8** —el `[:20]` que hace escalar bien a QA— (§3).
3. **Qué se pierde, y con qué se mediría** (§7), porque la calidad no se puede
   medir con el doble del LLM.

Y añade la que salió del camino: **por qué el instrumento no puede ser el mismo en
los dos nodos** (§4–§6).

---

## 1. Campo por campo: qué lleva cada llamada, y de qué tamaño

Medido con los constructores de producción (`build_stories_user`,
`build_criteria_user`), sumado sobre **todas** las llamadas del nodo. USD de
entrada, estimados.

### `STORIES` — una llamada por requisito funcional

| clave del payload | 1,76 KB | 10 KB | **20 KB** | % a 20 KB |
|---|---:|---:|---:|---:|
| `business_rules` (todas, en cada llamada) | 7 584 | 254 169 | **1 032 300** | **62,0%** |
| `processes` (todos, **con sus `steps`**) | 2 128 | 74 586 | 298 530 | 17,9% |
| `(system)` (idéntico, en cada llamada) | 18 128 | 105 369 | 210 738 | 12,7% |
| `actors` (todos) | 704 | 23 901 | 96 720 | 5,8% |
| `epics` (todas) | 1 712 | 9 951 | 19 902 | 1,2% |
| **`functional_requirement` ⇐ EL SUJETO** | 614 | 3 606 | **7 206** | **0,4%** |
| **total** | **30 870** | **471 582** | **1 665 396** | 4,996 USD |

### `CRITERIA` — una llamada por historia

| clave del payload | 1,76 KB | 10 KB | **20 KB** | % a 20 KB |
|---|---:|---:|---:|---:|
| `validations` (**TODAS, siempre**) | 6 882 | 235 980 | **945 000** | **54,2%** |
| `business_rules` (ancladas + **TODAS** si no hay ancla) | 4 477 | 102 520 | 407 429 | 23,4% |
| `(system)` (idéntico, en cada llamada) | 31 403 | 182 340 | 364 680 | 20,9% |
| **`story` ⇐ EL SUJETO** | 2 281 | 13 283 | **26 573** | **1,5%** |
| **total** | **45 043** | **534 123** | **1 743 682** | 5,231 USD |

**El sujeto de la llamada es el 0,4% del mensaje en `STORIES` y el 1,5% en
`CRITERIA`.** Todo lo demás es contexto, y todo el contexto —salvo el sujeto— es
**idéntico byte a byte** en las N llamadas del nodo. Ése es el desperdicio, y es
la misma forma que §3.bis.1 midió en QA (466 738 tokens de preámbulo reenviado,
el 55% de la factura del agente): aquí no es solo el `system`, es el `system`
**más el EF entero**.

Dos observaciones que la tabla regala:

- **A 1,76 KB el que manda es el `system`** (58,7% y 69,7%); a 20 KB manda el
  contexto del EF (62,0% y 54,2%). El diagnóstico depende del tamaño, y todo lo
  que el proyecto había mirado hasta §3.ter estaba en el extremo pequeño.
- **`processes` viaja con sus `steps`** — seis frases por proceso. A 20 KB son
  0,90 USD de pasos de proceso reenviados 186 veces.

---

## 2. Qué necesita de verdad: la lista, trazada al esquema de salida

No «el EF entero menos algo». Lo que sigue es, clave por clave, **qué produce el
modelo con ella** y **qué código lo comprueba**.

### `STORIES` → `StoryExtract` (`schemas/extraction.py:29`)

| campo de salida | qué clave del payload lo alimenta | quién lo valida |
|---|---|---|
| `role` | `actors[].name` | nada — texto libre |
| `goal`, `benefit` | `functional_requirement.text` (+ `processes[].steps` como color) | nada |
| `requirement_refs` | **NADA** — el payload solo trae su propio RF | `stories.py:_all_requirement_ids` |
| `process_refs` | `processes[].id` / `.name` | `valid_proc` |
| `rule_refs` | `business_rules[]` (id **y** statement: sin el texto no se puede elegir) | `valid_rule` |
| `depends_on_requirements` | **NADA** (ver §8) | `valid_req` |
| `epic_hint` | `epics[]` (id, título y `source_refs`, los tres los usa `_resolve_epic_ref`) | `_resolve_epic_ref` |
| `confidence` | — | esquema |

**Necesario y suficiente**: `functional_requirement`, `actors` (id+nombre),
`epics` (los tres campos), `processes` (id+nombre; los `steps` son *color*, no
ancla) y `business_rules` (id+statement).
**Innecesario medido**: `functional_requirement.priority` — el esquema de salida
de `STORIES` no tiene prioridad; la pone `PRIORITIZE` después. Cuesta ~5 tok por
llamada: se nombra por completitud, no por dinero.

### `CRITERIA` → `CriterionExtract` (`schemas/extraction.py:49`)

| campo de salida | qué clave lo alimenta | quién lo valida |
|---|---|---|
| `given`/`when`/`then`/`text` | `story.statement` + `business_rules` + `validations` | `has_body` |
| `source_refs` | `business_rules[].id` ∪ `validations[].id` | `valid_refs` (`criteria.py:64`) |
| `format` | — | esquema |

**Aquí `business_rules` y `validations` no son contexto: son el UNIVERSO DE
ANCLAS.** Un criterio sin `source_ref` real se descarta a cuarentena
(`criteria.py:104`). Lo que se quite del payload **no se puede citar**, y lo que
no se puede citar **no se convierte en criterio**. Esa asimetría gobierna todo lo
que sigue.

---

## 3. El precedente QA-D8: qué es de verdad el `[:20]`, y por qué no es esto

El encargo lo plantea bien: QA escala linealmente porque su payload por criterio
está acotado, y la cota es el `[:20]` de QA-D8. Pero mirando el código
(`ai/agents/qa/test_design.py:74-94`), **el `[:20]` no es el mecanismo: es el
respaldo del mecanismo.** El payload de QA tiene tres capas:

1. **Resolución por cita** — `CRITERION_MAP` resuelve, en Python y antes de gastar
   un token, las reglas y validaciones que **ese** criterio cita
   (`criterion_map.py:160-176`). Es O(1) por llamada y **no lleva `[:20]`**.
2. **Alcanzabilidad derivada** — `matching_entities` amplía con las validaciones
   de las entidades **nombradas en el texto** del criterio
   (`criterion_map.py:69-93`). Relevancia sacada de un dato real, no de una
   corazonada.
3. **El `[:20]`** — se aplica **solo** a `context.fields/entities/actors`, que el
   prompt usa como **nomenclatura** (cómo se llaman las cosas), nunca como ancla.
   Un caso no se ancla a un `field`.

**La conclusión, y es la respuesta a la pregunta:** la forma que aplica a Scrum es
la de **`CRITERION_MAP`, no la del `[:20]`**. En QA las anclas llegan resueltas y
lo que se trunca es la nomenclatura sobrante; en Scrum las anclas **son** las
listas que se querría truncar. Poner `business_rules[:20]` sobre un EF de 163
reglas sería recortar el universo de lo citable a las 20 primeras **por orden de
extracción**, que no es un orden con significado. Eso no es la cota de QA-D8: es
la cota que QA-D8 tuvo cuidado de no poner.

Y el motivo por el que QA pudo permitírselo se llama `CRITERION_MAP`. **Scrum no
tiene ese nodo.** Lo que sigue es qué pasa cuando se intenta construirlo.

---

## 4. El recall retrospectivo: la cota es segura solo donde hay ancla

Antes de proponer un filtro hay que saber qué se lleva por delante. El plan real
de 31 historias y 110 criterios **es el ground truth**: dice qué reglas citó de
verdad el modelo teniendo delante el EF entero. Se puede comprobar, sin LLM y sin
gastar, si un payload acotado **habría contenido esas citas**.

`medir_los_cuatro_puntos.py` §2 lo mide. Tres resultados, y son tres respuestas
distintas:

### A) `CRITERIA` con `rule_refs` — la cota es EXACTA

```
citas a regla dentro del ancla: 81/81 = 100% recall
```

De las 25 historias que traen `rule_refs`, **todas** las reglas que sus criterios
citaron estaban ya dentro de esos `rule_refs`. El filtro que `criteria.py:21-25`
ya aplica **no pierde nada medible**. No hay nada que arreglar aquí, y hay algo
que confirmar: el ancla existe, la produjo el nodo anterior, y funciona.

### B) `STORIES` — la cota NO es posible con los datos que hay

El EF **no enlaza un requisito con sus reglas**. Lo único que comparten es el
`source_ref` (el párrafo del documento) y el vocabulario. Medido sobre las 49
citas reales:

| sustituto de ancla | recall |
|---|---:|
| co-localización por `source_ref` | **71%** |
| solape léxico ≥ 25% | 61% |
| unión de los dos | **80%** |

**Uno de cada cinco enlaces que el modelo usó habría quedado fuera de alcance.**
Y el detalle importa más que la cifra: las reglas que se pierden son

```
BR-010 (5 citas) — Los jefes solo tienen visibilidad de las solicitudes de su propio equipo.
BR-007 (2 citas) — Una solicitud confirmada por RRHH queda registrada con estado 'aprobada'.
BR-005 (2 citas) — Cuando RRHH confirma, se descuentan automáticamente los días.
BR-013 (1 cita)  — El cálculo legal de los días queda FUERA del alcance del sistema.
```

Son **reglas transversales**: una de autorización, dos de estado global y una de
alcance. Una regla transversal, por definición, **no está co-localizada con
ningún requisito**, así que cualquier filtro por localidad la pierde — y pierde
exactamente la clase que peor se puede perder. No es un umbral mal calibrado: es
que la señal no existe. **Subir el umbral no lo arregla; lo empeora.**

### C) `CRITERIA` sin `rule_refs` — tampoco

Seis de las 31 historias no traen `rule_refs`, y hoy reciben **todas** las reglas
por el respaldo `or not rule_refs` (`criteria.py:24`). Ese respaldo no es peso
muerto: sus criterios citan 9 reglas. Pero el mismo sustituto por localidad cubre

```
1/9 = 11%
```

El contraejemplo está escrito: `US-027` («exportar un reporte con la información
de las solicitudes») cita **seis** reglas y la localidad no alcanza **ninguna**.
Una historia de reporte toca todo el dominio a propósito. **El respaldo se queda
como está.**

> **Lo que este método mide y lo que no.** Contesta «¿la cota habría quitado algo
> que de hecho se usó?» — condición **necesaria**. No contesta «¿qué habría hecho
> el modelo con otro payload?»: eso requiere una corrida pagada (§7).

---

## 5. La conclusión que ordena el bloque

**La cota es segura donde hay un ancla que resolver, y donde no la hay no es una
cota: es una apuesta.** En Scrum el ancla existe en un solo sitio —los `rule_refs`
que `STORIES` produce— y ahí ya está aplicada.

De modo que el instrumento que resuelve la cuadraticidad de Scrum **no es la
cota**: es el **lote**, el mismo del punto 4 aplicado a un segundo agente. El lote
no decide qué es relevante —no pierde nada— y divide el contexto compartido entre
K. Se paga en atención por unidad y en granularidad de cuarentena (D3 de
`diseno-recorte-qa-lotes.md`, ya argumentado), no en cobertura.

**Y hay que decir lo que el lote NO hace: no rompe el término cuadrático, lo
divide por K.** El contexto compartido sigue creciendo con N, así que el costo
sigue siendo `N²/K`. A 40 KB el problema vuelve. Lo único que lo haría lineal es
un ancla real por requisito — y ésa **no se puede fabricar en Scrum**, porque la
evidencia con la que se fabricaría (el párrafo, el verbatim) vive en el EF. Ver
§9.

---

## 6. El diseño

### D1 — `STORIES` en lotes de 10 requisitos funcionales

El sujeto de la llamada pesa 39 tok y el contexto compartido 8 915 (a 20 KB), así
que el lote es aquí más eficaz que en ningún otro sitio del proyecto: **cada RF que
se añade al lote es gratis salvo por su propio texto**.

El tope sale de la salida, con el mismo criterio que `diseno-recorte-qa-lotes.md`
§ topes: el mayor lote cuya salida real (x2,4–x3,1) sigue por debajo de
`CLAUDE_MAX_TOKENS` = 8 192. Medido sobre el plan real (104 tok por historia, 1,94
historias por RF ⇒ **202 tok estimados por RF**):

| lote | salida est. | real x2,4–x3,1 | veredicto |
|---:|---:|---:|:---|
| 5 | 1 009 | 2 421 – 3 127 | holgado |
| **10** | **2 018** | **4 842 – 6 255** | **elegido** |
| 20 | 4 035 | 9 684 – 12 509 | cruza el tope |

**Tope = 10 RF.** Efecto a 20 KB: 186 → 19 llamadas, 1 665 396 → 176 591 tok.

### D2 — `CRITERIA` en lotes de 5 historias, con el ancla intacta

Misma aritmética, sobre 307 tok estimados por historia:

| lote | salida est. | real x2,4–x3,1 | veredicto |
|---:|---:|---:|:---|
| **5** | **1 535** | **3 685 – 4 760** | **elegido** |
| 10 | 3 071 | 7 370 – 9 520 | cruza por arriba |

**Tope = 5 historias.** Es el mismo reparto que en QA —el nodo que emite más por
unidad se lleva el lote pequeño— y por la misma razón, no por simetría estética.

Dentro del lote, el payload conserva la estructura que hoy tiene: cada historia
con **sus** reglas ancladas (que ya es exacto), las validaciones **una vez por
lote** en vez de una por historia, y el respaldo completo **una vez por lote de
historias sin ancla**, agrupadas aparte. Efecto a 20 KB: 360 → 72 llamadas,
1 743 682 → 385 138 tok.

### D3 — El tope es una constante, no una decisión irreversible

Igual que en el punto 4: se sube cuando el libro mayor enseñe holgura en la
salida real. Empezar alto y descubrir el truncamiento cuesta una corrida pagada
que devuelve un plan con huecos.

### D4 — Lo que el lote NO puede tocar: el ancla

Con una llamada por RF, `stories.py:137` **fuerza** el RF de la pasada dentro de
`requirement_refs`:

```python
if rf_id not in req_refs:          # ancla obligatoria al RF de la pasada
    req_refs.append(rf_id)
```

Con un lote de 10 esa línea **etiquetaría cada historia con un RF arbitrario del
lote**. No es un riesgo: es una línea que mentiría. Lo mismo en `CRITERIA`, donde
`by_id = {r["ref"]: r["data"]}` (`criteria.py:82`) mapea por el ref de la llamada,
que con lote es el lote y no la historia.

**Condición dura de implementación** (idéntica a la del punto 4): el modelo
devuelve **a qué unidad pertenece cada ítem** —`requirement_ref` obligatorio en
`StoryExtract`, `story_ref` obligatorio en `CriterionExtract`— y Python lo **busca
en el lote y rechaza lo que no esté**, con `Observation`. Si esto se olvida, el
lote es la puerta por la que el modelo reasigna historias a requisitos que no las
piden, que es el peor error posible de este agente.

### D5 — La cota de validaciones por entidad: SÍ, pero no todavía

`matching_entities` (el mecanismo 2 de QA) aplica igual a `CRITERIA`: las
validaciones alcanzables desde las entidades nombradas en el `statement` de la
historia. El recall retrospectivo da **62/62 = 100%**, pero hay que declarar lo
que ese número vale: el EF real tiene **2 entidades y 6 validaciones**, y el
alcance medio es de **5,8 de 6**. El filtro no filtra nada, así que el 100% no
prueba nada. **La cota por entidad no está validada y no entra en la cifra del
informe.** Una vez aplicado el lote su valor en dinero es además pequeño (0,05 USD
a 10 KB, 0,21 a 20 KB): lo que se gana con ella no es dinero, es **caber** —ver
§10.

Queda con dueño: se valida cuando exista un EF con ≥ 8 entidades y ≥ 30
validaciones, con el mismo método de §4. Hasta entonces, las validaciones viajan
enteras una vez por lote.

---

## 7. Qué se pierde, y con qué se mide

El encargo lo pide explícitamente y tiene razón en la premisa: **el doble del LLM
no puede medir calidad.** El doble devuelve lo que se le programó devolver; con
lote o sin lote produce lo mismo. Sirve para tokens, llamadas y costo, y para
nada más. Lo que sigue separa lo que se sabe hoy, lo que se puede saber sin pagar
y lo que exige una corrida pagada.

### 7.1 Lo que se pierde, enumerado

| # | qué se pierde | con qué instrumento | ¿medido? |
|---|---|---|---|
| 1 | **Nada del payload.** El modelo ve el mismo contexto | lote | sí, por construcción |
| 2 | **Atención por unidad.** 10 RF en una llamada reciben menos foco que 1 | lote | **no, exige corrida pagada** |
| 3 | **Granularidad de la cuarentena.** Un lote irreparable pierde 10 RF, no 1 | lote | sí (aritmética) |
| 4 | **Granularidad de `by_stage`.** El costo por llamada deja de ser por RF | lote | sí; nadie lo usaba |
| 5 | **Riesgo de plantilla.** 10 RF juntos invitan a 10 historias con la misma forma | lote | **no, exige corrida pagada** |
| 6 | **Riesgo de reasignación.** Una historia colgada del RF equivocado | lote | lo impide D4, y se cuenta |
| 7 | Reglas fuera de alcance | cota | **no aplica: la cota no se pone** (§4B/§4C) |

Los dos que exigen corrida pagada son el 2 y el 5, y son **el mismo fenómeno**
visto desde dos lados: menos foco por unidad produce salida más uniforme.

### 7.2 Lo que se puede medir sin pagar, y ya está medido

- **El recall retrospectivo** (§4). Condición necesaria. Ya corrido; es lo que
  hizo caer la cota de `STORIES`.
- **La aritmética del lote**: llamadas, tokens, salida por llamada contra
  `CLAUDE_MAX_TOKENS`. Ya corrido (§6).

### 7.3 El par antes/después, y las filas que decide sin juez

Cuando haya saldo: **la misma corrida, el mismo documento, el mismo modelo, dos
veces** —con y sin lote— seguidas, y las dos en el libro mayor. Es el método que
OLL-D5 ya fijó para el proveedor local, y por el mismo motivo: se compara por
**magnitudes deterministas**, sin LLM juez. Las filas:

| fila | de dónde sale | qué detecta |
|---|---|---|
| cobertura de RF | `analysis.coverage` del artefacto | que el lote no deje requisitos sin historia |
| nº de historias / nº de criterios | conteo | que no se encoja la producción |
| **`|⋃ rule_refs|` / `|BR|`** | conteo sobre el artefacto | **la fila que decide**: si acotar o agrupar hubiera «hambreado» el anclaje, se ve aquí y en ningún otro sitio |
| refs citadas inexistentes | los `skipped` de cada nodo | invención; sube si el lote confunde al modelo |
| **historias ancladas al RF equivocado** | el rechazo de D4, contado | la reasignación del §7.1-6 |
| tasa de duplicados | el detector de LOT0, con la clave sin `criterion_ref` | el riesgo de plantilla del §7.1-5 |
| costo y llamadas por nodo | `GET /gasto/mensual` `by_stage` | el recorte, que es lo que se prometió |

**Y el coste honesto del experimento son TRES corridas, no dos**: el «antes» se
corre **dos veces** para tener el suelo de varianza. Un par solo no distingue el
efecto del lote del ruido de un proceso estocástico, y presentarlo como si lo
distinguiera sería exactamente el tipo de afirmación que este proyecto no hace.

### 7.4 Lo que solo mide una persona

Si las historias están **mejor o peor escritas** no lo dice ninguna magnitud. Lo
único honesto es una **revisión ciega**: N historias tomadas al azar de las dos
corridas, mezcladas y sin etiqueta, revisadas por el analista contra su requisito.
Cuesta tiempo de analista, no tokens, y hay que presupuestarlo como parte del
bloque en vez de descubrirlo después.

---

## 8. Un hallazgo del camino: `depends_on_requirements` pide lo que no se envía

`StoryExtract` tiene `depends_on_requirements` y `stories.md` lo describe como
«los **requisitos previos** cuya historia debe completarse antes… **Solo
referencias reales del EF**».

**El payload de `STORIES` no contiene ningún id de requisito salvo el propio.** Ni
en `epics` (sus `source_refs` son `MOD-`/`PRO-`), ni en `processes`, ni en
`business_rules`. Así que el modelo solo puede rellenar ese campo **adivinando la
convención** `REQ-F-00N` a partir del id que sí ve. En el plan real, 5 de 31
historias traen dependencias así.

El filtro anti-invención (`r in valid_req`) **no puede distinguir una inferencia
correcta de una conjetura afortunada**, porque el espacio de ids es secuencial y
adivinable. Y no es cosmético: `SPRINT_PLAN` respeta `dependencies` para ordenar
los sprints. Es coherente con el otro síntoma medido: **ninguna historia del plan
cita más de un requisito** (`requirement_refs > 1` en 0 de 31).

Tres salidas, y hay que elegir una en el bloque:

1. **Mandar el índice de requisitos** (id + texto) una vez por lote. A 20 KB son
   7 254 tok x 19 lotes = **0,41 USD** — deja de ser gratis, pero el lote es lo
   que lo hace pagable.
2. **Mandar solo los ids.** Barato (744 tok) e inútil: un id sin texto no sostiene
   un juicio de dependencia.
3. **Quitar el campo del esquema** y derivar las dependencias en Python. Es la
   dirección del proyecto (`_resolve_dependencies` ya es determinista; lo único
   no determinista es este campo) pero contradice **D8** del Agente Scrum, que
   eligió detección por LLM a propósito.

**Recomendación: (1).** El lote lo hace asequible por primera vez y conserva D8.
Con el lote de 10 el modelo ve además 10 RF reales, así que incluso sin (1) el
campo pasa de «imposible» a «parcial» — pero parcial y silencioso es peor que
caro y correcto.

---

## 9. Por qué Scrum es cuadrático, y dónde está el arreglo de verdad

El lote divide por K. Lo que hace que haya algo que dividir es que **el EF entrega
una bolsa de ítems sin enlazar**: requisitos por un lado, reglas por otro,
validaciones por otro, y ningún campo que diga qué regla restringe qué requisito.
Sin ese enlace, cualquier nodo que trabaje requisito a requisito tiene que llevar
la bolsa entera, y el término `N x contexto(N)` es inevitable.

**El enlace solo se puede fabricar donde vive la evidencia**, que es el EF: tiene
el verbatim, tiene el párrafo y tiene el documento delante. Un campo
`constrains_requirements` en `BusinessRule` —con la misma disciplina de
`source_ref` + `evidence` que el resto del contrato— haría lineal a Scrum y de
paso serviría al Agente BD (`rule_mappings`) y a QA.

**Fuera del alcance de este punto**, que es un recorte de costo y no un cambio de
contrato. Se escribe aquí para que la decisión exista: *el punto 2 compra un
factor 10; el enlace en el EF compra el exponente.*

---

## 10. Y lo que la cota compra que el lote no: caber

Con lote de 10, una llamada de `STORIES` a 20 KB pesa **~9 300 tokens**. Cabe en
Claude sin pestañear y cabe —justo— en el techo del proveedor local (**8B Q4 a
16K de contexto**, `diseno-llm-local-ollama.md`). A 40 KB pesa ~17 800 y **no
cabe**.

Es decir: para Claude la cota es una optimización que el lote ya casi agota; para
el proveedor local **la cota es la diferencia entre poder correr Scrum y no
poder**. Por eso D5 queda con dueño en vez de descartada, y por eso el orden
natural es **lote ahora, cota cuando OLL la necesite y un EF real permita
validarla**.

---

## 11. Plan de implementación por bloques

Tests mockeados, commit + push por bloque, REGLA R2 entre bloques.

- **SCR0 — El detector de reasignación, primero.** El conteo de «ítem devuelto que
  no pertenece al lote», con su `Observation`, y el candado que lo ve fallar.
  Antes que el lote, por la misma razón que LOT0 va antes que LOT2: si llega
  después, el antes/después del bloque no se puede leer.
- **SCR1 — El empaquetado.** Aritmética pura, sin LLM: partición de RF y de
  historias en lotes, ids estables, sin partir una unidad. Tests deterministas.
- **SCR2 — El lote en `run_structured_map`.** La clave de vuelta obligatoria
  (`requirement_ref` / `story_ref`), el desmontaje de `stories.py:137` y de
  `criteria.py:82`, el reintento partiendo el lote en dos **una** vez —con la
  precondición dura de que un `BudgetExceededError` **no** entre por ahí (§6.bis
  del diseño de gasto)—. **Todo el riesgo está aquí.**
- **SCR3 — El índice de requisitos** (§8, opción 1) y el candado de que
  `depends_on_requirements` solo cita lo que viajó.
- **SCR4 — El par antes/después real.** §7.3, tres corridas. **Se autoriza
  aparte.**

**No entra en el plan:** la cota por entidad (D5, sin validar), el enlace en el
contrato del EF (§9, cambio de contrato) y `ESTIMATE`/`PRIORITIZE` en lote —que es
el punto 3 aplazado y cuya prioridad hay que revisar: a 20 KB vale **2,03 USD**,
no los 0,178 con los que se aplazó (`diseno-control-de-gasto.md` §3.quater.4).
