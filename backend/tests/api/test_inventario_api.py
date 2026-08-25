"""API del Inventario de Sistemas (INV1).

Cubre el flujo completo (alta de sistema → carga de activos → versiones) y la
autorización del módulo, que es donde está el riesgo: el inventario lo LEE todo
el mundo pero solo lo ESCRIBEN admin y arquitecto, porque un activo mal cargado
envenena la fase RECONCILE de los tres agentes de diseño a la vez.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.permissions import UserRole
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


@pytest_asyncio.fixture
async def admin_token(client) -> str:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@urbano.com.pe",
            "full_name": "Admin Uno",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 200, r.text
    return await _login(client, "admin@urbano.com.pe")


async def _usuario(client, admin_token: str, role: UserRole) -> str:
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
    return await _login(client, email)


def esquema(*tablas: str) -> dict:
    return {
        "engine": "postgresql",
        "tables": [
            {
                "name": t,
                "columns": [
                    {"name": f"{t}_id", "type": "bigint", "primary_key": True},
                    {"name": "nombre", "type": "character varying(120)"},
                ],
                "primary_key": [f"{t}_id"],
            }
            for t in tablas
        ],
    }


async def _crear_sistema(client, token: str, name="TMS Moderno") -> str:
    r = await client.post(
        "/api/v1/inventario/systems",
        headers=_auth(token),
        json={"name": name, "kind": "destino", "description": "Sistema de destino"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


# --- flujo -------------------------------------------------------------------


async def test_flujo_completo_sistema_y_activos(client, admin_token):
    system_id = await _crear_sistema(client, admin_token)

    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets",
        headers=_auth(admin_token),
        json={
            "asset_type": "db_schema",
            "name": "core",
            "content": esquema("usuarios", "envios"),
            "origin": "ddl_dump",
            "origin_ref": "dump.sql",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["version"] == 1
    asset_id = r.json()["data"]["id"]

    # La ficha del sistema trae los activos vigentes y sus conteos.
    r = await client.get(
        f"/api/v1/inventario/systems/{system_id}", headers=_auth(admin_token)
    )
    data = r.json()["data"]
    assert data["asset_counts"] == {"db_schema": 1}
    assert data["assets"][0]["summary"] == {"tables": 2, "columns": 4}

    # El contenido completo solo al abrir el activo.
    r = await client.get(
        f"/api/v1/inventario/assets/{asset_id}", headers=_auth(admin_token)
    )
    assert len(r.json()["data"]["content"]["tables"]) == 2


async def test_recargar_crea_version_y_el_historial_queda_consultable(
    client, admin_token
):
    system_id = await _crear_sistema(client, admin_token)
    for tablas in (("usuarios",), ("usuarios", "envios")):
        r = await client.post(
            f"/api/v1/inventario/systems/{system_id}/assets",
            headers=_auth(admin_token),
            json={
                "asset_type": "db_schema",
                "name": "core",
                "content": esquema(*tablas),
                "origin": "ddl_dump",
            },
        )
        assert r.status_code == 200, r.text
    asset_id = r.json()["data"]["id"]
    assert r.json()["data"]["version"] == 2

    r = await client.get(
        f"/api/v1/inventario/assets/{asset_id}/versions", headers=_auth(admin_token)
    )
    assert [v["version"] for v in r.json()["data"]["items"]] == [2, 1]

    # El listado de activos muestra UNA fila (la vigente), no las dos versiones.
    r = await client.get(
        f"/api/v1/inventario/systems/{system_id}/assets", headers=_auth(admin_token)
    )
    assert len(r.json()["data"]["items"]) == 1
    assert r.json()["data"]["items"][0]["version"] == 2


async def test_marcar_activo_como_validado(client, admin_token):
    system_id = await _crear_sistema(client, admin_token)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets",
        headers=_auth(admin_token),
        json={
            "asset_type": "db_schema",
            "name": "core",
            "content": esquema("usuarios"),
            "origin": "introspection",
        },
    )
    asset_id = r.json()["data"]["id"]
    assert r.json()["data"]["validation_status"] == "importado"

    r = await client.patch(
        f"/api/v1/inventario/assets/{asset_id}/status",
        headers=_auth(admin_token),
        json={"validation_status": "validado"},
    )
    assert r.json()["data"]["validation_status"] == "validado"


async def test_editar_sistema_aplica_solo_lo_informado(client, admin_token):
    """PATCH parcial: lo que no viaja no se toca (y `updated_at` se refresca)."""
    system_id = await _crear_sistema(client, admin_token)
    r = await client.patch(
        f"/api/v1/inventario/systems/{system_id}",
        headers=_auth(admin_token),
        json={
            "status": "en_migracion",
            "stack": [{"layer": "database_relational", "technology": "PostgreSQL"}],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "en_migracion"
    assert data["stack"][0]["technology"] == "PostgreSQL"
    # No se informó `name` ni `description`: siguen como estaban.
    assert data["name"] == "TMS Moderno"
    assert data["description"] == "Sistema de destino"


async def test_renombrar_a_un_nombre_ya_tomado_es_409(client, admin_token):
    await _crear_sistema(client, admin_token, name="TMS Moderno")
    otro = await _crear_sistema(client, admin_token, name="TMS Legado")
    r = await client.patch(
        f"/api/v1/inventario/systems/{otro}",
        headers=_auth(admin_token),
        json={"name": "TMS Moderno"},
    )
    assert r.status_code == 409, r.text


async def test_nombre_de_sistema_repetido_es_409(client, admin_token):
    await _crear_sistema(client, admin_token)
    r = await client.post(
        "/api/v1/inventario/systems",
        headers=_auth(admin_token),
        json={"name": "TMS Moderno", "kind": "legado"},
    )
    assert r.status_code == 409, r.text
    assert "Ya existe" in r.json()["message"]


async def test_sistema_inexistente_es_404(client, admin_token):
    r = await client.get(
        "/api/v1/inventario/systems/01JZZZZZZZZZZZZZZZZZZZZZZZ",
        headers=_auth(admin_token),
    )
    assert r.status_code == 404, r.text


async def test_esquema_invalido_se_rechaza_al_cargar(client, admin_token):
    """No entra al inventario un esquema que INV4 no sabría comparar."""
    system_id = await _crear_sistema(client, admin_token)
    contenido = esquema("usuarios")
    contenido["tables"].append(contenido["tables"][0])
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets",
        headers=_auth(admin_token),
        json={
            "asset_type": "db_schema",
            "name": "core",
            "content": contenido,
            "origin": "ddl_dump",
        },
    )
    assert r.status_code == 409, r.text
    assert "duplicada" in r.json()["message"]


async def test_borrar_sistema_arrastra_sus_activos(client, admin_token):
    system_id = await _crear_sistema(client, admin_token)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets",
        headers=_auth(admin_token),
        json={
            "asset_type": "db_schema",
            "name": "core",
            "content": esquema("usuarios"),
            "origin": "ddl_dump",
        },
    )
    asset_id = r.json()["data"]["id"]

    r = await client.delete(
        f"/api/v1/inventario/systems/{system_id}", headers=_auth(admin_token)
    )
    assert r.status_code == 200, r.text
    r = await client.get(
        f"/api/v1/inventario/assets/{asset_id}", headers=_auth(admin_token)
    )
    assert r.status_code == 404


# --- ingesta de DDL (INV2) ---------------------------------------------------

DDL = """
CREATE TABLE usuarios (
  usuario_id BIGSERIAL PRIMARY KEY,
  nombre VARCHAR(120) NOT NULL,
  email VARCHAR(200) NOT NULL UNIQUE
);
CREATE TABLE envios (
  envio_id BIGSERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL
);
ALTER TABLE envios ADD CONSTRAINT fk_envios_usuario
  FOREIGN KEY (usuario_id) REFERENCES usuarios (usuario_id) ON DELETE CASCADE;
