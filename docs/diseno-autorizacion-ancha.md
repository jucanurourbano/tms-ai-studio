# La autorización ancha — punto 2 del CMP0

> **Estado: DISEÑADO, sin implementar. Ningún bloque autorizado (REGLA R2).**
> Instrumento del número: `backend/scripts/medir_propagacion_de_confianza.py`
> (lee artefactos ya persistidos, no corre ningún agente, **0,00 USD**).
> Cadena medida: la del CMP0 (`[DOBLE·CMP0]`, API `01M1CXYSWV2KG0B15A6YFJQWS3`)
> sobre el EF y el Scrum **reales** de julio.

---

## 0. Qué es esto y qué no

Es el segundo hallazgo de la corrida CMP0: la matriz de autorización que produce
el Agente API concede **más de lo que nadie autorizó**, y lo hace con la confianza
más alta del artefacto. No es un fallo del modelo —esta corrida usó dobles—, es
**maquinaria determinista** que da por dato lo que era un relleno.

Lo que **no** es: no toca la matriz de permisos de la plataforma (§6.1 de
`CLAUDE.md`). Aquí se habla de la autorización del sistema **que el ISDF diseña**,
no de quién entra al Studio.

---

## 1. El hallazgo, fila por fila

La matriz del CMP0 tiene **9 filas para 9 endpoints**:

| | filas |
|---|---:|
| totales | 9 |
| conceden acceso (`allow`) | **8** |
| …sin evidencia en lo que las sostiene | **8** |
| …y además `scope: all` (todas las filas) | **8** |
| …con confianza **mayor** que la de su base | **8** |
| deniegan (`default_deny`) | 1 |

Las ocho concesiones son, literalmente, éstas:

```
AUTH-001..004  ACT-001 Trabajador  allow/all  conf=0.9  base CRUD-001 (conf=0.5, evidence=null)
AUTH-005..008  ACT-001 Trabajador  allow/all  conf=0.9  base CRUD-002 (conf=0.5, evidence=null)
```

Traducido a lo que autoriza el contrato: **cualquier trabajador puede listar,
leer, crear y modificar la ficha de cualquier otro trabajador** (`GET/POST/PATCH
/api/v1/trabajadores`), sobre **todas** las filas. Y mientras tanto:

- El EF nombra **cuatro actores**, tres de ellos con evidencia verbatim y
  `confidence 0.95` — *Jefe directo*, *RRHH*, *Sistema de planillas*—, y **ninguno
  aparece en la matriz**. La pregunta que lo dice (`Q-004`, «3 actores no tienen
  acceso a ninguna operación») **no es bloqueante**.
- El único actor con accesos es el que la matriz CRUD del EF eligió, y lo eligió
  por ser `actors[0]`.
- **No hay un solo endpoint `DELETE`** en toda la especificación, porque la celda
  fabricada trae `delete: False` escrito a mano. La *forma* de la superficie de la
  API la fija un literal.

---

## 2. La causa, y por qué la fracción no depende del documento

`ai/agents/ef/infer.py:104-120`, nodo `INFER` del EF:

```python
# 4) CRUD: por entidad (read/create/update derivados; delete conservador).
first_actor = actors[0]["id"] if actors else None
for i, ent in enumerate(entities, start=1):
    crud.append({..., "actor_ref": first_actor, "create": True, "read": True,
                 "update": True, "delete": False,
                 "origin": "derived", "confidence": 0.5})
```

Una celda por entidad, siempre al primer actor, siempre `confidence 0.5`, siempre
`evidence: null`. **La matriz CRUD del EF no se extrae del documento en ningún
camino del código**: no hay dimensión de `EXTRACT` que la produzca, `CONSOLIDATE`
no la toca y `ASSEMBLE` la copia. Es un `for` sobre entidades.

Consecuencia que hay que leer despacio, porque es la que decide la forma del
arreglo: **la fracción de concesiones sin evidencia es 1,00 por construcción**, en
cualquier documento y a cualquier tamaño. Lo que escala es el número absoluto —
**≈4 endpoints concedidos por entidad, todos al mismo actor**: veinte entidades
son ochenta concesiones de todo-sobre-todo a `actors[0]`.

Y el nombre engaña: `basis="crud_matrix"` se lee como «lo dice la matriz CRUD del
EF», que suena a dato del documento.

---

## 3. Tres asimetrías invertidas

