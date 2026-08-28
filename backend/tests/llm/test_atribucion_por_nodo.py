"""Candado: toda llamada al modelo declara SU NODO (GAS-D10).

`by_stage` es la razón de ser de GAS2 —el antes/después con el que se demuestra
un recorte— y vale exactamente lo que valga la etiqueta de cada llamada. GAS1
puso la etiqueta en ``run_structured_map``, que cubre los nodos de tipo *map* y
**deja fuera a los de una sola llamada**. El agujero medido, antes de este
arreglo: quince sitios sin atribuir, entre ellos los cinco nodos LLM del Agente
Arquitectura —o sea el agente **entero**, cuyo gasto caía en ``stage = NULL``— y
el ``CRITIQUE`` de los otros cuatro.

La regla que fija este fichero tiene dos mitades, y las dos hacen falta:

1. **Nadie llama al modelo por fuera.** ``complete_json`` solo se invoca desde
   los dos sitios que etiquetan; cualquier tercero se saltaría la atribución
   entera, no solo el nombre del nodo.
2. **Nadie llama a ``complete_structured`` sin declarar el nodo.** La firma ya
   lo impide en tiempo de ejecución (``stage`` es keyword-only y sin default,
   igual que ``data_class`` y ``job_id`` en ``get_llm``), pero un ``TypeError``
   se descubre corriendo la rama y hay ramas que solo corren con un artefacto de
   cierta forma. El AST lo descubre al escribirlo.

Es un test de **código fuente**, como ``test_construcciones.py`` y por el mismo
motivo: un test de comportamiento no ve al que mañana escriba la llamada número
dieciséis.
"""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

#: Los DOS sitios que pueden etiquetar, y por qué son dos y no uno:
#:  - ``complete_structured`` cubre toda llamada estructurada del árbol, sea de
#:    un *map* o de una sola tirada;
#:  - el ``CRITIQUE`` del EF es el único ``complete_json`` suelto que queda (no
#:    valida contra un esquema Pydantic: tolera *fences* y reporta el error).
ETIQUETADORES = {
    "ai/agents/base/structured.py",
    "ai/agents/ef/critique.py",
}

#: ``MeteredLLMClient`` es la fontanería, no un llamador: ya lleva la etiqueta
#: puesta cuando delega en el cliente de debajo. Es el sitio que ANOTA la fila.
FONTANERIA = {"ai/llm/metering.py"}


def _modulos():
    for paquete in ("app", "ai"):
        for ruta in sorted((BACKEND / paquete).rglob("*.py")):
            yield ruta.relative_to(BACKEND).as_posix(), ruta


def _llamadas(arbol: ast.AST, nombre: str):
    """Todas las llamadas a ``nombre`` o ``algo.nombre`` del árbol."""
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        func = nodo.func
        if isinstance(func, ast.Name) and func.id == nombre:
            yield nodo
        elif isinstance(func, ast.Attribute) and func.attr == nombre:
            yield nodo


def test_complete_json_solo_se_llama_desde_los_dos_etiquetadores():
    """Mitad 1: nadie habla con el modelo por fuera de un sitio que etiqueta."""
    infractores = [
        f"{ruta}:{llamada.lineno}"
        for ruta, path in _modulos()
        if ruta not in ETIQUETADORES | FONTANERIA
        for llamada in _llamadas(
            ast.parse(path.read_text(encoding="utf-8")), "complete_json"
        )
    ]
    assert not infractores, (
        "Estas llamadas a `complete_json` no pasan por un etiquetador, así que su "
        "fila del libro mayor no sabrá de qué nodo es (GAS-D10). Usa "
        "`complete_structured(..., stage=...)`:\n  " + "\n  ".join(infractores)
    )


def test_toda_llamada_estructurada_declara_su_nodo():
    """Mitad 2: ``complete_structured`` siempre recibe ``stage=``."""
    infractores = []
    for ruta, path in _modulos():
        if ruta == "ai/agents/base/structured.py":
            continue  # es donde se define, y donde se etiqueta
        for llamada in _llamadas(
            ast.parse(path.read_text(encoding="utf-8")), "complete_structured"
        ):
            if not any(kw.arg == "stage" for kw in llamada.keywords):
                infractores.append(f"{ruta}:{llamada.lineno}")
    assert not infractores, (
        "Estas llamadas a `complete_structured` no declaran `stage=`, así que su "
        "gasto caería en `stage = NULL` y `by_stage` no podría separarlo:\n  "
        + "\n  ".join(infractores)
    )


def test_run_structured_map_tambien_declara_su_nodo():
    """El *map* etiqueta por la misma puerta: reenvía su ``stage`` hacia dentro."""
    infractores = []
    for ruta, path in _modulos():
        if ruta == "ai/agents/base/structured.py":
            continue
        for llamada in _llamadas(
            ast.parse(path.read_text(encoding="utf-8")), "run_structured_map"
        ):
            if not any(kw.arg == "stage" for kw in llamada.keywords):
                infractores.append(f"{ruta}:{llamada.lineno}")
    assert not infractores, "\n  ".join(infractores)


def test_stage_es_obligatorio_en_la_firma():
    """El candado de verdad es la firma: sin default, olvidarlo revienta.

    Se comprueba **provocando el olvido**, no leyendo la firma: un candado que
    solo se ha visto pasar es indistinguible de una función que no comprueba
    nada (misma regla que los candados de QC4).
    """
    import inspect

    from ai.agents.base.structured import complete_structured

    parametro = inspect.signature(complete_structured).parameters["stage"]
    assert parametro.kind is inspect.Parameter.KEYWORD_ONLY
    assert parametro.default is inspect.Parameter.empty

    with pytest.raises(TypeError, match="stage"):
        complete_structured(object(), system="s", user="u", schema=int)


@pytest.mark.asyncio
async def test_la_etiqueta_llega_al_cliente():
    """Y el comportamiento: el ``stage`` declarado es el que ve el cliente.

    Sin esto, las tres comprobaciones de arriba solo garantizarían que se
    escribe la palabra `stage`, no que llegue a la fila del libro mayor.
    """
    from pydantic import BaseModel

    from ai.agents.base.structured import complete_structured, run_structured_map

    class Vacio(BaseModel):
        pass

    class Cliente:
        def __init__(self, stage=None, visto=None):
            self.stage, self.visto = stage, visto if visto is not None else []

        def for_stage(self, stage):
            return Cliente(stage, self.visto)

        async def complete_json(self, *, system, user):
            self.visto.append(self.stage)
            return "{}"

    cliente = Cliente()
    await complete_structured(
        cliente, system="s", user="u", schema=Vacio, stage="CRITIQUE"
    )
    assert cliente.visto == ["CRITIQUE"]

    cliente.visto.clear()
    await run_structured_map(
        cliente,
        [{"id": "A"}, {"id": "B"}],
        build_system=lambda _i: "s",
        build_user=lambda _i: "u",
        schema=Vacio,
        ref_of=lambda i: i["id"],
        stage="EDGE_CASES",
        estimate_tokens=len,
    )
    assert cliente.visto == ["EDGE_CASES", "EDGE_CASES"]