"""


def _sql(contenido: str, nombre: str = "dump.sql") -> dict:
    return {"file": (nombre, contenido.encode("utf-8"), "application/sql")}


async def test_subir_un_dump_ddl_crea_el_activo(client, admin_token):
    system_id = await _crear_sistema(client, admin_token)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets/ddl?name=core",
        headers=_auth(admin_token),
        files=_sql(DDL),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["origin"] == "ddl_dump"
    assert data["origin_ref"] == "dump.sql"
    assert data["validation_status"] == "importado"
    assert data["import_report"]["tables"] == 2
    assert data["import_report"]["errors"] == []

    # El contenido quedó estructurado, con la FK y su acción.
    r = await client.get(
        f"/api/v1/inventario/assets/{data['id']}", headers=_auth(admin_token)
    )
    envios = next(
        t for t in r.json()["data"]["content"]["tables"] if t["name"] == "envios"
    )
    assert envios["foreign_keys"][0]["on_delete"] == "cascade"


async def test_recargar_el_dump_versiona(client, admin_token):
    system_id = await _crear_sistema(client, admin_token)
    for _ in range(2):
        r = await client.post(
            f"/api/v1/inventario/systems/{system_id}/assets/ddl?name=core",
            headers=_auth(admin_token),
            files=_sql(DDL),
        )
        assert r.status_code == 200, r.text
    assert r.json()["data"]["version"] == 2


async def test_un_dump_con_una_sentencia_ilegible_avisa_pero_carga_el_resto(
    client, admin_token
):
    """No se pierde el dump entero por una sentencia, pero se DICE qué faltó."""
    system_id = await _crear_sistema(client, admin_token)
    roto = "CREATE TABLE buena (id BIGSERIAL PRIMARY KEY);\nCREATE TABLE MAL (((;\n"
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets/ddl?name=core",
        headers=_auth(admin_token),
        files=_sql(roto),
    )
    assert r.status_code == 200, r.text
    reporte = r.json()["data"]["import_report"]
    assert reporte["tables"] == 1
    assert reporte["errors"][0]["line"] == 2
    assert "no interpretadas" in r.json()["message"]


async def test_un_archivo_sin_tablas_se_rechaza(client, admin_token):
    system_id = await _crear_sistema(client, admin_token)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets/ddl",
        headers=_auth(admin_token),
        files=_sql("GRANT SELECT ON algo TO alguien;"),
    )
    assert r.status_code == 409, r.text
    assert "tabla" in r.json()["message"].lower()


async def test_un_archivo_que_no_es_sql_se_rechaza(client, admin_token):
    system_id = await _crear_sistema(client, admin_token)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets/ddl",
        headers=_auth(admin_token),
        files=_sql(DDL, nombre="datos.csv"),
    )
    assert r.status_code == 409, r.text
    assert ".sql" in r.json()["message"]


async def test_subir_ddl_exige_escritura_en_el_inventario(client, admin_token):
    system_id = await _crear_sistema(client, admin_token)
    token = await _usuario(client, admin_token, UserRole.DEVELOPER)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets/ddl",
        headers=_auth(token),
        files=_sql(DDL),
    )
    assert r.status_code == 403


# --- ingesta de documentos (INV3) --------------------------------------------


async def test_subir_un_documento_extrae_conocimiento(
    client, admin_token, monkeypatch, tmp_path
):
    """Flujo completo con el LLM MOCKEADO (REGLA DE PRESUPUESTO).

    El cortafuegos autouse de conftest hace que un descuido aquí falle con un
    mensaje claro en vez de salir a la red.
    """
    import json
    import re

    from ai.llm.providers.anthropic import AnthropicLLMClient
    from app.config.settings import settings as app_settings
    from tests.inventory.fixtures import (
        APLICACIONES,
        DOCUMENTO_SINTETICO,
        MICROSERVICIOS,
        TABLAS_MAESTRAS,
        knowledge_del_documento,
    )

    monkeypatch.setattr(app_settings, "STORAGE_DIR", str(tmp_path))

    class _Mensaje:
        def __init__(self, content):
            self.content = content

    class ChatFalso:
        """Emula ``ChatAnthropic``: ``ainvoke`` devuelve un mensaje con ``.content``.

        El doble tiene que ser el **chat**, no un ``LLMClient``: el endpoint le
        pasa a ``extract_knowledge`` lo que devuelve la fábrica, y eso es el
        adaptador real del proveedor. Se responde con la forma de LISTA DE
        BLOQUES (thinking + text) que devuelve claude-sonnet-5, para que el
        camino ejercitado sea el de producción de punta a punta.
        """

        async def ainvoke(self, messages):
            _rol, user = messages[1]
            ids = re.findall(r"\[(el-\d+)\]", user)
            payload = json.dumps(knowledge_del_documento(ids[0] if ids else "el-0000"))
            return _Mensaje(
                [
                    {"type": "thinking", "thinking": "...", "signature": "abc"},
                    {"type": "text", "text": payload},
                ]
            )

    # El doble se inyecta en la FÁBRICA, que es donde LLM0 puso la construcción
    # del cliente. Antes se inyectaba en ``get_claude_client`` y se llegaba al
    # adaptador real por su camino de respaldo; ahora se construye el adaptador
    # real con el chat falso dentro, que dice lo mismo de forma directa y además
    # comprueba el rol y la clase de dato con que el endpoint pide el cliente.
    # Es lo que exige la capa 1 del cortafuegos (LLM1): fuera de la fábrica no
    # hay clientes, y el que sale de ella no puede llamar.
    def _fabrica_falsa(agent_role, *, data_class):
        assert agent_role == "inventory_doc"
        assert data_class == "real"
        return AnthropicLLMClient(client=ChatFalso())

    monkeypatch.setattr("ai.llm.get_llm", _fabrica_falsa)

    system_id = await _crear_sistema(client, admin_token)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets/document",
        headers=_auth(admin_token),
        files={
            "file": (
                "modernizacion.md",
                DOCUMENTO_SINTETICO.encode("utf-8"),
                "text/markdown",
            )
        },
    )
    assert r.status_code == 200, r.text
    reporte = r.json()["data"]["extraction_report"]
    assert reporte["modules"] == len(APLICACIONES) + len(MICROSERVICIOS)
    assert reporte["entities"] == len(TABLAS_MAESTRAS)
    assert reporte["decisions"] == 2
    assert reporte["discarded"] == []

    # Un activo `document` + uno `module` por módulo, todos con origen documento.
    r = await client.get(
        f"/api/v1/inventario/systems/{system_id}/assets", headers=_auth(admin_token)
    )
    items = r.json()["data"]["items"]
    assert len([i for i in items if i["asset_type"] == "document"]) == 1
    assert len([i for i in items if i["asset_type"] == "module"]) == 21
    assert all(i["origin"] == "document" for i in items)
    assert all(i["origin_ref"] == "modernizacion.md" for i in items)
    # Nace importado: cargar no es revisar.
    assert all(i["validation_status"] == "importado" for i in items)


async def test_un_documento_de_extension_no_soportada_se_rechaza(
    client, admin_token, monkeypatch, tmp_path
):
    from app.config.settings import settings as app_settings

    monkeypatch.setattr(app_settings, "STORAGE_DIR", str(tmp_path))
    system_id = await _crear_sistema(client, admin_token)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets/document",
        headers=_auth(admin_token),
        files={"file": ("hoja.xlsx", b"contenido", "application/vnd.ms-excel")},
    )
    assert r.status_code == 400, r.text


async def test_subir_documento_exige_escritura(client, admin_token):
    system_id = await _crear_sistema(client, admin_token)
    token = await _usuario(client, admin_token, UserRole.QA)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets/document",
        headers=_auth(token),
        files={"file": ("doc.md", b"# algo", "text/markdown")},
    )
    assert r.status_code == 403


# --- promoción al inventario (INV6) ------------------------------------------


async def _job_bd_completado(engine, artifact: dict) -> str:
    """Crea un job de BD terminado con su artefacto (sin correr el pipeline)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.agent import AgentType, JobStatus
    from app.repositories.agent_job_repository import AgentJobRepository

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        repo = AgentJobRepository(session)
        job = await repo.create_job(agent_type=AgentType.BD)
        await repo.update_job_status(job.id, JobStatus.COMPLETED)
        await repo.save_artifact(job.id, artifact, "1.0.0")
        await session.commit()
        return job.id


