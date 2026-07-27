"""Dependencias de **autenticación** de FastAPI (identidad, no permisos).

- ``get_current_user``: exige un JWT válido en ``Authorization: Bearer <token>``
  y devuelve el ``User``. Sin token / token inválido -> ``AuthError`` (401).
- ``get_optional_user``: variante que devuelve ``None`` en vez de fallar (la usa
  el registro para soportar el bootstrap del primer usuario sin auth).

La **autorización** (403 por rol/módulo) vive aparte, en
``app/dependencies/permissions.py``: ``require_module`` y ``require_admin_role``.
"""

from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.dependencies.database import get_session
from app.errors import AuthError
from app.models.user import User
from app.services.auth_service import AuthService

# ``auto_error=False``: no lanzamos el 403 por defecto de FastAPI; gestionamos el
# caso "sin token" nosotros para devolver un ``ApiResponse`` uniforme (401).
_bearer = HTTPBearer(auto_error=False, description="JWT de acceso (Bearer).")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resuelve el usuario autenticado o lanza 401."""
    if credentials is None or not credentials.credentials:
        raise AuthError("No autenticado: falta el token de acceso.")
    user_id = decode_access_token(credentials.credentials)
    return await AuthService(session).authenticate_token(user_id)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> Optional[User]:
    """Devuelve el usuario si hay un token válido; ``None`` en caso contrario."""
    if credentials is None or not credentials.credentials:
        return None
    user_id = decode_access_token(credentials.credentials)
    try:
        return await AuthService(session).authenticate_token(user_id)
    except AuthError:
        return None
