"""Mide los CUATRO PUNTOS del plan de recortes, aplicados. 0,00 USD.

`medir_linea_base.py` fija el «antes» de un requerimiento; `medir_escala_por_tamano.py`
mide cómo escala la cadena con el tamaño del documento. Este script contesta la
pregunta que viene después de las dos: **cuánto cuesta un requerimiento de 10 KB y
uno de 20 KB con los cuatro puntos aplicados**, y de dónde sale cada dólar.

Los cuatro puntos:

1. **El documento se enviaba dos veces** — ARREGLADO (2026-08-28). Ya está dentro
   de la columna «hoy»: este script no lo mide, lo hereda.
2. **La cota de Scrum** (`docs/diseno-cota-scrum.md`) — diseñado, sin implementar.
3. **El techo de entrada** (`docs/diseno-techo-de-entrada.md`) — diseñado, sin
   implementar.
4. **Los lotes de QA** (`docs/diseno-recorte-qa-lotes.md`) — diseñado, sin
   implementar.

Misma disciplina que sus dos hermanos: **los prompts se construyen con las
funciones de producción**, el chunker que cuenta los *chunks* es el real, los
multiplicadores salen de la cadena real (documento → EF → plan, tres corridas de
Claude que siguen en la base) y no se toca la red ni el libro mayor. Ejecutar esto
cuesta 0,00 USD.

Tres secciones:

* **§1 — campo por campo.** Qué lleva de verdad cada llamada de `STORIES` y de
  `CRITERIA`, desglosado por clave del payload. Es la lista que el punto 2 necesita
  para decidir qué se puede quitar, y enseña que **el sujeto de la llamada es el
  0,4% del mensaje**.
* **§2 — el recall retrospectivo.** Si la cota hubiera estado puesta, ¿seguiría
  estando en el payload lo que el modelo REALMENTE citó? El ground truth es el plan
  real: no es una opinión sobre la cota, es una comprobación contra lo que pasó.
* **§3 — los cuatro puntos aplicados**, a 10 KB y a 20 KB, con el techo de producto
  antes y después.

Uso (desde backend/, con el venv y Postgres arriba)::

    .venv/bin/python scripts/medir_los_cuatro_puntos.py

Ver ``docs/diseno-control-de-gasto.md`` §3.quater.
"""

import asyncio
import json
import math
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.agents.scrum.common import glossary_with_context  # noqa: E402
from ai.agents.scrum.prompts import build_system as scrum_system  # noqa: E402
from ai.tools.chunker import chunk_cir, estimate_tokens  # noqa: E402
from ai.tools.parsers import TextToCIRAdapter  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.dependencies.database import session_scope  # noqa: E402

#: La misma cadena real que usa `medir_escala_por_tamano.py`: el documento sigue en
#: disco, el EF salió de él y el plan salió del EF. Los tres son corridas contra
#: Claude, así que los multiplicadores no son supuestos.
EF_REAL = "01KY2V9HKCF0BSSPE7JQDBWX3V"
PLAN_REAL = "01KY33JDAV21N40N326TCR3JSS"
TAMANOS = (10_240, 20_480)