def _artefacto_bd(*tablas: str) -> dict:
    return {
        "target": {"engine": "postgresql"},
        "tables": [
            {
                "name": t,
                "columns": [
                    {
                        "name": f"{t}_id",
                        "logical_type": "bigint",
                        "type": "BIGINT",
                        "nullable": False,
                        "is_primary_key": True,
                    }
                ],
                "primary_key": {"name": f"pk_{t}", "columns": [f"{t}_id"]},
            }
            for t in tablas
        ],
    }


async def test_promover_un_job_de_bd_crea_el_activo(client, admin_token, engine):
    system_id = await _crear_sistema(client, admin_token)
    job_id = await _job_bd_completado(engine, _artefacto_bd("envios", "eventos"))

    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/promote",
        headers=_auth(admin_token),
        json={"job_id": job_id},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["origin"] == "isdf"
    assert job_id in data["origin_ref"]
    assert "generado por ISDF" in data["origin_ref"]
    assert set(data["changes"]["added"]) == {"envios", "eventos"}


async def test_promover_dos_veces_MEZCLA_y_no_pierde_lo_anterior(
    client, admin_token, engine
):
    """El riesgo real del bloque, verificado de extremo a extremo."""
    system_id = await _crear_sistema(client, admin_token)

    primero = await _job_bd_completado(engine, _artefacto_bd("envios", "eventos"))
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/promote",
        headers=_auth(admin_token),
        json={"job_id": primero},
    )
    assert r.status_code == 200, r.text

    segundo = await _job_bd_completado(engine, _artefacto_bd("clientes"))
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/promote",
        headers=_auth(admin_token),
        json={"job_id": segundo},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["version"] == 2
    assert data["changes"]["added"] == ["clientes"]
    assert set(data["changes"]["kept"]) == {"envios", "eventos"}

    # Y el activo vigente tiene LAS TRES tablas.
    r = await client.get(
        f"/api/v1/inventario/assets/{data['id']}", headers=_auth(admin_token)
    )
    nombres = {t["name"] for t in r.json()["data"]["content"]["tables"]}
    assert nombres == {"envios", "eventos", "clientes"}


