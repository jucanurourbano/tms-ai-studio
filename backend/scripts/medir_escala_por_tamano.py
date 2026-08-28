"""Mide cómo escala la cadena con el TAMAÑO del documento de entrada. 0,00 USD.

`medir_linea_base.py` fija el «antes» de **un** requerimiento. Este script
responde a otra pregunta: **ese requerimiento era de juguete**. El documento que
lo originó tiene 1 764 bytes y es un *prompt* escrito a mano; un documento de
Procesos de verdad trae 10–20 KB. La pregunta que hay que contestar antes de
diseñar cualquier recorte es si los 25–30 USD/mes aguantan el segundo caso.

Lo que este script mide de verdad, ejecutando nuestro propio código:

* **La cadena real, de punta a punta** (§1): el documento de 1 764 bytes que
  sigue en disco → el EF real que Claude produjo → el plan Scrum real de 31
  historias y 110 criterios. Son los MULTIPLICADORES medidos, no supuestos: 62
  criterios por KB de documento no es una estimación, es lo que pasó.
* **El EF, exacto, a cada tamaño** (§2): se corre el pipeline REAL del EF sobre
  documentos sintéticos de N bytes con un doble del LLM **calibrado** contra el
  artefacto real (misma densidad de ítems, mismos textos). Sale el número de
  *chunks*, las llamadas de `EXTRACT`, la entrada de `CRITIQUE` y el total.
* **El resto de la cadena** (§3): proyectado desde costes por unidad medidos, con
  el DRIVER de cada nodo escrito al lado. Los nodos cuadráticos se marcan.

Lo que NO mide, y por eso se declara: el `usage` real (§3.bis del diseño) y la
densidad de extracción de un documento LARGO. Lo segundo se modela **lineal**,
que es la hipótesis pesimista: un documento largo repite contexto y el `_merge`
de `consolidate` deduplica, así que la extracción real es probablemente
sublineal. Se imprime también el escenario al 50% de densidad para acotarlo.

Uso (desde backend/, con el venv y Postgres arriba)::

    .venv/bin/python scripts/medir_escala_por_tamano.py

Ver ``docs/diseno-control-de-gasto.md`` §3.ter.
"""

import asyncio
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.agents.scrum.common import glossary_with_context  # noqa: E402
from ai.agents.scrum.criteria import build_criteria_user  # noqa: E402
from ai.agents.scrum.epics import build_epics_user  # noqa: E402
from ai.agents.scrum.estimate import build_estimate_user  # noqa: E402
from ai.agents.scrum.prioritize import build_prioritize_user  # noqa: E402
from ai.agents.scrum.prompts import build_system as scrum_system  # noqa: E402
from ai.agents.scrum.stories import build_stories_user  # noqa: E402
from ai.orchestrator.checkpointer import build_memory_checkpointer  # noqa: E402
from ai.orchestrator.graph import build_ef_graph  # noqa: E402
from ai.tools.chunker import estimate_tokens  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.dependencies.database import session_scope  # noqa: E402

#: La cadena real que se usa de patrón. El EF salió del documento que sigue en
#: disco y el plan salió de ese EF: los tres eslabones son corridas reales
#: contra Claude, así que los multiplicadores de §1 son medidos.
EF_REAL = "01KY2V9HKCF0BSSPE7JQDBWX3V"
PLAN_REAL = "01KY33JDAV21N40N326TCR3JSS"

#: Tamaños que se miden. El primero es el documento real; los otros dos son el
#: rango que el usuario declara para un documento de Procesos de verdad.
TAMANOS = (1_764, 10_240, 20_480)

REGISTRO: list[dict] = []


# ---------------------------------------------------------------------------
# El espía: la misma costura por la que el libro mayor atribuye la fila.
# ---------------------------------------------------------------------------
class Espia:
    """Envuelve el doble del LLM y anota cada llamada con su nodo."""

    def __init__(self, inner, stage: str | None = None) -> None:
        self._inner, self._stage = inner, stage

    def for_stage(self, stage: str) -> "Espia":
        return Espia(self._inner, stage)

    async def complete_json(self, *, system: str, user: str) -> str:
        salida = await self._inner.complete_json(system=system, user=user)
        REGISTRO.append(
            {
                "stage": self._stage or "(sin etiqueta)",
                "in": estimate_tokens(system + user),
                "out": estimate_tokens(salida),
            }
        )
        return salida


