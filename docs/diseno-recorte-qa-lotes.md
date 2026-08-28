# Diseño — El recorte del punto 2: agrupar los *map* de QA en lotes

> **Estado: DISEÑADO, SIN IMPLEMENTAR. Ningún bloque autorizado (REGLA R2).**
>
> Línea base del «antes» en `docs/diseno-control-de-gasto.md` §3.bis. Escala por
> tamaño de documento en §3.ter. Este documento contesta D1–D4 y **corrige dos
> supuestos del enunciado** con medición, no con argumento.

---

## 0. El número que se recorta

De §3.bis.1, sobre el plan real de 31 historias y **110 criterios**:

| nodo | llamadas | firmas de `system` | entrada | USD est. |
|---|---:|---:|---:|---:|
| `TEST_DESIGN` | 110 | **1** | 307 280 | 1,4298 |
| `EDGE_CASES` | 110 | **1** | 290 880 | 1,0931 |

Una sola firma de `system` por nodo significa que el mismo preámbulo viaja 110
veces. **Desperdicio medido: 466 738 tokens = 1,40 USD estimados por corrida**,
el 55% de la factura del agente.

El enunciado original decía «110 → 1». No es alcanzable: consolidar 110 criterios
en una respuesta pide ~14 700 tokens de salida estimados contra los 8 192 de
`CLAUDE_MAX_TOKENS`. El recorte es **agrupar**.

---

## D1 — El lote: cómo se agrupan y qué pasa si trunca igual

### D1.1 Se agrupan por HISTORIA, empaquetando historias enteras

Tres formas posibles: bloques arbitrarios de N criterios en el orden del mapa ·
un lote por historia · **historias enteras empaquetadas hasta un tope**.

Se elige la tercera, y conviene decir primero **por qué NO por el ahorro**. Medí
el argumento que parecía obvio —que agrupar por historia ahorra el contexto de
historia que hoy viaja una vez por criterio— y **vale 6 239 tokens = 0,037 USD en
los dos nodos**, el 1,5% del recorte. No sostiene la decisión. Los bloques
arbitrarios de 10 dan 11 lotes contra los 12 del empaquetado por historia: una
llamada de diferencia, 0,007 USD. **Económicamente las tres formas empatan.**

Se elige por lo que no se mide en dólares:

- **Un lote coherente es un lote que el modelo puede leer.** Diez criterios de la
  misma historia (o de dos) son un encargo; diez criterios de diez historias
  distintas son diez encargos en un sobre. Es la diferencia que D3 discute.
- **Una historia NUNCA se parte.** Partirla manda su contexto dos veces —el
  ahorro que acabo de declarar irrelevante, ahora en negativo— y, peor, deja al
  modelo escribiendo dos veces el «camino feliz» de la misma historia sin poder
  verlo, que es exactamente la forma del duplicado de D2.
- **El empaquetado ya existe en la casa.** Es el mismo *first-fit-decreasing* que
  `SPRINT_PLAN` usa para meter historias en un sprint por capacidad. Determinista,
  con precedente y con tests que lo ejercen.

Medido sobre el plan real (30 historias con criterios, 110 criterios, 3,67 por
historia, la mayor con **9** — o sea que ninguna historia desborda un tope de 10):

| tope | lotes por nodo | preámbulos ahorrados | ahorro `TEST_DESIGN` | ahorro `EDGE_CASES` | % del desperdicio |
|---:|---:|---:|---:|---:|---:|
| 1 (hoy) | 110 | 0 | — | — | 0% |
| 3 | 30 | 80 | 0,5309 | 0,4968 | 74% |
| **5** | **24** | **86** | **0,5707** | **0,5341** | **79%** |
| **10** | **12** | **98** | **0,6503** | **0,6086** | **90%** |
| 20 | 6 | 104 | 0,6901 | 0,6458 | 95% |

**Corrección al enunciado: con historias enteras el «110 → ~11» es «110 → 12».**
Y el tope no es el mismo para los dos nodos — ver D4.

### D1.2 Si un lote trunca igual: se parte en dos, UNA vez, y nunca en silencio

**Cómo llega el fallo.** Una salida truncada llega como JSON inválido. El loop de
reparación de `complete_structured` lo reintenta hasta `max_repairs` y, si sigue
mal, devuelve `(None, error)` y `run_structured_map` manda el ítem a **cuarentena**.
Hoy eso cuesta **un criterio**; con lotes de 10 cuesta **diez**.