# --- constantes MEDIDAS (no elegidas) --------------------------------------
#: Suma de los seis `system` de EXTRACT: lo que cuesta un chunk de más.
EF_SYS_SEIS = 4_785
#: Tokens de salida de la dimensión mayor por token de chunk. Medido en
#: `medir_escala_por_tamano.py` §2: 3,05 / 2,95 / 2,94 / 3,20 en los cuatro puntos
#: de la tabla. Es lo que convierte un tamaño de chunk en un riesgo de truncamiento.
EF_EXPANSION = 3.0
#: `CRITIQUE` y la salida del EF, medidos a 20 KB con densidad lineal. Escalan con
#: el documento, no con el troceo: el punto 3 no los toca.
EF_CRITIQUE_20K, EF_SALIDA_20K = 63_171, 53_462
#: QA, de `medir_linea_base.py` sobre el plan real de 110 criterios.
QA_SYS_TD, QA_SYS_EC = 2_212, 2_070
QA_PAY_TD, QA_PAY_EC = 307_280 / 110 - QA_SYS_TD, 290_880 / 110 - QA_SYS_EC
QA_OUT_TD, QA_OUT_EC = 33_862 / 110, 14_694 / 110
QA_CRITIQUE_IN, QA_CRITIQUE_OUT = 5_709, 49
#: Eficiencia real del empaquetado por historias enteras (FFD), no el tope: con
#: tope 10 salen 12 lotes de 110 criterios y no 11 (`diseno-recorte-qa-lotes.md`).
QA_LOTE_TD, QA_LOTE_EC = 110 / 24, 110 / 12
#: Salida por unidad, medida sobre el plan real. Es lo que acota el tope del lote.
OUT_STORIES_POR_RF = 1.94 * 104
OUT_CRITERIA_POR_HISTORIA = 307
OUT_ESTIMATE_POR_HISTORIA, OUT_PRIORITIZE_POR_HISTORIA = 40, 30
#: Topes por nodo propuestos (§6 de `diseno-cota-scrum.md`): el mayor que deja la
#: salida real (x2,4–x3,1) por debajo de `CLAUDE_MAX_TOKENS`.
TOPE_STORIES, TOPE_CRITERIA, TOPE_EST_PRI = 10, 5, 20
#: Cota de chunk propuesta (§5 de `diseno-techo-de-entrada.md`).
CHUNK_MAX = 2_000


def _usd(entrada: float, salida: float = 0) -> float:
    return (
        entrada * settings.CLAUDE_PRICE_INPUT_PER_MTOK
        + salida * settings.CLAUDE_PRICE_OUTPUT_PER_MTOK
    ) / 1e6


def _tok(obj) -> int:  # noqa: ANN001
    return estimate_tokens(json.dumps(obj, ensure_ascii=False))


def _cabecera(txt: str) -> None:
    print(f"\n{'=' * 92}\n{txt}\n{'=' * 92}")


# ---------------------------------------------------------------------------
# Carga de la cadena real
# ---------------------------------------------------------------------------
async def _cargar() -> tuple[dict, dict, bytes]:
    from app.repositories.agent_job_repository import AgentJobRepository

    async with session_scope() as session:
        repo = AgentJobRepository(session)
        ef = (await repo.get_artifact(EF_REAL)).data
        plan = (await repo.get_artifact(PLAN_REAL)).data
    ruta = os.path.join(settings.STORAGE_DIR, ef["source"]["hash"] + ".txt")
    with open(ruta, "rb") as fh:
        fuente = fh.read()
    return ef, plan, fuente


def _replicar(lista: list[dict], k: float) -> list[dict]:
    """Réplica de una lista real a ``k`` veces su tamaño, con ids distintos."""
    n = max(1, round(len(lista) * k))
    return [
        dict(lista[i % len(lista)], id=f"{lista[i % len(lista)]['id']}-{i}")
        for i in range(n)
    ]


def _escalar(ef: dict, plan: dict, k: float) -> tuple[dict, list[dict]]:
    e = dict(ef)
    e["requirements"] = dict(
        ef["requirements"], functional=_replicar(ef["requirements"]["functional"], k)
    )
    for clave in ("business_rules", "validations", "processes", "actors", "fields"):
        e[clave] = _replicar(ef[clave], k)
    return e, _replicar(plan["stories"], k)


