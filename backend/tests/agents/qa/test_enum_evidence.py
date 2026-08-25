"""El tope de la evidencia de un enum: comportamiento y candado (A6 / F3).

Dos mitades, y la segunda es la que importa para mañana:

1. **Comportamiento** — por debajo del tope, el conjunto entero tal cual; por
   encima, la **huella**, nunca un conjunto recortado. Un enum a medias produce un
   caso que afirma que un valor legítimo debe rechazarse, y ese caso pasa la
   ejecución certificando una mentira; un hueco, en cambio, se ve.
2. **Candado de código fuente** — QC5 tiene que **reutilizar** esta función, no
   copiarla. El criterio 5 de A6 es explícito: el tope se escribe una vez y lo
   comparten los dos modos, o acaba habiendo dos copias de las constantes, y dos
   copias se separan en cuanto una se ajusta. Un test de comportamiento no ve al
   que mañana escriba su propio tope dentro de ``explore/``; un test de fuente sí,
   y falla en el momento en que se escribe.
"""

import ast
from pathlib import Path

from ai.agents.qa.common import CELDA_EXCEL_MAX_CHARS as CELDA_EXCEL
from ai.agents.qa.common import (
    ENUM_DIGEST_MUESTRA,
    ENUM_MAX_CHARS,
    ENUM_MAX_OPCIONES,
    enum_digest,
    enum_evidence,
)

BACKEND = Path(__file__).resolve().parents[3]


def _catalogo(n: int, prefijo: str = "VAL") -> list[str]:
    """Un catálogo de ``n`` valores con la forma de un maestro real."""
    return [f"{prefijo}-{i:04d}" for i in range(n)]


# --- comportamiento: por debajo del tope, el conjunto entero ------------------


def test_un_enum_de_dominio_viaja_entero_y_sin_tocar():
    valores = ["BORRADOR", "EMITIDA", "EN_RUTA", "ENTREGADA", "ANULADA"]
    assert enum_evidence(valores) == "BORRADOR, EMITIDA, EN_RUTA, ENTREGADA, ANULADA"


def test_el_separador_lo_pone_quien_llama():
    # El Modo A une con ", " y el extractor del Modo C con " | ". La función no
    # decide por ellos: decide el TOPE, que es lo que comparten.
    assert enum_evidence(["A", "B"], separator=" | ") == "A | B"


def test_el_conjunto_vacio_no_inventa_evidencia():
    assert enum_evidence([]) == ""
    assert enum_evidence(None) == ""


def test_justo_en_el_tope_de_opciones_todavia_es_el_conjunto():
    valores = _catalogo(ENUM_MAX_OPCIONES)
    assert enum_evidence(valores) == ", ".join(valores)


# --- comportamiento: por encima, huella; JAMÁS un recorte ---------------------


def test_por_encima_del_tope_de_opciones_se_emite_huella():
    valores = _catalogo(ENUM_MAX_OPCIONES + 1)
    evidencia = enum_evidence(valores)
    assert evidencia != ", ".join(valores)
    assert evidencia.startswith(f"{len(valores)} valores · sha256:")


def test_pocas_opciones_muy_largas_tambien_topan():
    # El tope en caracteres no es un adorno del tope en opciones: cinco valores
    # descriptivos rompen la misma celda que doscientos códigos.
    valores = ["X" * 300 for _ in range(5)]
    assert len(valores) <= ENUM_MAX_OPCIONES
    assert enum_evidence(valores).startswith("5 valores · sha256:")


def test_la_huella_nunca_es_un_conjunto_recortado():
    valores = _catalogo(1874, prefijo="DISTRITO")
    evidencia = enum_evidence(valores)
    # Dice su cardinalidad COMPLETA, así que la muestra no se puede leer como «el
    # enum»; y no es ningún prefijo del conjunto unido.
    assert "1874 valores" in evidencia
    for n in range(1, ENUM_DIGEST_MUESTRA + 5):
        assert evidencia != ", ".join(valores[:n])


def test_la_muestra_no_pasa_de_lo_declarado():
    valores = _catalogo(500)
    evidencia = enum_evidence(valores)
    presentes = [v for v in valores if v in evidencia]
    assert presentes == valores[:ENUM_DIGEST_MUESTRA]


def test_si_ni_un_valor_cabe_la_muestra_desaparece_entera():
    # Fail-closed: antes que una muestra que rompa el tope que la motivó, no hay
    # muestra. La huella sigue respondiendo «¿cambió el catálogo?».
    valores = ["Y" * (ENUM_MAX_CHARS * 2) for _ in range(30)]
    evidencia = enum_evidence(valores)
    assert "primeros:" not in evidencia
    assert evidencia.startswith("30 valores · sha256:")


