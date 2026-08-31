"""Candado AST: en el camino de la autorización, la confianza NO se escribe.

Es la **capa 3** de AUT-D3. Las otras tres tapan cosas distintas y ninguna
sustituye a esta:

1. la fábrica (``_rule()`` sin parámetro ``confidence``) impide el error local;
2. el contrato (``basis_confidence``/``basis_evidenced`` + validadores) impide el
   error remoto —el nodo que construye la fila por su cuenta—;
3. **este fichero** impide el RETROCESO: el nodo que mañana se escriba y no use
   la fábrica;
4. el auditor sobre lo persistido mide lo que se generó antes de la regla.

Por qué un test de código fuente y no de comportamiento: un test de
comportamiento no ve al que escriba la próxima fila. Mismo motivo y mismo
idioma que ``tests/llm/test_construcciones.py`` y ``test_atribucion_por_nodo.py``.

Estado en AUT0
--------------
El candado se escribe **antes** que el arreglo, y hoy FALLA a propósito: es la
red antes del trapecio. Va marcado ``xfail(strict=True)``, de modo que:

  - hoy la suite sigue verde y el fallo queda registrado, con sus infractores;
  - cuando AUT1 quite los literales, el ``xfail`` estricto **revienta** y obliga
    a borrar la marca. Un candado que se arregla solo y en silencio se olvida.
"""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[3]

#: El camino por el que la confianza de una CONCESIÓN llega al artefacto, y por
#: tanto el ámbito duro del candado:
#:  - ``authorization.py`` fabrica la matriz (el ``confidence=0.9`` del ``allow``);
#:  - ``endpoints.py`` premia con 0.9 la base MENOS evidenciada (``crud_matrix``),
#:    que es la asimetría §3.1 del diseño y no un detalle de otro nodo.
CAMINO_DE_LA_AUTORIZACION = (
    "ai/agents/api/authorization.py",
    "ai/agents/api/endpoints.py",
)

#: Exenciones, con su motivo escrito. La regla del proyecto sobre conjuntos de
#: exenciones (§8, señal 2) obliga a dos cosas: que cada entrada diga POR QUÉ, y
#: que exista un caso que caiga FUERA —si todo cae dentro, el candado no puede
#: fallar aunque el defecto exista—. El contra-caso es
#: ``test_un_fichero_no_exento_con_literal_si_se_caza``.
EXENTOS = {
    "ai/agents/api/rule_mapping.py": (
        "Residual declarado (§6 del diseño): el invariante se impone SOLO en la "
        "matriz de autorización, donde la confianza es portante. En "
        "`rule_mappings` es hoy decorativa —no la lee ningún gate ni ninguna "
        "pregunta—, y convertirla en portante en seis agentes a la vez es otro "
        "bloque, con su propio número."
    ),
}


def _ramas_de_valor(nodo: ast.AST) -> list[ast.AST]:
    """Las expresiones que pueden acabar SIENDO el valor.

    En ``0.9 if base == "crud_matrix" else 0.7`` —la forma real de
    ``endpoints.py:241``— la condición contiene una llamada, pero el valor que se
    escribe es una de las dos constantes. Mirar el nodo entero daba por bueno ese
    literal: el candado habría sido ciego **justo en la fila del hallazgo** (§3.1
    del diseño, "premia con 0.9 la base menos evidenciada"). Lo mismo con un
    ``conf or 0.9``, donde el número escrito a mano es el que gana cuando la
    fuente calla — que es exactamente el caso contra el que existe la regla.
    """
    if isinstance(nodo, ast.IfExp):
        return _ramas_de_valor(nodo.body) + _ramas_de_valor(nodo.orelse)
    if isinstance(nodo, ast.BoolOp):
        return [r for v in nodo.values for r in _ramas_de_valor(v)]
    return [nodo]


def _es_literal_numerico(nodo: ast.AST) -> bool:
    """¿El valor sale de una constante escrita aquí, y no de una fuente?

    Basta con que UNA rama sea un número escrito: lo que se prohíbe es que exista
    un camino por el que la confianza salga de un literal. Si ninguna rama lo es
    —una llamada, un nombre, una clave de un dict— el número viene de algún
    sitio, que es precisamente lo que se quiere.
    """
    return any(
        isinstance(rama, ast.Constant)
        and isinstance(rama.value, (int, float))
        and not isinstance(rama.value, bool)
        for rama in _ramas_de_valor(nodo)
    )


def literales_de_confianza(fuente: str) -> list[int]:
    """Líneas donde se escribe un número a mano como ``confidence``.

    Las tres formas con las que se puede escribir, porque tapar solo una deja las
    otras dos abiertas:
      - argumento con nombre:  ``_rule(..., confidence=0.9)``
      - clave de diccionario:  ``{"confidence": 0.9}``
      - asignación:            ``regla.confidence = 0.9``
    """
    arbol = ast.parse(fuente)
    lineas: list[int] = []

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.keyword):
            if nodo.arg == "confidence" and _es_literal_numerico(nodo.value):
                lineas.append(nodo.value.lineno)

        elif isinstance(nodo, ast.Dict):
            for clave, valor in zip(nodo.keys, nodo.values):
                if (
                    isinstance(clave, ast.Constant)
                    and clave.value == "confidence"
                    and _es_literal_numerico(valor)
                ):
                    lineas.append(clave.lineno)

        elif isinstance(nodo, (ast.Assign, ast.AnnAssign)):
            if nodo.value is None or not _es_literal_numerico(nodo.value):
                continue
            destinos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
            for destino in destinos:
                nombre = (
                    destino.attr
                    if isinstance(destino, ast.Attribute)
                    else destino.id if isinstance(destino, ast.Name) else None
                )
                if nombre == "confidence":
                    lineas.append(nodo.lineno)

    return sorted(set(lineas))