# ---------------------------------------------------------------------------
# §1 — campo por campo
# ---------------------------------------------------------------------------
def _piezas(e: dict, hist: list[dict], epicas: list[dict]) -> dict:
    """Tamaño de cada clave del payload, con los constructores de producción."""
    glos = glossary_with_context(None)
    br = {b["id"]: b for b in e["business_rules"]}
    rf = e["requirements"]["functional"]
    d = {
        "N": len(rf),
        "H": len(hist),
        "sys_stories": estimate_tokens(scrum_system("stories.md", glos)),
        "sys_criteria": estimate_tokens(scrum_system("criteria.md", glos)),
        "sys_estimate": estimate_tokens(scrum_system("estimate.md", glos)),
        "sys_prioritize": estimate_tokens(scrum_system("prioritize.md", glos)),
        "sys_epics": estimate_tokens(scrum_system("epics.md", glos)),
        "epics": _tok(
            [
                {"id": p["id"], "title": p["title"], "source_refs": p["source_refs"]}
                for p in epicas
            ]
        ),
        "processes": _tok(
            [
                {"id": p["id"], "name": p["name"], "steps": p.get("steps")}
                for p in e["processes"]
            ]
        ),
        "business_rules": _tok(
            [{"id": b["id"], "statement": b["statement"]} for b in e["business_rules"]]
        ),
        "actors": _tok([{"id": a["id"], "name": a["name"]} for a in e["actors"]]),
        "validations": _tok(
            [
                {"id": v["id"], "rule": v["rule"], "field_ref": v.get("field_ref")}
                for v in e["validations"]
            ]
        ),
        "functional_requirement": sum(
            _tok({"id": r["id"], "text": r["text"], "priority": r.get("priority")})
            for r in rf
        ),
    }
    d["epics_in"] = d["sys_epics"] + _tok(
        {
            "modules": [
                {"id": m["id"], "name": m["name"], "description": m.get("description")}
                for m in e["modules"]
            ],
            "processes": [
                {"id": p["id"], "name": p["name"], "description": p.get("description")}
                for p in e["processes"]
            ],
        }
    )
    d["story"] = d["reglas_ancladas"] = 0
    d["sin_ancla"] = 0
    for s in hist:
        refs = s["source_refs"].get("rule_refs") or []
        d["story"] += _tok(
            {
                "id": s["id"],
                "statement": s["statement"],
                "requirement_refs": s["source_refs"].get("requirement_refs", []),
            }
        )
        if refs:
            d["reglas_ancladas"] += _tok(
                [
                    {
                        "id": r,
                        "statement": (br.get(r) or e["business_rules"][0])["statement"],
                    }
                    for r in refs
                ]
            )
        else:
            d["sin_ancla"] += 1
    d["estimate_pay"] = sum(
        _tok(
            {
                "id": s["id"],
                "statement": s["statement"],
                "acceptance_criteria": [
                    {k: c.get(k) for k in ("given", "when", "then", "text")}
                    for c in s.get("acceptance_criteria", [])
                ],
                "source_refs": s["source_refs"],
            }
        )
        for s in hist
    )
    d["prioritize_pay"] = sum(
        _tok(
            {
                "id": s["id"],
                "statement": s["statement"],
                "story_points": s.get("story_points"),
                "requirement_refs": s["source_refs"].get("requirement_refs", []),
            }
        )
        for s in hist
    )
    return d


def _seccion_campos(ef: dict, plan: dict) -> None:
    _cabecera("§1 — CAMPO POR CAMPO: qué lleva de verdad cada llamada de Scrum")
    print("Suma sobre TODAS las llamadas del nodo, con los constructores de")
    print("producción. La fila que importa es la del SUJETO de la llamada.")
    for tamano in (1_764,) + TAMANOS:
        k = tamano / 1_764
        e, hist = _escalar(ef, plan, k)
        d = _piezas(e, hist, plan["epics"])
        N, H = d["N"], d["H"]
        print(f"\n  ── {tamano / 1000:.2f} KB · {N} RF · {H} historias ──")
        for nodo, campos in (
            (
                f"STORIES ({N} llamadas)",
                [
                    (
                        "business_rules   (todas, en cada llamada)",
                        N * d["business_rules"],
                    ),
                    (
                        "(system)         (idéntico, en cada llamada)",
                        N * d["sys_stories"],
                    ),
                    ("processes        (todos, con sus steps)", N * d["processes"]),
                    ("actors           (todos)", N * d["actors"]),
                    ("epics            (todas)", N * d["epics"]),
                    ("functional_req.  ⇐ EL SUJETO", d["functional_requirement"]),
                ],
            ),
            (
                f"CRITERIA ({H} llamadas)",
                [
                    ("validations      (TODAS, siempre)", H * d["validations"]),
                    (
                        "business_rules   (ancladas + TODAS si no hay ancla)",
                        d["reglas_ancladas"] + d["sin_ancla"] * d["business_rules"],
                    ),
                    (
                        "(system)         (idéntico, en cada llamada)",
                        H * d["sys_criteria"],
                    ),
                    ("story            ⇐ EL SUJETO", d["story"]),
                ],
            ),
        ):
            total = sum(v for _, v in campos)
            print(f"    {nodo}  ·  {total:,} tok  ·  {_usd(total):.4f} USD entrada")
            for nombre, valor in campos:
                print(
                    f"      {nombre:<46} {valor:>11,} tok  "
                    f"{100 * valor / total:>5.1f}%  {_usd(valor):>8.4f} USD"
                )
        print(
            f"    historias sin `rule_refs` (reciben TODAS las reglas): "
            f"{d['sin_ancla']}/{H}"
        )


