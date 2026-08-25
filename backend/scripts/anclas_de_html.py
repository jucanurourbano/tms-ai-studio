"""Imprime la tabla de anclas de un ``.html`` de disco. Para verlo con los ojos.

Existe porque un extractor determinista se juzga mirando su salida sobre una
página de verdad, y un test verde no enseña la tabla. No forma parte de la suite,
no sale a la red, no abre un navegador y **no escribe nada**: lee un fichero,
llama a ``anclas_de`` y pinta el resultado.

Uso (desde ``backend/``)::

    .venv/bin/python scripts/anclas_de_html.py \\
        tests/fixtures/qa_explore/tms_guias/02_guias_nueva.html --path /guias/nueva

El ``--path`` es el de la página observada, y es el que entra en cada ``ref``. Es
un *path*, nunca una URL: el host viene del alias y no viaja en el artefacto.

Lo que la tabla enseña además de las anclas: **los controles que se quedaron sin
ninguna**. Un hueco es una decisión —sin selector estable no se ancla— y verlo es
la mitad del valor de mirar.
"""

import argparse
import os
import sys

# Permite ejecutar el archivo directamente (agrega backend/ al path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.agents.qa.explore import dom  # noqa: E402
from ai.agents.qa.explore.extract import (  # noqa: E402
    CONTROLES,
    Ancla,
    anclas_de,
    selector_de_ancla,
    veces_por_selector,
)

ANCHO_VALOR = 28
ANCHO_EVIDENCIA = 64


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("html", help="Ruta del fichero .html a leer.")
    parser.add_argument(
        "--path",
        default="/",
        help="Path de la página observada, el que entra en el ref (default: /).",
    )
    parser.add_argument(
        "--evidencia",
        action="store_true",
        help="Imprime además la evidencia literal de cada ancla.",
    )
    return parser.parse_args()


def _recortar(texto: str, ancho: int) -> str:
    plano = " ".join(texto.split())
    return plano if len(plano) <= ancho else plano[: ancho - 1] + "…"


def _fila(ancla: Ancla) -> str:
    marca = "⚠" if ancla.fragil else " "
    return (
        f"{ancla.linea:>5}  {marca} {ancla.selector_strategy:<12}"
        f"{ancla.attribute:<11}{_recortar(ancla.value, ANCHO_VALOR):<{ANCHO_VALOR}}"
        f"  {ancla.selector}"
    )


def _sin_ancla(html: str) -> list[dom.Elemento]:
    """Los controles sin selector estable, para que el hueco se vea.

    Un control con selector y sin atributos de validación no sale aquí: no hay
    hueco que enseñar, simplemente no había nada que anclar."""
    elementos = dom.elementos(html)
    veces = veces_por_selector(elementos)
    return [
        elemento
        for elemento in elementos
        if elemento.tag in CONTROLES and selector_de_ancla(elemento, veces) is None
    ]


def main() -> None:
    args = _argumentos()
    with open(args.html, encoding="utf-8") as fichero:
        html = fichero.read()

    anclas = anclas_de(html, args.path)

    print(f"\n{args.html}  →  path {args.path}\n")
    print(
        f"{'LÍNEA':>5}  {'ESTRATEGIA':<14}{'ATRIBUTO':<11}{'VALOR':<{ANCHO_VALOR}}"
        "  SELECTOR"
    )
    print("─" * 110)
    for ancla in anclas:
        print(_fila(ancla))
        if args.evidencia:
            print(f"{'':>7}  └ {_recortar(ancla.evidence, ANCHO_EVIDENCIA)}")

    frágiles = [ancla for ancla in anclas if ancla.fragil]
    controles = {ancla.selector for ancla in anclas}
    print("─" * 110)
    print(
        f"{len(anclas)} anclas sobre {len(controles)} controles; "
        f"{len(frágiles)} frágiles (⚠ structural: un <div> nuevo las rompe)."
    )

    huerfanos = _sin_ancla(html)
    if huerfanos:
        print(
            f"\n{len(huerfanos)} controles SIN SELECTOR — de estos no se ancla nada, "
            "aunque lleven atributos de validación, y el hueco se ve en la cobertura:"
        )
        for elemento in huerfanos:
            print(f"  línea {elemento.linea:>4}: {_recortar(elemento.origen, 90)}")

    if not anclas:
        print(
            "\nNinguna ancla. No es necesariamente un error: una página sin "
            "controles con atributos de validación no tiene nada que anclar."
        )


if __name__ == "__main__":
    main()