Diez criterios sin casos no es un fallo silencioso —`TRACE_MATRIX` los ve como
huecos y el semáforo de cobertura `must`/`should` se pone en rojo, así que el plan
no pasa su propia puerta—, pero es una forma cara de fallar.

**La regla:** un lote cuyo loop de reparación se agota **se parte en dos y se
reintenta una sola vez**. Los cuatro porqués:

1. **Reintentar el mismo lote es tirar dinero.** Un truncamiento es determinista
   en tamaño: los mismos 10 criterios vuelven a truncar. El loop de reparación ya
   lo intentó dos veces.
2. **Partir por la mitad es lo más barato que cambia la variable que falló.**
3. **Un solo nivel, no recursivo.** La recursión converge al comportamiento de hoy
   —una llamada por criterio— y a su costo, que es justo lo que se quiere quitar.
   Si el medio lote también se agota, sus criterios van a cuarentena con una
   `Observation` que nombra el lote, sus criterios y el motivo.
4. **El reintento se cuenta.** Peor caso de una corrida de 12 lotes: 12 + 24 = 36
   llamadas, todavía 3x menos que 110.

**No se distingue truncamiento de esquema inválido, y es deliberado.**
`complete_structured` devuelve `(None, ultimo_error)` y desde fuera las dos causas
son la misma cosa. Separarlas pediría una heurística sobre el texto del error, y
una heurística que se equivoca manda un lote genuinamente malformado a una ronda
extra de llamadas inútiles. **Todo lote agotado se parte una vez.**

**Precondición dura, y es la trampa que GAS1 ya cazó una vez:** un
`BudgetExceededError` **no puede** entrar por esta puerta. Cae en la misma clase
de error que el esquema inválido, y si el partir-y-reintentar lo tratara igual,
una corrida al filo de su tope **duplicaría sus llamadas** intentando arreglar un
truncamiento que no existe. Es el mismo hallazgo de §6.bis del diseño de gasto
—«un freno no puede confundirse con un ítem en cuarentena»— reaparecido en el
sitio nuevo. Tres tests lo fijan allí; este bloque necesita el suyo.

---

## D2 — `_clave_duplicado` con `criterion_ref`: el lote NO lo resuelve

### El conteo pedido, sobre el plan real (330 casos, 0,00 USD)

| clave de identidad | grupos detectados | casos redundantes |
|---|---:|---:|
| hoy: `(criterion_ref, type, steps, test_data)` | **0** | **0** |
| sin `criterion_ref` | 8 | 212 |
| de esos 8 grupos, cuántos cruzan **historia** | **8 de 8** | |

**Qué prueba este cuadro y qué NO.** El 212 es el número **del doble**:
`QaRichLLM` fabrica los casos desde una plantilla, así que sus pasos y sus datos
se repiten entre criterios por construcción. **No es evidencia de con qué
frecuencia duplica el modelo real** y sería deshonesto presentarlo así.

Lo que sí prueba, y no depende del doble:

- **El 0 es estructural, no estadístico.** `criterion_ref` está en la clave, así
  que dos casos idénticos anclados a criterios distintos **jamás** se agrupan. El
  detector no es que no encuentre nada: es que no puede.
- **8 de 8 grupos cruzan historia**, así que ningún agrupamiento por historia los
  habría hecho visibles tampoco.

### La respuesta: el lote ayuda, no resuelve, y el orden importa

**No lo resuelve** por tres motivos, en orden de peso:

1. **Con 12 lotes siguen habiendo 12 lotes.** Los duplicados **entre** lotes
   quedan invisibles por exactamente la misma razón que hoy.
2. **Dentro de un lote, el modelo *puede* ver que está escribiendo lo mismo dos
   veces, así que probablemente escriba menos.** Pero «probablemente» es una
   esperanza a nivel de prompt, y la regla del proyecto es que las defensas viven
   en Python y no en el prompt (INV3).
3. **Y el lote empuja el riesgo en la dirección mala.** Diez criterios en una
   llamada invitan al modelo a escribir diez casos que comparten plantilla — que
   es la forma exacta de un duplicado entre criterios. Si el detector no los ve,
   **el agrupamiento podría aumentarlos mientras el informe sigue diciendo 0**.

Ese tercer punto **ordena los dos cambios**: el arreglo del detector entra
**antes o con** el agrupamiento, nunca después. Si no, el antes/después del
propio bloque no puede distinguir «el lote produjo menos casos porque fue más
listo» de «produjo los mismos y nadie se enteró».

### Pero el arreglo NO es quitar `criterion_ref` a secas

