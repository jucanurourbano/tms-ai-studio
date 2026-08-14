"""Nodo DATASET: datos de prueba reutilizables por entidad. **Sin LLM.**

Aquí hay una desviación deliberada del pipeline propuesto, que planteaba pedir al
modelo los valores concretos de cada dataset.

El problema de hacerlo así: los casos **ya tienen** valores concretos y anclados
—`000123456`, `2026-08-15`, el `null` del campo requerido—, porque TEST_DESIGN y
EDGE_CASES los produjeron con la evidencia delante. Pedir un segundo juego de
valores al modelo generaría datos que **divergen** de los que usan los casos: el
dataset diría que el saldo válido es 1500 y el caso probaría con 900, y quien
preparara el entorno con el dataset no estaría preparando lo que el caso necesita.
Dos verdades sobre el mismo dato es peor que una sola incompleta.

Así que el dataset se **cosecha** de los casos, agrupando por entidad: cada valor
que aparece aquí ya pasó por su cortafuegos, y dataset y casos son consistentes por
construcción. Y el pipeline queda con cuatro nodos LLM en vez de cinco.

Lo que se pierde: un dataset no cubre campos que ningún caso toca. Es un límite
honesto —esos campos tampoco tienen cobertura— y CRITIQUE lo puede reportar; el
alternativo era rellenarlos con valores inventados, que es la clase de dato que este
agente existe para no producir.
"""

from typing import Any, Optional

from .schemas.enums import DataKind


def _entity_of_field(
    field_ref: Optional[str], campos: dict[str, dict]
) -> Optional[str]:
    """Entidad a la que pertenece un campo del EF."""
    if not field_ref:
        return None
    return (campos.get(field_ref) or {}).get("entity_ref")


def _expectation(caso: dict[str, Any], kind: str) -> str:
    """Qué debe pasar con la fila, dicho con las palabras del caso que la produjo."""
    if kind == DataKind.VALID.value:
        return "Se acepta."
    refs = [r for r in (caso.get("source_refs") or []) if r.startswith(("BR-", "VAL-"))]
    limite = (caso.get("boundary") or {}).get("rule_ref")
    if limite:
        return f"Se rechaza por {limite}."
    if refs:
        return f"Se rechaza por {refs[0]}."
    return "Se rechaza."


def build_datasets(
    test_cases: list[dict[str, Any]], sources: dict[str, Any]
) -> dict[str, Any]:
    """Agrupa los datos de los casos en datasets por entidad."""
    ef = sources.get("ef", {}) or {}
    campos = {c.get("id"): c for c in ef.get("fields", []) or []}
    entidades = {e.get("id"): e for e in ef.get("entities", []) or []}
    nombres_a_ref = {
        (c.get("name") or "").casefold(): c.get("id")
        for c in ef.get("fields", []) or []
        if c.get("name")
    }

    # entity_ref -> kind -> {"values": {...}, "field_refs": [...], ...}
    por_entidad: dict[str, dict[str, dict[str, Any]]] = {}
    huerfanos: dict[str, dict[str, Any]] = {}

    for caso in test_cases:
        datos = caso.get("test_data") or []
        if not datos:
            continue
        for dato in datos:
            kind = dato.get("kind") or DataKind.VALID.value
            # El `field_ref` puede no venir (los casos de borde estructurales lo
            # omiten): se resuelve por nombre contra los campos del EF, que es un
            # emparejamiento exacto, no una aproximación.
            field_ref = dato.get("field_ref") or nombres_a_ref.get(
                (dato.get("name") or "").casefold()
            )
            entity_ref = _entity_of_field(field_ref, campos)
            destino = (
                por_entidad.setdefault(entity_ref, {}) if entity_ref else huerfanos
            )
            fila = destino.setdefault(
                kind,
                {
                    "kind": kind,
                    "values": {},
                    "field_refs": [],
                    "expectation": _expectation(caso, kind),
                    "anchor": caso.get("boundary"),
                    "case_ids": [],
                },
            )
            fila["values"][dato.get("name") or (field_ref or "campo")] = str(
                dato.get("value", "")
            )
            if field_ref and field_ref not in fila["field_refs"]:
                fila["field_refs"].append(field_ref)
            if caso["id"] not in fila["case_ids"]:
                fila["case_ids"].append(caso["id"])
            if fila["anchor"] is None and caso.get("boundary"):
                fila["anchor"] = caso["boundary"]

    datasets: list[dict[str, Any]] = []
    for i, (entity_ref, filas) in enumerate(sorted(por_entidad.items()), start=1):
        entidad = entidades.get(entity_ref) or {}
        nombre = entidad.get("name") or entity_ref
        datasets.append(
            {
                "id": f"DS-{i:03d}",
                "name": nombre,
                "entity_ref": entity_ref,
                "description": (
                    f"Datos de prueba de {nombre}, cosechados de los casos que los "
                    "usan: válidos, inválidos y de frontera."
                ),
                "rows": [
                    {
                        "id": f"DS-{i:03d}-R{j}",
                        "kind": fila["kind"],
                        "values": fila["values"],
                        "expectation": fila["expectation"],
                        "field_refs": fila["field_refs"],
                        "anchor": (
                            fila["anchor"]
                            if fila["kind"] == DataKind.BOUNDARY.value
                            else None
                        ),
                    }
                    for j, fila in enumerate(
                        sorted(filas.values(), key=lambda f: f["kind"]), start=1
                    )
                ],
                "source_refs": [entity_ref] if entity_ref else [],
                "origin": "derived",
            }
        )

    observaciones: list[dict] = []
    if huerfanos:
        # Datos que no se pudieron atribuir a ninguna entidad del EF. No se
        # inventa una entidad para alojarlos ni se tiran: se declaran.
        nombres = sorted(
            {n for fila in huerfanos.values() for n in fila["values"].keys()}
        )
        observaciones.append(
            {
                "description": (
                    "Hay datos de prueba que no se pudieron atribuir a ninguna "
                    f"entidad del EF y quedaron fuera de los datasets: {', '.join(nombres)}."
                ),
                "reason": "Campo sin FLD- que lo respalde.",
            }
        )

    return {"datasets": datasets, "observations": observaciones}