def _usd(entrada: int, salida: int = 0) -> float:
    return (
        entrada * settings.CLAUDE_PRICE_INPUT_PER_MTOK
        + salida * settings.CLAUDE_PRICE_OUTPUT_PER_MTOK
    ) / 1e6


# ---------------------------------------------------------------------------
# §1 — la cadena real, leída de la base
# ---------------------------------------------------------------------------
async def _cargar_reales() -> tuple[dict, dict, bytes]:
    from app.repositories.agent_job_repository import AgentJobRepository

    async with session_scope() as session:
        repo = AgentJobRepository(session)
        ef = (await repo.get_artifact(EF_REAL)).data
        plan = (await repo.get_artifact(PLAN_REAL)).data
    ruta = os.path.join(settings.STORAGE_DIR, ef["source"]["hash"] + ".txt")
    with open(ruta, "rb") as fh:
        fuente = fh.read()
    return ef, plan, fuente


def _ratios(ef: dict, plan: dict, fuente: bytes) -> dict:
    kb = len(fuente) / 1000
    rf = len(ef["requirements"]["functional"])
    historias = len(plan["stories"])
    criterios = sum(len(h.get("acceptance_criteria") or []) for h in plan["stories"])
    items_ef = sum(len(v) for v in ef["requirements"].values()) + sum(
        len(ef[k])
        for k in (
            "actors",
            "modules",
            "menus",
            "processes",
            "business_rules",
            "validations",
            "fields",
            "entities",
            "relationships",
            "crud",
            "apis",
        )
    )
    return {
        "bytes": len(fuente),
        "items_ef_por_kb": items_ef / kb,
        "rf_por_kb": rf / kb,
        "historias_por_rf": historias / rf,
        "criterios_por_historia": criterios / historias,
        "criterios_por_kb": criterios / kb,
        "rf": rf,
        "historias": historias,
        "criterios": criterios,
        "epicas": len(plan["epics"]),
    }


# ---------------------------------------------------------------------------
# §2 — el EF, exacto, a cada tamaño
# ---------------------------------------------------------------------------
#: Marcador de cada dimensión en su `system`, y de qué lista del artefacto real
#: se toman los ítems que el doble devuelve. Es lo que hace al doble
#: **calibrado** y no inventado: los textos son los que Claude escribió.
DIMENSIONES = {
    "REQUISITOS": (
        "requirements",
        {
            "business": "requirements.business",
            "functional": "requirements.functional",
            "non_functional": "requirements.non_functional",
        },
    ),
    "ACTORES": ("actors", {"actors": "actors"}),
    "MÓDULOS": ("modules_menus", {"modules": "modules", "menus": "menus"}),
    "PROCESOS": ("processes", {"processes": "processes"}),
    "REGLAS DE NEGOCIO": (
        "rules_validations",
        {"business_rules": "business_rules", "validations": "validations"},
    ),
    "CAMPOS": ("fields", {"fields": "fields"}),
}

#: Claves que el esquema de extracción NO acepta: el artefacto ya lleva el `id`
#: puesto por `_merge`, y devolverlo desde el "LLM" sería devolver algo que el
#: modelo real nunca escribe.
FUERA_DEL_ESQUEMA = ("id", "linked_field_ref", "entity_id")


def _rebanar(ef: dict, ruta: str) -> list[dict]:
    nodo: object = ef
    for parte in ruta.split("."):
        nodo = nodo[parte]  # type: ignore[index]
    return [
        {k: v for k, v in item.items() if k not in FUERA_DEL_ESQUEMA}
        for item in nodo  # type: ignore[union-attr]
    ]