async def test_no_se_promueve_un_job_sin_terminar(client, admin_token, engine):
    """Un artefacto a medias metería en el inventario un diseño incompleto."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.agent import AgentType, JobStatus
    from app.repositories.agent_job_repository import AgentJobRepository

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        repo = AgentJobRepository(session)
        job = await repo.create_job(agent_type=AgentType.BD)
        await repo.update_job_status(job.id, JobStatus.FAILED)
        await session.commit()
        job_id = job.id

    system_id = await _crear_sistema(client, admin_token)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/promote",
        headers=_auth(admin_token),
        json={"job_id": job_id},
    )
    assert r.status_code == 409, r.text
    assert "terminado" in r.json()["message"]


async def test_no_se_promueve_un_agente_que_no_produce_activos(
    client, admin_token, engine
):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.agent import AgentType, JobStatus
    from app.repositories.agent_job_repository import AgentJobRepository

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        repo = AgentJobRepository(session)
        job = await repo.create_job(agent_type=AgentType.SCRUM)
        await repo.update_job_status(job.id, JobStatus.COMPLETED)
        await repo.save_artifact(job.id, {"epics": []}, "1.0.0")
        await session.commit()
        job_id = job.id

    system_id = await _crear_sistema(client, admin_token)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/promote",
        headers=_auth(admin_token),
        json={"job_id": job_id},
    )
    assert r.status_code == 409, r.text
    assert "no produce activos" in r.json()["message"]


async def test_promover_exige_escritura_en_el_inventario(client, admin_token, engine):
    system_id = await _crear_sistema(client, admin_token)
    job_id = await _job_bd_completado(engine, _artefacto_bd("envios"))
    token = await _usuario(client, admin_token, UserRole.DEVELOPER)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/promote",
        headers=_auth(token),
        json={"job_id": job_id},
    )
    assert r.status_code == 403


async def test_el_arquitecto_si_puede_promover(client, admin_token, engine):
    token = await _usuario(client, admin_token, UserRole.ARQUITECTO)
    system_id = await _crear_sistema(client, token, name="TMS Legado")
    job_id = await _job_bd_completado(engine, _artefacto_bd("envios"))
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/promote",
        headers=_auth(token),
        json={"job_id": job_id},
    )
    assert r.status_code == 200, r.text


# --- introspección: guard en la API ------------------------------------------


async def test_la_introspeccion_exige_rol_admin_no_basta_inventario_full(
    client, admin_token
):
    """Se conecta a producción: el arquitecto cura el inventario, pero no esto.

    Si bastara `inventario` FULL, un grant de inventario daría acceso a bases de
    datos de producción. Fail-closed, mismo criterio que los endpoints que mutan
    roles.
    """
    system_id = await _crear_sistema(client, admin_token)
    token = await _usuario(client, admin_token, UserRole.ARQUITECTO)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets/introspect",
        headers=_auth(token),
        json={"alias": "legado"},
    )
    assert r.status_code == 403, r.text
    assert "Administrador" in r.json()["message"]

    r = await client.get(
        "/api/v1/inventario/introspection/sources", headers=_auth(token)
    )
    assert r.status_code == 403


async def test_sin_configuracion_la_introspeccion_no_conecta_a_nada(
    client, admin_token
):
    """Por defecto está desactivada: no hay orígenes y no se puede invocar."""
    r = await client.get(
        "/api/v1/inventario/introspection/sources", headers=_auth(admin_token)
    )
    assert r.status_code == 200
    assert r.json()["data"]["items"] == []

    system_id = await _crear_sistema(client, admin_token)
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets/introspect",
        headers=_auth(admin_token),
        json={"alias": "lo_que_sea"},
    )
    assert r.status_code == 403, r.text
    assert "desactivada" in r.json()["message"]


# --- autorización ------------------------------------------------------------


async def test_sin_token_es_401(client):
    r = await client.get("/api/v1/inventario/systems")
    assert r.status_code == 401


async def test_todos_los_roles_pueden_consultar_el_inventario(client, admin_token):
    """Es conocimiento transversal: nadie debería tener que pedir permiso."""
    await _crear_sistema(client, admin_token)
    for role in (
        UserRole.PROCESOS,
        UserRole.ANALISTA,
        UserRole.ARQUITECTO,
        UserRole.DEVELOPER,
        UserRole.QA,
    ):
        token = await _usuario(client, admin_token, role)
        r = await client.get("/api/v1/inventario/systems", headers=_auth(token))
        assert r.status_code == 200, f"{role.value} no puede leer: {r.text}"
        assert len(r.json()["data"]["items"]) == 1


async def test_el_arquitecto_cura_el_inventario(client, admin_token):
    token = await _usuario(client, admin_token, UserRole.ARQUITECTO)
    system_id = await _crear_sistema(client, token, name="TMS Legado")
    r = await client.post(
        f"/api/v1/inventario/systems/{system_id}/assets",
        headers=_auth(token),
        json={
            "asset_type": "db_schema",
            "name": "core",
            "content": esquema("usuarios"),
            "origin": "ddl_dump",
        },
    )
    assert r.status_code == 200, r.text


async def test_los_demas_roles_no_escriben_en_el_inventario(client, admin_token):
    """403 exacto: leer sí, curar no."""
    system_id = await _crear_sistema(client, admin_token)
    for role in (
        UserRole.PROCESOS,
        UserRole.ANALISTA,
        UserRole.DEVELOPER,
        UserRole.QA,
    ):
        token = await _usuario(client, admin_token, role)
        r = await client.post(
            "/api/v1/inventario/systems",
            headers=_auth(token),
            json={"name": f"Intento {role.value}", "kind": "legado"},
        )
        assert r.status_code == 403, f"{role.value} pudo crear un sistema: {r.text}"

        r = await client.post(
            f"/api/v1/inventario/systems/{system_id}/assets",
            headers=_auth(token),
            json={
                "asset_type": "db_schema",
                "name": "core",
                "content": esquema("usuarios"),
                "origin": "ddl_dump",
            },
        )
        assert r.status_code == 403, f"{role.value} pudo cargar un activo: {r.text}"

        r = await client.delete(
            f"/api/v1/inventario/systems/{system_id}", headers=_auth(token)
        )
        assert r.status_code == 403


async def test_el_403_explica_que_es_solo_lectura(client, admin_token):
    """El mensaje distingue "sin acceso" de "solo lectura" (contrato de la casa)."""
    token = await _usuario(client, admin_token, UserRole.QA)
    r = await client.post(
        "/api/v1/inventario/systems",
        headers=_auth(token),
        json={"name": "Otro", "kind": "legado"},
    )
    assert r.status_code == 403
    assert "solo permite consultar" in r.json()["message"]


async def test_me_expone_el_modulo_inventario(client, admin_token):
    """El frontend pinta la navegación con esto; sin la clave, no hay sección."""
    token = await _usuario(client, admin_token, UserRole.DEVELOPER)
    r = await client.get("/api/v1/auth/me", headers=_auth(token))
    assert r.json()["data"]["modules"]["inventario"] == "read"

    r = await client.get("/api/v1/auth/me", headers=_auth(admin_token))
    assert r.json()["data"]["modules"]["inventario"] == "full"
