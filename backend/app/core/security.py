"""Utilidades de seguridad: hashing de contraseñas y JWT.

- Contraseñas: **bcrypt** a través de ``passlib`` (nunca se guardan ni loguean en
  claro; solo se persiste el hash).
- Tokens: **JWT** firmados con ``python-jose`` (HS256 por defecto). El ``sub`` del
  token es el id del usuario; la expiración proviene de ``settings``.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config.settings import settings

# ``deprecated="auto"`` permite migrar el esquema de hash en el futuro sin romper
# los hashes existentes.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Devuelve el hash bcrypt de una contraseña en claro."""
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verifica una contraseña en claro contra su hash bcrypt."""
    return _pwd_context.verify(password, password_hash)


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    """Crea un JWT de acceso cuyo ``sub`` es el id del usuario."""
    minutes = expires_minutes or settings.JWT_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """Valida un JWT y devuelve su ``sub`` (id de usuario), o ``None`` si es
    inválido, está mal firmado o expiró."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None