class LlmCalibrado:
    """Doble del LLM del EF con la DENSIDAD medida en el artefacto real.

    No inventa contenido: cicla los ítems que Claude produjo de verdad y les
    pone un sufijo por llamada para que `consolidate._merge` no los colapse.

    El presupuesto de ítems se calcula sobre los **bytes del documento**
    repartidos entre sus *chunks*, y NO sobre el tamaño del mensaje que llega.
    La diferencia importa: §2.bis mide que un texto plano por encima del umbral
    se envía DOS VECES en cada llamada, y un doble que contara ítems por bytes
    recibidos duplicaría también la extracción — atribuyéndole al modelo un
    efecto que es del chunker.
    """

    def __init__(self, ef: dict, items_por_llamada: float) -> None:
        self._ef = ef
        self._items = items_por_llamada
        self._n = 0

    async def complete_json(self, *, system: str, user: str) -> str:
        self._n += 1
        marca = f"v{self._n}"
        for clave, (_dim, listas) in DIMENSIONES.items():
            if clave not in system:
                continue
            salida: dict[str, list] = {}
            for campo, ruta in listas.items():
                plantillas = _rebanar(self._ef, ruta)
                if not plantillas:
                    salida[campo] = []
                    continue
                # Proporción real de esta lista dentro del artefacto (92 ítems),
                # aplicada al presupuesto de este fragmento.
                cuantos = max(1, round(self._items * len(plantillas) / 92))
                items = []
                for i in range(cuantos):
                    item = dict(plantillas[i % len(plantillas)])
                    for campo_texto in ("text", "name", "statement", "rule"):
                        if campo_texto in item:
                            item[campo_texto] = f"{item[campo_texto]} [{marca}-{i}]"
                    items.append(item)
                salida[campo] = items
            return json.dumps(salida, ensure_ascii=False)
        # CRITIQUE: no aporta volumen de entrada, solo consume.
        return json.dumps(
            {"ambiguities": [], "missing_info": [], "inconsistencies": []}
        )


def _documento(tamano: int, fuente: bytes, con_titulos: bool) -> str:
    """Documento sintético de ~``tamano`` bytes, con la prosa real del original.

    Dos formas, porque **chunkean distinto y esa es media respuesta**: el texto
    plano (el *prompt* escrito a mano) no tiene títulos y produce UN chunk sea
    cual sea su tamaño; el documento estructurado corta por título.
    """
    parrafos = [p for p in fuente.decode().split("\n\n") if p.strip()]
    partes: list[str] = []
    largo = 0
    i = 0
    while largo < tamano:
        if con_titulos and i % 4 == 0:
            titulo = f"\n## Sección {i // 4 + 1}\n"
            partes.append(titulo)
            largo += len(titulo)
        p = parrafos[i % len(parrafos)]
        partes.append(p)
        largo += len(p) + 2
        i += 1
    return "\n\n".join(partes)


def _chunks_de(texto: str) -> int:
    """Cuántos chunks hará el chunker REAL con este texto. Sin LLM y sin grafo."""
    from ai.tools.chunker import chunk_cir
    from ai.tools.parsers import TextToCIRAdapter

    cir = TextToCIRAdapter.adapt(texto, title="escala.txt")
    return chunk_cir(
        cir, token_threshold=settings.SINGLE_SHOT_TOKEN_THRESHOLD
    ).chunks_total


async def _medir_ef(texto: str, ef_real: dict, densidad: float, factor: float) -> dict:
    """Corre el pipeline REAL del EF. Devuelve lo medido y lo que el agente diría."""
    REGISTRO.clear()
    recogido: dict = {}

    async def persist(job_id, artifact, status, metrics):  # noqa: ANN001
        recogido["metrics"] = metrics
        recogido["artifact"] = artifact

    presupuesto = densidad * factor * (len(texto) / 1000) / max(1, _chunks_de(texto))
    doble = LlmCalibrado(ef_real, presupuesto)
    grafo = build_ef_graph(build_memory_checkpointer())
    await grafo.ainvoke(
        {
            "job_id": "ESCALA",
            "filename": "escala.txt",
            "text": texto,
            "status": "PENDING",
        },
        config={
            "configurable": {
                "thread_id": f"ESCALA-{len(texto)}-{factor}",
                "llm": Espia(doble),
                # El grafo del EF lee el doble de CRITIQUE por su propia clave.
                "critique_llm": Espia(doble).for_stage("CRITIQUE"),
                "persist": persist,
            }
        },
    )
    por_nodo: dict[str, dict] = defaultdict(lambda: {"n": 0, "in": 0, "out": 0})
    for fila in REGISTRO:
        d = por_nodo[fila["stage"]]
        d["n"] += 1
        d["in"] += fila["in"]
        d["out"] += fila["out"]
    salida_max = max((f["out"] for f in REGISTRO), default=0)
    return {
        "por_nodo": dict(por_nodo),
        "metrics": recogido.get("metrics", {}),
        "artifact": recogido.get("artifact", {}),
        "salida_max_por_llamada": salida_max,
    }