# ---------------------------------------------------------------------------
# §2 — el recall retrospectivo
# ---------------------------------------------------------------------------
def _plano(t: str) -> str:
    n = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in n if not unicodedata.combining(c)).casefold()


def _anclas(source_ref) -> set[str]:  # noqa: ANN001
    """Normaliza un ``source_ref`` libre del EF a un conjunto de anclas."""
    return set(re.findall(r"parrafo[ _]?(\d+)", _plano(source_ref or "")))


def _palabras(t: str) -> set[str]:
    return set(re.findall(r"\w{5,}", _plano(t)))


def _seccion_recall(ef: dict, plan: dict) -> None:
    _cabecera("§2 — RECALL RETROSPECTIVO: ¿la cota habría quitado algo que se usó?")
    print("Ground truth: lo que el modelo REALMENTE citó en el plan real. No mide si")
    print("la cota es buena idea; mide si habría dejado fuera de alcance una cita que")
    print("de hecho ocurrió. Es condición NECESARIA, no suficiente (§7 del diseño).")
    BR = {b["id"]: b for b in ef["business_rules"]}
    VAL = {v["id"]: v for v in ef["validations"]}
    FLD = {f["id"]: f for f in ef["fields"]}
    RF = {r["id"]: r for r in ef["requirements"]["functional"]}

    # A) STORIES: la cita historia → BR, contra los sustitutos de ancla posibles.
    tot = coloc = lex = union = 0
    transversales: dict[str, int] = {}
    for s in plan["stories"]:
        req = (s["source_refs"].get("requirement_refs") or [None])[0]
        r = RF.get(req)
        if not r:
            continue
        anc = _anclas(r.get("source_ref"))
        txt = _palabras(f"{r.get('text', '')} {r.get('evidence', '')}")
        for rid in s["source_refs"].get("rule_refs") or []:
            b = BR.get(rid)
            if not b:
                continue
            tot += 1
            c = bool(_anclas(b.get("source_ref")) & anc)
            pal = _palabras(b.get("statement", ""))
            x = bool(pal and len(pal & txt) / len(pal) >= 0.25)
            coloc += c
            lex += x
            union += c or x
            if not (c or x):
                transversales[rid] = transversales.get(rid, 0) + 1
    print(f"\n  A) STORIES — {tot} citas (historia → regla) con base en el EF")
    print(
        f"     co-localización por `source_ref` : {coloc:>3}/{tot} = {100*coloc/tot:>3.0f}% recall"
    )
    print(
        f"     solape léxico >= 25%             : {lex:>3}/{tot} = {100*lex/tot:>3.0f}% recall"
    )
    print(
        f"     unión de las dos                 : {union:>3}/{tot} = {100*union/tot:>3.0f}% recall"
    )
    print("     lo que la cota perdería, y POR QUÉ (reglas transversales):")
    for rid, n in sorted(transversales.items(), key=lambda p: -p[1]):
        print(f"       {rid} ({n} citas) — {BR[rid]['statement'][:66]}")

    # B) CRITERIA: la cita criterio → BR/VAL, contra el ancla que ya existe.
    dentro = fuera = 0
    val_dentro = val_tot = 0
    alcance = []
    sin_ancla_citas = sin_ancla_cubiertas = 0
    for s in plan["stories"]:
        rr = set(s["source_refs"].get("rule_refs") or [])
        ents = {
            e["id"]
            for e in ef["entities"]
            if len(_plano(e.get("name") or "")) >= 4
            and _plano(e["name"]) in _plano(s.get("statement", ""))
        }
        alc = {
            vid
            for vid, v in VAL.items()
            if (FLD.get(v.get("field_ref")) or {}).get("entity_ref") in ents
        }
        alcance.append(len(alc))
        req = (s["source_refs"].get("requirement_refs") or [None])[0]
        anc = _anclas((RF.get(req) or {}).get("source_ref"))
        respaldo = {rid for rid, b in BR.items() if _anclas(b.get("source_ref")) & anc}
        for c in s.get("acceptance_criteria", []):
            for ref in c.get("source_refs", []):
                if ref in BR:
                    if rr:
                        dentro += ref in rr
                        fuera += ref not in rr
                    else:
                        sin_ancla_citas += 1
                        sin_ancla_cubiertas += ref in respaldo
                elif ref in VAL:
                    val_tot += 1
                    val_dentro += ref in alc
    print(f"\n  B) CRITERIA — historias CON `rule_refs` (el ancla ya existe)")
    print(
        f"     citas a regla dentro del ancla   : {dentro:>3}/{dentro+fuera} = "
        f"{100*dentro/max(1,dentro+fuera):>3.0f}% recall  ⇐ la cota es EXACTA"
    )
    print(
        f"     citas a validación dentro del alcance por entidad: "
        f"{val_dentro}/{val_tot} = {100*val_dentro/max(1,val_tot):.0f}%"
    )
    print(
        f"     validaciones alcanzables por historia: "
        f"{sum(alcance)/len(alcance):.1f} de {len(VAL)}  ⇐ la prueba NO ejercita el filtro"
    )
    print(f"\n  C) CRITERIA — historias SIN `rule_refs` (no hay ancla que resolver)")
    print(
        f"     el respaldo por co-localización cubre: {sin_ancla_cubiertas}/"
        f"{sin_ancla_citas} = {100*sin_ancla_cubiertas/max(1,sin_ancla_citas):.0f}% "
        f" ⇐ NO se puede acotar"
    )


