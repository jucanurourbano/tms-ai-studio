"""Nodo ER_DIAGRAM: diagrama entidad-relación en Mermaid, **determinista**.

Mismo principio que el nodo DIAGRAMS del Agente Arquitectura: el diagrama se
construye desde el modelo ya validado, no lo escribe el LLM. Así la sintaxis Mermaid
es válida por construcción y el diagrama nunca contradice a las tablas.

Notación de cardinalidad (``erDiagram`` de Mermaid):

- ``||--o{`` uno a muchos: la FK admite varias filas hijas (el caso normal).
- ``||--||`` uno a uno: la FK es única, así que solo puede haber una fila hija.
- El lado izquierdo pasa a ``|o`` cuando la FK admite nulos: la fila hija puede
  existir sin padre.
"""

import re


def _mid(name: str) -> str:
    """Identificador seguro para Mermaid (alfanumérico y guion bajo)."""
    return re.sub(r"[^0-9A-Za-z_]", "_", name or "")


def _label(text: str) -> str:
    """Etiqueta de relación: una línea, sin comillas ni caracteres conflictivos."""
    limpio = " ".join((text or "").split()).replace('"', "'")
    return limpio[:40] or "relaciona"


def _attribute_type(column: dict) -> str:
    """Tipo del atributo: el **lógico**, que es siempre un único token.

    Se usa el tipo lógico y no el físico a propósito: ``NUMERIC(12,2)`` llevaría
    paréntesis y comas, que rompen el parseo de atributos de Mermaid.
    """
    return _mid(column.get("logical_type") or "string")


def build_er_diagram(tables: list[dict], *, with_attributes: bool = True) -> dict:
    """Genera el bloque ``er_diagram`` del artefacto (Mermaid ``erDiagram``)."""
    lineas = ["erDiagram"]

    if with_attributes:
        for table in tables:
            lineas.append(f"  {_mid(table['name'])} {{")
            for column in table.get("columns", []):
                marca = _key_marker(table, column)
                sufijo = f" {marca}" if marca else ""
                lineas.append(
                    f"    {_attribute_type(column)} {_mid(column['name'])}{sufijo}"
                )
            lineas.append("  }")

    for table in tables:
        for fk in table.get("foreign_keys", []):
            lineas.append(_relationship_line(table, fk))

    return {"format": "mermaid", "code": "\n".join(lineas)}


def _key_marker(table: dict, column: dict) -> str:
    """Marca ``PK``/``FK``/``UK`` del atributo (Mermaid solo admite una)."""
    if column.get("is_primary_key"):
        return "PK"
    if any(column["name"] in fk["columns"] for fk in table.get("foreign_keys", [])):
        return "FK"
    if any(
        column["name"] in uq["columns"] for uq in table.get("unique_constraints", [])
    ):
        return "UK"
    return ""


def _relationship_line(table: dict, fk: dict) -> str:
    """Línea de relación padre→hijo con la cardinalidad correcta."""
    columnas = {c["name"]: c for c in table.get("columns", [])}
    opcional = any(columnas.get(c, {}).get("nullable", True) for c in fk["columns"])
    unica = any(
        set(uq["columns"]) == set(fk["columns"])
        for uq in table.get("unique_constraints", [])
    ) or set(fk["columns"]) == set((table.get("primary_key") or {}).get("columns", []))

    izquierda = "|o" if opcional else "||"
    derecha = "||" if unica else "o{"
    etiqueta = _label(fk.get("relationship_ref") or fk.get("name"))
    return (
        f"  {_mid(fk['references_table'])} {izquierda}--{derecha} "
        f'{_mid(table["name"])} : "{etiqueta}"'
    )
