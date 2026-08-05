"""Tests del recorrido de linaje transitivo (BD0).

La cadena ISDF se enlaza con un único ``input_job_id`` por job: el Agente BD debe
alcanzar el EF **dos saltos** más arriba (BD → Arquitectura → Scrum → EF). Estos
tests fijan esa escalera y sus casos degenerados (eslabón roto, ciclo, tope).
"""

from types import SimpleNamespace

from ai.agents.base.lineage import resolve_ancestor, resolve_lineage
from app.models.agent import AgentType


def _job(job_id: str, agent_type: AgentType, input_job_id: str | None = None):
    """Job mínimo: el recorrido solo necesita id, agent_type e input_job_id."""
    return SimpleNamespace(id=job_id, agent_type=agent_type, input_job_id=input_job_id)


class FakeRepo:
    """Repositorio en memoria con la interfaz mínima (``get_job``)."""

    def __init__(self, jobs):
        self._jobs = {j.id: j for j in jobs}
        self.reads: list[str] = []

    async def get_job(self, job_id: str):
        self.reads.append(job_id)
        return self._jobs.get(job_id)


def _cadena_completa():
    """EF → Scrum → Arquitectura → BD, tal como la construye el servicio."""
    ef = _job("ef1", AgentType.EF)
    scrum = _job("sc1", AgentType.SCRUM, "ef1")
    arq = _job("ar1", AgentType.ARQUITECTURA, "sc1")
    bd = _job("bd1", AgentType.BD, "ar1")
    return bd, FakeRepo([ef, scrum, arq, bd])


async def test_resuelve_la_cadena_completa_desde_bd():
    """Dos saltos transitivos: el job BD alcanza Arquitectura, Scrum y EF."""
    bd, repo = _cadena_completa()
    chain = await resolve_lineage(repo, bd)

    assert set(chain) == {
        AgentType.BD,
        AgentType.ARQUITECTURA,
        AgentType.SCRUM,
        AgentType.EF,
    }
    assert chain[AgentType.BD].id == "bd1"
    assert chain[AgentType.ARQUITECTURA].id == "ar1"
    assert chain[AgentType.SCRUM].id == "sc1"
    assert chain[AgentType.EF].id == "ef1"


async def test_incluye_el_propio_job_sin_releerlo():
    """El job de partida entra en la cadena sin una lectura extra al repositorio."""
    bd, repo = _cadena_completa()
    await resolve_lineage(repo, bd)
    assert "bd1" not in repo.reads  # solo se leen los antecesores
    assert repo.reads == ["ar1", "sc1", "ef1"]


async def test_ancestor_devuelve_el_eslabon_pedido():
    bd, repo = _cadena_completa()
    ef = await resolve_ancestor(repo, bd, AgentType.EF)
    assert ef is not None and ef.id == "ef1"


async def test_ancestor_no_se_devuelve_a_si_mismo():
    """Pedir el antecesor del propio agente devuelve ``None``, no el job de partida."""
    bd, repo = _cadena_completa()
    assert await resolve_ancestor(repo, bd, AgentType.BD) is None


async def test_ancestor_ausente_es_none():
    """Un eslabón que no está en la cadena no se inventa."""
    bd, repo = _cadena_completa()
    assert await resolve_ancestor(repo, bd, AgentType.API) is None


async def test_cadena_truncada_no_lanza():
    """Si falta un eslabón intermedio se devuelve lo alcanzado, sin excepción.

    Reportar el hueco con un mensaje de dominio (GateError) es tarea del servicio;
    esta utilidad no decide qué es un error.
    """
    arq = _job("ar1", AgentType.ARQUITECTURA, "sc-desaparecido")
    bd = _job("bd1", AgentType.BD, "ar1")
    chain = await resolve_lineage(FakeRepo([arq, bd]), bd)
    assert set(chain) == {AgentType.BD, AgentType.ARQUITECTURA}


async def test_sin_input_job_id_la_cadena_es_solo_el_job():
    ef = _job("ef1", AgentType.EF)
    chain = await resolve_lineage(FakeRepo([ef]), ef)
    assert set(chain) == {AgentType.EF}


async def test_un_ciclo_no_cuelga_el_recorrido():
    """Datos corruptos con referencia circular terminan, no giran para siempre."""
    a = _job("a", AgentType.BD, "b")
    b = _job("b", AgentType.ARQUITECTURA, "a")
    chain = await resolve_lineage(FakeRepo([a, b]), a)
    assert set(chain) == {AgentType.BD, AgentType.ARQUITECTURA}


async def test_gana_el_antecesor_mas_cercano():
    """Con el mismo agent_type repetido, se conserva el que produjo la entrada."""
    lejano = _job("ef-viejo", AgentType.EF)
    cercano = _job("ef-nuevo", AgentType.EF, "ef-viejo")
    bd = _job("bd1", AgentType.BD, "ef-nuevo")
    chain = await resolve_lineage(FakeRepo([lejano, cercano, bd]), bd)
    assert chain[AgentType.EF].id == "ef-nuevo"


async def test_max_depth_acota_el_recorrido():
    """El tope de saltos se respeta (backstop ante cadenas absurdamente largas)."""
    jobs = [_job(f"j{i}", AgentType.BD, f"j{i + 1}") for i in range(6)]
    chain = await resolve_lineage(FakeRepo(jobs), jobs[0], max_depth=3)
    # Solo se visitan 3 jobs; todos son BD, así que la cadena colapsa a una clave.
    assert set(chain) == {AgentType.BD}
    assert chain[AgentType.BD].id == "j0"