### 3.1 La confianza sube al propagarse

`authorization.py:133` escribe `confidence=0.9` sobre una base de `0.5`. Y
`endpoints.py:241` lo dice sin ambigüedad:

```python
"confidence": 0.9 if operation.get("basis") == "crud_matrix" else 0.7,
```

**El proyecto premia con su confianza más alta a la base menos evidenciada.** El
0.9 no es un error de dedo: es la creencia de que una celda CRUD es lo más firme
que hay, escrita en dos ficheros.

Medida transversal sobre la cadena real (mitad 3 del informe del script): **53 de
137** ítems con refs resolubles llevan una confianza mayor que la de algo que
citan. Ese 39% es un **techo, no una medida**, y el propio script lo etiqueta así:
no todo ref es un apoyo. El contraejemplo está medido — `FLD-001` (0.95) cita
`ENT-001` (0.6), pero `INFER` derivó la entidad **del** campo, así que la
dirección del apoyo está invertida. De ahí la decisión **AUT-D3**: el invariante se
define sobre **bases declaradas**, no sobre cualquier ref. En la matriz de
autorización no hay esa duda: sus `source_refs` **son** sus bases, y ahí la cifra
es exacta, **8 de 8**.

### 3.2 `scope: all` es el valor que se escribe por SILENCIO

`build_base_matrix` escribe `scope="all"` en cuanto hay una celda; `apply_scopes`
solo puede **acotarlo** si el modelo propone algo. Si el modelo no propone nada —o
si su propuesta se descarta por no citar una regla real, que es la defensa
correcta— la fila se queda diciendo «todas las filas».

Es la **cuarta** aparición de la misma regla del proyecto: *la ausencia de un dato
no es el valor 0 de ese dato* (`sqlglot` degradando a `Command`; redactar en vez
de rechazar; `usage` ausente ≠ `usage` cero; Ollama truncando en silencio). Aquí
la ausencia se escribe como el valor **más ancho posible**.

Y el contrato lo confiesa en su propia docstring (`AuthScope`):

> «Cualquier valor distinto de `ALL`/`NONE` describe un filtro por fila y **exige
> la columna real** que lo materializa».

Es decir: **el alcance más ancho es el único que no tiene que justificarse.** El
validador `_un_alcance_sin_columna_es_ambiguo` protege el alcance estrecho y deja
libre el ancho.

### 3.3 Bloquea el hueco estrecho y pasa la concesión ancha

De las cuatro preguntas del CMP0, las dos bloqueantes son el mecanismo de
autenticación y **un** endpoint sin autorizar. Las ocho concesiones de
todo-sobre-todo no generan ni una pregunta no bloqueante.

Lo más incómodo es que la rama honesta **ya está escrita**. `question_gen.py`
bloquea `resources_without_operations` con este motivo:

> «El EF no tiene celdas en la matriz CRUD para sus entidades, así que no se generó
> ningún endpoint: **inventarles un dueño habría sido peor**.»

El Agente API ya sabe que inventar un dueño es peor que dejar el hueco. Pero el EF
**se lo inventa antes**, así que esa rama solo se alcanza donde no hay entidad —
por eso el único `deny` del CMP0 es el del catálogo de estados.

---

## 4. EL NÚMERO: qué cuesta cada forma

Lo que el arreglo no puede hacer es convertir cada celda en una pregunta. Medido:

| forma | preguntas bloqueantes | veredicto |
|---|---:|---|
| **hoy** | 2 (`Q-001` auth, `Q-002` 1 endpoint sin autorizar) | miente |
| **una pregunta por celda sin evidencia** | **10** | **rechazada** |
| **agrupada por clase de vacío (elegida)** | **2** | ídem que hoy |

- La **forma ingenua** no falla por «8 de 9» en este documento: falla porque la
  fracción es **1,00 por construcción** (§2). Serían 8 preguntas aquí y 80 con
  veinte entidades, **en toda corrida**, y el Agente API pasaría a exigir una
  sesión de afinamiento antes de servir para nada. Un agente que siempre pregunta
  todo es tan inservible como uno que nunca pregunta nada.
- La **forma elegida** no añade preguntas porque **la pregunta ya existe y ya está
  agrupada**: las ocho filas pasan a `deny`, sus endpoints entran en
  `unauthorized_endpoints` y `Q-002` cambia de «(1 sin autorizar)» a «(9 sin
  autorizar)». Misma pregunta, mismo panel, una respuesta más ancha.