La clave de hoy es `(criterion_ref, type, steps, test_data)`. Falta algo:
**`expected_result`**. Si se quita `criterion_ref` y se deja el resto, dos casos
con los mismos pasos y los mismos datos pero **resultado esperado distinto** se
reportan como duplicados — y eso no es un duplicado, es la forma más común de un
**par de borde**.

**Propuesta:** la identidad de un caso es *qué hace* **y** *qué debe producir*:

```
(type, steps, test_data, expected_result)      # sale criterion_ref, entra expected_result
```

**Y un duplicado entre criterios NO se borra.** `find_duplicates` ya solo reporta
—quien poda es `apply_case_cap`, y poda por criterio—, y así debe seguir: borrar
uno dejaría un criterio sin su caso (hueco de cobertura falso) o, peor, un caso
compartido en silencio por dos filas de la matriz de trazabilidad. Lo que un
duplicado entre criterios dice es otra cosa y más interesante: **dos criterios de
aceptación están pidiendo lo mismo**. Es un hallazgo sobre el **plan**, para el QA
lead, y su `Observation` tiene que decir eso y no «sobra un caso».

**Tamaño del cambio:** una función de cinco líneas, su `Observation` y sus tests.
No depende del agrupamiento ni al revés. Se puede cerrar solo, y debería, porque
además es lo que hace medible el bloque grande.

---

## D3 — Qué se pierde al agrupar: el trade-off honesto

**Tres pérdidas, una ganancia inesperada y una cosa que NO se toca.**

### Se pierde: atención por criterio. Sí, y no se puede medir sin gastar

Es real y hay que decirlo sin adornos. Una llamada con un criterio dedica toda su
ventana a ese criterio; una con diez la reparte. La literatura y la experiencia
dicen que la calidad cae con la posición en la lista, y que el ítem número diez
recibe menos que el primero.

**Lo que no se puede hacer es cuantificarlo con el instrumento de coste 0**: el
doble de la suite responde por plantilla y no tiene nada que degradar. Esta es la
única pregunta de las cuatro cuya respuesta **exige una corrida pagada**, y por
eso el bloque necesita una comparación cualitativa: el mismo plan, antes y
después, seguidas, y una lectura humana de una muestra de casos. Lo barato es que
el par cuesta lo que dice §3.bis.5 y ya está presupuestado.

Mitigación de diseño, no de prompt: **el tope por nodo de D4**. Cinco criterios en
`TEST_DESIGN` reparten menos que diez.

### Se pierde: la cuarentena se vuelve gruesa

Ya está en D1.2. Un criterio irreparable hoy cuesta un criterio; en un lote cuesta
el lote, mitigado a medio lote por el partir-y-reintentar. Es un empeoramiento
real del **peor caso**, aceptado a cambio de 90% del desperdicio, y visible: la
cobertura lo enseña en rojo.

### Se pierde: granularidad en el libro mayor

Hoy la fila de `TEST_DESIGN` en `by_stage` es la suma de 110 llamadas; mañana de
12. No cambia el total ni la atribución por nodo —que es lo que GAS2 construyó—,
pero sí desaparece la posibilidad de decir «el criterio AC-US-017-02 costó X». No
existía la intención de decirlo y `stage` nunca llevó el `ref`, así que la pérdida
es teórica; se anota para que nadie la descubra buscándola.

### Se GANA algo que no se buscaba: el proveedor local

Hoy `EDGE_CASES` hace 110 llamadas con `concurrency=3`: 37 tandas. Con 12 lotes son
4 tandas de llamadas más largas. Contra Claude eso es probablemente más rápido de
pared y sin más riesgo (el `timeout` de 180 s aguanta de sobra una salida de 3 000
tokens).

**Contra el modelo local de OLL es decisivo.** `max_concurrency=1` y ~10 tok/s
significan que hoy el local pagaría **110 veces** el reprocesado del preámbulo de
2 200 tokens, que a velocidad de CPU es la parte que manda. Menos llamadas y más
largas es exactamente lo que un modelo local prefiere, y `OLLAMA_TIMEOUT=1200` ya
está dimensionado para salidas largas. **El agrupamiento no compite con OLL: lo
hace viable.** Merece estar escrito porque cambia el orden de prioridad entre los
dos frentes si alguna vez chocan.

### Lo que NO se pierde, y es lo único innegociable: el ancla

`CRITERION_MAP` sigue fijando en Python qué pares (historia, criterio) existen
**antes** de gastar un token. El lote cambia cuántas entradas viajan por llamada,
**no quién decide qué entradas hay**. El cortafuegos anti-invención queda intacto,
y esa es la propiedad que cualquier recorte de este agente tiene que respetar.

