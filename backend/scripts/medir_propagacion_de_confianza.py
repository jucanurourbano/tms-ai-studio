"""Mide dos cosas sobre una cadena ya persistida: qué sostiene cada concesión de
acceso y dónde sube la confianza al propagarse.

Por qué existe
--------------
El punto 2 del CMP0 —la **autorización ancha**— se apoya en un número que hay que
poder volver a sacar: *cuántas* celdas de la matriz de autorización conceden
acceso apoyadas en algo que no cita evidencia. De ese número depende la FORMA del
arreglo: si casi todas las celdas se convirtieran en preguntas bloqueantes, el
Agente API pasaría a necesitar intervención humana en cada corrida, y eso también
es un fallo. Primero el número, después la forma.

Mide sobre **artefactos ya guardados**: no corre ningún agente, no llama a ningún
modelo y no escribe nada. Coste **0,00 USD**.

Las dos mitades del informe, y por qué una es exacta y la otra un techo
----------------------------------------------------------------------
1. **La matriz de autorización (exacta).** Una fila ``allow`` cita en
   ``source_refs`` exactamente aquello en lo que se apoya —la celda CRUD del EF—,
   así que "¿tiene evidencia lo que la sostiene?" se responde sin interpretar
   nada.

2. **La cadena completa (techo, no medida).** Aquí se compara la confianza de cada
   ítem con la de todo ref que resuelva, y **no todo ref es un apoyo**: hay refs
   de pertenencia y hay refs cuya dirección está invertida (``INFER`` deriva las
   entidades DE los campos, así que un campo que cita a su entidad no descansa en
   ella). Por eso la segunda cifra es un **límite superior** y se etiqueta como
   tal: sirve para decidir dónde mirar, no para afirmar cuántos defectos hay. El
   invariante que se propone en el diseño se define sobre **bases declaradas**,
   que hoy ningún nodo declara — y eso es justamente lo que el diseño arregla.

Uso (desde backend/, con el venv y Postgres arriba)::

    .venv/bin/python scripts/medir_propagacion_de_confianza.py [--job <api_job_id>]

Sin ``--job`` mide el job de API más reciente y desanda su cadena por
``input_job_id`` hasta el EF.
"""

import argparse
import asyncio
import os
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.dependencies.database import session_scope  # noqa: E402
from app.models.agent import AgentJob, AgentType  # noqa: E402
from app.repositories.agent_job_repository import AgentJobRepository  # noqa: E402

RAYA = "=" * 78

#: Claves cuyo valor es una referencia a otro ítem. La lista es deliberadamente
#: ancha: la segunda mitad del informe es un techo, y un techo se calcula
#: incluyendo lo dudoso, no excluyéndolo.
CLAVES_DE_REF = (
    "source_ref",
    "source_refs",
    "column_ref",
    "column_refs",
    "crud_refs",
    "field_ref",
    "entity_ref",
    "actor_ref",
    "endpoint_ref",
    "rule_ref",
    "scope_column_refs",
    "requirement_refs",
    "story_ref",
)


def indexar(nombre: str, nodo: Any, indice: dict[str, dict]) -> None:
    """Registra todo ítem con ``id`` para poder resolver refs después."""
    if isinstance(nodo, dict):
        if isinstance(nodo.get("id"), str) and nodo["id"]:
            indice.setdefault(
                nodo["id"],
                {
                    "artefacto": nombre,
                    "confidence": nodo.get("confidence"),
                    "evidence": nodo.get("evidence"),
                    "origin": nodo.get("origin"),
                },
            )
        for valor in nodo.values():
            indexar(nombre, valor, indice)
    elif isinstance(nodo, list):
        for valor in nodo:
            indexar(nombre, valor, indice)


def refs_de(item: dict) -> list[str]:
    refs: list[str] = []
    for clave in CLAVES_DE_REF:
        valor = item.get(clave)
        if isinstance(valor, str):
            refs.append(valor)
        elif isinstance(valor, list):
            refs.extend(x for x in valor if isinstance(x, str))
    return refs


