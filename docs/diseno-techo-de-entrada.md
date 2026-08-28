# Punto 3 — El techo de entrada: un chunk sin cota es dos fallos, no uno

> **Estado: DISEÑADO, SIN IMPLEMENTAR.** Ningún bloque autorizado (REGLA R2).
> Instrumento: `backend/scripts/medir_los_cuatro_puntos.py` §3 y §4 (0,00 USD).
> Contexto: `diseno-control-de-gasto.md` §3.ter.4 y §3.ter.6.

---

## 0. El encargo

§3.ter.4 midió que **por encima de 11,1 KB de texto plano la dimensión mayor de
`EXTRACT` no cabe en `CLAUDE_MAX_TOKENS` = 8 192 y se trunca**: cae en cuarentena
con su observación —ruidoso, no silencioso— pero el EF **pierde esa dimensión
entera**. §3.ter.5 anotó de paso que **el chunker no tiene tope de tamaño**.

El encargo pregunta dos cosas:

1. **¿El chunker sin tope es parte del mismo problema o uno aparte?**
2. **¿Cuál es el techo de producto DESPUÉS del arreglo del punto 1?**

Las respuestas cortas: **es el mismo problema —de hecho es *el* problema, y el
techo de 11,1 KB es su síntoma—**, y **el techo después del punto 1 no se movió:
sigue en 11,1 KB para el EF y en 1,1 KB para la cadena**, porque el punto 1 tocó
la entrada y estos dos techos son de salida y de presupuesto.

---

## 1. Los tres síntomas, medidos

Con el parser y el chunker reales, sin LLM (`_troceo_real` del instrumento):

| documento | forma | tokens | `single_shot` | chunks | mayor |
|---:|:---|---:|:---:|---:|---:|
| 5 074 B | plano | 1 270 | sí | 1 | 1 270 |
| 10 321 B | plano | 2 581 | sí | 1 | 2 581 |
| **11 071 B** | plano | **2 769** | sí | 1 | **2 769** ⇐ aquí empieza a truncar |
| 12 070 B | plano | 3 019 | sí | 1 | 3 019 |
| 16 869 B | plano | 4 218 | **no** | **1** | **4 218** |
| 20 508 B | plano | 5 128 | no | **1** | **5 128** |
| 40 054 B | plano | 10 015 | no | **1** | **10 015** |
| 16 547 B | estructurado | 4 103 | no | **14** | **322** |
| 20 664 B | estructurado | 5 123 | no | **18** | **322** |
| 40 175 B | estructurado | 9 960 | no | **34** | **322** |

Tres patologías, y **ninguna fila con un chunk de tamaño razonable**:

1. **Trunca.** Por encima de 2 769 tokens (~11,1 KB) la salida de la dimensión
   mayor pasa de 8 192. Pasa en **las dos formas**, porque por debajo de 16,4 KB
   ambas son `single_shot`.
2. **No acota.** Un texto plano de 40 KB es **un** chunk de 10 015 tokens. No hay
   tamaño de documento que lo parta: el texto plano no tiene títulos y el corte es
   por título.
3. **Se pulveriza.** Un documento estructurado por encima de 16,4 KB se parte en
   chunks de **322 tokens**, y cada llamada de `EXTRACT` lleva **794 tokens de
   instrucciones para 322 de documento: el 71% del mensaje es preámbulo.** A 20 KB
   son **108 llamadas** donde caben 18.

---

## 2. La respuesta a la primera pregunta: es un solo problema

Las tres son **el mismo invariante que falta: nada acota un chunk, ni por arriba
ni por abajo.**

El chunker tiene exactamente una decisión de tamaño, `SINGLE_SHOT_TOKEN_THRESHOLD`
= 4 096, y esa decisión **no es un presupuesto: es un desvío**. Elige *por qué
camino* se trocea, no *de qué tamaño sale* lo troceado. Después de elegir el
camino, lo que acota un chunk no es un número nuestro: es **la densidad de títulos
del documento del cliente**.

Y hay un dato que lo remata:

> **El umbral está 48% por encima del punto en que la salida trunca.**
> `SINGLE_SHOT_TOKEN_THRESHOLD` = 4 096 promete «esto cabe en una pasada» para
> documentos cuya extracción **no cabe en una respuesta** (2 769). Entre 11,1 KB y
> 16,4 KB el chunker declara `single_shot` y `EXTRACT` trunca — el sistema afirma
> que cabe justo donde no cabe.

De ahí que el techo de 11,1 KB **no sea una propiedad de `EXTRACT`**. `EXTRACT`
hace lo correcto: pide, no cabe, repara dos veces, y cuarentena con observación.
El techo es la consecuencia observable de que quien decide cuánto documento entra
en una llamada no mira cuánto va a salir.

**Un problema, tres síntomas, un arreglo.**

---

## 3. Por qué el punto 1 no lo movió (y qué sí movió)

El punto 1 quitó una duplicación de **entrada** (el documento viajaba en `context`
y en `text`). Estos dos techos son de otra cosa:

| techo | naturaleza | antes del punto 1 | después |
|---|---|---:|---:|
| `EXTRACT` trunca | **salida** contra `CLAUDE_MAX_TOKENS` | 11,1 KB | **11,1 KB** (sin cambio) |
| el freno mata al EF (x2,4) | **presupuesto** | 26,8 KB | 28,6 KB |
| el freno mata la **cadena** (x2,4) | presupuesto, y es de **QA** | 1,1 KB | **1,1 KB** |

El punto 1 valió 0,09 USD sobre 43 y **1,8 KB de holgura en un agente que no era
el cuello de botella**. Está bien que así sea —se aprobó por techo de producto y
por llamadas que no extraían nada, no por presupuesto— pero conviene que quede
escrito: **el techo de producto de la cadena, hoy, es el mismo que antes del
punto 1.**

---

## 4. El arreglo, en dos mitades — y las dos hacen falta

Exactamente la misma forma que el punto 1, y por el mismo motivo: una mitad sin la
otra es una regla que alguien tiene que recordar.

### Mitad 1 — El parser tiene que producir algo partible

`TextToCIRAdapter`, en la rama sin estructura, mete **todo** el texto en **un**
`PARAGRAPH` (`text_adapter.py:36-40`). Y sin embargo `parse_blocks(text)` **ya
había encontrado los párrafos**: la rama los reúne y los tira.

```
texto plano de 3 párrafos → parse_blocks: 3 bloques → CIR: 2 elementos (section + 1 paragraph)
```

Un chunker con presupuesto **no puede partir un elemento** —las tablas no se
parten y ésa es una garantía que se conserva—, así que sobre el CIR de hoy la
mitad 2 no tendría dónde cortar. Un párrafo por `PARAGRAPH`, que es lo que hacen
las otras tres ramas de los parsers.

> **Invariante que esto restaura, igual que el punto 1:** el adaptador de texto
> plano deja de ser la excepción. Después de la mitad 1, los cuatro parsers
> producen CIRs de la misma forma, y el chunker deja de tener que saber de dónde
> vino el documento.

### Mitad 2 — El chunker tiene un presupuesto, con techo y con suelo

- **`CHUNK_MAX_TOKENS`.** Todo grupo cuyo cuerpo lo supere se parte en frontera de
  elemento. Las tablas siguen sin partirse: una tabla más grande que el
  presupuesto es **su propio chunk** y se declara.
- **`CHUNK_MIN_TOKENS`.** Grupos consecutivos se **funden** hasta llenar el
  presupuesto. Es lo que mata el caso de los 322 tokens.
- **`single_shot` deja de ser un umbral y pasa a ser un resultado**: «el
  presupuesto produjo exactamente un chunk». Un concepto donde hoy hay dos, y se
  acaba el desvío que decide por camino en vez de por tamaño.

**Cómo se elige `CHUNK_MAX_TOKENS`, y por qué no es un número inventado.** El
límite que manda es la **salida**, así que se deriva de ella:

```
CHUNK_MAX ≈ CLAUDE_MAX_TOKENS / EXPANSIÓN − margen
```

La expansión —tokens de salida de la dimensión mayor por token de chunk— está
**medida**, no supuesta: 3,05 / 2,95 / 2,94 / 3,20 en los cuatro puntos de la
tabla de `medir_escala_por_tamano.py` §2. Con 3,0: 8 192 / 3,0 = 2 730.