# ---------------------------------------------------------------------------
# §3 — los cuatro puntos aplicados
# ---------------------------------------------------------------------------
def _documento(tamano: int, fuente: bytes, con_titulos: bool) -> str:
    parrafos = [p for p in fuente.decode().split("\n\n") if p.strip()]
    partes: list[str] = []
    largo = i = 0
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


def _troceo_real(texto: str) -> tuple[int, int]:
    """Chunks y tamaño del mayor, con el chunker y el parser REALES."""
    res = chunk_cir(
        TextToCIRAdapter.adapt(texto, title="escala.txt"),
        token_threshold=settings.SINGLE_SHOT_TOKEN_THRESHOLD,
    )
    return res.chunks_total, max(c.token_estimate for c in res.chunks)


def _ef(tamano: int, cuerpo_tok: int, chunks: int) -> tuple[int, float, float]:
    """(llamadas, USD, pico de salida) del EF con ese troceo."""
    entrada = chunks * EF_SYS_SEIS + 6 * cuerpo_tok
    entrada += int(EF_CRITIQUE_20K * tamano / 20_480)
    salida = int(EF_SALIDA_20K * tamano / 20_480)
    return 6 * chunks + 1, _usd(entrada, salida), EF_EXPANSION * cuerpo_tok / chunks


def _scrum(d: dict, lote: bool) -> tuple[int, float, float, float]:
    """(llamadas, USD, pico salida STORIES, pico salida CRITERIA)."""
    N, H = d["N"], d["H"]
    ll_st = math.ceil(N / TOPE_STORIES) if lote else N
    ll_cr = math.ceil(H / TOPE_CRITERIA) if lote else H
    compartido = (
        d["sys_stories"]
        + d["epics"]
        + d["processes"]
        + d["business_rules"]
        + d["actors"]
    )
    in_st = ll_st * compartido + d["functional_requirement"]
    # CRITERIA: el ancla ya recorta las reglas de las historias que la tienen; lo
    # que el lote divide es el `system`, las validaciones y el respaldo sin ancla.
    in_cr = (
        ll_cr * (d["sys_criteria"] + d["validations"])
        + d["story"]
        + d["reglas_ancladas"]
        + math.ceil(d["sin_ancla"] / (TOPE_CRITERIA if lote else 1))
        * d["business_rules"]
    )
    in_ep = H * d["sys_estimate"] + d["estimate_pay"]
    in_pr = H * d["sys_prioritize"] + d["prioritize_pay"]
    entrada = d["epics_in"] + in_st + in_cr + in_ep + in_pr
    salida = (
        300
        + N * OUT_STORIES_POR_RF
        + H * OUT_CRITERIA_POR_HISTORIA
        + H * (OUT_ESTIMATE_POR_HISTORIA + OUT_PRIORITIZE_POR_HISTORIA)
    )
    llam = 1 + ll_st + ll_cr + 2 * H
    pico_st = (TOPE_STORIES if lote else 1) * OUT_STORIES_POR_RF
    pico_cr = (TOPE_CRITERIA if lote else 1) * OUT_CRITERIA_POR_HISTORIA
    return llam, _usd(entrada, salida), pico_st, pico_cr


