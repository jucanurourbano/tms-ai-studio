"""Agente BD (cuarto agente del ISDF, fase DISEÑAR).

Consume el ``ArchitectureArtifact`` (gate ``ready_for_next_stage=true``) y, de
forma transitiva, el ``EFArtifact`` de origen —su materia prima principal— para
producir el **modelo de datos físico**: tablas tipadas, claves, índices
justificados, constraints derivadas de las reglas del EF, DDL ejecutable,
datos semilla, diccionario de datos y diagrama entidad-relación.

Principio rector: **el LLM nunca escribe SQL.** Decide semántica (qué tipo
lógico, qué constraint, qué índice se justifica) y Python renderiza el DDL de
forma determinista y lo valida sin LLM.
"""
