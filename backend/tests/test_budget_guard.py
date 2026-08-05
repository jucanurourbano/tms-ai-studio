"""Test del cortafuegos contra la API real de Anthropic (REGLA DE PRESUPUESTO).

Los nodos generativos caen en ``ClaudeLLMClient`` cuando nadie inyecta un mock por
``config``. Un test nuevo que se olvide del mock intentaría una llamada real, así
que ``tests/conftest.py`` bloquea el cliente de forma autouse. Este test verifica
**el cortafuegos en sí**: si alguien lo quita o lo rompe, esto falla.

No es una precaución teórica: durante BD3, tres tests del bloque anterior dejaron
de tener stub en el nodo TABLES y llegaron a la API (rechazada con 400, sin coste).
De ahí viene esta protección.
"""

import pytest

from ai.agents.base.structured import ClaudeLLMClient


async def test_el_cliente_real_de_anthropic_esta_bloqueado_en_tests():
    with pytest.raises(AssertionError, match="REGLA DE PRESUPUESTO"):
        await ClaudeLLMClient().complete_json(system="s", user="u")


def test_el_cortafuegos_nombra_como_arreglarlo():
    """El mensaje debe decir qué hacer, no solo que algo falló."""
    from app.dependencies.claude import get_claude_client

    with pytest.raises(AssertionError) as exc:
        get_claude_client()
    mensaje = str(exc.value)
    assert "config['configurable']['llm']" in mensaje
    assert "tests/mocks.py" in mensaje