def _scrum_quinto(d: dict) -> tuple[int, float]:
    """El punto 2 más el APLAZADO (ESTIMATE+PRIORITIZE en lote). Va aparte."""
    N, H = d["N"], d["H"]
    ll_st = math.ceil(N / TOPE_STORIES)
    ll_cr = math.ceil(H / TOPE_CRITERIA)
    ll_ep = math.ceil(H / TOPE_EST_PRI)
    compartido = (
        d["sys_stories"]
        + d["epics"]
        + d["processes"]
        + d["business_rules"]
        + d["actors"]
    )
    entrada = (
        d["epics_in"]
        + ll_st * compartido
        + d["functional_requirement"]
        + ll_cr * (d["sys_criteria"] + d["validations"])
        + d["story"]
        + d["reglas_ancladas"]
        + math.ceil(d["sin_ancla"] / TOPE_CRITERIA) * d["business_rules"]
        + ll_ep * (d["sys_estimate"] + d["sys_prioritize"])
        + d["estimate_pay"]
        + d["prioritize_pay"]
    )
    salida = (
        300
        + N * OUT_STORIES_POR_RF
        + H * OUT_CRITERIA_POR_HISTORIA
        + H * (OUT_ESTIMATE_POR_HISTORIA + OUT_PRIORITIZE_POR_HISTORIA)
    )
    return 1 + ll_st + ll_cr + 2 * ll_ep, _usd(entrada, salida)


def _qa(criterios: int, lote: bool) -> tuple[int, float, float]:
    td = math.ceil(criterios / QA_LOTE_TD) if lote else criterios
    ec = math.ceil(criterios / QA_LOTE_EC) if lote else criterios
    entrada = (
        td * QA_SYS_TD
        + criterios * QA_PAY_TD
        + ec * QA_SYS_EC
        + criterios * QA_PAY_EC
        + QA_CRITIQUE_IN
    )
    salida = criterios * (QA_OUT_TD + QA_OUT_EC) + QA_CRITIQUE_OUT
    return td + ec + 1, _usd(entrada, salida), (criterios / td) * QA_OUT_TD


