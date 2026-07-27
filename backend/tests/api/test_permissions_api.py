"""Tests de la APLICACIÓN de permisos en la API (matriz + grants).

Recorren la matriz completa contra endpoints reales: por cada rol se comprueba
lectura y escritura de EF / Scrum / Arquitectura / Configuración, más los grants
que suman y las guardas de gestión de usuarios.

**Ningún test ejecuta un análisis real.** Para probar que una escritura está
PERMITIDA se envía una petición que el permiso deja pasar pero que el handler
rechaza antes de invocar al agente (Content-Type no soportado, o un job de origen
inexistente): basta comprobar que la respuesta **no** es 403. Las escrituras
denegadas sí devuelven 403 exacto, y ahí el handler nunca se ejecuta.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.permissions import AccessLevel, Module, UserRole
from app.dependencies.database import get_session
from main import app

PASSWORD = "superseguro1"


@pytest_asyncio.fixture
async def client(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _login(client, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


async def _bootstrap_admin(client) -> str:
    """Crea el primer usuario (admin por bootstrap) y devuelve su token."""
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@urbano.com.pe",
            "full_name": "Admin Uno",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["role"] == "admin"
    return await _login(client, "admin@urbano.com.pe")


async def _crear_usuario(client, admin_token: str, role: UserRole) -> tuple[str, str]:
    """Registra un usuario con el rol dado. Devuelve ``(user_id, token)``."""
    email = f"{role.value}@urbano.com.pe"
    r = await client.post(
        "/api/v1/auth/register",
        headers=_auth(admin_token),
        json={
            "email": email,
            "full_name": f"Usuario {role.value}",
            "password": PASSWORD,
            "role": role.value,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["role"] == role.value
    return r.json()["data"]["id"], await _login(client, email)


# --- sondas por módulo -------------------------------------------------------
# Para cada módulo: una petición de LECTURA y una de ESCRITURA. La de escritura
# está construida para NO llegar a ejecutar el agente (ver docstring del módulo).


async def _leer(client, token: str, module: Module):
    rutas = {
        Module.EF: "/api/v1/ef/jobs",
        Module.SCRUM: "/api/v1/scrum/jobs",
        Module.ARQUITECTURA: "/api/v1/arquitectura/jobs",
        Module.CONFIG: "/api/v1/auth/users",
    }
    return await client.get(rutas[module], headers=_auth(token))


async def _escribir(client, token: str, module: Module):
    if module is Module.EF:
        # Content-Type no soportado: si el permiso pasa, el handler responde 400
        # sin tocar el pipeline.
        return await client.post(
            "/api/v1/ef/analyze",
            headers={**_auth(token), "content-type": "text/plain"},
            content="lo que sea",
        )
    if module is Module.SCRUM:
        # Job EF inexistente: el gate corta antes de ejecutar el grafo.
        return await client.post(
            "/api/v1/scrum/plans",
            headers=_auth(token),
            json={"ef_job_id": "NO_EXISTE"},
        )
    if module is Module.ARQUITECTURA:
        return await client.post(
            "/api/v1/arquitectura/designs",
            headers=_auth(token),
            json={"scrum_job_id": "NO_EXISTE"},
        )
    if module is Module.CONFIG:
        # Registrar un usuario es escritura de configuración.
        return await client.post(
            "/api/v1/auth/register",
            headers=_auth(token),
            json={
                "email": "nuevo.sonda@urbano.com.pe",
                "full_name": "Sonda",
                "password": PASSWORD,
                "role": UserRole.ANALISTA.value,
            },
        )
    raise AssertionError(f"módulo sin sonda: {module}")


# Acceso esperado por rol sobre los módulos que HOY tienen endpoints.
# (api/backend/frontend/qa/bd/devops están en el enum pero aún sin API.)
ESPERADO: dict[UserRole, dict[Module, AccessLevel | None]] = {
    UserRole.PROCESOS: {
        Module.EF: AccessLevel.FULL,
        Module.SCRUM: None,
        Module.ARQUITECTURA: None,
        Module.CONFIG: None,
    },
    UserRole.ANALISTA: {
        Module.EF: AccessLevel.FULL,
        Module.SCRUM: AccessLevel.FULL,
        Module.ARQUITECTURA: None,
        Module.CONFIG: None,
    },
    UserRole.ARQUITECTO: {
        Module.EF: AccessLevel.READ,
        Module.SCRUM: AccessLevel.READ,
        Module.ARQUITECTURA: AccessLevel.FULL,
        Module.CONFIG: None,
    },
    UserRole.DEVELOPER: {
        Module.EF: None,
        Module.SCRUM: AccessLevel.READ,
        Module.ARQUITECTURA: AccessLevel.READ,
        Module.CONFIG: None,
    },
    UserRole.QA: {
        Module.EF: None,
        Module.SCRUM: AccessLevel.READ,
        Module.ARQUITECTURA: None,
        Module.CONFIG: None,
    },
}


@pytest.mark.parametrize("role", list(ESPERADO))
async def test_matriz_aplicada_en_la_api(client, role: UserRole):
    """Cada rol accede EXACTAMENTE a lo que dice la matriz (lectura y escritura)."""
    admin_token = await _bootstrap_admin(client)
    _, token = await _crear_usuario(client, admin_token, role)

    for module, nivel in ESPERADO[role].items():
        # --- lectura ---
        r = await _leer(client, token, module)
        if nivel is None:
            assert r.status_code == 403, (
                f"{role.value} NO debería leer {module.value} "
                f"(recibido {r.status_code})"
            )
        else:
            assert r.status_code == 200, (
                f"{role.value} debería leer {module.value} "
                f"(recibido {r.status_code}: {r.text[:200]})"
            )

        # --- escritura ---
        r = await _escribir(client, token, module)
        if nivel is AccessLevel.FULL:
            assert (
                r.status_code != 403
            ), f"{role.value} debería poder escribir en {module.value}"
        else:
            assert r.status_code == 403, (
                f"{role.value} NO debería escribir en {module.value} "
                f"(recibido {r.status_code})"
            )


async def test_admin_accede_a_todo(client):
    """El admin lee y escribe en todos los módulos con API."""
    token = await _bootstrap_admin(client)
    for module in (Module.EF, Module.SCRUM, Module.ARQUITECTURA, Module.CONFIG):
        assert (await _leer(client, token, module)).status_code == 200
        assert (await _escribir(client, token, module)).status_code != 403


async def test_403_explica_el_motivo_en_español(client):
    """El 403 dice qué falta: sin acceso al módulo vs. solo lectura."""
    admin_token = await _bootstrap_admin(client)

    # Sin acceso al módulo.
    _, procesos = await _crear_usuario(client, admin_token, UserRole.PROCESOS)
    r = await _leer(client, procesos, Module.ARQUITECTURA)
    assert r.status_code == 403
    mensaje = r.json()["message"]
    assert "no tiene acceso" in mensaje
    assert "Arquitectura" in mensaje

    # Con lectura pero sin edición.
    _, arquitecto = await _crear_usuario(client, admin_token, UserRole.ARQUITECTO)
    r = await _escribir(client, arquitecto, Module.EF)
    assert r.status_code == 403
    mensaje = r.json()["message"]
    assert "solo permite consultar" in mensaje
    assert "Agente EF" in mensaje


# --- /auth/me expone los permisos resueltos ---------------------------------


async def test_me_devuelve_rol_y_modulos_efectivos(client):
    """``/auth/me`` trae el rol y los módulos ya resueltos (rol + grants)."""
    admin_token = await _bootstrap_admin(client)
    _, token = await _crear_usuario(client, admin_token, UserRole.ARQUITECTO)

    r = await client.get("/api/v1/auth/me", headers=_auth(token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["role"] == "arquitecto"
    assert data["modules"] == {
        "arquitectura": "full",
        "ef": "read",
        "scrum": "read",
    }
    assert data["grants"] == []
    assert "password_hash" not in data


# --- grants: suman sobre el rol ---------------------------------------------


async def test_grant_abre_un_modulo_al_que_el_rol_no_llega(client):
    """Un grant READ de Scrum permite a `procesos` LEER Scrum, no escribirlo."""
    admin_token = await _bootstrap_admin(client)
    user_id, token = await _crear_usuario(client, admin_token, UserRole.PROCESOS)

    assert (await _leer(client, token, Module.SCRUM)).status_code == 403

    r = await client.put(
        f"/api/v1/auth/users/{user_id}/grants",
        headers=_auth(admin_token),
        json={"grants": [{"module": "scrum", "level": "read"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["modules"]["scrum"] == "read"

    assert (await _leer(client, token, Module.SCRUM)).status_code == 200
    assert (await _escribir(client, token, Module.SCRUM)).status_code == 403


async def test_grant_full_habilita_escritura(client):
    """Un grant FULL sobre Scrum permite al arquitecto escribir en Scrum."""
    admin_token = await _bootstrap_admin(client)
    user_id, token = await _crear_usuario(client, admin_token, UserRole.ARQUITECTO)

    assert (await _escribir(client, token, Module.SCRUM)).status_code == 403

    r = await client.put(
        f"/api/v1/auth/users/{user_id}/grants",
        headers=_auth(admin_token),
        json={"grants": [{"module": "scrum", "level": "full"}]},
    )
    assert r.status_code == 200
    assert (await _escribir(client, token, Module.SCRUM)).status_code != 403


async def test_grant_inferior_no_resta_al_rol(client):
    """Un grant READ sobre EF no degrada el FULL que da el rol `analista`."""
    admin_token = await _bootstrap_admin(client)
    user_id, token = await _crear_usuario(client, admin_token, UserRole.ANALISTA)

    r = await client.put(
        f"/api/v1/auth/users/{user_id}/grants",
        headers=_auth(admin_token),
        json={"grants": [{"module": "ef", "level": "read"}]},
    )
    assert r.status_code == 200
    assert r.json()["data"]["modules"]["ef"] == "full"
    # Sigue pudiendo escribir en EF.
    assert (await _escribir(client, token, Module.EF)).status_code != 403


async def test_grants_se_reemplazan_por_completo(client):
    """PUT de grants es un *replace*: lo que no viene, se elimina."""
    admin_token = await _bootstrap_admin(client)
    user_id, token = await _crear_usuario(client, admin_token, UserRole.PROCESOS)

    await client.put(
        f"/api/v1/auth/users/{user_id}/grants",
        headers=_auth(admin_token),
        json={
            "grants": [
                {"module": "scrum", "level": "read"},
                {"module": "arquitectura", "level": "read"},
            ]
        },
    )
    assert (await _leer(client, token, Module.SCRUM)).status_code == 200
    assert (await _leer(client, token, Module.ARQUITECTURA)).status_code == 200

    # Se deja solo Scrum: Arquitectura debe cerrarse.
    r = await client.put(
        f"/api/v1/auth/users/{user_id}/grants",
        headers=_auth(admin_token),
        json={"grants": [{"module": "scrum", "level": "read"}]},
    )
    assert r.status_code == 200
    assert (await _leer(client, token, Module.SCRUM)).status_code == 200
    assert (await _leer(client, token, Module.ARQUITECTURA)).status_code == 403

    # Lista vacía: solo queda el rol.
    r = await client.put(
        f"/api/v1/auth/users/{user_id}/grants",
        headers=_auth(admin_token),
        json={"grants": []},
    )
    assert r.status_code == 200
    assert r.json()["data"]["grants"] == []
    assert (await _leer(client, token, Module.SCRUM)).status_code == 403


# --- gestión de usuarios: solo admin ----------------------------------------


@pytest.mark.parametrize(
    "role",
    [UserRole.PROCESOS, UserRole.ANALISTA, UserRole.ARQUITECTO, UserRole.QA],
)
async def test_no_admin_no_toca_usuarios(client, role: UserRole):
    """Ningún rol no-admin lista usuarios, cambia roles ni edita grants."""
    admin_token = await _bootstrap_admin(client)
    victima_id, _ = await _crear_usuario(client, admin_token, UserRole.DEVELOPER)
    _, token = await _crear_usuario(client, admin_token, role)

    assert (
        await client.get("/api/v1/auth/users", headers=_auth(token))
    ).status_code == 403

    r = await client.patch(
        f"/api/v1/auth/users/{victima_id}/role",
        headers=_auth(token),
        json={"role": "admin"},
    )
    assert r.status_code == 403

    r = await client.put(
        f"/api/v1/auth/users/{victima_id}/grants",
        headers=_auth(token),
        json={"grants": [{"module": "config", "level": "full"}]},
    )
    assert r.status_code == 403

    r = await client.patch(
        f"/api/v1/auth/users/{victima_id}",
        headers=_auth(token),
        json={"is_active": False},
    )
    assert r.status_code == 403


async def test_grant_de_config_no_permite_escalar_privilegios(client):
    """Un grant de `config` da el panel, pero NO cambiar roles ni grants.

    Es la guarda anti-escalada: si `require_module(CONFIG, FULL)` bastara para
    tocar roles, conceder `config` equivaldría a regalar el rol admin.
    """
    admin_token = await _bootstrap_admin(client)
    user_id, token = await _crear_usuario(client, admin_token, UserRole.QA)
    otro_id, _ = await _crear_usuario(client, admin_token, UserRole.DEVELOPER)

    r = await client.put(
        f"/api/v1/auth/users/{user_id}/grants",
        headers=_auth(admin_token),
        json={"grants": [{"module": "config", "level": "full"}]},
    )
    assert r.status_code == 200

    # Ya puede ver el panel...
    assert (
        await client.get("/api/v1/auth/users", headers=_auth(token))
    ).status_code == 200
    # ...pero no elevar privilegios.
    r = await client.patch(
        f"/api/v1/auth/users/{otro_id}/role",
        headers=_auth(token),
        json={"role": "admin"},
    )
    assert r.status_code == 403
    r = await client.put(
        f"/api/v1/auth/users/{otro_id}/grants",
        headers=_auth(token),
        json={"grants": [{"module": "ef", "level": "full"}]},
    )
    assert r.status_code == 403
    # Ni crear otro admin, aunque pueda registrar usuarios.
    r = await client.post(
        "/api/v1/auth/register",
        headers=_auth(token),
        json={
            "email": "colado@urbano.com.pe",
            "full_name": "Colado",
            "password": PASSWORD,
            "role": "admin",
        },
    )
    assert r.status_code == 403
    assert "Administrador" in r.json()["message"]


async def test_admin_cambia_rol_y_el_acceso_cambia_en_caliente(client):
    """Cambiar el rol cambia los permisos sin re-emitir el token (sesión intacta)."""
    admin_token = await _bootstrap_admin(client)
    user_id, token = await _crear_usuario(client, admin_token, UserRole.PROCESOS)

    assert (await _leer(client, token, Module.SCRUM)).status_code == 403

    r = await client.patch(
        f"/api/v1/auth/users/{user_id}/role",
        headers=_auth(admin_token),
        json={"role": "analista"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["role"] == "analista"

    # MISMO token: el JWT identifica al usuario, no lleva permisos dentro.
    assert (await _leer(client, token, Module.SCRUM)).status_code == 200


async def test_admin_no_cambia_su_propio_rol(client):
    """Guarda anti-bloqueo: un admin no puede degradarse a sí mismo."""
    admin_token = await _bootstrap_admin(client)
    me = (await client.get("/api/v1/auth/me", headers=_auth(admin_token))).json()[
        "data"
    ]

    r = await client.patch(
        f"/api/v1/auth/users/{me['id']}/role",
        headers=_auth(admin_token),
        json={"role": "qa"},
    )
    assert r.status_code == 403
    assert "su propio rol" in r.json()["message"]


async def test_rol_invalido_rechazado(client):
    """Un rol que no existe en el enum se rechaza con 422 (validación)."""
    admin_token = await _bootstrap_admin(client)
    user_id, _ = await _crear_usuario(client, admin_token, UserRole.QA)
    r = await client.patch(
        f"/api/v1/auth/users/{user_id}/role",
        headers=_auth(admin_token),
        json={"role": "superusuario"},
    )
    assert r.status_code == 422


async def test_catalogo_de_roles_para_el_panel(client):
    """``/auth/roles`` expone la matriz y las etiquetas (solo con Configuración)."""
    admin_token = await _bootstrap_admin(client)
    r = await client.get("/api/v1/auth/roles", headers=_auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert {x["value"] for x in data["roles"]} == {r.value for r in UserRole}
    assert {x["value"] for x in data["modules"]} == {m.value for m in Module}
    assert data["levels"] == ["read", "full"]
    procesos = next(x for x in data["roles"] if x["value"] == "procesos")
    assert procesos["modules"] == {"ef": "full"}
    assert procesos["label"] == "Procesos"

    # Un rol sin Configuración no lo ve.
    _, token = await _crear_usuario(client, admin_token, UserRole.QA)
    assert (
        await client.get("/api/v1/auth/roles", headers=_auth(token))
    ).status_code == 403


async def test_sin_token_sigue_siendo_401_no_403(client):
    """La autenticación se evalúa antes que los permisos."""
    await _bootstrap_admin(client)
    for ruta in ("/api/v1/ef/jobs", "/api/v1/scrum/jobs", "/api/v1/auth/users"):
        r = await client.get(ruta)
        assert r.status_code == 401, ruta