- Y el semáforo **no cambia de color**: `metrics.endpoints_unauthorized` ya vale
  **1** hoy, así que `all_endpoints_authorized` ya es `false` y el artefacto ya no
  habilitaba a Backend. Rojo → rojo. Lo único que cambia es que **la matriz deja
  de afirmar algo falso** mientras está en rojo.
- La pregunta resultante es además **más fácil de responder que la de hoy**,
  porque trae los candidatos: el EF nombra cuatro actores con evidencia verbatim y
  la pregunta los enumera (AUT-D4). Hoy dice «¿quién puede llamar a esta
  operación?» y no ofrece ni un nombre.

**Conclusión del trade-off:** el coste humano del arreglo es **una respuesta más
en una pregunta que ya había que responder**. No hay dilema; el dilema lo creaba
la forma ingenua.

---

## 5. Decisiones (AUT-D1 … AUT-D8)

### AUT-D1 — una celda sin evidencia no concede

`effect="deny"`, `basis="unevidenced_crud"` (valor nuevo de `AuthBasis`), `note`
con el motivo. **No** se marca `allow` provisional, y la razón está en la docstring
del propio nodo:

> «El modelo solo puede restringir. Una alucinación puede dejar a alguien viendo de
> menos —que se detecta al usar el sistema— pero nunca de más.»

Un `allow` provisional sobrevive a que alguien construya desde el artefacto
ignorando el semáforo; un `deny` provisional produce un sistema cerrado que falla
**al usarlo**, ruidosamente. Se elige la dirección que el nodo ya había elegido.

La celda **no se borra del EF**: sigue en `crud[]` como sugerencia derivada, para
que la pregunta pueda enumerarla y para que `crud_cells_covered` no mienta en la
otra dirección.

### AUT-D2 — `scope`: el silencio tiene su propio valor

`AuthScope` gana **`UNSCOPED = "unscoped"`**: «nadie declaró alcance». `ALL` queda
para la universalidad **declarada** (una regla del EF que dice «todos ven todo»).
`ambiguous` sigue significando otra cosa —alcance declarado que ninguna columna
materializa— y son ortogonales.

Contrato `ApiArtifact` → **v1.1.0**, retrocompatible: un enum que gana un valor no
invalida artefactos viejos. Lo que sí hay que declarar: en los artefactos ya
persistidos, `all` **sobredeclara** —significa «silencio»— y no hay forma de
distinguirlo a posteriori. Se dice en el propio doc en vez de descubrirse.

En la UI, `unscoped` es un **hueco visible** en la matriz (celda con su color), no
una nota al pie: es el patrón de §5.1 y el de la matriz de trazabilidad de QA.

### AUT-D3 — la confianza se calcula; no se escribe

Función única, en `ai/agents/base/confianza.py`:

```python
def confianza_derivada(bases: Sequence[Base], *, tope: float) -> Optional[float]:
    """Nunca por encima del mínimo de las fuentes.

    - Sin bases            → None  (no 0.0, no un default: es ausencia de dato)
    - Alguna base sin conf → None  (una fuente sin medir no sostiene una medida)
    - Con bases            → min(tope, min(confianzas))
    """
```

`tope` es lo máximo que el nodo se atreve a añadir **por su cuenta**, y sigue
siendo una constante escrita; lo que deja de existir es la posibilidad de escribir
un número **por encima de la fuente**.

**Cómo se impone —cuatro capas, y cada una tapa lo que la anterior no puede:**

1. **La fábrica no tiene dónde escribir un literal.** `_rule()` de
   `authorization.py` **pierde el parámetro `confidence`** y gana
   `bases: list[Base]`. Mismo mecanismo que `alcance_para_prompt()` (lo único que
   el modelo sabe del destino) y que `stage` keyword-only sin default: no es una
   norma, es que el sitio donde equivocarse ya no existe.
2. **El contrato lo valida.** `AuthorizationRule` gana `basis_confidence:
   Optional[float]` y `basis_evidenced: bool`, y un `model_validator` hermano del
   que ya hay:
   - `confidence > basis_confidence` → `ValueError`.
   - `effect=ALLOW` y `scope ∈ {ALL, UNSCOPED}` y `basis_evidenced is not True` →
     `ValueError`.
   Un validador no puede resolver `CRUD-001` contra el EF, así que la confianza y
   la evidencia de la base **viajan en la fila**. Se duplica un dato, y se declara:
   a cambio, **el artefacto se audita solo**, sin cargar el EF — que es lo que hace
   posible la capa 4 sobre artefactos ya guardados.