def _seccion_cuatro_puntos(ef: dict, plan: dict, fuente: bytes, ratios: dict) -> dict:
    _cabecera("§3 — LOS CUATRO PUNTOS APLICADOS (USD estimados; el real es 2,4–3,1x)")
    utilizable = _utilizable()
    resumen: dict[int, tuple[float, float, float]] = {}
    for tamano in TAMANOS:
        k = tamano / ratios["bytes"]
        criterios = round(ratios["criterios_por_kb"] * tamano / 1000)
        e, hist = _escalar(ef, plan, k)
        d = _piezas(e, hist, plan["epics"])
        print(
            f"\n{'─' * 92}\n{tamano / 1000:.1f} KB · {d['N']} RF · {d['H']} historias"
            f" · {criterios:,} criterios\n{'─' * 92}"
        )
        print(
            f"  {'agente / variante':<38} {'llam':>6} {'USD':>8} {'x2,4':>8} "
            f"{'x3,1':>8}  nota"
        )
        filas: dict[str, float] = {}

        def linea(etiqueta: str, llam: int, u: float, nota: str = "") -> None:
            filas[etiqueta] = u
            print(
                f"  {etiqueta:<38} {llam:>6,} {u:>8.3f} {u * 2.4:>8.2f} "
                f"{u * 3.1:>8.2f}  {nota}"
            )

        for forma in ("plano", "estructurado"):
            texto = _documento(tamano, fuente, forma == "estructurado")
            chunks_hoy, _ = _troceo_real(texto)
            cuerpo = sum(
                c.token_estimate
                for c in chunk_cir(
                    TextToCIRAdapter.adapt(texto, title="escala.txt"),
                    token_threshold=settings.SINGLE_SHOT_TOKEN_THRESHOLD,
                ).chunks
            )
            for etiqueta, chunks in (
                (f"EF · hoy ({forma})", chunks_hoy),
                (
                    f"EF · + punto 3 ({forma})",
                    max(1, math.ceil(cuerpo / CHUNK_MAX)),
                ),
            ):
                llam, u, pico = _ef(tamano, cuerpo, chunks)
                linea(
                    etiqueta,
                    llam,
                    u,
                    f"{chunks} chunks · pico salida {pico:,.0f}"
                    + ("  ⚠ TRUNCA" if pico > settings.CLAUDE_MAX_TOKENS else ""),
                )
        for etiqueta, lote in (("SCRUM · hoy", False), ("SCRUM · + punto 2", True)):
            llam, u, p1, p2 = _scrum(d, lote)
            linea(etiqueta, llam, u, f"pico salida ST {p1:,.0f} · CR {p2:,.0f}")
        llam, u = _scrum_quinto(d)
        linea("SCRUM ·   + el 5.º (E/P en lote, aplazado)", llam, u)
        for etiqueta, lote in (("QA · hoy", False), ("QA · + punto 4", True)):
            llam, u, pico = _qa(criterios, lote)
            linea(etiqueta, llam, u, f"pico salida TEST_DESIGN {pico:,.0f}")

        hoy = filas["EF · hoy (plano)"] + filas["SCRUM · hoy"] + filas["QA · hoy"]
        cuatro = (
            filas["EF · + punto 3 (plano)"]
            + filas["SCRUM · + punto 2"]
            + filas["QA · + punto 4"]
        )
        cinco = (
            filas["EF · + punto 3 (plano)"]
            + filas["SCRUM ·   + el 5.º (E/P en lote, aplazado)"]
            + filas["QA · + punto 4"]
        )
        resumen[tamano] = (hoy, cuatro, cinco)
        print(
            f"\n  {'CADENA EF+Scrum+QA':<38} {'':>6} {'USD':>8} {'x2,4':>8} {'x3,1':>8}"
        )
        for etiqueta, valor in (
            ("hoy (el punto 1 ya está dentro)", hoy),
            ("con los CUATRO puntos", cuatro),
            ("+ el 5.º (Scrum E/P en lote)", cinco),
        ):
            print(
                f"  {etiqueta:<38} {'':>6} {valor:>8.2f} {valor * 2.4:>8.2f} "
                f"{valor * 3.1:>8.2f}"
            )
        print(
            f"  {'recorte':<38} {'':>6} {100 * (1 - cuatro / hoy):>7.0f}% "
            f"{'':>8} {'(con el 5.º: ' + f'{100 * (1 - cinco / hoy):.0f}%)':>18}"
        )
        print(f"\n  ¿pasa el freno del job? ({utilizable:.4f} USD utilizables, a x2,4)")
        for nombre, u in (
            ("EF", filas["EF · + punto 3 (plano)"]),
            ("Scrum", filas["SCRUM ·   + el 5.º (E/P en lote, aplazado)"]),
            ("QA", filas["QA · + punto 4"]),
        ):
            print(
                f"     {nombre:<6} {u * 2.4:>7.2f} USD  "
                f"{'PASA' if u * 2.4 <= utilizable else 'FRENA'}"
            )
    return resumen


def _utilizable() -> float:
    from decimal import Decimal

    from ai.llm.budget import margen_del_job
    from ai.llm.metering import costo_maximo_de_una_llamada

    maximo = costo_maximo_de_una_llamada(
        (settings.CLAUDE_PRICE_INPUT_PER_MTOK, settings.CLAUDE_PRICE_OUTPUT_PER_MTOK)
    )
    return float(Decimal(str(settings.LLM_JOB_CAP_USD)) - margen_del_job(maximo))


