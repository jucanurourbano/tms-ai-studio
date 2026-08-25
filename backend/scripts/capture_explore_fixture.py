"""Captura un escenario de fixtures del Modo C **una vez, a mano y con permiso**.

No forma parte de la suite y no corre en CI: sale a la red contra una aplicación
viva, y eso es siempre una decisión de una persona, nunca de un runner.

Uso (desde ``backend/``, con el venv y la exploración habilitada en el despliegue)::

    .venv/bin/python scripts/capture_explore_fixture.py \\
        --alias tms-qa --out tests/fixtures/qa_explore/tms_guias \\
        --path /guias --path /guias/nueva

Lo que hace que este script exista, además de la comodidad: **entre capturar y
guardar hay un paso obligatorio**. Una captura de una aplicación autenticada es un
volcado de datos de producción y el repositorio es para siempre, así que todo pasa
por ``escenario_saneado()``, que sanea y **revienta** si lo saneado todavía viola
el candado de fixtures. Escribir a mano en ``tests/fixtures/qa_explore/`` se puede
—las trampas se escriben así—, pero entonces el candado de la suite es lo único
que separa una captura cruda del historial de git, y por eso también existe.

⚠️  Hoy este script no llega a capturar nada: no hay driver de navegador (QC5 lo
añade sobre la misma costura). Falla con el mensaje de ``build_driver``, que dice
exactamente eso, en vez de fingir que exploró.
"""

import argparse
import asyncio
import json
import os
import sys

# Permite ejecutar el archivo directamente (agrega backend/ al path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.agents.qa.explore.sanitize import escenario_saneado  # noqa: E402
from ai.agents.qa.explore.session import ExploreSession  # noqa: E402
from ai.agents.qa.explore.target import assert_target_authorized  # noqa: E402


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--alias",
        required=True,
        help="Alias autorizado del destino. NUNCA una URL: la capa 1 del guard "
        "no acepta coordenadas del cliente.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Directorio del escenario, p. ej. tests/fixtures/qa_explore/tms_guias",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        dest="paths",
        help="Path adicional a visitar (repetible). La entrada del destino "
        "siempre se visita.",
    )
    return parser.parse_args()


async def _capturar(alias: str, paths: list[str]) -> tuple[list, str]:
    """Explora el destino y devuelve las páginas observadas y su host."""
    destino = assert_target_authorized(alias)
    sesion = ExploreSession(destino)
    try:
        entrada = await sesion.abrir()
        for path in paths:
            await sesion.visitar(destino.origin + path, depth=1, desde=entrada)
        return sesion.paginas, destino.host
    finally:
        await sesion.cerrar()


def main() -> None:
    args = _argumentos()
    paginas, host = asyncio.run(_capturar(args.alias, args.paths))
    if not paginas:
        raise SystemExit(
            "No se observó ninguna página: revisa la allowlist y el destino. No "
            "se escribe un escenario vacío, que sería indistinguible de una "
            "aplicación vacía."
        )

    escenario = escenario_saneado(paginas, hosts_a_ocultar=[host])

    os.makedirs(args.out, exist_ok=True)
    for nombre, contenido in escenario.archivos.items():
        with open(os.path.join(args.out, nombre), "w", encoding="utf-8") as fichero:
            fichero.write(contenido)
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(escenario.manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Escenario escrito en {args.out}: {len(escenario.archivos)} páginas.")
    print(f"El saneador retiró {len(escenario.retirados)} cosas:")
    clases: dict[str, int] = {}
    for retirado in escenario.retirados:
        clases[retirado.clase] = clases.get(retirado.clase, 0) + 1
    for clase, cuantas in sorted(clases.items()):
        print(f"  - {clase}: {cuantas}")
    print(
        "Revisa el resultado antes de comitear: el candado cubre dígitos, host y "
        "el atributo de valor, no un nombre propio en un párrafo."
    )


if __name__ == "__main__":
    main()