3. **Candado AST** (precedente `tests/llm/test_construcciones.py`,
   `test_atribucion_por_nodo.py`): ningún literal numérico asignado a `confidence`
   ni a `"confidence"` dentro de `ai/agents/api/`, salvo en `confianza.py`. Tapa el
   nodo nuevo que no use la fábrica.
4. **Auditor desde el artefacto persistido**:
   `scripts/medir_propagacion_de_confianza.py`, que ya existe y ya da el número.
   Tapa lo que se generó **antes** de la regla.

Ninguna de las cuatro es la buena por sí sola: 1 impide el error local, 2 impide
el error remoto, 3 impide el retroceso y 4 mide lo viejo.

### AUT-D4 — la pregunta se agrupa, y trae los candidatos

Una sola pregunta bloqueante por clase de vacío, con los refs enumerados
(`_MAX_REFS_EN_TEXTO` ya existe) **y con la lista de actores que el EF sí evidenció**:

> «¿Quién puede llamar a estas 9 operaciones? El EF nombra 4 actores con evidencia
> —Trabajador, Jefe directo, RRHH, Sistema de planillas— y ninguno tiene una
> concesión evidenciada: la matriz CRUD que se usó la derivó el EF sin citar el
> documento.»

Enumerar los candidatos no es cortesía: es lo que convierte una pregunta abierta
en una que se responde en un minuto, y el afinamiento que no se abandona es el que
hace útil todo el ciclo.

### AUT-D5 — `actors_without_access` sube a bloqueante, pero **acoplado**

Un actor sin accesos, por sí solo, puede ser correcto (participa en el proceso sin
usar el sistema) y bloquear por eso sería ruido. Pero **un actor con evidencia sin
accesos + concesiones sin evidencia a otro actor** es la firma exacta del
`actors[0]`. Bloquea la **conjunción**, nunca cada mitad por separado.

### AUT-D6 — pii: `all` no es ambigüedad, y hoy no bloquea

`_check_pii` mira `r.get("ambiguous")`. Una fila `allow/all` no es ambigua, así que
**un endpoint que expone datos personales a todo el mundo pasa el check**. Se
amplía: `allow` + `scope ∈ {ALL, UNSCOPED}` + esquema de respuesta con `pii` →
error L1 `pii_with_unrestricted_scope`.

Honestidad sobre esta corrida: **el CMP0 no ejerce ese guard.** La única columna
que el BD marcó `pii` es `solicitude_estados.nombre` —el nombre de un catálogo de
estados, o sea un falso positivo del BD— y su endpoint es justamente el único
`deny`. Ninguna de las ocho concesiones expone pii. Así que la ampliación se
escribe **con fixture propia**, y esta corrida no es evidencia de que funcione.
(El falso positivo del BD es hallazgo aparte, no de este punto.)

### AUT-D7 — de dónde sale la evidencia (la mitad que no está en la API)

Los D1–D6 hacen que el agente **deje de mentir**; ninguno hace que **acierte**.
Para eso la matriz CRUD tiene que poder llevar evidencia, y hoy no puede. Tres
caminos:

| camino | coste | veredicto |
|---|---|---|
| **(a)** No fabricar: `crud` vacío y preguntar | 0 llamadas | Suelo. Honesto y **siempre** rojo: nunca se acierta sin humano. |
| **(b)** Derivar de `processes` (léxico, sin LLM) | 0 llamadas | **Rechazado**: «Revisión por jefe directo (aprobar o rechazar)» → *update* exige un mapeo verbo→CRUD que es una conjetura con aspecto de derivación. Es el error que este punto denuncia, movido de sitio. |
| **(c)** Extraer con structured output y **cita verbatim obligatoria** | **~0,01 USD estimados por proceso** | **Recomendado.** |

El coste de (c) está medido con el EF real: el payload —pasos del proceso, actores
con su evidencia, entidades— pesa **460 tokens** (`estimate_tokens`), y con el
`system` y la salida sale ~0,01 USD estimados **por proceso**. Es despreciable
—la cadena cuesta 20–45 USD estimados a 10–20 KB—
y el patrón anti-invención ya está escrito seis veces en el repositorio: el modelo
elige de un conjunto cerrado (actor × entidad × operación, ambos ya extraídos) y
**cita el fragmento**; sin cita, no hay celda. Lo que **no** se admite es una celda
derivada del silencio.