# ---------------------------------------------------------------------------
# §3 — el resto de la cadena, por coste unitario medido
# ---------------------------------------------------------------------------
def _scrum_por_tamano(ef: dict, plan: dict, escala: float) -> list[dict]:
    """Mide los seis nodos de Scrum con el EF y el plan REALES, escalados.

    Los prompts se construyen con las funciones de producción, así que el tamaño
    por llamada es exacto. Lo que se escala es el NÚMERO de ítems, y en los dos
    nodos cuadráticos también el contexto que cada llamada arrastra.
    """
    glosario = glossary_with_context(None)
    rf = ef["requirements"]["functional"]
    historias = plan["stories"]
    epicas = plan["epics"]

    def x(lista: list, k: float) -> list:
        """Réplica de una lista real a ``k`` veces su tamaño (ids distintos)."""
        n = max(1, round(len(lista) * k))
        return [
            dict(lista[i % len(lista)], id=f"{lista[i % len(lista)]['id']}-{i}")
            for i in range(n)
        ]

    ef_esc = dict(ef)
    ef_esc["requirements"] = dict(ef["requirements"], functional=x(rf, escala))
    for clave in ("business_rules", "validations", "processes", "actors", "fields"):
        ef_esc[clave] = x(ef[clave], escala)
    rf_esc = ef_esc["requirements"]["functional"]
    hist_esc = x(historias, escala)

    filas = []
    for nodo, plantilla, n, build in (
        (
            "EPICS",
            "epics.md",
            1,
            lambda: build_epics_user(ef_esc["modules"], ef_esc["processes"]),
        ),
        (
            "STORIES",
            "stories.md",
            len(rf_esc),
            lambda: [build_stories_user(r, ef_esc, epicas) for r in rf_esc],
        ),
        (
            "CRITERIA",
            "criteria.md",
            len(hist_esc),
            lambda: [build_criteria_user(h, ef_esc) for h in hist_esc],
        ),
        (
            "ESTIMATE",
            "estimate.md",
            len(hist_esc),
            lambda: [build_estimate_user(h) for h in hist_esc],
        ),
        (
            "PRIORITIZE",
            "prioritize.md",
            len(hist_esc),
            lambda: [build_prioritize_user(h) for h in hist_esc],
        ),
    ):
        sys_tok = estimate_tokens(scrum_system(plantilla, glosario))
        payloads = build()
        if isinstance(payloads, str):
            payloads = [payloads]
        entrada = n * sys_tok + sum(estimate_tokens(p) for p in payloads)
        filas.append({"nodo": nodo, "n": n, "in": entrada})
    return filas


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------
def _cabecera(txt: str) -> None:
    print(f"\n{'=' * 78}\n{txt}\n{'=' * 78}")