Con una condición de implementación que hay que escribir en el bloque: hoy
`_case_from_extract(propuesta, entry, …)` ancla el caso a `entry`, **el único
criterio de la llamada**. Con un lote, el modelo tiene que devolver a qué criterio
pertenece cada caso, y Python tiene que **buscarlo en el lote y rechazar lo que no
esté**. Es el mismo cortafuegos, un nivel más arriba; si se olvida, el lote se
convierte en la puerta por la que el modelo reasigna casos a criterios que no le
tocaban — y eso sería un caso falso con aspecto de trazado, que es el peor error
posible de este agente.

---

## D4 — `TEST_DESIGN`: el mismo agrupamiento, distinto TOPE

`TEST_DESIGN` cuesta 1,4298 contra 1,0931 de `EDGE_CASES`, o sea que es el más
caro. **Su naturaleza no impide agruparlo. Su volumen de SALIDA acota el lote.**

Medido sobre el plan real:

| nodo | salida por llamada (est.) | lote de 10 ⇒ salida (est.) | real a x2,4–x3,1 | contra `CLAUDE_MAX_TOKENS` = 8 192 |
|---|---:|---:|---:|:---|
| `TEST_DESIGN` | 307 | 3 070 | **7 368 – 9 517** | **cruza el tope por arriba** |
| `EDGE_CASES` | 133 | 1 330 | 3 192 – 4 123 | holgado |

`TEST_DESIGN` emite hasta cuatro casos **con pasos** por criterio; `EDGE_CASES`
emite menos y más cortos. Por eso su salida por llamada es 2,3x.

**Propuesta: tope POR NODO, no global.**

| nodo | tope | llamadas | ahorro USD est. |
|---|---:|---:|---:|
| `EDGE_CASES` | **10** | 110 → **12** | 0,6086 |
| `TEST_DESIGN` | **5** | 110 → **24** | 0,5707 |
| | | **220 → 36** | **1,179 = 84% del desperdicio** |

Los seis puntos porcentuales que se dejan (0,08 USD) compran que el nodo caro no
viva al borde del truncamiento. Y el tope es **una constante, no una decisión
irreversible**: si la primera corrida real enseña en el libro mayor que la salida
de `TEST_DESIGN` va holgada, se sube a 10 y se recuperan. Al revés —empezar en 10
y descubrir el truncamiento— cuesta una corrida pagada que devuelve un plan con
huecos.

### Y una trampa de código que el bloque tiene que resolver, no descubrir

```python
# ai/agents/qa/test_design.py:237
for propuesta in (data.get("cases") or [])[:MAX_CASES_PER_CALL]:
```

`MAX_CASES_PER_CALL = 4` es hoy **por llamada**, y hoy una llamada es un criterio,
así que significa «cuatro casos por criterio». Con un lote de 5 significaría
**cuatro casos para los cinco criterios juntos**: el recorte convertiría en 4 los
20 casos esperados y la cobertura se caería sin que nada dijera por qué. Tiene que
pasar a ser **por criterio dentro del lote**. Lo mismo con `not_testable`, que hoy
es un veredicto de la llamada y pasa a serlo de cada criterio del lote.

---

## Bloques propuestos (ninguno autorizado)

| bloque | qué | por qué en ese orden |
|---|---|---|
| **LOT0** | El detector de duplicados: `criterion_ref` fuera, `expected_result` dentro, `Observation` reescrita. Tests. | D2: sin esto, el antes/después del bloque grande no se puede leer. Independiente y pequeño. |
| **LOT1** | El empaquetado determinista (historias enteras, FFD, tope por nodo) + su test. Sin tocar el grafo. | Es aritmética pura y se prueba sin LLM, como `SPRINT_PLAN`. |
| **LOT2** | `run_structured_map` acepta lotes: prompts, anclaje por criterio dentro del lote, `MAX_CASES_PER_CALL` por criterio, partir-y-reintentar con el candado del `BudgetExceededError`. | Es donde vive todo el riesgo. |
| **LOT3** | La corrida real del par antes/después, con el tope del job subido a conciencia. **Se autoriza aparte.** | Es la única que contesta D3, y la única que cuesta dinero. |

**Colisión declarada con OLL:** LOT2 y el proveedor local tocan cosas distintas y
no chocan, pero el agrupamiento **mejora** el caso del local (D3). Si hay que
elegir, LOT0+LOT1+LOT2 antes de OLL4 hace que la corrida local sea más barata y
más rápida de lo que OLL0 midió.
