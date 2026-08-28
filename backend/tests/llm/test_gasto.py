"""GAS1 — el libro mayor y el freno: la medición, la aritmética y el fail-closed.

Lo que se fija aquí no es que el gasto se mida, sino que **falla hacia el lado
seguro**: sin libro mayor no se llama, la ausencia de ``usage`` no vale cero, y
el tope se comprueba **antes** de gastar y no después.

Ver ``docs/diseno-control-de-gasto.md``.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ai.llm import PROVIDERS, budget, get_llm
from ai.llm.metering import (
    Completion,
    MeteredLLMClient,
    Usage,
    costo,
    costo_maximo_de_una_llamada,
    usage_desde_mensaje,
)
from ai.llm.pricing import compute_cost
from app.config.settings import settings

PRECIOS = (3.0, 15.0)


class MensajeFalso:
    """``AIMessage`` realista: lista de bloques (thinking+text) y su ``usage``."""

    def __init__(self, texto="{}", usage=None):
        self.content = [
            {"type": "thinking", "thinking": "..."},
            {"type": "text", "text": texto},
        ]
        if usage is not None:
            self.usage_metadata = usage


class ClienteInterno:
    """Doble del cliente del proveedor: devuelve ``Completion``, cuenta llamadas."""

    provider = "anthropic"
    model = "claude-sonnet-5"
    data_class = "sintetico"

    def __init__(self, usage=None, texto='{"ok": true}'):
        self.usage = usage
        self.texto = texto
        self.llamadas: list[tuple[str, str]] = []

    async def complete(self, *, system: str, user: str) -> Completion:
        self.llamadas.append((system, user))
        return Completion(text=self.texto, usage=self.usage)


class InternoQueExplota:
    """Si el freno funciona, este cliente NUNCA llega a invocarse."""

    provider = "anthropic"
    model = "claude-sonnet-5"
    data_class = "real"

    async def complete(self, *, system: str, user: str) -> Completion:
        raise AssertionError(
            "El freno dejó pasar la llamada: se tocó el cliente interno. El tope "
            "tiene que negarse ANTES de gastar, no después."
        )


def medido(interno, *, job_id="JOB-1", agent_role="qa", stage=None):
    return MeteredLLMClient(interno, agent_role=agent_role, job_id=job_id, stage=stage)


# ---------------------------------------------------------------------------
# GAS-D2 — todo lo que sale de la fábrica sale medido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("proveedor", sorted(PROVIDERS))
def test_todo_proveedor_registrado_sale_medido_de_la_fabrica(proveedor, monkeypatch):
    """El candado del bloque: la medición es función de ``PROVIDERS``.

    Igual que el cortafuegos de LLM1: envolver en ``get_llm`` y no en cada
    proveedor existe para que registrar uno nuevo herede la medición y el freno
    sin que nadie se acuerde. Si esto se comprobara solo sobre Anthropic, el
    segundo proveedor entraría sin freno y la suite seguiría verde.
    """
    monkeypatch.setattr(settings, "LLM_PROVIDER", proveedor)
    monkeypatch.setattr(settings, "LLM_ROLE_OVERRIDES", {})
    llm = get_llm("ef", data_class="sintetico", job_id="JOB-1")
    assert isinstance(llm, MeteredLLMClient)
    assert llm.job_id == "JOB-1"


@pytest.mark.parametrize("proveedor", sorted(PROVIDERS))
def test_todo_proveedor_expone_el_protocolo_interno(proveedor):
    """Sin ``complete`` no hay ``usage``, y el proveedor produciría filas 100%
    estimadas sin que nada lo dijera. Se exige el método, no se tolera su falta."""
    spec = PROVIDERS[proveedor]
    cliente = spec.build_client(model=spec.default_model(), data_class="sintetico")
    interno = getattr(cliente, "inner", cliente)
    assert hasattr(interno, "complete"), (
        f"El proveedor '{proveedor}' no implementa `complete(...) -> Completion`, "
        "así que su gasto se anotaría siempre como ESTIMADO."
    )


def test_la_fabrica_no_falsea_la_identidad_al_envolver():
    """El envoltorio delega, no contesta por su cuenta: si inventara el proveedor
    o el modelo, los tests que vigilan la resolución vigilarían al envoltorio."""
    llm = get_llm("bd", data_class="sintetico", job_id=None)
    assert llm.provider == "anthropic"
    assert llm.model == settings.CLAUDE_MODEL
    assert llm.data_class == "sintetico"


# ---------------------------------------------------------------------------
# GAS-D4 — usage ausente NO es usage cero
# ---------------------------------------------------------------------------


async def test_un_mensaje_realista_da_usage_real_y_los_cinco_contadores(libro_mayor):
    interno = ClienteInterno(
        usage=Usage(
            input_tokens=1000,
            output_tokens=400,
            cache_read=200,
            cache_write=50,
            reasoning=120,
        )
    )
    await medido(interno, stage="EDGE_CASES").complete_json(system="s", user="u")

    (fila,) = libro_mayor.filas
    assert fila.usage_source == "real"
    assert (fila.input_tokens, fila.output_tokens) == (1000, 400)
    assert (fila.cache_read_tokens, fila.cache_write_tokens) == (200, 50)
    assert fila.reasoning_tokens == 120
    assert fila.stage == "EDGE_CASES"
    assert fila.agent_role == "qa"
    assert fila.job_id == "JOB-1"


async def test_sin_usage_la_fila_va_estimada_y_JAMAS_en_cero(libro_mayor, caplog):
    """Se prueba QUITANDO el ``usage``, no asumiéndolo.

    Anotar 0 dejaría el tope ciego: el sistema seguiría gastando creyendo que no
    gasta, que es el único resultado peor que pararse.
    """
    interno = ClienteInterno(usage=None, texto='{"algo": "con contenido real"}')
    with caplog.at_level("WARNING"):
        await medido(interno).complete_json(system="sistema largo", user="usuario")

    (fila,) = libro_mayor.filas
    assert fila.usage_source == "estimado"
    assert fila.input_tokens > 0 and fila.output_tokens > 0
    assert fila.cost_usd > 0
    assert "no reportó usage" in caplog.text


def test_el_extractor_de_usage_distingue_ausencia_de_cero():
    assert usage_desde_mensaje(MensajeFalso()) is None
    assert usage_desde_mensaje(MensajeFalso(usage={"input_tokens": 0})) is None
    leido = usage_desde_mensaje(
        MensajeFalso(
            usage={
                "input_tokens": 10,
                "output_tokens": 3,
                "input_token_details": {"cache_read": 4, "cache_creation": 1},
                "output_token_details": {"reasoning": 2},
            }
        )
    )
    assert leido == Usage(10, 3, cache_read=4, cache_write=1, reasoning=2)


# ---------------------------------------------------------------------------
# GAS-D3 — la aritmética de la caché
# ---------------------------------------------------------------------------


def test_sin_cache_el_costo_es_byte_a_byte_el_de_siempre():
    """Hoy el caching no está activado, así que la fórmula nueva DEBE reducirse a
    la vieja. Si no, este bloque sería un cambio de números disfrazado de freno."""
    for entrada, salida in ((5061, 6133), (107181, 22110), (1, 1), (0, 0)):
        assert float(costo(Usage(entrada, salida), PRECIOS)) == compute_cost(
            entrada, salida, PRECIOS
        )


def test_con_cache_se_aplica_la_tarifa_correcta_y_reasoning_no_suma():
    """``input_tokens`` viene con la caché YA sumada: aplicarle la tarifa plana
    cobraría 10x de más las lecturas y 20% de menos las escrituras."""
    usage = Usage(
        input_tokens=1000,
        output_tokens=100,
        cache_read=600,
        cache_write=200,
        reasoning=60,
    )
    # base = 1000 - 600 - 200 = 200
    esperado = Decimal(
        str((200 * 3 + 600 * 3 * 0.10 + 200 * 3 * 1.25 + 100 * 15) / 1_000_000)
    )
    assert costo(usage, PRECIOS).quantize(Decimal("0.000001")) == esperado.quantize(
        Decimal("0.000001")
    )
    # `reasoning` es un SUBCONJUNTO de output, ya cobrado: subirlo no mueve nada.
    assert costo(usage, PRECIOS) == costo(
        Usage(1000, 100, cache_read=600, cache_write=200, reasoning=99), PRECIOS
    )


def test_una_base_negativa_yerra_hacia_cobrar_de_mas(caplog):
    """No debería ocurrir —la caché no puede exceder al total que la incluye—.

    Si ocurre, el error va del lado que NO deja el tope ciego: la base se cae a
    ``input_tokens`` y los términos de caché siguen sumando, así que el resultado
    es el máximo defendible y nunca menos que tratar la entrada como plana. Y se
    avisa: un dato incoherente que se corrige en silencio es un dato incoherente
    que nadie va a investigar.
    """
    raro = Usage(input_tokens=100, output_tokens=0, cache_read=500)
    with caplog.at_level("WARNING"):
        cobrado = costo(raro, PRECIOS)
    assert cobrado > costo(Usage(100, 0), PRECIOS)
    assert "menor que la caché declarada" in caplog.text


def test_el_costo_maximo_de_una_llamada_sale_de_los_supuestos_declarados():
    """100 000 in x $3 + 8 192 out x $15 = 0,42288. Es el número que dimensiona
    los dos márgenes, y por eso los dos supuestos son configurables."""
    assert costo_maximo_de_una_llamada(PRECIOS) == Decimal("0.422880")


# ---------------------------------------------------------------------------
# GAS-D7 — sin libro mayor legible, la llamada se NIEGA
# ---------------------------------------------------------------------------


async def test_sin_sumidero_instalado_la_llamada_se_niega(monkeypatch):
    """El fail-closed, visto FALLAR: se quita el sumidero de pruebas y la misma
    llamada que pasa abajo, aquí no pasa."""
    monkeypatch.setattr("ai.llm.budget._SINK", budget.SumideroQueNiega())
    with pytest.raises(budget.BudgetUnavailableError, match="libro mayor"):
        await medido(InternoQueExplota()).complete_json(system="s", user="u")


async def test_con_el_sumidero_instalado_la_misma_llamada_pasa(libro_mayor):
    """La otra mitad del par: sin esto, el test de arriba no distingue el
    fail-closed de un cliente que simplemente no funciona."""
    texto = await medido(ClienteInterno(usage=Usage(10, 5))).complete_json(
        system="s", user="u"
    )
    assert texto == '{"ok": true}'
    assert len(libro_mayor.filas) == 1


async def test_un_libro_mayor_que_revienta_al_leer_tambien_niega(monkeypatch):
    """La base caída no es "gastado = 0": es "no se sabe", y no se sabe niega."""

    class SumideroRoto:
        async def totales(self, **_kwargs):
            raise RuntimeError("la base no responde")

        async def anotar(self, fila):  # pragma: no cover - no se llega
            raise AssertionError("no debería anotarse nada")

    monkeypatch.setattr("ai.llm.budget._SINK", SumideroRoto())
    with pytest.raises(budget.BudgetUnavailableError, match="fail-closed"):
        await medido(InternoQueExplota()).complete_json(system="s", user="u")


async def test_si_no_se_puede_anotar_se_falla_en_vez_de_seguir(monkeypatch):
    """El dinero ya está gastado, pero una fila que no se escribe es gasto que el
    tope no ve — y a partir de ahí el freno protege un número que no es el real."""

    class SumideroQueNoAnota:
        async def totales(self, **_kwargs):
            return budget.Totales(mes_usd=Decimal("0"), job_usd=Decimal("0"))

        async def anotar(self, fila):
            raise RuntimeError("disco lleno")

    monkeypatch.setattr("ai.llm.budget._SINK", SumideroQueNoAnota())
    with pytest.raises(budget.BudgetUnavailableError, match="YA FACTURADA|no se pudo"):
        await medido(ClienteInterno(usage=Usage(1, 1))).complete_json(
            system="s", user="u"
        )


# ---------------------------------------------------------------------------
# GAS-D5 / GAS-D6 — los topes, el margen y el MENSAJE
# ---------------------------------------------------------------------------


def _sumidero_con(mes="0", job="0"):
    class Fijo:
        filas: list = []

        async def totales(self, **_kwargs):
            return budget.Totales(mes_usd=Decimal(mes), job_usd=Decimal(job))

        async def anotar(self, fila):
            self.filas.append(fila)

    return Fijo()


async def test_el_freno_del_job_niega_ANTES_de_tocar_el_cliente(monkeypatch):
    monkeypatch.setattr("ai.llm.budget._SINK", _sumidero_con(job="4.9"))
    with pytest.raises(budget.BudgetExceededError) as exc:
        await medido(InternoQueExplota()).complete_json(system="s", user="u")
    assert exc.value.code == "budget_job_cap"


async def test_el_freno_del_mes_niega_ANTES_de_tocar_el_cliente(monkeypatch):
    monkeypatch.setattr("ai.llm.budget._SINK", _sumidero_con(mes="99.9"))
    with pytest.raises(budget.BudgetExceededError) as exc:
        await medido(InternoQueExplota(), job_id=None).complete_json(
            system="s", user="u"
        )
    assert exc.value.code == "budget_monthly_cap"


async def test_el_mensaje_dice_cuanto_llevaba_y_cuanto_pedia_lo_que_lo_cruzo(
    monkeypatch,
):
    """Sin esas dos cifras, subir el tope es a ciegas: se sabe que frenó, pero no
    si frenó por poco o por mucho ni cuánto habría hecho falta."""
    monkeypatch.setattr("ai.llm.budget._SINK", _sumidero_con(job="4.5000"))
    with pytest.raises(budget.BudgetExceededError) as exc:
        await medido(InternoQueExplota()).complete_json(system="s", user="u")

    mensaje = str(exc.value)
    assert "5.0000" in mensaje, "no dice cuál es el tope"
    assert "4.5000" in mensaje, "no dice cuánto llevaba gastado"
    assert "0.4229" in mensaje, "no dice cuánto pedía la llamada que lo cruzó"
    assert "1.2686" in mensaje, "no dice el margen reservado"
    assert "LLM_JOB_CAP_USD" in mensaje, "no dice qué variable subir"


async def test_los_tres_numeros_son_configurables_por_entorno(monkeypatch):
    """El tope tiene que poder subirse cuando llegue un documento de Procesos
    grande: los 5 USD están dimensionados sobre 28 filas, de las cuales solo ~8
    son corridas reales, y se recalibran con datos."""
    monkeypatch.setattr(settings, "LLM_JOB_CAP_USD", 50.0)
    monkeypatch.setattr("ai.llm.budget._SINK", _sumidero_con(job="4.9"))
    interno = ClienteInterno(usage=Usage(1, 1))
    await medido(interno).complete_json(system="s", user="u")  # ya no frena
    assert len(interno.llamadas) == 1


def test_el_objetivo_del_mes_NO_bloquea():
    """El tercer número se reporta y nunca frena: un objetivo que solo se
    manifiesta cuando el freno actúa se cumple por accidente."""
    assert settings.LLM_MONTHLY_TARGET_USD < settings.LLM_MONTHLY_CAP_USD
    # Gastado por encima del objetivo pero por debajo del techo: no frena.
    budget.verificar_mes(Decimal("40"), Decimal("0.42288"))
    with pytest.raises(budget.BudgetExceededError):
        budget.verificar_mes(Decimal("99.9"), Decimal("0.42288"))


def test_el_margen_impide_cruzar_el_tope_con_llamadas_en_vuelo():
    """El precio declarado: un pedazo de techo inutilizable a cambio de que el
    tope duro no se cruce nunca."""
    tope = Decimal(str(settings.LLM_MONTHLY_CAP_USD))
    margen = budget.margen_del_mes(Decimal("0.42288"))
    assert margen == Decimal("3.38304")
    budget.verificar_mes(tope - margen, Decimal("0.42288"))  # justo en el filo
    with pytest.raises(budget.BudgetExceededError):
        budget.verificar_mes(tope - margen + Decimal("0.01"), Decimal("0.42288"))


async def test_sin_job_id_no_hay_freno_de_job_pero_SI_se_anota(libro_mayor):
    """La ingesta de documentos del inventario. Si no contara para el mes, el mes
    tendría una fuga por el único sitio que ingiere documentos reales."""
    llm = medido(
        ClienteInterno(usage=Usage(9000, 500)), job_id=None, agent_role="inventory_doc"
    )
    await llm.complete_json(system="s", user="u")
    (fila,) = libro_mayor.filas
    assert fila.job_id is None
    assert fila.agent_role == "inventory_doc"
    assert fila.cost_usd > 0


# ---------------------------------------------------------------------------
# GAS-D8 — el mes se corta en America/Lima
# ---------------------------------------------------------------------------


def test_el_mes_se_corta_en_lima_y_no_en_la_zona_del_servidor():
    """Un contenedor en UTC rueda de mes a las 19:00 de Lima. La fila de las
    21:00 del 31 de agosto en Lima es del 1 de septiembre en UTC, y pertenece a
    AGOSTO."""
    fin_de_agosto_en_lima = datetime(2026, 9, 1, 2, 0, tzinfo=timezone.utc)
    assert budget.etiqueta_del_mes(fin_de_agosto_en_lima) == "2026-08"

    desde, hasta = budget.limites_del_mes(fin_de_agosto_en_lima)
    assert desde == datetime(2026, 8, 1, 5, 0, tzinfo=timezone.utc)
    assert hasta == datetime(2026, 9, 1, 5, 0, tzinfo=timezone.utc)
    assert desde <= fin_de_agosto_en_lima < hasta


def test_el_corte_de_diciembre_no_se_sale_del_calendario():
    desde, hasta = budget.limites_del_mes(
        datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc)
    )
    assert (desde.year, desde.month) == (2026, 12)
    assert (hasta.year, hasta.month) == (2027, 1)


def test_la_zona_tiene_un_unico_lector(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BUDGET_TZ", "UTC")
    desde, _ = budget.limites_del_mes(datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc))
    assert desde == datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# GAS-D10 — la atribución por nodo, y la concurrencia
# ---------------------------------------------------------------------------


async def test_for_stage_etiqueta_sin_duplicar_el_cliente():
    interno = ClienteInterno(usage=Usage(1, 1))
    base = medido(interno)
    etiquetado = base.for_stage("TEST_DESIGN")
    assert etiquetado.stage == "TEST_DESIGN"
    assert base.stage is None
    assert etiquetado.inner is interno
    assert etiquetado.job_id == base.job_id


async def test_tres_workers_concurrentes_no_se_cruzan_la_atribucion(libro_mayor):
    """El caso que mata a ``client.last_usage``: el cliente es COMPARTIDO por los
    workers de un *map*, así que un atributo mutable atribuiría el ``usage`` de
    una llamada a otra. Con una fila por llamada, no hay dónde cruzarse."""

    class InternoPorLlamada:
        provider = "anthropic"
        model = "claude-sonnet-5"
        data_class = "real"

        async def complete(self, *, system, user):
            n = int(user)
            await asyncio.sleep(0.01 * (3 - n))  # terminan en orden inverso
            return Completion(text="{}", usage=Usage(n * 100, n))

    compartido = medido(InternoPorLlamada()).for_stage("EDGE_CASES")
    await asyncio.gather(
        *(compartido.complete_json(system="s", user=str(n)) for n in (1, 2, 3))
    )

    porcentajes = {f.input_tokens: f.output_tokens for f in libro_mayor.filas}
    assert porcentajes == {100: 1, 200: 2, 300: 3}
    assert {f.stage for f in libro_mayor.filas} == {"EDGE_CASES"}


async def test_un_item_que_repara_dos_veces_deja_TRES_filas(libro_mayor):
    """La tasa de reparación deja de ser folclore: es ``filas / ítems - 1``.

    Es la causa 1 del subconteo —el loop factura hasta 3 veces y se apuntaba 1— y
    la métrica principal que OLL-D1 declara para el experimento local.
    """
    from pydantic import BaseModel

    from ai.agents.base.structured import run_structured_map

    class Esquema(BaseModel):
        valor: int

    class InternoQueReparaDosVeces:
        provider = "anthropic"
        model = "claude-sonnet-5"
        data_class = "real"

        def __init__(self):
            self.n = 0

        async def complete(self, *, system, user):
            self.n += 1
            texto = "no es json" if self.n < 3 else '{"valor": 7}'
            return Completion(text=texto, usage=Usage(10, 5))

    resultados, cuarentena, _ = await run_structured_map(
        medido(InternoQueReparaDosVeces()),
        [{"ref": "R-1"}],
        build_system=lambda i: "s",
        build_user=lambda i: "u",
        schema=Esquema,
        ref_of=lambda i: i["ref"],
        stage="ESTIMATE",
        estimate_tokens=len,
    )
    assert not cuarentena and resultados[0]["data"] == {"valor": 7}
    assert len(libro_mayor.filas) == 3, "un ítem, tres llamadas, tres filas"
    assert {f.stage for f in libro_mayor.filas} == {"ESTIMATE"}


async def test_run_structured_map_tolera_un_mock_sin_for_stage(libro_mayor):
    """Los mocks de la suite no tienen ``for_stage`` y no deben tenerlo: es una
    etiqueta, no dinero, así que su ausencia no es fail-open."""
    from ai.agents.base.structured import for_stage

    class MockPelado:
        async def complete_json(self, *, system, user):
            return "{}"

    mock = MockPelado()
    assert for_stage(mock, "LO_QUE_SEA") is mock


# ---------------------------------------------------------------------------
# El cortafuegos: la capa 1 tiene que tapar las DOS bocas
# ---------------------------------------------------------------------------


async def test_la_capa_1_tapa_las_DOS_bocas_del_cliente():
    """La capa 1 tapaba ``complete_json``; el envoltorio llama a ``complete``.

    Se comprueba **estructuralmente** —que las dos bocas sean atributos de
    instancia puestos por el cortafuegos— y no solo llamando: llamar no
    distingue nada, porque con Anthropic la llamada choca igualmente contra la
    capa 3 (``get_claude_client``) y el test pasaría con la capa 1 rota. Lo que
    la capa 1 aporta es cubrir a **todo proveedor registrado**, incluido el que
    no pase por esa costura histórica; ese es el hueco que esto vigila.
    """
    llm = get_llm("ef", data_class="real", job_id="JOB-1")
    interno = llm.inner
    for boca in ("complete_json", "complete"):
        assert boca in vars(interno), (
            f"La capa 1 del cortafuegos no tapó `{boca}` en el cliente que "
            "devuelve la fábrica. `MeteredLLMClient` llama al protocolo INTERNO "
            "`complete(...)`, así que tapar solo la boca pública deja salir a la "
            "red a cualquier proveedor que no pase por `get_claude_client`."
        )
    with pytest.raises(AssertionError, match="REGLA DE PRESUPUESTO"):
        await llm.complete_json(system="s", user="u")
