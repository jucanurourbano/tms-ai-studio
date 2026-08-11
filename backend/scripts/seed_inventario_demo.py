"""Seed de demostración del Inventario de Sistemas (CIERRE del módulo INV).

Crea el sistema destino **TMS Moderno** con las 15 tablas maestras del esquema
compartido, para poder ver el módulo funcionando de extremo a extremo: inventario
→ diseño de BD → badges de reconciliación.

⚠️  LOS NOMBRES SON SINTÉTICOS.

El documento real (``PROYECTO_MODERNIZACION_v4``) no está en el repositorio. Lo
que aquí se reproduce es la FORMA acordada del sistema destino —15 tablas
maestras— con nombres genéricos y plausibles de un TMS de courier. No se adivinan
los nombres reales de Urbano: un seed de demostración que pareciera el esquema
verdadero acabaría tomándose por tal.

Cuando el documento se incorpore, se sustituyen los nombres aquí y en
``tests/inventory/fixtures.py``.

Uso::

    python -m scripts.seed_inventario_demo            # crea o actualiza
    python -m scripts.seed_inventario_demo --borrar   # elimina el sistema demo
"""

import argparse
import asyncio
import sys
from typing import Any

from app.dependencies.database import session_scope
from app.models.inventory import (
    InventoryAssetOrigin,
    InventoryAssetType,
    InventorySystemKind,
    InventorySystemStatus,
)
from app.repositories.inventory_repository import InventoryRepository

SISTEMA = "TMS Moderno"

#: Las 15 tablas maestras del esquema compartido (nombres SINTÉTICOS).
#: Cada una con las columnas que cualquier tabla maestra tendría, para que la
#: reconciliación tenga estructura real que comparar y no solo nombres.
MAESTRAS: dict[str, list[tuple[str, str, bool]]] = {
    # tabla: [(columna, tipo, nullable)]
    "usuarios": [
        ("nombre", "character varying(150)", False),
        ("email", "character varying(200)", False),
        ("activo", "boolean", False),
        ("creado_en", "timestamp with time zone", False),
    ],
    "clientes": [
        ("razon_social", "character varying(200)", False),
        ("ruc", "character varying(20)", False),
        ("activo", "boolean", False),
    ],
    "destinatarios": [
        ("nombre", "character varying(200)", False),
        ("documento", "character varying(20)", True),
        ("telefono", "character varying(30)", True),
    ],
    "ubigeos": [
        ("codigo", "character varying(10)", False),
        ("departamento", "character varying(80)", False),
        ("provincia", "character varying(80)", False),
        ("distrito", "character varying(80)", False),
    ],
    "sedes": [
        ("nombre", "character varying(120)", False),
        ("direccion", "character varying(250)", True),
    ],
    "rutas": [
        ("codigo", "character varying(30)", False),
        ("descripcion", "character varying(200)", True),
    ],
    "vehiculos": [
        ("placa", "character varying(15)", False),
        ("capacidad_kg", "numeric(10,2)", True),
    ],
    "couriers": [
        ("nombre", "character varying(150)", False),
        ("documento", "character varying(20)", False),
        ("activo", "boolean", False),
    ],
    "tipos_servicio": [
        ("nombre", "character varying(80)", False),
        ("leadtime_horas", "integer", True),
    ],
    "estados_envio": [
        ("codigo", "character varying(30)", False),
        ("nombre", "character varying(80)", False),
    ],
    "tarifas": [
        ("monto", "numeric(12,2)", False),
        ("vigente_desde", "date", False),
    ],
    "monedas": [
        ("codigo", "character varying(3)", False),
        ("nombre", "character varying(50)", False),
    ],
    "empresas": [
        ("razon_social", "character varying(200)", False),
        ("ruc", "character varying(20)", False),
    ],
    "contratos": [
        ("numero", "character varying(40)", False),
        ("vigente_hasta", "date", True),
    ],
    "motivos_devolucion": [
        ("codigo", "character varying(30)", False),
        ("descripcion", "character varying(200)", False),
    ],
}

#: Tipo lógico del Agente BD por tipo físico (para que RECONCILE compare igual).
_LOGICOS = {
    "character varying": "string",
    "boolean": "boolean",
    "timestamp with time zone": "timestamptz",
    "numeric": "decimal",
    "integer": "integer",
    "date": "date",
    "bigint": "bigint",
}


def _logico(tipo: str) -> str | None:
    for prefijo, logico in _LOGICOS.items():
        if tipo.startswith(prefijo):
            return logico
    return None


def build_schema() -> dict[str, Any]:
    """Contenido del activo ``db_schema`` con las 15 maestras."""
    tablas = []
    for nombre, columnas in MAESTRAS.items():
        pk = (
            f"{nombre.rstrip('s')}_id"
            if not nombre.endswith("es")
            else f"{nombre[:-2]}_id"
        )
        tablas.append(
            {
                "name": nombre,
                "schema_name": None,
                "comment": f"Tabla maestra: {nombre}",
                "columns": [
                    {
                        "name": pk,
                        "type": "bigint",
                        "logical_type": "bigint",
                        "nullable": False,
                        "default": None,
                        "primary_key": True,
                        "comment": None,
                    },
                    *[
                        {
                            "name": columna,
                            "type": tipo,
                            "logical_type": _logico(tipo),
                            "nullable": nulo,
                            "default": None,
                            "primary_key": False,
                            "comment": None,
                        }
                        for columna, tipo, nulo in columnas
                    ],
                ],
                "primary_key": [pk],
                "foreign_keys": [],
                "constraints": [],
                "indexes": [],
            }
        )
    return {"engine": "postgresql", "tables": tablas}


async def seed(borrar: bool = False) -> None:
    async with session_scope() as session:
        repo = InventoryRepository(session)
        existente = await repo.get_system_by_name(SISTEMA)

        if borrar:
            if existente is None:
                print(f"No existe «{SISTEMA}»: nada que borrar.")
                return
            await repo.delete_system(existente)
            print(f"Sistema «{SISTEMA}» eliminado del inventario.")
            return

        system = existente
        if system is None:
            system = await repo.create_system(
                name=SISTEMA,
                kind=InventorySystemKind.DESTINO,
                description=(
                    "Sistema destino del programa de modernización. Esquema "
                    "compartido por los microservicios. NOMBRES SINTÉTICOS: el "
                    "documento de modernización no está en el repositorio."
                ),
                status=InventorySystemStatus.EN_CONSTRUCCION,
                stack=[
                    {"layer": "cloud", "technology": "AWS"},
                    {
                        "layer": "database_relational",
                        "technology": "PostgreSQL",
                        "version": "16",
                    },
                    {
                        "layer": "framework_frontend",
                        "technology": "React",
                        "version": "19",
                    },
                ],
            )
            print(f"Sistema «{SISTEMA}» creado.")
        else:
            print(f"Sistema «{SISTEMA}» ya existía: se añade una versión nueva.")

        contenido = build_schema()
        asset = await repo.add_asset_version(
            system_id=system.id,
            asset_type=InventoryAssetType.DB_SCHEMA,
            name="core",
            content=contenido,
            origin=InventoryAssetOrigin.MANUAL,
            origin_ref="seed de demostración (nombres sintéticos)",
            description="Esquema compartido: tablas maestras del TMS moderno.",
        )
        print(
            f"Activo «core» v{asset.version} con "
            f"{len(contenido['tables'])} tablas maestras."
        )
        print(f"\nAbre:  /inventario/{system.id}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--borrar", action="store_true", help="Elimina el sistema de demostración."
    )
    args = parser.parse_args()
    asyncio.run(seed(borrar=args.borrar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
