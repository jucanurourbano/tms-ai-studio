"""Guard fail-closed de ClickUp (cuenta COMPARTIDA por la organización).

Toda operación de escritura DEBE pasar por ``assert_target_authorized(list_id)``.
Garantía estructural (CLAUDE.md):

- **Sin allowlist configurada ⇒ no se escribe nada** (fail-closed).
- El destino solo es válido si la lista está en ``CLICKUP_ALLOWED_LIST_IDS`` **y**
  (cuando se puede resolver) pertenece al ``CLICKUP_SPACE_ID`` de Sistemas.

En la fase (a) (export) no se llama a la API: el guard se usa igualmente como
única puerta de escritura para la fase (b). ``resolve_space`` es inyectable para
poder probar la resolución ``list → folder → space`` sin API real.
"""

from typing import Callable, Optional

from ai.errors import ClickUpForbiddenError
from app.config.settings import settings


def clickup_configured() -> bool:
    """True solo si hay token, espacio de Sistemas y allowlist no vacía."""
    return bool(
        settings.CLICKUP_API_TOKEN
        and settings.CLICKUP_SPACE_ID
        and settings.CLICKUP_ALLOWED_LIST_IDS
    )


def assert_target_authorized(
    list_id: str,
    *,
    resolve_space: Optional[Callable[[str], str]] = None,
) -> None:
    """Autoriza (o rechaza) escribir en ``list_id``. Fail-closed.

    - Sin allowlist configurada → ``ClickUpForbiddenError``.
    - ``list_id`` fuera de la allowlist → ``ClickUpForbiddenError``.
    - Si se provee ``resolve_space`` (list → space), exige que el espacio
      resuelto sea exactamente ``CLICKUP_SPACE_ID``.
    """
    allowlist = settings.CLICKUP_ALLOWED_LIST_IDS
    if not allowlist:
        raise ClickUpForbiddenError(
            "ClickUp no está configurado (sin allowlist de listas). "
            "Fail-closed: no se escribe nada."
        )
    if list_id not in allowlist:
        raise ClickUpForbiddenError(
            f"La lista {list_id} no está en la allowlist autorizada de Sistemas."
        )
    if resolve_space is not None:
        space_id = resolve_space(list_id)
        if space_id != settings.CLICKUP_SPACE_ID:
            raise ClickUpForbiddenError(
                f"La lista {list_id} pertenece al espacio {space_id}, no al espacio "
                f"autorizado de Sistemas ({settings.CLICKUP_SPACE_ID})."
            )
