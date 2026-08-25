"""Candado de la regla R1: una costura parcheable se llama por su módulo.

Un ``from modulo import simbolo`` a nivel de módulo **resuelve el enlace al
importar**. A partir de ahí, sustituir el atributo del módulo de origen —que es lo
que hace ``monkeypatch.setattr``— no alcanza a ese enlace ya resuelto: el
importador se queda con la referencia vieja y ninguna capa del cortafuegos lo ve.

Nos mordió dos veces:

* **LLM1** — ``tests/orchestrator/test_claude.py`` importaba el constructor por su
  nombre al cargar el módulo y construía el cliente REAL de Anthropic sin que
  ninguna capa lo viera. De ahí también la desviación de §7.1 del diseño
  multiproveedor: la capa 1 envuelve ``build_client`` de cada ``ProviderSpec`` en
  vez de sustituir ``get_llm``, porque seis de los quince consumidores resuelven
  ``get_llm`` a nivel de módulo y perseguirlos uno a uno es el trabajo manual que
  la capa venía a evitar.
* **QC3** — ``ExploreSession`` llama a ``_driver.build_driver(...)`` **por el
  módulo** por este mismo motivo; con un nombre importado, el cortafuegos del
  navegador —la única capa que existe para ese riesgo— no habría alcanzado nada.

Este test es el candado general. Un **import dentro de una función** sí resuelve
en cada llamada y por tanto es válido: es la escapatoria legítima, y por eso se
distingue del import de nivel de módulo en vez de prohibirlos todos.
"""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

#: Símbolo parcheable → ficheros donde SÍ puede aparecer un import por nombre.
#: Siempre su dueño, y a lo sumo el ``__init__`` que lo reexporta (que es un
#: alias del atributo, no un enlace que alguien vaya a llamar).
COSTURAS: dict[str, set[str]] = {
    "build_driver": {
        "ai/agents/qa/explore/driver.py",
        "ai/agents/qa/explore/__init__.py",
    },
    "get_claude_client": {"app/dependencies/claude.py"},
}


def _fuentes():
    for paquete in ("app", "ai"):
        for ruta in sorted((BACKEND / paquete).rglob("*.py")):
            relativa = ruta.relative_to(BACKEND).as_posix()
            yield relativa, ast.parse(ruta.read_text(encoding="utf-8"))


def _imports_de_nivel_de_modulo(arbol) -> list[ast.ImportFrom]:
    """Los ``from … import …`` que NO están dentro de una función.

    Los de dentro se resuelven en cada llamada, así que el parche los alcanza.
    """
    anidados = {
        id(hijo)
        for nodo in ast.walk(arbol)
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
        for hijo in ast.walk(nodo)
        if isinstance(hijo, ast.ImportFrom)
    }
    return [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom) and id(nodo) not in anidados
    ]


@pytest.mark.parametrize("simbolo", sorted(COSTURAS))
def test_ninguna_costura_se_importa_por_nombre_a_nivel_de_modulo(simbolo):
    permitidos = COSTURAS[simbolo]
    infractores = [
        f"{relativa}:{nodo.lineno}"
        for relativa, arbol in _fuentes()
        if relativa not in permitidos
        for nodo in _imports_de_nivel_de_modulo(arbol)
        if any(alias.name == simbolo for alias in nodo.names)
    ]
    assert infractores == [], (
        f"«{simbolo}» es una costura que el cortafuegos parchea: importarla por "
        "nombre a nivel de módulo congela el enlace y el parche no lo alcanza. "
        "Llámala por el módulo (`_mod.func(...)`). Infractores: "
        + ", ".join(infractores)
    )


@pytest.mark.parametrize("simbolo", sorted(COSTURAS))
def test_cada_costura_sigue_existiendo_donde_dice_su_dueno(simbolo):
    """Si alguien renombra la función, el candado de arriba pasaría a vigilar un
    nombre que ya no existe — es decir, dejaría de vigilar en silencio."""
    duenos = [
        relativa
        for relativa, arbol in _fuentes()
        if relativa in COSTURAS[simbolo]
        and any(
            isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
            and nodo.name == simbolo
            for nodo in ast.walk(arbol)
        )
    ]
    assert duenos, f"«{simbolo}» no está definida en ninguno de sus dueños."


def test_un_import_de_nivel_de_modulo_se_distingue_de_uno_dentro_de_una_funcion():
    """El candado, probado introduciendo la violación: sin esta distinción sería
    o inútil (permitiría el import congelado) o insufrible (prohibiría el
    diferido, que es la escapatoria correcta y la que usa el proveedor)."""
    arbol = ast.parse(
        "from x import build_driver\n"
        "def f():\n"
        "    from y import build_driver\n"
        "    return build_driver\n"
    )
    de_modulo = _imports_de_nivel_de_modulo(arbol)
    assert [nodo.module for nodo in de_modulo] == ["x"]
