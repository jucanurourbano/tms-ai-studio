"""GAS2 — ``GET /gasto/mensual``: el permiso, la honestidad y el desglose.

Un tope que no se mira se conoce bloqueando. Este endpoint es la ventana, y lo
que se ejerce aqui es que sea una ventana honesta: que diga cuanto se lleva
gastado contra los TRES numeros (incluido el objetivo, que no frena nunca y por
eso es el que se olvida), que declare que fraccion de la cifra es una estimacion
y que reparta el gasto por nodo del grafo, que es el desglose con el que se
demuestra un recorte.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from ai.llm.budget import SpendRow
from app.core.permissions import UserRole
from app.dependencies.database import get_session
from app.models.agent import AgentType
from app.repositories.agent_job_repository import AgentJobRepository
from app.repositories.llm_spend_repository import LlmSpendRepository
from main import app

PASSWORD = "superseguro1"


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(factory):
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


@pytest_asyncio.fixture
async def qa_token(client, admin_token) -> str:
    """Un rol funcional cualquiera: tiene su modulo, no tiene ``config``."""
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "qa@urbano.com.pe",
            "full_name": "QA Uno",
            "password": PASSWORD,
            "role": UserRole.QA.value,
        },
        headers=_auth(admin_token),
    )
    assert r.status_code == 200, r.text
    return await _login(client, "qa@urbano.com.pe")


def fila(**kwargs) -> SpendRow:
    base = dict(
        agent_role="qa",
        provider="anthropic",
        model="claude-sonnet-5",
        usage_source="real",
        input_tokens=1000,
        output_tokens=200,
        cost_usd=Decimal("0.010000"),
    )
    base.update(kwargs)
    return SpendRow(**base)


async def sembrar(factory, *filas) -> None:
    async with factory() as session:
        repo = LlmSpendRepository(session)
        for f in filas:
            await repo.anotar(f)
        await session.commit()


async def _get(client, token) -> dict:
    r = await client.get("/api/v1/gasto/mensual", headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ---------------------------------------------------------------------------
# Permiso: ``config`` READ
# ---------------------------------------------------------------------------


async def test_sin_token_responde_401(client):
    assert (await client.get("/api/v1/gasto/mensual")).status_code == 401


async def test_un_rol_sin_config_no_ve_el_gasto_de_la_organizacion(client, qa_token):
    """El desglose del mes es dato de costo de la organizacion. A quien se le
    frena un job le corresponde el mensaje del 409, no esta pantalla."""
    r = await client.get("/api/v1/gasto/mensual", headers=_auth(qa_token))
    assert r.status_code == 403
    # El 403 dice QUE falta, nunca un "no autorizado" seco.
    assert "Configuración" in r.json()["message"]


async def test_config_read_lo_ve(client, admin_token):
    assert (
        await client.get("/api/v1/gasto/mensual", headers=_auth(admin_token))
    ).status_code == 200


# ---------------------------------------------------------------------------
# Los tres numeros (GAS-D6)
# ---------------------------------------------------------------------------


async def test_publica_los_tres_topes_y_el_avance_contra_cada_uno(
    client, admin_token, factory, monkeypatch
):
    """El objetivo no frena nunca, y por eso es el que se cumple por accidente si
    no se publica. Toda cifra se compara contra 30, no contra 100."""
    from app.config.settings import settings

    monkeypatch.setattr(settings, "LLM_MONTHLY_CAP_USD", 100.0)
    monkeypatch.setattr(settings, "LLM_MONTHLY_TARGET_USD", 30.0)
    monkeypatch.setattr(settings, "LLM_JOB_CAP_USD", 5.0)
    await sembrar(factory, fila(cost_usd=Decimal("15.000000")))

    data = await _get(client, admin_token)
    assert data["spent_usd"] == "15.000000"
    assert data["target_usd"] == "30.000000"
    assert data["cap_usd"] == "100.000000"
    assert data["job_cap_usd"] == "5.000000"
    assert data["target_pct"] == 50.0
    assert data["cap_pct"] == 15.0


async def test_un_tope_en_cero_no_reporta_cero_por_ciento(
    client, admin_token, factory, monkeypatch
):
    """Con tope 0, ``0%`` diria "no has empezado" justo cuando cualquier gasto ya
    lo cruzo. El porcentaje no existe, y eso se dice con ``null``."""
    from app.config.settings import settings

    monkeypatch.setattr(settings, "LLM_MONTHLY_TARGET_USD", 0.0)
    await sembrar(factory, fila(cost_usd=Decimal("1.000000")))

    assert (await _get(client, admin_token))["target_pct"] is None


async def test_un_mes_sin_llamadas_no_presume_de_medicion(client, admin_token):
    """Cero llamadas daria ``real`` por aritmetica —cero estimadas de cero— y eso
    afirma calidad de medicion sobre nada (la forma que prohibe GAS-D4)."""
    data = await _get(client, admin_token)
    assert data["calls"] == 0
    assert data["spent_usd"] == "0.000000"
    assert data["usage_source"] == "sin_datos"


# ---------------------------------------------------------------------------
# La fraccion estimada (criterio 2)
# ---------------------------------------------------------------------------


async def test_mixto_y_la_fraccion_estimada_viajan_en_la_respuesta(
    client, admin_token, factory
):
    """La fraccion es del DINERO, no de las llamadas: una sola llamada cara
    estimada mueve la cifra mucho mas que cien baratas, y la de llamadas ya es
    derivable de los dos contadores."""
    await sembrar(
        factory,
        fila(cost_usd=Decimal("3.000000")),
        fila(cost_usd=Decimal("0.010000")),
        fila(cost_usd=Decimal("0.010000")),
        fila(usage_source="estimado", cost_usd=Decimal("1.000000")),
    )

    data = await _get(client, admin_token)
    assert data["usage_source"] == "mixto"
    assert data["estimated_calls"] == 1
    assert data["calls"] == 4
    assert data["estimated_cost_usd"] == "1.000000"
    # 1.00 / 4.02: un cuarto del dinero es deducido aunque solo lo sea 1 de 4
    # llamadas. Esa es la diferencia que hace util medirla sobre el importe.
    assert data["estimated_fraction"] == pytest.approx(0.2488, abs=1e-4)


async def test_todo_medido_dice_real_y_fraccion_cero(client, admin_token, factory):
    await sembrar(factory, fila(cost_usd=Decimal("1.000000")))
    data = await _get(client, admin_token)
    assert data["usage_source"] == "real"
    assert data["estimated_fraction"] == 0.0


# ---------------------------------------------------------------------------
# El desglose (GAS-D10)
# ---------------------------------------------------------------------------


async def test_by_stage_llega_hasta_la_respuesta_con_el_hueco_visible(
    client, admin_token, factory
):
    """El antes/despues de recortar un nodo, y el gasto que ningun nodo reclama."""
    await sembrar(
        factory,
        fila(stage="EDGE_CASES", cost_usd=Decimal("0.800000")),
        fila(stage="EDGE_CASES", cost_usd=Decimal("0.200000")),
        fila(agent_role="ef", stage=None, cost_usd=Decimal("0.300000")),
    )

    por_nodo = {
        (f["agent_role"], f["stage"]): f
        for f in (await _get(client, admin_token))["by_stage"]
    }
    assert por_nodo[("qa", "EDGE_CASES")]["cost_usd"] == "1.000000"
    assert por_nodo[("qa", "EDGE_CASES")]["calls"] == 2
    # El hueco es una fila con su costo, no la ausencia de una fila.
    assert por_nodo[("ef", None)]["cost_usd"] == "0.300000"


async def test_top_jobs_nombra_el_job_y_su_agente(client, admin_token, factory):
    async with factory() as session:
        job = (await AgentJobRepository(session).create_job(AgentType.QA)).id
        await session.commit()
    await sembrar(factory, fila(job_id=job, cost_usd=Decimal("2.000000")))

    top = (await _get(client, admin_token))["top_jobs"]
    assert top[0]["job_id"] == job
    assert top[0]["agent_role"] == "qa"
    assert top[0]["cost_usd"] == "2.000000"


async def test_el_mes_y_su_zona_se_declaran_en_la_respuesta(client, admin_token):
    """El mes del libro mayor puede no ser el de la factura de Anthropic (residual
    declarado en GAS-D8): quien concilie necesita ver contra que periodo lo hace."""
    data = await _get(client, admin_token)
    assert data["timezone"] == "America/Lima"
    assert len(data["month"]) == 7 and data["month"][4] == "-"
    assert data["period"]["from"] < data["period"]["to"]
