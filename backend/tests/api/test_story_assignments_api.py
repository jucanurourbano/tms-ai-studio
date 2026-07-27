"""Tests de equipo y asignación de historias del plan Scrum.

Las asignaciones viven FUERA del artefacto: se comprueba explícitamente que
asignar no muta el ``ScrumArtifact``. Ningún test ejecuta el agente: el plan se
siembra directamente en la BD con un artefacto mínimo.
"""

import csv
import io

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.permissions import UserRole
from app.dependencies.database import get_session
from app.models.agent import AgentArtifactRow, AgentJob, AgentType, JobStatus
from main import app

PASSWORD = "superseguro1"

ARTIFACT = {
    "schema_version": "1.0.0",
    "stories": [
        {
            "id": "US-001",
            "goal": "Registrar guía",
            "story_points": 5,
            "priority": "must",
            "external_key": "US-001",
        },
        {
            "id": "US-002",
            "goal": "Consultar checkpoint",
            "story_points": 3,
            "priority": "should",
            "external_key": "US-002",
        },
        {
            "id": "US-003",
            "goal": "Anular guía",
            "story_points": 8,
            "priority": "could",
            "external_key": "US-003",
        },
    ],
    "epics": [],
    "sprints": [{"id": "Sprint 1", "story_ids": ["US-001", "US-002"]}],
    "unassigned_story_ids": ["US-003"],
    "product_backlog": {"ordered_story_ids": ["US-001", "US-002", "US-003"]},
}


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


