"""Nodo DICTIONARY: diccionario de datos derivado del modelo (sin LLM).

Una fila por columna, con su tipo físico, obligatoriedad, papel en las claves,
descripción, ejemplo y trazabilidad al EF. **No hay una segunda pasada al modelo**:
las descripciones y los ejemplos ya los produjo TABLES, así que el diccionario es
una proyección de ``tables[]`` y no una versión paralela del mismo contenido que
pudiera contradecirla.
"""

from .ddl.render import render_type


def _key_marker(table: dict, column: dict) -> str:
    """Papel de la columna en las claves: ``PK``, ``FK``, ``UQ`` o su combinación."""
    marcas: list[str] = []
    if column.get("is_primary_key"):
        marcas.append("PK")
    if any(column["name"] in fk["columns"] for fk in table.get("foreign_keys", [])):
        marcas.append("FK")
    if any(
        column["name"] in uq["columns"] for uq in table.get("unique_constraints", [])
    ):
        marcas.append("UQ")
    return ",".join(marcas) or "—"


def build_data_dictionary(tables: list[dict], engine: str) -> list[dict]:
    """Construye el diccionario de datos completo, en el orden del esquema."""
    entradas: list[dict] = []
    for table in tables:
        for column in table.get("columns", []):
            entradas.append(
                {
                    "id": f"DIC-{len(entradas) + 1:04d}",
                    "table": table["name"],
                    "column": column["name"],
                    "type": column.get("type") or render_type(column, engine),
                    "nullable": bool(column.get("nullable", True)),
                    "key": _key_marker(table, column),
                    "description": column.get("description"),
                    "example": column.get("example"),
                    "source_refs": list(column.get("source_refs") or []),
                    "origin": column.get("origin") or "derived",
                }
            )
    return entradas