**Propuesta: `CHUNK_MAX_TOKENS = 2 000`** ⇒ pico de salida ~6 000, **27% de
holgura**. Los 730 tokens que se dejan compran no vivir al borde, igual que los
seis puntos porcentuales que el punto 4 deja en `TEST_DESIGN`.

`CHUNK_MIN_TOKENS = 1 000` (la mitad): por debajo, fundir; por encima, emitir.

### La fusión y el invariante del punto 1

Fundir grupos consecutivos cruza títulos, y el punto 1 fijó que *el texto de un
elemento va al contexto **o** al cuerpo, nunca a los dos*. La regla se conserva
tal cual, solo hay que leerla con precisión: **la vincula al elemento que ABRE el
chunk.** El que abre pone su texto en el breadcrumb; los títulos intermedios de un
chunk fundido **se renderizan en el cuerpo**, que es donde tiene que estar el
título de una subsección que el modelo va a leer entera. Cero duplicación, y el
`element_id` de cada uno sigue en `element_ids` (misma mecánica que el `carried`
de hoy).

---

## 5. Lo que el arreglo cuesta y lo que compra

| documento | forma | hoy | con el punto 3 |
|---|---|---|---|
| 10 KB | plano | 1 chunk · 7 llam · **0,557 USD** · pico 7 749 | 2 chunks · 13 llam · **0,571 USD** · pico 3 874 |
| 10 KB | estructurado | 1 chunk · 7 llam · 0,557 USD | 2 chunks · 13 llam · 0,571 USD |
| 20 KB | plano | 1 chunk · 7 llam · 1,098 USD · **pico 15 387 ⚠ TRUNCA** | 3 chunks · 19 llam · **1,127 USD** · pico 5 129 |
| 20 KB | estructurado | **18 chunks · 109 llam · 1,343 USD** | 3 chunks · 19 llam · **1,128 USD** |

**Hay que decirlo sin adornos: sobre texto plano el punto 3 CUESTA dinero
(+2,6%).** Lo que compra no es un descuento, es un techo. Sobre documento
estructurado —que es la forma de un `.docx` de Procesos real— **ahorra un 16%** y
baja de 109 llamadas a 19.

Y compra una tercera cosa que no está en la tabla: **las dos formas convergen.**
Hoy el mismo contenido cuesta 1,098 o 1,343 según tenga títulos, y falla de dos
maneras distintas. Con presupuesto cuestan 1,127 y 1,128 y no fallan. Es la
recomendación de §3.ter.6 —«no distinguir por modo, distinguir por tamaño»—
conseguida **por construcción** en vez de por una regla que alguien aplica.

---

## 6. El residual: la densidad varía, y un techo estático no la sigue

`CHUNK_MAX = 2 000` está calibrado con la expansión de **un** documento (43,1
ítems por KB). Un documento más denso —una tabla de reglas, un anexo de
validaciones— expande más y puede truncar aun dentro del presupuesto.

**Segunda línea de defensa, y es la misma que el punto 4:** si una dimensión
trunca, **se parte ese chunk en dos y se reintenta, UNA vez**. No recursivo
(converge al costo de hoy) y sin intentar distinguir truncamiento de esquema malo,
que desde fuera no son distinguibles.

**Precondición dura, idéntica a la del punto 4 y a la que GAS1 cazó en §6.bis:** un
`BudgetExceededError` **no puede entrar por esa rama**. Si entra, una corrida al
filo del tope duplica sus llamadas justo cuando se le acaba el presupuesto.

---

## 7. El pre-flight, que el presupuesto hace posible

Con un presupuesto, **el número de chunks pasa a ser una función determinista de
los bytes**, y con él las llamadas de `EXTRACT` y la estimación. Es lo que hacía
falta para las tres consecuencias que §3.ter.6 dejó sin dueño:

1. **Un máximo para `content`.** Hoy `AnalyzeTextRequest.content` declara
   `min_length=100` y **ningún máximo**, mientras la ruta de fichero pasa por
   `MAX_UPLOAD_MB`. La puerta que un usuario recorre pegando texto es la única sin
   tope.
