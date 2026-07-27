"""Matriz de permisos por rol y módulo — **ÚNICA fuente de verdad**.

Este módulo define QUIÉN puede acceder a QUÉ dentro del ISDF y con qué nivel.
Nada más en el backend (ni en el frontend) debe volver a codificar estas reglas:
la API expone los módulos efectivos de cada usuario en ``GET /auth/me`` para que
el cliente pinte la navegación sin duplicar la lógica.

Conceptos
---------
- **Módulo** (:class:`Module`): un agente del ISDF (fase) o la configuración de
  la plataforma. Los agentes aún no implementados ("próximamente") ya tienen su
  módulo declarado, de modo que asignar permisos no requiera tocar el enum.
- **Nivel** (:class:`AccessLevel`): ``READ`` (solo lectura) o ``FULL`` (crear /
  editar / afinar). ``FULL`` **implica** ``READ``.
- **Rol** (:class:`UserRole`): rol funcional del usuario. Da el permiso *base*.
- **Grants** (``user_module_grants``): asignaciones adicionales por usuario que
  **SUMAN** sobre el rol y **nunca restan** (ver :func:`effective_modules`).

Módulos deliberadamente sin rol asignado (solo ``admin``): ``bd`` y ``devops``.
No se les inventó dueño porque el modelo de permisos acordado no los menciona;
cuando el equipo decida a qué rol pertenecen, basta añadirlos a la matriz.
"""

from enum import Enum
from typing import Iterable, Mapping


class Module(str, Enum):
    """Módulos protegibles: un agente del ISDF, o la configuración."""

    EF = "ef"
    SCRUM = "scrum"
    ARQUITECTURA = "arquitectura"
    BD = "bd"
    API = "api"
    BACKEND = "backend"
    FRONTEND = "frontend"
    QA = "qa"
    DEVOPS = "devops"
    #: Gestión de usuarios y ajustes de la plataforma.
    CONFIG = "config"


class AccessLevel(str, Enum):
    """Nivel de acceso a un módulo. ``FULL`` implica ``READ``."""

    READ = "read"
    FULL = "full"


class UserRole(str, Enum):
    """Rol funcional del usuario (permiso base según :data:`ROLE_MATRIX`)."""

    ADMIN = "admin"
    PROCESOS = "procesos"
    ANALISTA = "analista"
    ARQUITECTO = "arquitecto"
    DEVELOPER = "developer"
    QA = "qa"


#: Rol por defecto de un usuario nuevo y destino de los ``member`` históricos
#: al migrar (ver migración ``0006_roles_por_fase``).
DEFAULT_ROLE = UserRole.ANALISTA

# Orden de los niveles: permite comparar "¿alcanza lo concedido para lo exigido?".
_RANK: dict[AccessLevel, int] = {AccessLevel.READ: 1, AccessLevel.FULL: 2}

#: Módulos de construcción (hoy "próximamente"; el enum ya está preparado).
_CONSTRUCCION = (Module.API, Module.BACKEND, Module.FRONTEND)

#: Matriz rol → {módulo: nivel}. `admin` se construye aparte (FULL en todo).
ROLE_MATRIX: dict[UserRole, dict[Module, AccessLevel]] = {
    UserRole.ADMIN: {module: AccessLevel.FULL for module in Module},
    UserRole.PROCESOS: {
        Module.EF: AccessLevel.FULL,
    },
    UserRole.ANALISTA: {
        Module.EF: AccessLevel.FULL,
        Module.SCRUM: AccessLevel.FULL,
    },
    UserRole.ARQUITECTO: {
        Module.ARQUITECTURA: AccessLevel.FULL,
        Module.EF: AccessLevel.READ,
        Module.SCRUM: AccessLevel.READ,
    },
    UserRole.DEVELOPER: {
        **{module: AccessLevel.FULL for module in _CONSTRUCCION},
        Module.ARQUITECTURA: AccessLevel.READ,
        Module.SCRUM: AccessLevel.READ,
    },
    UserRole.QA: {
        Module.QA: AccessLevel.FULL,
        Module.SCRUM: AccessLevel.READ,
    },
}


#: Nombre legible de cada módulo, para los mensajes de error de la API (403).
MODULE_LABELS: dict[Module, str] = {
    Module.EF: "Agente EF",
    Module.SCRUM: "Agente Scrum",
    Module.ARQUITECTURA: "Agente Arquitectura",
    Module.BD: "Agente Base de Datos",
    Module.API: "Agente API",
    Module.BACKEND: "Agente Backend",
    Module.FRONTEND: "Agente Frontend",
    Module.QA: "Agente QA",
    Module.DEVOPS: "Agente DevOps",
    Module.CONFIG: "Configuración",
}

#: Nombre legible de cada rol (mensajes de error y panel de administración).
ROLE_LABELS: dict[UserRole, str] = {
    UserRole.ADMIN: "Administrador",
    UserRole.PROCESOS: "Procesos",
    UserRole.ANALISTA: "Analista",
    UserRole.ARQUITECTO: "Arquitecto",
    UserRole.DEVELOPER: "Developer",
    UserRole.QA: "QA",
}


def satisfies(granted: AccessLevel, required: AccessLevel) -> bool:
    """``True`` si el nivel concedido alcanza el exigido (``FULL`` cubre ``READ``)."""
    return _RANK[granted] >= _RANK[required]


def role_modules(role: UserRole) -> dict[Module, AccessLevel]:
    """Permisos base del rol (copia, para que nadie mute la matriz)."""
    return dict(ROLE_MATRIX.get(role, {}))


def effective_modules(
    role: UserRole,
    grants: Iterable[tuple[Module, AccessLevel]] = (),
) -> dict[Module, AccessLevel]:
    """Módulos efectivos del usuario: rol **+** grants, quedándose con el mayor.

    Los grants solo pueden **sumar**: si el rol ya concede ``FULL`` y un grant
    dice ``READ``, se conserva ``FULL``. Así una asignación adicional nunca
    degrada el permiso que da el rol.
    """
    effective = role_modules(role)
    for module, level in grants:
        current = effective.get(module)
        if current is None or satisfies(level, current):
            effective[module] = level
    return effective


def has_access(
    effective: Mapping[Module, AccessLevel],
    module: Module,
    level: AccessLevel = AccessLevel.READ,
) -> bool:
    """``True`` si los módulos efectivos cubren ``module`` con al menos ``level``."""
    granted = effective.get(module)
    return granted is not None and satisfies(granted, level)


def can(
    role: UserRole,
    grants: Iterable[tuple[Module, AccessLevel]],
    module: Module,
    level: AccessLevel = AccessLevel.READ,
) -> bool:
    """Atajo: resuelve los módulos efectivos y comprueba el acceso."""
    return has_access(effective_modules(role, grants), module, level)