async def main() -> None:
    ef, plan, fuente = await _cargar_reales()
    r = _ratios(ef, plan, fuente)

    _cabecera("§1 — LA CADENA REAL, MEDIDA (documento → EF → plan, todo Claude real)")
    print(f"Documento fuente: {r['bytes']:,} bytes ({r['bytes']/1000:.2f} KB)")
    print(
        f"EF real       : {r['rf']} requisitos funcionales · "
        f"{r['items_ef_por_kb']:.1f} ítems por KB de documento"
    )
    print(
        f"Plan real     : {r['epicas']} épicas · {r['historias']} historias · "
        f"{r['criterios']} criterios"
    )
    print("Multiplicadores MEDIDOS (no supuestos):")
    print(f"  {r['rf_por_kb']:6.2f} requisitos funcionales por KB de documento")
    print(f"  {r['historias_por_rf']:6.2f} historias por requisito funcional")
    print(f"  {r['criterios_por_historia']:6.2f} criterios por historia")
    print(f"  {r['criterios_por_kb']:6.2f} CRITERIOS POR KB DE DOCUMENTO")

    densidad = r["items_ef_por_kb"]

    for factor, etiqueta in (
        (1.0, "densidad lineal (pesimista)"),
        (0.5, "densidad al 50% (sublineal)"),
    ):
        _cabecera(f"§2 — EL AGENTE EF, MEDIDO A CADA TAMAÑO — {etiqueta}")
        print(
            f"{'tamaño':>9} {'forma':<13} {'chunks':>6} {'EXTRACT':>16} "
            f"{'CRITIQUE in':>12} {'total in':>10} {'USD est.':>9} "
            f"{'metrics':>8} {'out/llam':>9}"
        )
        for tamano in TAMANOS:
            for con_titulos in (False, True):
                texto = _documento(tamano, fuente, con_titulos)
                res = await _medir_ef(texto, ef, densidad, factor)
                pn = res["por_nodo"]
                ex = pn.get("EXTRACT", {"n": 0, "in": 0, "out": 0})
                cr = pn.get("CRITIQUE", {"n": 0, "in": 0, "out": 0})
                total_in = sum(d["in"] for d in pn.values())
                total_out = sum(d["out"] for d in pn.values())
                m = res["metrics"]
                forma = "estructurado" if con_titulos else "plano"
                pico = res["salida_max_por_llamada"]
                aviso = "!" if pico > settings.CLAUDE_MAX_TOKENS else " "
                print(
                    f"{len(texto):>9,} {forma:<13} "
                    f"{m.get('chunks_total', 0):>6} "
                    f"{ex['n']:>4} llam {ex['in']:>8,} "
                    f"{cr['in']:>12,} {total_in:>10,} "
                    f"{_usd(total_in, total_out):>9.4f} "
                    f"{float(m.get('cost') or 0):>8.4f} {pico:>8,}{aviso}"
                )
        if factor == 1.0:
            print()
            print("`metrics` es lo que el AGENTE apuntaría en su artefacto, y le falta")
            print("CRITIQUE: `node_critique` no devuelve métricas, así que la llamada")
            print("más grande del EF nunca entró en `metrics.tokens`. Desde GAS1 el")
            print("libro mayor sí la ve, porque mide en el CLIENTE (GAS-D1).")
            print()
            print(
                f"`out/llam` con `!` supera CLAUDE_MAX_TOKENS "
                f"({settings.CLAUDE_MAX_TOKENS}): esa llamada NO se frena, se"
            )
            print("TRUNCA. Es el mismo límite que hace inalcanzable el «110 → 1» de")
            print("QA, y el que ya obligó a subir el default de 4096 a 8192.")

    _cabecera("§2.bis — EL DOCUMENTO SE ENVIABA DOS VECES (ARREGLADO)")
    print("Salió de la tabla de arriba: entre 16,3 KB y 16,9 KB el `EXTRACT` de un")
    print("texto plano DUPLICABA su entrada con un 3% más de documento. No era una")
    print("no-linealidad, era una duplicación, y se comprueba sin LLM ni grafo.")
    print("La columna «se envía» valía 2.00x por encima del umbral; hoy vale 1.00x:")
    print()
    from ai.tools.chunker import chunk_cir  # noqa: E402
    from ai.tools.parsers import TextToCIRAdapter  # noqa: E402

    print(
        f"{'documento':>10} {'single_shot':>12} {'chunks':>7} {'context':>9} "
        f"{'text':>9} {'se envía':>9}"
    )
    for tamano in (3_000, 16_000, 17_000, 20_480, 40_000):
        texto = _documento(tamano, fuente, False)
        cir = TextToCIRAdapter.adapt(texto, title="escala.txt")
        res = chunk_cir(cir, token_threshold=settings.SINGLE_SHOT_TOKEN_THRESHOLD)
        c = res.chunks[0]
        veces = (len(c.context) + len(c.text)) / len(texto)
        print(
            f"{len(texto):>10,} {str(res.single_shot):>12} {res.chunks_total:>7} "
            f"{len(c.context):>9,} {len(c.text):>9,} {veces:>8.2f}x"
        )
    print()
    print("LA CAUSA: `TextToCIRAdapter` metía TODO el texto plano en un único")
    print("elemento SECTION. Por debajo del umbral el chunker toma el camino")
    print("`single_shot` y el `context` es el título; por encima toma el camino por")
    print("títulos, y ahí `_context_for(section)` devuelve el breadcrumb MÁS el texto")
    print("del elemento — que en texto plano era el documento entero. El chunk salía")
    print("con el documento en `context` y otra vez en `text`, y `build_user` manda")
    print("los dos en el MISMO mensaje.")
    print()
    print("EL ARREGLO, en dos mitades:")
    print("  1. El texto de una SECTION es un RÓTULO, nunca el cuerpo. Era el único")
    print("     `add_section` del repositorio que pasaba contenido; el cuerpo pasa a")
    print("     un PARAGRAPH. Restaura el invariante que los demás parsers cumplían.")
    print("  2. El elemento que ABRE un chunk aporta su texto al contexto O al")
    print("     cuerpo, nunca a los dos. Sin esto, (1) sería una regla que alguien")
    print("     tiene que recordar en el próximo parser.")
    print()
    print("DE PROPINA, del arreglo (2): un grupo sin cuerpo ya no gasta un chunk.")
    print("Un título seguido de su subtítulo producía un FRAGMENTO con solo el")
    print("título — seis llamadas por dimensión que no podían extraer nada. En un")
    print("documento con esa forma los chunks bajan a la mitad (25 → 12 medido).")
    print("Su `element_id` se arrastra al chunk siguiente: la provenance no cambia.")

    _cabecera("§3 — SCRUM, POR NODO Y POR TAMAÑO (prompts de producción, exactos)")
    print(
        f"{'tamaño':>9} {'nodo':<11} {'llam':>5} {'in_tok':>10} {'USD est.':>9}  driver"
    )
    DRIVERS = {
        "EPICS": "1 llamada; payload ∝ módulos+procesos",
        "STORIES": "1 por RF; payload lleva TODO el EF ⇒ CUADRÁTICO",
        "CRITERIA": "1 por historia; payload lleva TODAS las validaciones ⇒ CUADRÁTICO",
        "ESTIMATE": "1 por historia; payload solo la historia ⇒ lineal",
        "PRIORITIZE": "1 por historia; payload solo la historia ⇒ lineal",
    }
    for tamano in TAMANOS:
        escala = tamano / r["bytes"]
        filas = _scrum_por_tamano(ef, plan, escala)
        total = 0
        for fila in filas:
            total += fila["in"]
            print(
                f"{tamano:>9,} {fila['nodo']:<11} {fila['n']:>5} {fila['in']:>10,} "
                f"{_usd(fila['in']):>9.4f}  {DRIVERS[fila['nodo']]}"
            )
        print(f"{'':>9} {'— subtotal':<11} {'':>5} {total:>10,} {_usd(total):>9.4f}\n")

    _cabecera("§4 — QA, POR TAMAÑO (lineal: el payload por criterio está acotado)")
    # Coste por criterio MEDIDO en la línea base: 2,5228 USD / 220 llamadas
    # (TEST_DESIGN + EDGE_CASES) sobre 110 criterios reales.
    POR_CRITERIO_USD = 2.5228 / 110
    print(
        f"Coste por criterio medido (§3.bis.1): {POR_CRITERIO_USD:.4f} USD "
        f"(2 llamadas: TEST_DESIGN + EDGE_CASES)"
    )
    print(f"{'tamaño':>9} {'criterios':>10} {'llamadas':>9} {'USD est.':>9}")
    for tamano in TAMANOS:
        criterios = round(r["criterios_por_kb"] * tamano / 1000)
        print(
            f"{tamano:>9,} {criterios:>10,} {criterios * 2 + 1:>9,} "
            f"{criterios * POR_CRITERIO_USD:>9.4f}"
        )

    _cabecera("§5 — EL FRENO DEL JOB, POR AGENTE")
    from decimal import Decimal

    from ai.llm.budget import margen_del_job
    from ai.llm.metering import costo_maximo_de_una_llamada

    maximo = costo_maximo_de_una_llamada(
        (settings.CLAUDE_PRICE_INPUT_PER_MTOK, settings.CLAUDE_PRICE_OUTPUT_PER_MTOK)
    )
    utilizable = float(Decimal(str(settings.LLM_JOB_CAP_USD)) - margen_del_job(maximo))
    print(
        f"Tope por job {settings.LLM_JOB_CAP_USD} USD ⇒ utilizable {utilizable:.4f} USD"
    )
    print("(el tope es POR JOB, y cada agente es un job: se comparan uno a uno)")
    print(
        f"\n{'tamaño':>9} {'agente':<8} {'USD est.':>9} {'x2,4 real':>10} "
        f"{'x3,1 real':>10}  ¿frena?"
    )
    for tamano in TAMANOS:
        escala = tamano / r["bytes"]
        criterios = round(r["criterios_por_kb"] * tamano / 1000)
        scrum_in = sum(f["in"] for f in _scrum_por_tamano(ef, plan, escala))
        estimados = {
            "scrum": _usd(scrum_in),
            "qa": criterios * POR_CRITERIO_USD,
        }
        for agente, est in estimados.items():
            bajo, alto = est * 2.4, est * 3.1
            veredicto = (
                "SÍ, seguro"
                if bajo > utilizable
                else ("probable" if alto > utilizable else "no")
            )
            print(
                f"{tamano:>9,} {agente:<8} {est:>9.4f} {bajo:>10.4f} {alto:>10.4f}"
                f"  {veredicto}"
            )

    _cabecera("§6 — EL NÚMERO QUE SE PEDÍA: a qué tamaño MUERE cada agente")
    print("Bisección sobre el mismo instrumento. El tope es por job, así que el")
    print("documento máximo procesable es el del PRIMER agente que lo cruza.")
    print(f"\n{'agente':<8} {'factor':>7} {'bytes máx':>10} {'≈ KB':>6}  qué lo empuja")

    async def _ef_usd(tamano: int) -> float:
        res = await _medir_ef(_documento(tamano, fuente, False), ef, densidad, 1.0)
        pn = res["por_nodo"]
        return _usd(
            sum(d["in"] for d in pn.values()), sum(d["out"] for d in pn.values())
        )

    def _scrum_usd(tamano: int) -> float:
        return _usd(
            sum(f["in"] for f in _scrum_por_tamano(ef, plan, tamano / r["bytes"]))
        )

    def _qa_usd(tamano: int) -> float:
        return round(r["criterios_por_kb"] * tamano / 1000) * POR_CRITERIO_USD

    TECHO = 60_000

    async def _biseccion(cabe) -> int:
        """Mayor tamaño (bytes) que sigue cumpliendo ``cabe``. ``TECHO`` = saturó."""
        bajo, alto = 200, TECHO
        for _ in range(16):
            medio = (bajo + alto) // 2
            ok = cabe(medio)
            if asyncio.iscoroutine(ok):
                ok = await ok
            if ok:
                bajo = medio
            else:
                alto = medio
        return bajo

    async def _cabe(coste, factor: float, tamano: int) -> bool:
        valor = coste(tamano)
        if asyncio.iscoroutine(valor):
            valor = await valor
        return valor * factor <= utilizable

    def _kb(limite: int) -> str:
        return (
            f">{TECHO/1000:.0f} (fuera del rango medido)"
            if limite >= TECHO - 200
            else f"{limite/1000:.1f}"
        )

    for agente, coste, empuja in (
        ("ef", _ef_usd, "CRITIQUE sin techo + la salida de EXTRACT"),
        ("scrum", _scrum_usd, "STORIES y CRITERIA: el contexto va en CADA llamada"),
        ("qa", _qa_usd, "2 llamadas por criterio, y 62 criterios por KB"),
    ):
        for factor in (1.0, 2.4, 3.1):
            limite = await _biseccion(lambda t, c=coste, f=factor: _cabe(c, f, t))
            print(
                f"{agente:<8} {'x' + str(factor):>7} {limite:>10,} "
                f"{_kb(limite):>26}  {empuja if factor == 1.0 else ''}"
            )

    print()
    print("El x1,0 es el escenario IMPOSIBLEMENTE optimista (el `usage` real igual")
    print("al estimado); el x2,4-x3,1 es el rango que el mecanismo del §3 predice.")
    print()
    print("Y el techo que NO es de dinero, medido aparte: el EF no muere por el")
    print("tope, muere antes por la SALIDA. Mayor documento cuya dimensión más")
    print(
        "grande sigue cabiendo en CLAUDE_MAX_TOKENS " f"({settings.CLAUDE_MAX_TOKENS}):"
    )

    async def _cabe_la_salida(tamano: int) -> bool:
        res = await _medir_ef(_documento(tamano, fuente, False), ef, densidad, 1.0)
        return res["salida_max_por_llamada"] <= settings.CLAUDE_MAX_TOKENS

    limite = await _biseccion(_cabe_la_salida)
    print(f"  texto plano: {limite:,} bytes ({limite/1000:.1f} KB)")
    print("  Por encima, la dimensión trunca su JSON y cae en CUARENTENA con su")
    print("  observación (no es silencioso), pero el EF pierde esa dimensión")
    print("  entera. Ése es el límite real de lo que el sistema procesa hoy.")


if __name__ == "__main__":
    asyncio.run(main())