def recorrer(nombre: str, nodo: Any, ruta: str, filas: list[dict]) -> None:
    """Acumula todo ítem que tenga confianza numérica."""
    if isinstance(nodo, dict):
        if isinstance(nodo.get("confidence"), (int, float)):
            filas.append({"lista": f"{nombre}{ruta}", "item": nodo})
        for clave, valor in nodo.items():
            recorrer(nombre, valor, f"{ruta}.{clave}", filas)
    elif isinstance(nodo, list):
        for valor in nodo:
            recorrer(nombre, valor, ruta, filas)


def informe_matriz(api: dict, indice: dict[str, dict]) -> dict:
    """La mitad exacta: qué sostiene cada concesión."""
    matriz = api.get("authorization_matrix", []) or []
    allow = [r for r in matriz if r.get("effect") == "allow"]
    sin_evidencia: list[dict] = []
    suben: list[dict] = []

    for regla in allow:
        bases = [indice[ref] for ref in regla.get("source_refs", []) if ref in indice]
        if bases and not any(b["evidence"] for b in bases):
            sin_evidencia.append(regla)
        confianzas = [
            b["confidence"] for b in bases if isinstance(b["confidence"], (int, float))
        ]
        propia = regla.get("confidence")
        if confianzas and isinstance(propia, (int, float)):
            if propia > min(confianzas) + 1e-9:
                suben.append({"regla": regla, "base": min(confianzas)})

    anchas = [
        r for r in sin_evidencia if r.get("scope") == "all" and not r.get("ambiguous")
    ]
    return {
        "matriz": matriz,
        "allow": allow,
        "sin_evidencia": sin_evidencia,
        "anchas_sin_evidencia": anchas,
        "suben": suben,
    }


def informe_cadena(
    artefactos: dict[str, dict], indice: dict[str, dict]
) -> list[tuple[str, int, int]]:
    """La mitad que es un techo: dónde sube la confianza, por lista."""
    filas: list[dict] = []
    for nombre, artefacto in artefactos.items():
        recorrer(nombre, artefacto, "", filas)

    conteo: dict[str, list[int]] = {}
    for fila in filas:
        item = fila["item"]
        confianzas = [
            indice[ref]["confidence"]
            for ref in refs_de(item)
            if ref in indice and isinstance(indice[ref]["confidence"], (int, float))
        ]
        if not confianzas:
            continue
        par = conteo.setdefault(fila["lista"], [0, 0])
        par[0] += 1
        if item["confidence"] > min(confianzas) + 1e-9:
            par[1] += 1
    return sorted(
        ((lista, con, sube) for lista, (con, sube) in conteo.items()),
        key=lambda t: (-t[2], t[0]),
    )


