"""Agente API (quinto agente del ISDF, fase CONSTRUIR).

Consume el ``DatabaseArtifact`` (gate ``ready_for_next_stage``) y, transitivamente,
Arquitectura, Scrum y EF, para producir el ``ApiArtifact v1.0.0``: la
especificación de las APIs que consumirán los Agentes Backend y Frontend.

Dos reglas rectoras gobiernan el agente (ver ``docs/diseno-agente-api.md``):

1. **El LLM nunca escribe OpenAPI.** Decide semántica; Python renderiza el
   documento 3.1 y lo valida sin LLM.
2. **La autorización es fail-closed.** Lo que nadie autorizó explícitamente queda
   denegado, y la ambigüedad se resuelve con una pregunta bloqueante, no con un
   permiso por defecto.
"""