2. **Una estimación antes de gastar**: bytes → chunks → llamadas → USD.
3. **Que hable de LA CADENA y no del EF.** Quien pega 10 KB no está pidiendo un EF
   de 0,57 USD: está pidiendo, si sigue hasta QA, **20,9 USD estimados** (§3.quater).
   Hoy no hay forma de que lo sepa antes de que un job muera.

Fuera del alcance de este punto **el (2) y el (3)**, que son producto y no
recorte; **dentro, el (1)**, porque es una línea y porque sin ella el presupuesto
del chunker acota los chunks pero no la factura.

---

## 8. El techo de producto, antes y después

**Bytes máximos antes de que el freno del job mate la corrida** (tope 5,00 USD ⇒
3,7314 utilizables), y aparte el techo que no es de dinero:

| agente | hoy (punto 1 dentro) x2,4 | con los 4 puntos + el 5.º x2,4 |
|---|---:|---:|
| EF | 29 112 B | 28 274 B |
| Scrum | 3 675 B | 7 710 B |
| **QA ⇐ el que manda** | **1 082 B** | **2 012 B** |

| techo | hoy | con el punto 3 |
|---|---|---|
| `EXTRACT` trunca (salida) | **11,1 KB** | **desaparece** — chunk acotado a 2 000 tok ⇒ pico ~6 000 (27% de holgura) |

**Las tres conclusiones, y la tercera es la que importa:**

1. **El punto 3 quita el techo estructural del EF.** Por encima de 11,1 KB el
   sistema deja de devolver un EF al que le falta una dimensión. Eso es lo que se
   compra, y no se compra con ningún otro punto.
2. **El punto 3 no mueve el techo de la cadena** (de hecho lo baja 838 B en el EF,
   por las llamadas de más). Nunca iba a moverlo: el EF aguanta 28 KB y el que
   manda es QA a 1,1.
3. **Ni con los cuatro puntos ni con el quinto pasa un documento de 10 KB.** El
   techo de la cadena va de 1,1 a 2,0 KB. **`LLM_JOB_CAP_USD` = 5 está calibrado
   para el documento de juguete**, y ningún recorte de prompt lo arregla: un
   requerimiento de 10 KB cuesta 28–36 USD reales con todo aplicado. O se sube el
   tope a conciencia —GAS-D11 existe justamente para eso, y su mensaje dice cuánto
   pedía la llamada que lo cruzó— o el costo marginal se va a cero con el
   proveedor local, que es de lo que trata §5.6.

---

## 9. Plan de implementación por bloques

Tests mockeados, commit + push por bloque, REGLA R2 entre bloques.

- **TE0 — La mitad 1.** Un `PARAGRAPH` por párrafo en la rama sin estructura de
  `TextToCIRAdapter`. Candado: el CIR de texto plano tiene la misma forma que el
  de los otros tres parsers. **Se ve fallar** contra el código de hoy. Sin efecto
  en el chunking todavía (todos los párrafos caen en el mismo grupo), que es
  exactamente la prueba de que la mitad 2 hace falta.
- **TE1 — La mitad 2: el presupuesto.** `CHUNK_MAX_TOKENS` / `CHUNK_MIN_TOKENS`,
  el corte por frontera de elemento, la fusión con títulos intermedios al cuerpo,
  `single_shot` como resultado. Candados: ningún chunk por encima del techo;
  ningún chunk por debajo del suelo salvo el último; los `element_ids` **particionan**
  el CIR (ni se pierden ni se duplican); una tabla nunca se parte.
- **TE2 — El reintento partiendo** (§6), con el candado de que un
  `BudgetExceededError` no entra por ahí.
- **TE3 — El máximo de `content`** (§7.1).
- **TE4 — La corrida real.** El par antes/después sobre el documento de 1,76 KB
  que sigue en disco, que es además el A/B que OLL-D5 reclama. **Se autoriza
  aparte.**

**No entra:** el pre-flight y su aviso al usuario (§7.2 y §7.3) — es producto, y
se decide con la cifra de §3.quater delante.
