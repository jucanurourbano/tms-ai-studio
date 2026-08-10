"""Tests de la matriz de permisos (``app/core/permissions.py``).

Cubren la matriz COMPLETA rol × módulo × nivel: para cada rol se declara el
acceso esperado y se comprueba tanto lo permitido como lo denegado, de modo que
ampliar un permiso por error rompa un test. También cubren que los grants SUMAN
y nunca restan.
"""

import pytest

from app.core.permissions import (
    ROLE_MATRIX,
    AccessLevel,
    Module,
    UserRole,
    can,
    effective_modules,
    has_access,
    role_modules,
    satisfies,
)

FULL = AccessLevel.FULL
READ = AccessLevel.READ

# Acceso ESPERADO por rol (lo que no aparece = sin acceso de ningún tipo).
# Es una declaración independiente de ROLE_MATRIX a propósito: si alguien cambia
# la matriz, este test lo detecta en vez de acompañarlo.
ESPERADO: dict[UserRole, dict[Module, AccessLevel]] = {
    UserRole.ADMIN: {module: FULL for module in Module},
    UserRole.PROCESOS: {Module.EF: FULL, Module.INVENTARIO: READ},
    UserRole.ANALISTA: {
        Module.EF: FULL,
        Module.SCRUM: FULL,
        Module.INVENTARIO: READ,
    },
    UserRole.ARQUITECTO: {
        Module.ARQUITECTURA: FULL,
        Module.BD: FULL,
        Module.INVENTARIO: FULL,
        Module.EF: READ,
        Module.SCRUM: READ,
    },
    UserRole.DEVELOPER: {
        Module.API: FULL,
        Module.BACKEND: FULL,
        Module.FRONTEND: FULL,
        Module.ARQUITECTURA: READ,
        Module.BD: READ,
        Module.SCRUM: READ,
        Module.INVENTARIO: READ,
    },
    UserRole.QA: {Module.QA: FULL, Module.SCRUM: READ, Module.INVENTARIO: READ},
}


def test_todos_los_roles_estan_en_la_matriz():
    """Ningún rol se queda sin fila (un rol sin matriz no tendría acceso a nada)."""
    assert set(ROLE_MATRIX) == set(UserRole)
    assert set(ESPERADO) == set(UserRole)


@pytest.mark.parametrize("role", list(UserRole))
def test_matriz_completa_por_rol(role: UserRole):
    """Para cada rol: cada módulo × cada nivel, permitido o denegado según ESPERADO."""
    esperado = ESPERADO[role]
    for module in Module:
        concedido = esperado.get(module)
        for nivel in (READ, FULL):
            permitido = concedido is not None and satisfies(concedido, nivel)
            assert can(role, (), module, nivel) is permitido, (
                f"{role.value} / {module.value} / {nivel.value}: "
                f"se esperaba {'permitido' if permitido else 'denegado'}"
            )


def test_full_implica_read():
    """``FULL`` cubre ``READ``; ``READ`` no cubre ``FULL``."""
    assert satisfies(FULL, READ) is True
    assert satisfies(FULL, FULL) is True
    assert satisfies(READ, READ) is True
    assert satisfies(READ, FULL) is False


def test_procesos_solo_toca_ef_y_consulta_el_inventario():
    """`procesos` tiene FULL en EF, lectura del inventario y NADA más.

    El inventario es la excepción consciente (INV1): quien levanta requisitos
    necesita poder consultar qué existe ya antes de pedir que se construya de
    nuevo. Negarle esa lectura sería justo el error que el módulo viene a
    corregir. En todo lo demás sigue sin acceso ni de lectura.
    """
    assert can(UserRole.PROCESOS, (), Module.EF, FULL)
    assert can(UserRole.PROCESOS, (), Module.INVENTARIO, READ)
    assert not can(UserRole.PROCESOS, (), Module.INVENTARIO, FULL)
    for module in Module:
        if module in (Module.EF, Module.INVENTARIO):
            continue
        assert not can(UserRole.PROCESOS, (), module, READ)


def test_el_inventario_lo_lee_todo_el_mundo_y_lo_cura_el_arquitecto():
    """INV1: transversal en lectura, curado por quien responde de su calidad.

    Un activo mal cargado envenena la fase RECONCILE de Arquitectura, BD y API a
    la vez, así que escribir en el inventario no es una operación cualquiera.
    """
    for role in UserRole:
        assert can(
            role, (), Module.INVENTARIO, READ
        ), f"{role.value} no puede consultar el inventario"
    for role in (UserRole.ADMIN, UserRole.ARQUITECTO):
        assert can(role, (), Module.INVENTARIO, FULL)
    for role in (UserRole.PROCESOS, UserRole.ANALISTA, UserRole.DEVELOPER, UserRole.QA):
        assert not can(
            role, (), Module.INVENTARIO, FULL
        ), f"{role.value} no debería poder escribir en el inventario"


