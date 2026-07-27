"""Dependencias de autorización por módulo del ISDF.

``require_module(module, level)`` es la única puerta de entrada a los endpoints
protegidos: resuelve los permisos efectivos del usuario autenticado (rol +
grants, ver ``app/core/permissions.py``) y deniega con **403** y un mensaje claro
en español si no alcanzan.

Uso típico — lectura a nivel de router y escritura por endpoint::

    router = APIRouter(
        prefix="/ef",
        dependencies=[Depends(require_module(Module.EF, AccessLevel.READ))],
    )

    @router.post(
        "/analyze",
        dependencies=[Depends(require_module(Module.EF, AccessLevel.FULL))],
    )
    async def analyze(...): ...
"""

from typing import Awaitable, Callable

from fastapi import Depends

from app.core.permissions import (
    MODULE_LABELS,
    ROLE_LABELS,
    AccessLevel,
    Module,
    can,
    effective_modules,
)
from app.dependencies.current_user import get_current_user
from app.errors import ForbiddenError
from app.models.user import User, UserRole


def _denial_message(user: User, module: Module, level: AccessLevel) -> str:
    """Mensaje de 403 explicando QUÉ falta y POR QUÉ (nunca un 'no autorizado' seco)."""
    modulo = MODULE_LABELS.get(module, module.value)
    rol = ROLE_LABELS.get(user.role, user.role.value)
    tiene_lectura = can(user.role, user.grant_pairs(), module, AccessLevel.READ)
    if level is AccessLevel.FULL and tiene_lectura:
        return (
            f"Tu rol ({rol}) solo permite consultar «{modulo}», no modificarlo. "
            "Pide a un administrador acceso de edición a este módulo."
        )
    return (
        f"Tu rol ({rol}) no tiene acceso al módulo «{modulo}». "
        "Pide a un administrador que te lo asigne."
    )


def require_module(
    module: Module, level: AccessLevel = AccessLevel.READ
) -> Callable[..., Awaitable[User]]:
    """Construye una dependencia que exige ``level`` sobre ``module``.

    Devuelve el usuario autenticado si tiene acceso; lanza ``ForbiddenError``
    (403) en caso contrario. La autenticación (401) la resuelve antes
    ``get_current_user``.
    """

    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if not can(user.role, user.grant_pairs(), module, level):
            raise ForbiddenError(_denial_message(user, module, level))
        return user

    return _dependency


async def require_admin_role(user: User = Depends(get_current_user)) -> User:
    """Exige el **rol** ``admin`` estricto, ignorando los grants.

    Reservado a las operaciones que pueden elevar privilegios (cambiar el rol de
    un usuario, editar sus grants, crear otro admin). Si bastara con
    ``require_module(CONFIG, FULL)``, conceder un grant de ``config`` convertiría
    a cualquiera en administrador de facto: podría auto-asignarse cualquier
    permiso. Fail-closed a propósito.
    """
    if user.role is not UserRole.ADMIN:
        raise ForbiddenError(
            "Esta operación requiere el rol de Administrador "
            "(no puede concederse mediante accesos adicionales)."
        )
    return user


def user_modules(user: User) -> dict[str, str]:
    """Módulos efectivos del usuario, serializables para la API.

    Lo consume ``GET /auth/me`` para que el frontend pinte la navegación sin
    reimplementar la matriz.
    """
    return {
        module.value: level.value
        for module, level in effective_modules(user.role, user.grant_pairs()).items()
    }
