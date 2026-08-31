"""La CAPA 4 de AUT-D3: el auditor sobre lo ya persistido, y su definición.

Las tres primeras capas impiden escribir una concesión sin respaldo. Ninguna
toca lo que ya está guardado, y lo guardado es lo que alguien puede leer hoy
para construir. De ahí el censo (``--censo``): cuántas celdas falsas hay YA en
la base.

Lo que este fichero fija no es la aritmética del script —eso lo hace la corrida—
sino **la definición de celda falsa**, que es de donde sale el número:

    una fila que CONCEDE (``allow``) y cuya base NO cita evidencia.

Falsa no quiere decir que el acceso sea incorrecto: quiere decir que la fila
**afirma un respaldo que no existe**. Puede acertar por casualidad; lo que no
puede es demostrarlo. Y tres casos vecinos que NO son eso, cada uno con su
motivo, porque un contador que mete de más se desactiva igual de rápido que uno
que mete de menos.

Sin base de datos y sin red: se mide sobre dicts, que es la forma en la que el
artefacto vive en `agent_artifacts.data`.
"""

import pytest

from scripts.medir_propagacion_de_confianza import indexar, informe_matriz


def _indice(*items) -> dict:
    indice: dict = {}
    indexar("ef", {"cosas": list(items)}, indice)
    return indice


CRUD_SIN_EVIDENCIA = {"id": "CRUD-001", "confidence": 0.5, "evidence": None}
BR_CON_EVIDENCIA = {
    "id": "BR-003",
    "confidence": 0.8,
    "evidence": "El jefe directo aprueba o rechaza la solicitud.",
}


def _regla(**kw) -> dict:
    base = {
        "id": "AUTH-001",
        "effect": "allow",
        "scope": "all",
        "actor_ref": "ACT-001",
        "basis": "crud_matrix",
        "source_refs": ["CRUD-001"],
        "confidence": 0.9,
        "ambiguous": False,
    }
    base.update(kw)
    return base


def test_la_celda_del_cmp0_es_falsa_y_es_ancha():
    """El caso exacto del informe: allow + scope=all + base sin evidencia."""
    m = informe_matriz(
        {"authorization_matrix": [_regla()]}, _indice(CRUD_SIN_EVIDENCIA)
    )
    assert len(m["sin_evidencia"]) == 1
    assert len(m["anchas_sin_evidencia"]) == 1
    assert len(m["suben"]) == 1  # 0.9 sobre una base de 0.5
    assert m["sin_base_resoluble"] == []


def test_una_concesion_con_evidencia_detras_no_es_falsa():
    """El contra-caso. Sin él, un contador que devuelva todo lo que ve pasaría
    igual: hay que ver al detector decir que NO."""
    m = informe_matriz(
        {
            "authorization_matrix": [
                _regla(basis="business_rule", source_refs=["BR-003"])
            ]
        },
        _indice(BR_CON_EVIDENCIA),
    )
    assert m["sin_evidencia"] == []
    assert m["anchas_sin_evidencia"] == []


def test_un_deny_nunca_cuenta_aunque_su_base_este_vacia():
    """Una denegación sin respaldo cierra de más: se detecta al usar el sistema.
    La asimetría rectora del agente es la razón de que solo se cuente `allow`."""
    m = informe_matriz(
        {
            "authorization_matrix": [
                _regla(effect="deny", scope="none", basis="default_deny")
            ]
        },
        _indice(CRUD_SIN_EVIDENCIA),
    )
    assert m["allow"] == []
    assert m["sin_evidencia"] == []


def test_una_base_que_no_resuelve_no_se_cuenta_como_buena_NI_como_falsa():
    """La regla del proyecto: la ausencia de un dato no es el valor 0 del dato.

    Es un caso REAL del censo, no hipotético: en la base hay dos filas `allow`
    que citan `BR-003` sobre un EF cuya única regla es `BR-001`. Contarlas como
    buenas las escondería; contarlas como falsas afirmaría algo que no se ha
    medido. Salen en su propia línea, y la fracción se calcula sin ellas.
    """
    m = informe_matriz(
        {"authorization_matrix": [_regla(source_refs=["BR-003"])]},
        _indice(CRUD_SIN_EVIDENCIA),  # BR-003 no está en el índice
    )
    assert m["sin_evidencia"] == []
    assert len(m["sin_base_resoluble"]) == 1


def test_una_sola_base_evidenciada_basta_para_sostener_la_fila():
    """`any`, no `all`: citar dos fuentes y que una evidencie es suficiente.
    Se fija a propósito para que endurecerlo mañana sea una decisión y no un
    efecto lateral."""
    m = informe_matriz(
        {"authorization_matrix": [_regla(source_refs=["CRUD-001", "BR-003"])]},
        _indice(CRUD_SIN_EVIDENCIA, BR_CON_EVIDENCIA),
    )
    assert m["sin_evidencia"] == []


@pytest.mark.parametrize(
    "scope, ambiguous, ancha",
    [
        ("all", False, True),
        ("unscoped", False, False),  # el valor que llega en AUT2
        ("own", False, False),
        ("own_team", True, False),  # alcance declarado sin columna: ya bloquea hoy
        ("all", True, False),
    ],
)
def test_ancha_es_all_y_no_ambigua(scope, ambiguous, ancha):
    """Qué cuenta como ANCHA, con casos dentro y fuera del conjunto (§8, señal 2).

    Una ambigua ya produce pregunta bloqueante hoy, así que sumarla al recuento
    de anchas contaría dos veces el mismo coste humano y `10 preguntas` dejaría
    de ser el número que decidió la forma del arreglo.
    """
    m = informe_matriz(
        {"authorization_matrix": [_regla(scope=scope, ambiguous=ambiguous)]},
        _indice(CRUD_SIN_EVIDENCIA),
    )
    assert bool(m["anchas_sin_evidencia"]) is ancha