def test_arquitecto_lee_ef_y_scrum_pero_no_escribe():
    """El arquitecto ve el insumo (EF/Scrum) sin poder modificarlo."""
    assert can(UserRole.ARQUITECTO, (), Module.EF, READ)
    assert not can(UserRole.ARQUITECTO, (), Module.EF, FULL)
    assert can(UserRole.ARQUITECTO, (), Module.SCRUM, READ)
    assert not can(UserRole.ARQUITECTO, (), Module.SCRUM, FULL)
    assert can(UserRole.ARQUITECTO, (), Module.ARQUITECTURA, FULL)


def test_solo_admin_accede_a_configuracion():
    """`config` (usuarios/ajustes) es exclusivo de admin vía rol."""
    assert can(UserRole.ADMIN, (), Module.CONFIG, FULL)
    for role in UserRole:
        if role is UserRole.ADMIN:
            continue
        assert not can(role, (), Module.CONFIG, READ)


def test_devops_declarado_sin_dueño_salvo_admin():
    """`devops` existe en el enum pero solo lo alcanza admin (sin dueño acordado)."""
    assert can(UserRole.ADMIN, (), Module.DEVOPS, FULL)
    for role in UserRole:
        if role is UserRole.ADMIN:
            continue
        assert not can(role, (), Module.DEVOPS, READ)


def test_bd_es_del_arquitecto_y_el_developer_solo_lo_lee():
    """`bd` (BD0): FULL para quien diseña datos, READ hacia adelante en la cadena.

    El arquitecto diseña el modelo físico (misma fase DISEÑAR). El developer lo
    **consume** desde api/backend/frontend, así que lo lee sin poder editarlo. El
    analista no lo alcanza: sus módulos están *antes* de `bd` en la cadena.
    """
    assert can(UserRole.ARQUITECTO, (), Module.BD, FULL)
    assert can(UserRole.DEVELOPER, (), Module.BD, READ)
    assert not can(UserRole.DEVELOPER, (), Module.BD, FULL)
    for role in (UserRole.ANALISTA, UserRole.PROCESOS, UserRole.QA):
        assert not can(role, (), Module.BD, READ)


def test_grant_de_bd_eleva_al_developer_a_full():
    """Un developer con grant de `bd` obtiene FULL sin tocar la matriz (acordado)."""
    grants = [(Module.BD, FULL)]
    assert can(UserRole.DEVELOPER, grants, Module.BD, FULL)
    # Y no abre nada más de la fase DISEÑAR.
    assert not can(UserRole.DEVELOPER, grants, Module.ARQUITECTURA, FULL)


# --- grants: SUMAN, nunca restan --------------------------------------------


def test_grant_añade_modulo_que_el_rol_no_da():
    """Un grant concede acceso a un módulo ausente en el rol."""
    assert not can(UserRole.PROCESOS, (), Module.SCRUM, READ)
    grants = [(Module.SCRUM, READ)]
    assert can(UserRole.PROCESOS, grants, Module.SCRUM, READ)
    # Solo lo concedido: READ no habilita FULL.
    assert not can(UserRole.PROCESOS, grants, Module.SCRUM, FULL)


def test_grant_eleva_de_read_a_full():
    """Un grant FULL sobre un módulo que el rol da en READ eleva el nivel."""
    assert not can(UserRole.ARQUITECTO, (), Module.SCRUM, FULL)
    grants = [(Module.SCRUM, FULL)]
    assert can(UserRole.ARQUITECTO, grants, Module.SCRUM, FULL)


def test_grant_inferior_no_degrada_el_rol():
    """Un grant READ sobre un módulo con FULL por rol NO resta: sigue en FULL."""
    grants = [(Module.EF, READ)]
    efectivos = effective_modules(UserRole.ANALISTA, grants)
    assert efectivos[Module.EF] is FULL
    assert can(UserRole.ANALISTA, grants, Module.EF, FULL)


def test_grants_no_afectan_a_otros_modulos():
    """Conceder un módulo no abre ninguno más.

    `procesos` parte de `ef` (FULL) + `inventario` (READ, transversal): el grant
    añade `arquitectura` y NADA más.
    """
    grants = [(Module.ARQUITECTURA, FULL)]
    efectivos = effective_modules(UserRole.PROCESOS, grants)
    assert set(efectivos) == {Module.EF, Module.INVENTARIO, Module.ARQUITECTURA}


def test_grant_de_config_concede_configuracion():
    """Los grants también alcanzan `config` (es lo que permite el modelo aditivo).

    La protección contra escalada de privilegios no está aquí, sino en los
    endpoints que mutan roles/grants, que exigen rol admin estricto.
    """
    assert can(UserRole.QA, [(Module.CONFIG, FULL)], Module.CONFIG, FULL)


def test_role_modules_devuelve_copia():
    """Mutar el resultado no puede corromper la matriz global."""
    modules = role_modules(UserRole.PROCESOS)
    modules[Module.DEVOPS] = FULL
    assert Module.DEVOPS not in ROLE_MATRIX[UserRole.PROCESOS]


def test_has_access_con_modulo_ausente():
    """Un módulo que no está en los efectivos siempre deniega."""
    assert has_access({Module.EF: FULL}, Module.EF, FULL)
    assert not has_access({Module.EF: FULL}, Module.QA, READ)
    assert not has_access({}, Module.EF, READ)
