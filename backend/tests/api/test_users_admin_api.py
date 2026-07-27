"""Tests de la gestión completa de usuarios: editar, contraseña, baja y actividad.

Cubren las salvaguardas, que son la parte delicada: no eliminarse a sí mismo, no
quedarse sin administradores, baja LÓGICA (la fila sobrevive y la trazabilidad
con ella) y el resumen de actividad que recomienda desactivar en vez de eliminar.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.permissions import UserRole
from app.dependencies.database import get_session
from app.models.user import User
from main import app

PASSWORD = "superseguro1"
OTRA = "otrasegura99"


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


async def _login(client, email: str, password: str = PASSWORD) -> tuple[int, dict]:
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return r.status_code, r.json()


async def _token(client, email: str, password: str = PASSWORD) -> str:
    code, body = await _login(client, email, password)
    assert code == 200, body
    return body["data"]["access_token"]


async def _bootstrap_admin(client) -> str:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@urbano.com.pe",
            "full_name": "Admin Uno",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 200, r.text
    return await _token(client, "admin@urbano.com.pe")


async def _crear(client, admin_token: str, email: str, role=UserRole.ANALISTA) -> dict:
    r = await client.post(
        "/api/v1/auth/register",
        headers=_auth(admin_token),
        json={
            "email": email,
            "full_name": "Usuario Prueba",
            "password": PASSWORD,
            "role": role.value,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


# --- editar perfil ----------------------------------------------------------


async def test_editar_nombre_y_correo(client):
    admin = await _bootstrap_admin(client)
    u = await _crear(client, admin, "edita@urbano.com.pe")

    r = await client.patch(
        f"/api/v1/auth/users/{u['id']}/profile",
        headers=_auth(admin),
        json={"full_name": "Nombre Nuevo", "email": "nuevo.correo@urbano.com.pe"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["full_name"] == "Nombre Nuevo"
    assert data["email"] == "nuevo.correo@urbano.com.pe"

    # El correo nuevo sirve para entrar; el viejo ya no.
    assert (await _login(client, "nuevo.correo@urbano.com.pe"))[0] == 200
    assert (await _login(client, "edita@urbano.com.pe"))[0] == 401


async def test_editar_solo_el_nombre_no_toca_el_correo(client):
    admin = await _bootstrap_admin(client)
    u = await _crear(client, admin, "parcial@urbano.com.pe")

    r = await client.patch(
        f"/api/v1/auth/users/{u['id']}/profile",
        headers=_auth(admin),
        json={"full_name": "Solo Nombre"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["email"] == "parcial@urbano.com.pe"


async def test_editar_a_un_correo_ya_usado_409(client):
    admin = await _bootstrap_admin(client)
    await _crear(client, admin, "ocupado@urbano.com.pe")
    otro = await _crear(client, admin, "otro@urbano.com.pe")

    r = await client.patch(
        f"/api/v1/auth/users/{otro['id']}/profile",
        headers=_auth(admin),
        json={"email": "ocupado@urbano.com.pe"},
    )
    assert r.status_code == 409
    assert "correo" in r.json()["message"]


async def test_el_correo_de_un_usuario_dado_de_baja_sigue_reservado(client):
    """La única de la tabla cubre las bajas: reutilizar el correo exige reactivar."""
    admin = await _bootstrap_admin(client)
    baja = await _crear(client, admin, "baja@urbano.com.pe")
    otro = await _crear(client, admin, "vigente@urbano.com.pe")

    assert (
        await client.delete(f"/api/v1/auth/users/{baja['id']}", headers=_auth(admin))
    ).status_code == 200

    r = await client.patch(
        f"/api/v1/auth/users/{otro['id']}/profile",
        headers=_auth(admin),
        json={"email": "baja@urbano.com.pe"},
    )
    assert r.status_code == 409


# --- restablecer contraseña -------------------------------------------------


async def test_restablecer_contrasena(client):
    admin = await _bootstrap_admin(client)
    u = await _crear(client, admin, "reset@urbano.com.pe")

    r = await client.post(
        f"/api/v1/auth/users/{u['id']}/password",
        headers=_auth(admin),
        json={"password": OTRA},
    )
    assert r.status_code == 200
    # La respuesta jamás incluye el hash ni la contraseña.
    assert "password_hash" not in r.json()["data"]
    assert "password" not in r.json()["data"]

    assert (await _login(client, "reset@urbano.com.pe", OTRA))[0] == 200
    assert (await _login(client, "reset@urbano.com.pe", PASSWORD))[0] == 401


async def test_contrasena_corta_rechazada(client):
    admin = await _bootstrap_admin(client)
    u = await _crear(client, admin, "corta@urbano.com.pe")
    r = await client.post(
        f"/api/v1/auth/users/{u['id']}/password",
        headers=_auth(admin),
        json={"password": "1234"},
    )
    assert r.status_code == 422


# --- actividad --------------------------------------------------------------


async def test_actividad_vacia_no_recomienda_desactivar(client):
    admin = await _bootstrap_admin(client)
    u = await _crear(client, admin, "sinhuella@urbano.com.pe")

    r = await client.get(f"/api/v1/auth/users/{u['id']}/activity", headers=_auth(admin))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data == {
        "jobs": 0,
        "validations": 0,
        "total": 0,
        "recommend_deactivate": False,
    }


async def test_actividad_cuenta_los_jobs_del_usuario(client, engine):
    """Un job creado por el usuario cuenta como huella y recomienda desactivar."""
    from app.models.agent import AgentJob, AgentType

    admin = await _bootstrap_admin(client)
    u = await _crear(client, admin, "conhuella@urbano.com.pe")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(AgentJob(agent_type=AgentType.EF, created_by=u["id"]))
        await s.commit()

    r = await client.get(f"/api/v1/auth/users/{u['id']}/activity", headers=_auth(admin))
    data = r.json()["data"]
    assert data["jobs"] == 1
    assert data["total"] == 1
    assert data["recommend_deactivate"] is True


# --- baja lógica ------------------------------------------------------------


async def test_baja_conserva_la_fila_y_bloquea_el_acceso(client, engine):
    admin = await _bootstrap_admin(client)
    u = await _crear(client, admin, "adios@urbano.com.pe")

    r = await client.delete(f"/api/v1/auth/users/{u['id']}", headers=_auth(admin))
    assert r.status_code == 200

    # Ya no inicia sesión...
    assert (await _login(client, "adios@urbano.com.pe"))[0] == 401
    # ...ni aparece en el listado...
    listado = await client.get("/api/v1/auth/users", headers=_auth(admin))
    assert all(x["id"] != u["id"] for x in listado.json()["data"]["items"])
    # ...pero la FILA SIGUE AHÍ (trazabilidad intacta).
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        row = await s.scalar(select(User).where(User.id == u["id"]))
        assert row is not None
        assert row.deleted_at is not None
        assert row.is_active is False
        assert row.full_name == "Usuario Prueba"  # no se anonimiza


async def test_baja_de_un_usuario_no_borra_sus_jobs(client, engine):
    """El historial sobrevive a la baja y sigue apuntando a su autor."""
    from app.models.agent import AgentJob, AgentType

    admin = await _bootstrap_admin(client)
    u = await _crear(client, admin, "autor@urbano.com.pe")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(AgentJob(agent_type=AgentType.EF, created_by=u["id"]))
        await s.commit()

    await client.delete(f"/api/v1/auth/users/{u['id']}", headers=_auth(admin))

    async with factory() as s:
        job = await s.scalar(select(AgentJob).where(AgentJob.created_by == u["id"]))
        assert job is not None


async def test_no_puedes_eliminarte_a_ti_mismo(client):
    admin = await _bootstrap_admin(client)
    me = (await client.get("/api/v1/auth/me", headers=_auth(admin))).json()["data"]

    r = await client.delete(f"/api/v1/auth/users/{me['id']}", headers=_auth(admin))
    assert r.status_code == 403
    assert "tu propia cuenta" in r.json()["message"]


async def test_no_puedes_eliminar_al_ultimo_admin(client):
    """Con dos admins se puede eliminar uno; al quedar uno solo, se protege."""
    admin = await _bootstrap_admin(client)
    segundo = await _crear(client, admin, "admin2@urbano.com.pe", UserRole.ADMIN)
    token2 = await _token(client, "admin2@urbano.com.pe")

    # El segundo admin elimina al primero: queda él, así que se permite.
    me = (await client.get("/api/v1/auth/me", headers=_auth(admin))).json()["data"]
    r = await client.delete(f"/api/v1/auth/users/{me['id']}", headers=_auth(token2))
    assert r.status_code == 200

    # Ahora `segundo` es el único admin: no puede eliminarse (guarda de "a ti
    # mismo") y tampoco podría otro admin, porque no queda ninguno más.
    r = await client.delete(
        f"/api/v1/auth/users/{segundo['id']}", headers=_auth(token2)
    )
    assert r.status_code == 403


async def test_no_puedes_desactivar_al_ultimo_admin(client):
    """`config` FULL es concedible por grant: sin esta guarda habría lockout."""
    admin = await _bootstrap_admin(client)
    me = (await client.get("/api/v1/auth/me", headers=_auth(admin))).json()["data"]

    # Un usuario con `config` FULL por GRANT (no admin).
    gestor = await _crear(client, admin, "gestor@urbano.com.pe", UserRole.QA)
    await client.put(
        f"/api/v1/auth/users/{gestor['id']}/grants",
        headers=_auth(admin),
        json={"grants": [{"module": "config", "level": "full"}]},
    )
    token_gestor = await _token(client, "gestor@urbano.com.pe")

    r = await client.patch(
        f"/api/v1/auth/users/{me['id']}",
        headers=_auth(token_gestor),
        json={"is_active": False},
    )
    assert r.status_code == 403
    assert "último administrador" in r.json()["message"]

    # Y el admin sigue pudiendo entrar.
    assert (await _login(client, "admin@urbano.com.pe"))[0] == 200


async def test_usuario_inexistente_404(client):
    admin = await _bootstrap_admin(client)
    for method, ruta, body in (
        ("patch", "/api/v1/auth/users/NADIE/profile", {"full_name": "X"}),
        ("post", "/api/v1/auth/users/NADIE/password", {"password": PASSWORD}),
        ("delete", "/api/v1/auth/users/NADIE", None),
    ):
        r = await getattr(client, method)(
            ruta, headers=_auth(admin), **({"json": body} if body else {})
        )
        assert r.status_code == 404, ruta


@pytest.mark.parametrize(
    "role", [UserRole.PROCESOS, UserRole.ANALISTA, UserRole.ARQUITECTO, UserRole.QA]
)
async def test_sin_configuracion_no_gestiona_usuarios(client, role: UserRole):
    """Los endpoints nuevos exigen el módulo `config`, como el resto del panel."""
    admin = await _bootstrap_admin(client)
    victima = await _crear(client, admin, "victima@urbano.com.pe")
    intruso = await _crear(client, admin, f"{role.value}@urbano.com.pe", role)
    token = await _token(client, f"{role.value}@urbano.com.pe")

    vid = victima["id"]
    assert (
        await client.patch(
            f"/api/v1/auth/users/{vid}/profile",
            headers=_auth(token),
            json={"full_name": "Hackeado"},
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/auth/users/{vid}/password",
            headers=_auth(token),
            json={"password": OTRA},
        )
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/auth/users/{vid}", headers=_auth(token))
    ).status_code == 403
    assert (
        await client.get(f"/api/v1/auth/users/{vid}/activity", headers=_auth(token))
    ).status_code == 403
    assert intruso["role"] == role.value