@pytest_asyncio.fixture
async def scrum_job(engine) -> str:
    """Siembra un job Scrum COMPLETED con artefacto (sin ejecutar el agente)."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        job = AgentJob(agent_type=AgentType.SCRUM, status=JobStatus.COMPLETED)
        s.add(job)
        await s.flush()
        s.add(AgentArtifactRow(job_id=job.id, schema_version="1.0.0", data=ARTIFACT))
        await s.commit()
        return job.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _token(client, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


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


async def _crear_miembro(
    client,
    admin: str,
    email: str,
    *,
    nombre: str = "Ana Pérez",
    role=UserRole.DEVELOPER,
    institucional: str | None = None,
    especialidad: str | None = None,
    disponible: bool = True,
) -> dict:
    r = await client.post(
        "/api/v1/auth/register",
        headers=_auth(admin),
        json={
            "email": email,
            "full_name": nombre,
            "password": PASSWORD,
            "role": role.value,
        },
    )
    assert r.status_code == 200, r.text
    user = r.json()["data"]

    cuerpo: dict = {}
    if institucional is not None:
        cuerpo["institutional_email"] = institucional
    if especialidad is not None:
        cuerpo["specialty"] = especialidad
    if not disponible:
        cuerpo["available_for_assignment"] = False
    if cuerpo:
        r = await client.patch(
            f"/api/v1/auth/users/{user['id']}/profile",
            headers=_auth(admin),
            json=cuerpo,
        )
        assert r.status_code == 200, r.text
        user = r.json()["data"]
    return user


# --- perfil de equipo -------------------------------------------------------


async def test_perfil_de_equipo_se_guarda_y_expone(client):
    admin = await _bootstrap_admin(client)
    u = await _crear_miembro(
        client,
        admin,
        "ana.login@urbano.pe",
        institucional="ana.perez@urbano.com.pe",
        especialidad="backend",
    )
    assert u["institutional_email"] == "ana.perez@urbano.com.pe"
    assert u["specialty"] == "backend"
    assert u["available_for_assignment"] is True


async def test_equipo_lista_solo_a_los_asignables(client):
    """Fuera: los no disponibles y los inactivos."""
    admin = await _bootstrap_admin(client)
    await _crear_miembro(client, admin, "ana@urbano.com.pe", nombre="Ana Pérez")
    no_disp = await _crear_miembro(
        client, admin, "nodisp@urbano.com.pe", nombre="No Disponible", disponible=False
    )
    inactivo = await _crear_miembro(
        client, admin, "inactivo@urbano.com.pe", nombre="Inactivo"
    )
    await client.patch(
        f"/api/v1/auth/users/{inactivo['id']}",
        headers=_auth(admin),
        json={"is_active": False},
    )

    r = await client.get("/api/v1/scrum/team", headers=_auth(admin))
    assert r.status_code == 200
    ids = {m["id"] for m in r.json()["data"]["items"]}
    assert no_disp["id"] not in ids
    assert inactivo["id"] not in ids
    # El propio admin sí (está activo y disponible por defecto).
    assert len(ids) == 2


async def test_equipo_cae_al_correo_de_acceso_si_no_hay_institucional(client):
    admin = await _bootstrap_admin(client)
    await _crear_miembro(client, admin, "solologin@urbano.com.pe")

    admin_id = await _me(client, admin)
    r = await client.get("/api/v1/scrum/team", headers=_auth(admin))
    miembro = next(m for m in r.json()["data"]["items"] if m["id"] != admin_id)
    # Sin correo institucional se cae al de acceso: la tarea nunca queda sin
    # destinatario en el export.
    assert miembro["institutional_email"] == "solologin@urbano.com.pe"


async def _me(client, token: str) -> str:
    r = await client.get("/api/v1/auth/me", headers=_auth(token))
    return r.json()["data"]["id"]


# --- asignar / desasignar ---------------------------------------------------


async def test_asignar_y_listar(client, scrum_job):
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(
        client, admin, "ana@urbano.com.pe", nombre="Ana Pérez", especialidad="backend"
    )

    r = await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(admin),
        json={"story_id": "US-001", "user_id": ana["id"]},
    )
    assert r.status_code == 200, r.text

    r = await client.get(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments", headers=_auth(admin)
    )
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["story_id"] == "US-001"
    assert items[0]["user_id"] == ana["id"]
    assert items[0]["user"]["full_name"] == "Ana Pérez"
    assert items[0]["user"]["specialty"] == "backend"
    assert items[0]["assigned_at"] is not None
    assert items[0]["assigned_by"] == await _me(client, admin)


async def test_reasignar_sustituye_no_duplica(client, scrum_job):
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe", nombre="Ana")
    luis = await _crear_miembro(client, admin, "luis@urbano.com.pe", nombre="Luis")

    for uid in (ana["id"], luis["id"]):
        r = await client.patch(
            f"/api/v1/scrum/jobs/{scrum_job}/assignments",
            headers=_auth(admin),
            json={"story_id": "US-001", "user_id": uid},
        )
        assert r.status_code == 200, r.text

    r = await client.get(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments", headers=_auth(admin)
    )
    items = r.json()["data"]["items"]
    assert len(items) == 1  # una sola fila por historia
    assert items[0]["user_id"] == luis["id"]


async def test_desasignar_con_user_id_null(client, scrum_job):
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe")

    await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(admin),
        json={"story_id": "US-002", "user_id": ana["id"]},
    )
    r = await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(admin),
        json={"story_id": "US-002", "user_id": None},
    )
    assert r.status_code == 200
    r = await client.get(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments", headers=_auth(admin)
    )
    assert r.json()["data"]["items"] == []


async def test_asignar_no_muta_el_artefacto(client, scrum_job):
    """La filosofía del proyecto: el artefacto es la salida del agente y no se toca."""
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe")

    antes = (
        await client.get(
            f"/api/v1/scrum/jobs/{scrum_job}/artifact", headers=_auth(admin)
        )
    ).json()["data"]
    await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(admin),
        json={"story_id": "US-001", "user_id": ana["id"]},
    )
    despues = (
        await client.get(
            f"/api/v1/scrum/jobs/{scrum_job}/artifact", headers=_auth(admin)
        )
    ).json()["data"]
    assert antes == despues


async def test_historia_inexistente_rechazada(client, scrum_job):
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe")
    r = await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(admin),
        json={"story_id": "US-999", "user_id": ana["id"]},
    )
    assert r.status_code >= 400
    assert "no pertenece" in r.json()["message"]


async def test_usuario_no_asignable_rechazado(client, scrum_job):
    admin = await _bootstrap_admin(client)
    no_disp = await _crear_miembro(
        client, admin, "nodisp@urbano.com.pe", disponible=False
    )
    r = await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(admin),
        json={"story_id": "US-001", "user_id": no_disp["id"]},
    )
    assert r.status_code >= 400
    assert "no está disponible" in r.json()["message"]


async def test_job_inexistente_rechazado(client):
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe")
    r = await client.patch(
        "/api/v1/scrum/jobs/NO_EXISTE/assignments",
        headers=_auth(admin),
        json={"story_id": "US-001", "user_id": ana["id"]},
    )
    assert r.status_code >= 400


# --- permisos ---------------------------------------------------------------


async def test_analista_puede_asignar(client, scrum_job):
    """`analista` tiene Scrum FULL: asigna."""
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe")
    await _crear_miembro(
        client, admin, "analista@urbano.com.pe", role=UserRole.ANALISTA
    )
    token = await _token(client, "analista@urbano.com.pe")

    r = await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(token),
        json={"story_id": "US-001", "user_id": ana["id"]},
    )
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("role", [UserRole.ARQUITECTO, UserRole.DEVELOPER, UserRole.QA])
async def test_solo_lectura_no_asigna_pero_si_consulta(client, scrum_job, role):
    """Con Scrum en READ se ven las asignaciones y el equipo, pero no se asigna."""
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe")
    await _crear_miembro(client, admin, f"{role.value}@urbano.com.pe", role=role)
    token = await _token(client, f"{role.value}@urbano.com.pe")

    assert (
        await client.get(
            f"/api/v1/scrum/jobs/{scrum_job}/assignments", headers=_auth(token)
        )
    ).status_code == 200
    assert (
        await client.get("/api/v1/scrum/team", headers=_auth(token))
    ).status_code == 200

    r = await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(token),
        json={"story_id": "US-001", "user_id": ana["id"]},
    )
    assert r.status_code == 403


async def test_procesos_no_ve_nada_de_scrum(client, scrum_job):
    admin = await _bootstrap_admin(client)
    await _crear_miembro(
        client, admin, "procesos@urbano.com.pe", role=UserRole.PROCESOS
    )
    token = await _token(client, "procesos@urbano.com.pe")
    assert (
        await client.get("/api/v1/scrum/team", headers=_auth(token))
    ).status_code == 403


# --- export con el responsable ----------------------------------------------


async def test_export_csv_incluye_el_correo_institucional_del_asignado(
    client, scrum_job
):
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(
        client,
        admin,
        "ana.login@urbano.pe",
        nombre="Ana Pérez",
        institucional="ana.perez@urbano.com.pe",
    )
    await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(admin),
        json={"story_id": "US-001", "user_id": ana["id"]},
    )

    r = await client.get(
        f"/api/v1/scrum/jobs/{scrum_job}/export?format=csv", headers=_auth(admin)
    )
    assert r.status_code == 200
    reader = list(csv.reader(io.StringIO(r.json()["data"]["content"])))
    columna = reader[0].index("Assignee")
    valores = {fila[1]: fila[columna] for fila in reader[1:]}
    # La asignada lleva el correo INSTITUCIONAL, no el de acceso.
    assert valores["Registrar guía"] == "ana.perez@urbano.com.pe"
    # Las demás, vacío: ClickUp las importa sin asignar.
    assert valores["Consultar checkpoint"] == ""


async def test_export_json_incluye_assignee_email(client, scrum_job):
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(
        client, admin, "ana@urbano.com.pe", institucional="ana.perez@urbano.com.pe"
    )
    await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(admin),
        json={"story_id": "US-003", "user_id": ana["id"]},
    )
    r = await client.get(
        f"/api/v1/scrum/jobs/{scrum_job}/export?format=json", headers=_auth(admin)
    )
    filas = r.json()["data"]["content"]
    asignada = next(f for f in filas if f["external_key"] == "US-003")
    assert asignada["assignee_email"] == "ana.perez@urbano.com.pe"


# --- asignación de SPRINT completo (cascada derivada) -----------------------


async def test_asignar_sprint_cascada_a_sus_historias(client, scrum_job):
    """Asignar el sprint hace que sus historias sin dueño se muestren a su nombre."""
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe", nombre="Ana")

    r = await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/sprint-assignments",
        headers=_auth(admin),
        json={"sprint_id": "Sprint 1", "user_id": ana["id"]},
    )
    assert r.status_code == 200, r.text

    data = (
        await client.get(
            f"/api/v1/scrum/jobs/{scrum_job}/assignments", headers=_auth(admin)
        )
    ).json()["data"]

    # US-001 y US-002 están en Sprint 1 -> heredadas. US-003 no (va al backlog).
    por_historia = {i["story_id"]: i for i in data["items"]}
    assert set(por_historia) == {"US-001", "US-002"}
    assert all(i["source"] == "sprint" for i in por_historia.values())
    assert all(i["user_id"] == ana["id"] for i in por_historia.values())

    assert len(data["sprints"]) == 1
    assert data["sprints"][0]["sprint_id"] == "Sprint 1"
    assert data["sprints"][0]["user"]["full_name"] == "Ana"


async def test_la_asignacion_por_historia_prevalece_sobre_la_del_sprint(
    client, scrum_job
):
    """La historia asignada explícitamente NO se pisa al asignar el sprint."""
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe", nombre="Ana")
    luis = await _crear_miembro(client, admin, "luis@urbano.com.pe", nombre="Luis")

    # US-001 explícitamente a Luis; el sprint completo a Ana.
    await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(admin),
        json={"story_id": "US-001", "user_id": luis["id"]},
    )
    await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/sprint-assignments",
        headers=_auth(admin),
        json={"sprint_id": "Sprint 1", "user_id": ana["id"]},
    )

    items = {
        i["story_id"]: i
        for i in (
            await client.get(
                f"/api/v1/scrum/jobs/{scrum_job}/assignments", headers=_auth(admin)
            )
        ).json()["data"]["items"]
    }
    assert items["US-001"]["user_id"] == luis["id"]
    assert items["US-001"]["source"] == "story"
    assert items["US-002"]["user_id"] == ana["id"]
    assert items["US-002"]["source"] == "sprint"


async def test_desasignar_el_sprint_deshace_la_cascada_y_conserva_lo_explicito(
    client, scrum_job
):
    """La cascada es derivada: quitarla no deja filas huérfanas ni borra la excepción."""
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe", nombre="Ana")
    luis = await _crear_miembro(client, admin, "luis@urbano.com.pe", nombre="Luis")

    await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(admin),
        json={"story_id": "US-001", "user_id": luis["id"]},
    )
    await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/sprint-assignments",
        headers=_auth(admin),
        json={"sprint_id": "Sprint 1", "user_id": ana["id"]},
    )
    r = await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/sprint-assignments",
        headers=_auth(admin),
        json={"sprint_id": "Sprint 1", "user_id": None},
    )
    assert r.status_code == 200

    data = (
        await client.get(
            f"/api/v1/scrum/jobs/{scrum_job}/assignments", headers=_auth(admin)
        )
    ).json()["data"]
    assert data["sprints"] == []
    # Solo sobrevive la asignación explícita.
    assert [i["story_id"] for i in data["items"]] == ["US-001"]
    assert data["items"][0]["user_id"] == luis["id"]


async def test_reasignar_el_sprint_no_pisa_las_excepciones(client, scrum_job):
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe", nombre="Ana")
    luis = await _crear_miembro(client, admin, "luis@urbano.com.pe", nombre="Luis")

    await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/assignments",
        headers=_auth(admin),
        json={"story_id": "US-001", "user_id": luis["id"]},
    )
    for uid in (ana["id"], luis["id"], ana["id"]):
        r = await client.patch(
            f"/api/v1/scrum/jobs/{scrum_job}/sprint-assignments",
            headers=_auth(admin),
            json={"sprint_id": "Sprint 1", "user_id": uid},
        )
        assert r.status_code == 200

    data = (
        await client.get(
            f"/api/v1/scrum/jobs/{scrum_job}/assignments", headers=_auth(admin)
        )
    ).json()["data"]
    assert len(data["sprints"]) == 1  # una sola fila por sprint
    items = {i["story_id"]: i for i in data["items"]}
    assert items["US-001"]["user_id"] == luis["id"]  # la excepción intacta


async def test_asignar_sprint_no_muta_el_artefacto(client, scrum_job):
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe")
    antes = (
        await client.get(
            f"/api/v1/scrum/jobs/{scrum_job}/artifact", headers=_auth(admin)
        )
    ).json()["data"]
    await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/sprint-assignments",
        headers=_auth(admin),
        json={"sprint_id": "Sprint 1", "user_id": ana["id"]},
    )
    despues = (
        await client.get(
            f"/api/v1/scrum/jobs/{scrum_job}/artifact", headers=_auth(admin)
        )
    ).json()["data"]
    assert antes == despues


async def test_sprint_inexistente_rechazado(client, scrum_job):
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe")
    r = await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/sprint-assignments",
        headers=_auth(admin),
        json={"sprint_id": "Sprint 99", "user_id": ana["id"]},
    )
    assert r.status_code >= 400
    assert "no pertenece" in r.json()["message"]


@pytest.mark.parametrize("role", [UserRole.ARQUITECTO, UserRole.DEVELOPER, UserRole.QA])
async def test_solo_lectura_no_asigna_sprints(client, scrum_job, role):
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(client, admin, "ana@urbano.com.pe")
    await _crear_miembro(client, admin, f"{role.value}@urbano.com.pe", role=role)
    token = await _token(client, f"{role.value}@urbano.com.pe")
    r = await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/sprint-assignments",
        headers=_auth(token),
        json={"sprint_id": "Sprint 1", "user_id": ana["id"]},
    )
    assert r.status_code == 403


async def test_export_incluye_las_historias_heredadas_del_sprint(client, scrum_job):
    """Lo que el equipo ve en pantalla es lo que sale en el CSV."""
    admin = await _bootstrap_admin(client)
    ana = await _crear_miembro(
        client,
        admin,
        "ana@urbano.com.pe",
        nombre="Ana",
        institucional="ana.perez@urbano.com.pe",
    )
    await client.patch(
        f"/api/v1/scrum/jobs/{scrum_job}/sprint-assignments",
        headers=_auth(admin),
        json={"sprint_id": "Sprint 1", "user_id": ana["id"]},
    )

    r = await client.get(
        f"/api/v1/scrum/jobs/{scrum_job}/export?format=csv", headers=_auth(admin)
    )
    reader = list(csv.reader(io.StringIO(r.json()["data"]["content"])))
    columna = reader[0].index("Assignee")
    valores = {fila[1]: fila[columna] for fila in reader[1:]}
    # Las dos del sprint heredan el responsable; la del backlog sigue vacía.
    assert valores["Registrar guía"] == "ana.perez@urbano.com.pe"
    assert valores["Consultar checkpoint"] == "ana.perez@urbano.com.pe"
    assert valores["Anular guía"] == ""