La evidencia existe en el documento real: el `PRO-001` del EF de julio trae
`evidence` verbatim con «la solicitud le llega a su jefe directo, quien puede
aprobarla o rechazarla… pasa al área de Recursos Humanos para la validación
final… El trabajador puede cancelar su solicitud mientras no haya sido confirmada
por RRHH». Ahí están los tres actores que la matriz perdió.

**Hallazgo lateral que (c) obliga a arreglar:** `processes[].actor_refs` guarda
**nombres, no ids** (`["Trabajador", "Jefe directo", …]` en vez de `ACT-00N`). Un
ancla que no resuelve no es un ancla.

### AUT-D8 — lo que NO se toca

- La matriz de permisos de la plataforma (§6.1). Otro problema, otro sujeto.
- `AuthEffect` sigue con dos valores. «Provisional» no es un efecto: un efecto es
  una decisión, y el punto entero es que aquí no hay decisión que registrar.
- El `default_deny` visible, el `ambiguous` estructural y la regla de que
  `apply_scopes` **nunca crea** una regla: las tres se quedan como están. Son la
  parte que sí estaba bien.

---

## 6. Residual declarado

- **Los otros sitios donde la confianza se escribe a mano.** Hay ~20 constantes de
  confianza fuera de los esquemas (`bd/catalogs.py`, `bd/tables.py`,
  `bd/relations.py`, `bd/indexes.py`, `bd/constraints.py`, `api/rule_mapping.py`,
  `ef/interpret.py`, `ef/infer.py`). Este diseño impone el invariante **solo en la
  matriz de autorización**, donde la confianza es portante. En el resto la
  confianza es hoy decorativa, y convertirla en portante en seis agentes a la vez
  es otro bloque, con su propio número. Enumerado para que la decisión exista.
- **`bd.tables.columns`: 11 de 12 suben** (mitad 3 del informe). Es el segundo
  candidato natural, y ahí la confianza sí se lee (alimenta `type_ambiguous` y las
  preguntas al DBA). Con dueño escrito, sin bloque.
- **El techo del 39% no es una cuenta de defectos** y no debe citarse como tal
  mientras las bases no se declaren. La cifra que se puede defender es 8 de 8.

---

## 7. Bloques (tests mockeados, commit+push por bloque; ninguno autorizado)

- **AUT0 — el auditor y el candado.** `medir_propagacion_de_confianza.py` (hecho) +
  candado AST de la capa 3 + los tests **vistos fallar** contra el código actual.
  Sin tocar producción: es la red antes del trapecio.
- **AUT1 — la confianza calculada.** `confianza_derivada` + `_rule()` sin
  parámetro + `basis_confidence`/`basis_evidenced` en la fila + los dos
  `model_validator`. Contrato → v1.1.0.
- **AUT2 — la celda sin evidencia no concede.** `AuthBasis.UNEVIDENCED_CRUD`,
  `AuthScope.UNSCOPED`, la pregunta agrupada con candidatos (AUT-D4), el acople de
  AUT-D5, la ampliación pii de AUT-D6 con su fixture. Aquí está todo el riesgo:
  toca lo que autoriza.
- **AUT3 — la evidencia en el EF** (AUT-D7 camino (c)) + `actor_refs` a ids.
  Es el único que hace que el agente **acierte**, y el único que gasta.
- **AUT4 — el par antes/después.** Se re-corre CMP0 (0,00 USD, dobles) y se
  comprueba: **0 filas `allow` sin evidencia**, `Q-002` nombrando 9 operaciones y 4
  actores, semáforo rojo con el mismo motivo de siempre. La corrida **con modelo
  real se autoriza aparte**.

---

## 8. Cómo se verá que funcionó

Mismo instrumento, misma cadena, tres líneas del informe:

```
  conceden acceso (allow) ........ 0        (hoy 8)
  ...sin evidencia en su base .... 0        (hoy 8)
  agrupada por clase de vacío .... 2        (hoy 2, y hoy miente)
```

Y tras **AUT3**, con la matriz CRUD extraída del documento, esas ocho filas vuelven
a existir — pero repartidas entre cuatro actores y con una cita verbatim detrás de
cada una.