# --- comportamiento: la huella sirve para lo único que se le pide -------------


def test_la_huella_es_estable_entre_corridas():
    valores = _catalogo(200)
    assert enum_digest(valores) == enum_digest(list(valores))


def test_reordenar_el_catalogo_no_se_reporta_como_cambio():
    valores = _catalogo(200)
    revueltos = list(reversed(valores))
    assert enum_digest(revueltos).split(";")[0] == enum_digest(valores).split(";")[0]


def test_un_valor_que_cambia_cambia_la_huella():
    valores = _catalogo(200)
    otro = valores[:-1] + ["VAL-9999"]
    assert enum_digest(otro) != enum_digest(valores)


def test_un_valor_repetido_es_un_cambio_del_catalogo():
    # No se deduplica a propósito: si el maestro repite un valor, eso ES un cambio.
    valores = _catalogo(200)
    assert enum_digest(valores + [valores[0]]) != enum_digest(valores)


def test_ninguna_evidencia_rompe_la_celda_del_analista():
    for n in (1, ENUM_MAX_OPCIONES, 196, 400, 1874, 5000):
        evidencia = enum_evidence(_catalogo(n))
        assert len(evidencia) <= ENUM_MAX_CHARS
        assert len(evidencia) < CELDA_EXCEL


# --- el Modo A, que es quien llama hoy ---------------------------------------


def test_el_modo_a_usa_la_funcion_y_no_su_propio_join():
    fuente = (BACKEND / "ai/agents/qa/edge_cases.py").read_text(encoding="utf-8")
    assert 'enum_evidence(campo["enum"])' in fuente
    assert '", ".join(campo["enum"])' not in fuente


# --- candado: una sola definición del tope, un solo cálculo de la huella ------

#: El dueño. Cualquier otro módulo que declare estas constantes o que vuelva a
#: calcular una huella de enum está fabricando la segunda copia que A6 prohíbe.
DUENO = "ai/agents/qa/common.py"

#: Los nombres que solo puede ligar el dueño.
CONSTANTES = {
    "ENUM_MAX_OPCIONES",
    "ENUM_MAX_CHARS",
    "ENUM_DIGEST_MUESTRA",
    # Desde QC5: el límite de rotura de la celda lo comprueba el extractor del
    # Modo C, así que ya son dos módulos los que podrían escribir el número.
    "CELDA_EXCEL_MAX_CHARS",
}


def _fuentes_de_qa():
    raiz = BACKEND / "ai/agents/qa"
    for ruta in sorted(raiz.rglob("*.py")):
        relativa = ruta.relative_to(BACKEND).as_posix()
        if relativa == DUENO:
            continue
        yield relativa, ruta.read_text(encoding="utf-8")


def _nombres_asignados(texto: str) -> set[str]:
    nombres: set[str] = set()
    for nodo in ast.walk(ast.parse(texto)):
        if isinstance(nodo, ast.Assign):
            objetivos = nodo.targets
        elif isinstance(nodo, ast.AnnAssign):
            objetivos = [nodo.target]
        else:
            continue
        for objetivo in objetivos:
            if isinstance(objetivo, ast.Name):
                nombres.add(objetivo.id)
    return nombres


def test_nadie_mas_declara_las_constantes_del_tope():
    infractores = [
        ruta
        for ruta, texto in _fuentes_de_qa()
        if _nombres_asignados(texto) & CONSTANTES
    ]
    assert infractores == [], (
        "El tope del enum se declara UNA vez, en "
        f"{DUENO}, y los dos modos lo importan (A6, criterio 5). Copias en: "
        f"{infractores}"
    )


def test_nadie_mas_calcula_una_huella():
    # Cualquier reimplementación de la huella necesita hashear. Vigilar el hash es
    # vigilar la copia sin tener que adivinar cómo la escribirá quien la escriba.
    infractores = [
        ruta
        for ruta, texto in _fuentes_de_qa()
        if "hashlib" in texto or "sha256" in texto
    ]
    assert infractores == [], (
        "La huella de un enum se calcula UNA vez, en "
        f"{DUENO}. Reimplementaciones en: {infractores}"
    )


def test_el_candado_se_ve_fallar():
    # Un candado que solo se ha visto pasar es indistinguible de una función que
    # devuelve la lista vacía. Se le mete la violación y tiene que verla.
    copia = "ENUM_MAX_OPCIONES = 999\n"
    assert _nombres_asignados(copia) & CONSTANTES == {"ENUM_MAX_OPCIONES"}
    anotada = "ENUM_MAX_CHARS: int = 999\n"
    assert _nombres_asignados(anotada) & CONSTANTES == {"ENUM_MAX_CHARS"}
