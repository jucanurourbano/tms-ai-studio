"""Regresión: parseo de la respuesta del LLM cuando ``content`` es una LISTA de bloques.

Bug reproducido: con ``langchain-anthropic`` 1.x + ``claude-sonnet-5`` la respuesta
llega como ``AIMessage.content`` = ``[{"type":"thinking",...}, {"type":"text",...}]``
(lista de bloques). ``ClaudeLLMClient.complete_json`` hacía ``str(content)``, lo que
producía un *repr* de Python con comillas simples; ``json.loads`` lo rechazaba y TODAS
las dimensiones caían en cuarentena ("schema inválido") aun habiendo consumido tokens
(output=0, cobertura 0%).

Ningún test lo detectaba porque los mocks devuelven ``json.dumps(...)`` (JSON perfecto),
nunca la forma real de la lista de bloques.

Los payloads de estos tests son fieles a lo capturado del run "Gestión de solicitudes
de vacaciones" (job ``01KY0XHSQGCJ4VD4V3XTTT2AXB``).
"""

import json

from ai.agents.base.structured import (
    ClaudeLLMClient,
    complete_structured,
    loads_json,
    message_text,
)
from ai.agents.ef.schemas.extraction import RequirementsExtract

# JSON real que el modelo colocó en el bloque ``text`` (dimensión requirements).
_REQ_JSON = (
    '{"business": [], "functional": [{"text": "Registrar solicitud de vacaciones", '
    '"source_ref": "el-0001", "evidence": "El colaborador registra su solicitud", '
    '"confidence": 0.9, "origin": "stated"}], "non_functional": []}'
)

# Forma EXACTA de ``AIMessage.content`` que produce langchain-anthropic 1.x para
# una respuesta con razonamiento: bloque ``thinking`` + bloque ``text``.
_BLOCK_CONTENT = [
    {
        "type": "thinking",
        "thinking": "Analizando el fragmento de vacaciones...",
        "signature": "abc",
    },
    {"type": "text", "text": _REQ_JSON},
]


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChat:
    """Emula ``ChatAnthropic``: ``ainvoke`` devuelve un mensaje con ``.content``."""

    def __init__(self, content):
        self._content = content

    async def ainvoke(self, _messages):
        return _FakeMessage(self._content)


# --- message_text -----------------------------------------------------------


def test_message_text_extrae_texto_de_lista_de_bloques():
    assert message_text(_BLOCK_CONTENT) == _REQ_JSON


def test_message_text_ignora_thinking_y_concatena_multiples_text():
    content = [
        {"type": "thinking", "thinking": "..."},
        {"type": "text", "text": '{"a":'},
        {"type": "text", "text": "1}"},
    ]
    assert message_text(content) == '{"a":1}'


def test_message_text_pasa_string_tal_cual():
    assert message_text('{"a":1}') == '{"a":1}'


def test_str_de_la_lista_NO_es_json_valido():
    """Documenta la causa raíz: ``str(lista)`` era irreparable para json.loads."""
    roto = str(_BLOCK_CONTENT)
    try:
        json.loads(roto)
        raise AssertionError("str(lista) no debería ser JSON válido")
    except json.JSONDecodeError:
        pass


# --- loads_json (tolerante a fences) ----------------------------------------


def test_loads_json_directo():
    assert loads_json('{"a": 1}') == {"a": 1}


def test_loads_json_con_fence_markdown():
    assert loads_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_loads_json_con_prosa_alrededor():
    assert loads_json('Aquí tienes el JSON: {"a": 1}. Fin.') == {"a": 1}


# --- ClaudeLLMClient (adaptador real, cliente inyectado) --------------------


async def test_complete_json_extrae_json_de_bloques():
    """REGRESIÓN: el adaptador real devuelve el JSON puro, no el repr de la lista."""
    client = ClaudeLLMClient(client=_FakeChat(_BLOCK_CONTENT))
    raw = await client.complete_json(system="s", user="u")
    assert raw == _REQ_JSON
    assert json.loads(raw)["functional"][0]["text"].startswith("Registrar")


async def test_complete_structured_valida_respuesta_en_bloques():
    """De punta a punta: bloques -> texto -> json.loads -> Pydantic válido."""
    llm = ClaudeLLMClient(client=_FakeChat(_BLOCK_CONTENT))
    model, error = await complete_structured(
        llm, system="s", user="u", schema=RequirementsExtract, max_repairs=0
    )
    assert error == ""
    assert model is not None
    assert model.functional[0].text == "Registrar solicitud de vacaciones"


async def test_complete_structured_bloques_con_fence():
    """El bloque text puede venir con fences markdown pese al prompt: también valida."""
    content = [{"type": "text", "text": f"```json\n{_REQ_JSON}\n```"}]
    llm = ClaudeLLMClient(client=_FakeChat(content))
    model, error = await complete_structured(
        llm, system="s", user="u", schema=RequirementsExtract, max_repairs=0
    )
    assert error == "" and model is not None
    assert model.functional[0].source_ref == "el-0001"
