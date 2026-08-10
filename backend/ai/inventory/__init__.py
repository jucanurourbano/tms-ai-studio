"""Ingesta y reconciliación del Inventario de Sistemas.

- ``ddl_import``: dump DDL (.sql) -> contenido estructurado de un activo
  ``db_schema``, con sqlglot y **sin LLM**. Es el gemelo inverso del renderizador
  del Agente BD: allí Python escribe SQL desde un modelo, aquí Python lee SQL
  hacia un modelo. En ninguno de los dos interviene el modelo de lenguaje.
"""