def _infractores(rutas) -> list[str]:
    encontrados = []
    for ruta in rutas:
        fuente = (BACKEND / ruta).read_text(encoding="utf-8")
        encontrados += [f"{ruta}:{linea}" for linea in literales_de_confianza(fuente)]
    return encontrados


@pytest.mark.xfail(
    strict=True,
    reason=(
        "AUT0 escribe el candado; AUT1 quita los literales. Cuando pase, este "
        "xfail estricto falla por PASAR y hay que borrar la marca."
    ),
)
def test_la_confianza_no_se_escribe_en_el_camino_de_la_autorizacion():
    """El candado. Hoy falla: son los 2 literales que AUT1 tiene que borrar."""
    infractores = _infractores(CAMINO_DE_LA_AUTORIZACION)
    assert not infractores, (
        "La confianza de una concesión se CALCULA a partir de sus bases "
        "(`confianza_derivada`, AUT-D3), nunca se escribe: un literal puede "
        "quedar por encima de la fuente que lo sostiene, y ahí es donde "
        "`allow/all conf=0.9` acaba apoyado en una celda de `conf=0.5` sin "
        "evidencia.\n  " + "\n  ".join(infractores)
    )


def test_hoy_los_infractores_son_exactamente_los_dos_del_informe():
    """Lo que el candado ve HOY, fijado para que AUT1 se lea como un diff.

    Sin esto, el `xfail` de arriba solo diría "algo falla". Esta comprobación
    dice QUÉ falla, y es la que convierte el candado en una medición.
    """
    assert _infractores(CAMINO_DE_LA_AUTORIZACION) == [
        "ai/agents/api/authorization.py:133",
        "ai/agents/api/endpoints.py:241",
    ]


def test_un_fichero_no_exento_con_literal_si_se_caza():
    """El contra-caso de la exención (§8, señal 2).

    `rule_mapping.py` está exento y sus literales no se reportan. Si el candado
    devolviera la lista vacía por cualquier otro motivo —un `walk` que no entra,
    un `arg` mal comparado—, la exención lo taparía y no habría forma de notarlo.
    Así que se comprueba que el MISMO detector, sobre el MISMO fichero, sí ve
    algo: lo que exime es la lista, no una ceguera del detector.
    """
    exento = "ai/agents/api/rule_mapping.py"
    assert exento in EXENTOS
    fuente = (BACKEND / exento).read_text(encoding="utf-8")
    assert literales_de_confianza(fuente), (
        "El detector no ve los literales de un fichero que sabemos que los "
        "tiene: la exención estaría escondiendo un detector roto."
    )
    assert exento not in CAMINO_DE_LA_AUTORIZACION


def test_cada_exencion_dice_por_que_y_apunta_a_un_fichero_real():
    for ruta, motivo in EXENTOS.items():
        assert (
            BACKEND / ruta
        ).is_file(), f"exención sobre un fichero que no existe: {ruta}"
        assert len(motivo) > 60, f"la exención de {ruta} no explica nada"


# --- El detector, visto fallar y visto no dar falsos positivos ---------------


@pytest.mark.parametrize(
    "fuente, linea",
    [
        ("_rule(ep, actor, confidence=0.9)", 1),
        ('regla = {"confidence": 0.85}', 1),
        ("fila.confidence = 0.5", 1),
        ("confidence = 0.5", 1),
        # La forma real de `endpoints.py`: un ternario entre dos constantes.
        ('_rule(ep, confidence=0.9 if base == "crud_matrix" else 0.7)', 1),
        # Multilínea: la que se escribe cuando el `_rule(` ya no cabe.
        ("_rule(\n    ep,\n    confidence=0.9,\n)", 3),
        # El default escrito a mano: el número que gana cuando la fuente calla.
        ("_rule(ep, confidence=conf or 0.9)", 1),
    ],
)
def test_el_candado_caza_cada_forma_de_escribir_el_numero(fuente, linea):
    """Se ve FALLAR: un candado que solo se ha visto pasar es indistinguible de
    una función que devuelve la lista vacía (misma regla que los de QC4)."""
    assert literales_de_confianza(fuente) == [linea]


@pytest.mark.parametrize(
    "fuente",
    [
        # Lo que AUT1 va a escribir: la confianza viene de las bases.
        "_rule(ep, actor, confidence=confianza_derivada(bases, tope=TOPE))",
        "_rule(ep, actor, confidence=fuente['confidence'])",
        "_rule(ep, actor, confidence=None)",
        "_rule(ep, actor, confidence=conf)",
        'regla = {"confidence": confianza_derivada(bases, tope=0.9)}',
        # Un número que no es una confianza no se toca.
        "_rule(ep, actor, threshold=0.9)",
        'payload = {"score": 0.9}',
        # `True` es `int` en Python: un booleano no es una confianza escrita.
        "_rule(ep, actor, confidence=True)",
    ],
)
def test_el_candado_no_marca_lo_que_no_es_un_literal_escrito(fuente):
    """Y el contra-caso del contra-caso: un candado que marca todo se desactiva
    a la semana. `TOPE` es una constante y sigue siendo legítima —lo que se
    prohíbe es el número que NO pasa por la fuente, no la palabra 0.9."""
    assert literales_de_confianza(fuente) == []
