"""Export fase (a): CSV/JSON compatible con la importación de ClickUp.

Solo lectura del ``ScrumArtifact`` -> archivo. **Sin token y sin riesgo**: el
usuario importa manualmente. No crea nada en ClickUp.
"""

import csv
import io
from typing import Any

from .mapping import story_rows

# Columnas en el orden del importador de ClickUp.
_COLUMNS = [
    ("list", "List"),
    ("task_name", "Task Name"),
    ("description", "Description"),
    ("status", "Status"),
    ("priority", "Priority"),
    ("points", "Points"),
    ("epic", "Epic"),
    ("tags", "Tags"),
    ("external_key", "External Key"),
]


def to_clickup_rows(artifact: dict[str, Any]) -> list[dict]:
    """Filas estructuradas (JSON) para importar/consumir programáticamente."""
    return story_rows(artifact)


def to_clickup_csv(artifact: dict[str, Any]) -> str:
    """Cadena CSV lista para importar en ClickUp (una fila por historia)."""
    rows = story_rows(artifact)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([header for _key, header in _COLUMNS])
    for row in rows:
        writer.writerow([_render(row.get(key)) for key, _header in _COLUMNS])
    return buffer.getvalue()


def _render(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)
