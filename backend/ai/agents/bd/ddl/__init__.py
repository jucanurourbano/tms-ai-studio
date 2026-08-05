"""Generación y validación deterministas del DDL.

El LLM nunca escribe SQL: aquí se **renderiza** el modelo físico ya validado al
dialecto del motor y se comprueba, sin base de datos, que lo generado es correcto.
"""

from .render import build_ddl_scripts, render_type
from .validate import validate_ddl

__all__ = ["build_ddl_scripts", "render_type", "validate_ddl"]