async def cargar(
    job_id: Optional[str],
) -> tuple[dict[str, dict], dict[str, str], Optional[dict]]:
    """Carga la cadena hacia atrás desde un job de API."""
    async with session_scope() as session:
        repo = AgentJobRepository(session)
        if job_id is None:
            fila = await session.execute(
                select(AgentJob)
                .where(AgentJob.agent_type == AgentType.API)
                .order_by(AgentJob.created_at.desc())
                .limit(1)
            )
            job = fila.scalar_one_or_none()
            if job is None:
                raise SystemExit("No hay ningún job de API en la base.")
            job_id = job.id

        artefactos: dict[str, dict] = {}
        ids: dict[str, str] = {}
        procedencia: Optional[dict] = None
        actual: Optional[str] = job_id
        while actual:
            job = await repo.get_job(actual)
            if job is None:
                break
            fila = await repo.get_artifact(actual)
            nombre = job.agent_type.value
            if fila is not None:
                artefactos[nombre] = fila.data
            ids[nombre] = f"{actual}  {job.status.value}  «{job.title}»"
            # La procedencia vive en `metrics` del JOB y no dentro del artefacto
            # (el artefacto es la salida del agente y no se muta desde fuera).
            if procedencia is None:
                procedencia = (job.metrics or {}).get("provenance")
            actual = job.input_job_id
        return artefactos, ids, procedencia


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", help="id del job de API a medir")
    args = parser.parse_args()

    artefactos, ids, procedencia = await cargar(args.job)
    if "api" not in artefactos:
        raise SystemExit("Ese job de API no tiene artefacto: no hay nada que medir.")

    indice: dict[str, dict] = {}
    for nombre, artefacto in artefactos.items():
        indexar(nombre, artefacto, indice)

    api = artefactos["api"]
    m = informe_matriz(api, indice)
    bloqueantes = [
        q for q in api.get("questions_for_tech_lead", []) or [] if q.get("blocking")
    ]

    print(RAYA)
    print("PROPAGACIÓN DE CONFIANZA Y APOYO DE LAS CONCESIONES — 0,00 USD")
    print(RAYA)
    print("\nCadena medida (de la API hacia atrás):")
    for nombre, detalle in ids.items():
        print(f"  {nombre:14} {detalle}")
    if procedencia:
        print(
            f"\n  ⚠ procedencia: {procedencia.get('kind')} / "
            f"{procedencia.get('block')} — {procedencia.get('llm')}"
        )
        print("    Mide la maquinaria determinista, no la calidad del modelo.")

    print(f"\n{RAYA}\n1) LA MATRIZ DE AUTORIZACIÓN (medida exacta)\n{RAYA}")
    print(f"  filas totales .................. {len(m['matriz'])}")
    print(f"  conceden acceso (allow) ........ {len(m['allow'])}")
    print(f"  ...sin evidencia en su base .... {len(m['sin_evidencia'])}")
    print(f"  ...y además scope=all .......... {len(m['anchas_sin_evidencia'])}")
    print(f"  ...con confianza > su base ..... {len(m['suben'])}")
    print("\n  detalle de las concesiones sin evidencia:")
    for regla in m["sin_evidencia"]:
        bases = [
            f"{ref}(conf={indice[ref]['confidence']}, evidence="
            f"{'sí' if indice[ref]['evidence'] else 'null'})"
            for ref in regla.get("source_refs", [])
            if ref in indice
        ]
        print(
            f"    {regla['id']}  {regla['actor_ref']:8} {regla['effect']}/"
            f"{regla['scope']:9} conf={regla.get('confidence')}  "
            f"base: {', '.join(bases) or '(ninguna resuelta)'}"
        )

    print(f"\n{RAYA}\n2) EL COSTE HUMANO DE CADA FORMA (preguntas bloqueantes)\n{RAYA}")
    n = len(m["anchas_sin_evidencia"])
    print(f"  hoy ............................ {len(bloqueantes)}")
    for q in bloqueantes:
        print(f"      {q['id']}  {q['question'][:62]}")
    print(
        f"  una pregunta por celda ......... {len(bloqueantes) + n}   ← forma ingenua"
    )
    print(
        f"  agrupada por clase de vacío .... {len(bloqueantes)}   ← +0, la absorbe la que ya existe"
    )

    print(
        f"\n{RAYA}\n3) LA CADENA COMPLETA (TECHO, no medida — ver el docstring)\n{RAYA}"
    )
    print(f"  {'lista':52} {'con refs':>9} {'suben':>7}")
    total_con, total_sube = 0, 0
    for lista, con, sube in informe_cadena(artefactos, indice):
        total_con += con
        total_sube += sube
        print(f"  {lista:52} {con:9} {sube:7}")
    print(f"  {'TOTAL':52} {total_con:9} {total_sube:7}")
    print(
        "\n  Recordatorio: no todo ref es un apoyo. Este número es un límite "
        "superior\n  y sirve para decidir dónde mirar, no para contar defectos."
    )
    print(RAYA)


if __name__ == "__main__":
    asyncio.run(main())