def _seccion_techo(ef: dict, plan: dict, fuente: bytes, ratios: dict) -> None:
    _cabecera("§4 — EL TECHO DE PRODUCTO, ANTES Y DESPUÉS")
    utilizable = _utilizable()

    def coste(tamano: int, todo: bool) -> dict[str, float]:
        k = tamano / ratios["bytes"]
        e, hist = _escalar(ef, plan, k)
        d = _piezas(e, hist, plan["epics"])
        texto = _documento(tamano, fuente, False)
        chunks_hoy, _ = _troceo_real(texto)
        cuerpo = sum(
            c.token_estimate
            for c in chunk_cir(
                TextToCIRAdapter.adapt(texto, title="escala.txt"),
                token_threshold=settings.SINGLE_SHOT_TOKEN_THRESHOLD,
            ).chunks
        )
        chunks = max(1, math.ceil(cuerpo / CHUNK_MAX)) if todo else chunks_hoy
        _, ef_usd, _ = _ef(tamano, cuerpo, chunks)
        if todo:
            _, sc = _scrum_quinto(d)
        else:
            _, sc, _, _ = _scrum(d, False)
        _, qa, _ = _qa(round(ratios["criterios_por_kb"] * tamano / 1000), todo)
        return {"EF": ef_usd, "Scrum": sc, "QA": qa}

    def limite(agente: str, todo: bool, factor: float) -> int:
        bajo, alto = 200, 80_000
        for _ in range(20):
            medio = (bajo + alto) // 2
            if coste(medio, todo)[agente] * factor <= utilizable:
                bajo = medio
            else:
                alto = medio
        return bajo

    print(f"Bytes máximos antes de que el freno del job mate la corrida.")
    print(f"Tope {settings.LLM_JOB_CAP_USD} USD ⇒ utilizable {utilizable:.4f} USD.\n")
    print(f"{'agente':<8} {'variante':<28} {'x2,4':>11} {'x3,1':>11}")
    for agente in ("EF", "Scrum", "QA"):
        for todo, etiqueta in (
            (False, "hoy (punto 1 dentro)"),
            (True, "con los 4 puntos + el 5.º"),
        ):
            print(
                f"{agente:<8} {etiqueta:<28} {limite(agente, todo, 2.4):>10,}B "
                f"{limite(agente, todo, 3.1):>10,}B"
                + ("   ⇐ el que manda" if agente == "QA" else "")
            )
    print(f"\nY el techo que NO es de dinero (la salida de EXTRACT contra")
    print(f"CLAUDE_MAX_TOKENS = {settings.CLAUDE_MAX_TOKENS}):")
    bajo, alto = 200, 60_000
    for _ in range(18):
        medio = (bajo + alto) // 2
        _, mayor = _troceo_real(_documento(medio, fuente, False))
        if EF_EXPANSION * mayor <= settings.CLAUDE_MAX_TOKENS:
            bajo = medio
        else:
            alto = medio
    print(f"  hoy         : {bajo:,} B ({bajo / 1000:.1f} KB) — por encima el EF")
    print(f"                pierde una dimensión entera (cuarentena, no silencio).")
    print(
        f"  con punto 3 : SIN TECHO — el chunk se acota a {CHUNK_MAX:,} tok ⇒ pico de "
        f"salida ~{EF_EXPANSION * CHUNK_MAX:,.0f} tok "
        f"({100 * (1 - EF_EXPANSION * CHUNK_MAX / settings.CLAUDE_MAX_TOKENS):.0f}% de holgura)"
    )


async def main() -> None:
    ef, plan, fuente = await _cargar()
    kb = len(fuente) / 1000
    criterios = sum(len(h.get("acceptance_criteria") or []) for h in plan["stories"])
    ratios = {"bytes": len(fuente), "criterios_por_kb": criterios / kb}
    _seccion_campos(ef, plan)
    _seccion_recall(ef, plan)
    _seccion_cuatro_puntos(ef, plan, fuente, ratios)
    _seccion_techo(ef, plan, fuente, ratios)


if __name__ == "__main__":
    asyncio.run(main())
