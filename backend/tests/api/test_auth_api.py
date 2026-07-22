"""Tests de la API de autenticación: registro/bootstrap, login, rutas protegidas.

Usan la BD SQLite in-memory de ``conftest`` y el flujo real de auth (JWT reales),
sin mockear ``get_current_user``.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.dependencies.database import get_session
from main import app


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


async def _bootstrap_admin(client) -> str:
    """Crea el primer usuario (admin por bootstrap) y devuelve su token."""
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@urbano.com.pe",
            "full_name": "Admin Uno",
            "password": "superseguro1",
        },
    )
    assert r.status_code == 200
    assert r.json()["data"]["role"] == "admin"
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@urbano.com.pe", "password": "superseguro1"},
    )
    assert login.status_code == 200
    return login.json()["data"]["access_token"]


async def test_bootstrap_status_refleja_si_hay_usuarios(client):
    # Sin usuarios: necesita bootstrap.
    r = await client.get("/api/v1/auth/bootstrap-status")
    assert r.status_code == 200
    assert r.json()["data"]["needs_bootstrap"] is True

    # Tras crear el primer admin: ya no.
    await _bootstrap_admin(client)
    r = await client.get("/api/v1/auth/bootstrap-status")
    assert r.json()["data"]["needs_bootstrap"] is False


async def test_bootstrap_primer_usuario_nace_admin(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "PRIMERO@urbano.com.pe",
            "full_name": "Primero",
            "password": "superseguro1",
            "role": "member",  # se ignora en el bootstrap
        },
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["role"] == "admin"  # bootstrap fuerza admin
    assert data["email"] == "primero@urbano.com.pe"  # normalizado a minúsculas
    assert data["is_active"] is True


async def test_registro_sin_auth_rechazado_si_ya_hay_usuarios(client):
    await _bootstrap_admin(client)
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "otro@urbano.com.pe",
            "full_name": "Otro",
            "password": "superseguro1",
        },
    )
    assert r.status_code == 403
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "ForbiddenError"


async def test_admin_registra_member(client):
    token = await _bootstrap_admin(client)
    r = await client.post(
        "/api/v1/auth/register",
        headers=_auth(token),
        json={
            "email": "member@urbano.com.pe",
            "full_name": "Miembro",
            "password": "superseguro1",
            "role": "member",
        },
    )
    assert r.status_code == 200
    assert r.json()["data"]["role"] == "member"


async def test_registro_email_duplicado_409(client):
    token = await _bootstrap_admin(client)
    r = await client.post(
        "/api/v1/auth/register",
        headers=_auth(token),
        json={
            "email": "admin@urbano.com.pe",
            "full_name": "Repetido",
            "password": "superseguro1",
        },
    )
    assert r.status_code == 409
    assert r.json()["data"]["code"] == "ConflictError"


async def test_login_ok_devuelve_token_y_usuario(client):
    await _bootstrap_admin(client)
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@urbano.com.pe", "password": "superseguro1"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["expires_in"] > 0
    assert data["user"]["email"] == "admin@urbano.com.pe"
    assert "password_hash" not in data["user"]


async def test_login_fallido_password_incorrecta_401(client):
    await _bootstrap_admin(client)
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@urbano.com.pe", "password": "equivocada"},
    )
    assert r.status_code == 401
    assert r.json()["data"]["code"] == "AuthError"


async def test_login_email_inexistente_401(client):
    await _bootstrap_admin(client)
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "nadie@urbano.com.pe", "password": "superseguro1"},
    )
    assert r.status_code == 401


async def test_me_con_y_sin_token(client):
    token = await _bootstrap_admin(client)

    r = await client.get("/api/v1/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["data"]["email"] == "admin@urbano.com.pe"

    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["data"]["code"] == "AuthError"

    r = await client.get("/api/v1/auth/me", headers=_auth("token-invalido"))
    assert r.status_code == 401


async def test_endpoint_ef_protegido_con_y_sin_token(client):
    token = await _bootstrap_admin(client)

    # Sin token -> 401 con mensaje claro.
    r = await client.get("/api/v1/ef/jobs")
    assert r.status_code == 401
    assert r.json()["success"] is False
    assert "token" in r.json()["message"].lower()

    # Con token válido -> 200.
    r = await client.get("/api/v1/ef/jobs", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["success"] is True


async def test_panel_usuarios_solo_admin(client):
    admin_token = await _bootstrap_admin(client)

    # El admin registra un member y este inicia sesión.
    await client.post(
        "/api/v1/auth/register",
        headers=_auth(admin_token),
        json={
            "email": "member@urbano.com.pe",
            "full_name": "Miembro",
            "password": "superseguro1",
            "role": "member",
        },
    )
    member_token = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "member@urbano.com.pe", "password": "superseguro1"},
        )
    ).json()["data"]["access_token"]

    # El admin lista usuarios.
    r = await client.get("/api/v1/auth/users", headers=_auth(admin_token))
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 2

    # El member no puede.
    r = await client.get("/api/v1/auth/users", headers=_auth(member_token))
    assert r.status_code == 403
    assert r.json()["data"]["code"] == "ForbiddenError"


async def test_desactivar_usuario_impide_login(client):
    admin_token = await _bootstrap_admin(client)
    member = (
        await client.post(
            "/api/v1/auth/register",
            headers=_auth(admin_token),
            json={
                "email": "member@urbano.com.pe",
                "full_name": "Miembro",
                "password": "superseguro1",
                "role": "member",
            },
        )
    ).json()["data"]

    # Desactivar.
    r = await client.patch(
        f"/api/v1/auth/users/{member['id']}",
        headers=_auth(admin_token),
        json={"is_active": False},
    )
    assert r.status_code == 200
    assert r.json()["data"]["is_active"] is False

    # No puede iniciar sesión.
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "member@urbano.com.pe", "password": "superseguro1"},
    )
    assert r.status_code == 401


async def test_admin_no_puede_desactivarse_a_si_mismo(client):
    admin_token = await _bootstrap_admin(client)
    me = (await client.get("/api/v1/auth/me", headers=_auth(admin_token))).json()[
        "data"
    ]
    r = await client.patch(
        f"/api/v1/auth/users/{me['id']}",
        headers=_auth(admin_token),
        json={"is_active": False},
    )
    assert r.status_code == 403
