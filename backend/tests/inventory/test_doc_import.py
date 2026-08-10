"""Extracción de conocimiento desde documentos hacia el inventario (INV3).

**LLM siempre mockeado** (REGLA DE PRESUPUESTO). Lo que estos tests protegen no es
la calidad de la extracción —eso depende del modelo— sino las defensas de Python
que hay ALREDEDOR: que nada entre al inventario sin una cita verificable, y que lo
descartado quede escrito.

El inventario es la memoria de lo que existe de verdad. Una entidad inventada aquí
hace que RECONCILE dé por existente una tabla que nadie creó.
"""

import json
import re

import pytest

from ai.inventory.doc_import import (
    build_assets,
    build_fragments,
    build_system,
    document_to_cir,
    extract_knowledge,
)
from ai.tools.parsers import TextToCIRAdapter

from .fixtures import (
    APLICACIONES,
    DOCUMENTO_SINTETICO,
    MICROSERVICIOS,
    TABLAS_MAESTRAS,
    knowledge_del_documento,
)

_ELEMENT_RE = re.compile(r"\[(el-\d+)\]")


class MockLLM:
    """LLM mockeado: responde citando un ``element_id`` REAL del fragmento."""

    def __init__(self, build_payload=None):
        self.build_payload = build_payload or (
            lambda element_id: knowledge_del_documento(element_id)
        )
        self.calls: list[str] = []

    async def complete_json(self, *, system: str, user: str) -> str:
        self.calls.append(user)
        ids = _ELEMENT_RE.findall(user)
        return json.dumps(self.build_payload(ids[0] if ids else "el-0000"))


class FixedLLM:
    """LLM mockeado que devuelve SIEMPRE la misma carga, cite lo que cite."""

    def __init__(self, payload: dict):
        self.payload = payload

    async def complete_json(self, *, system: str, user: str) -> str:
        return json.dumps(self.payload)


def _fragmentos(texto: str = DOCUMENTO_SINTETICO) -> list[dict]:
    cir = TextToCIRAdapter.adapt(texto, title="modernizacion.md")
    return build_fragments(cir)


# --- el prompt ---------------------------------------------------------------


def test_el_system_prompt_prohibe_inventar_y_trae_el_glosario():
    system = build_system()
    assert "PROHIBIDO INVENTAR" in system
    # El glosario logístico (INV0) entra: sin él "recaudo" o "manifiesto" se leen
    # como palabras corrientes y salen entidades mal entendidas.
    assert "GLOSARIO LOGÍSTICO" in system
    assert "manifiesto" in system
    assert "source_ref" in system and "evidence" in system


# --- fragmentado -------------------------------------------------------------


def test_los_fragmentos_llevan_los_element_id_reales():
    """El modelo solo puede citar lo que se le entrega; en Python se verifica."""
    fragmentos = _fragmentos()
    assert fragmentos
    for fragmento in fragmentos:
        assert fragmento["element_ids"]
        for element_id in _ELEMENT_RE.findall(fragmento["text"]):
            assert element_id in fragmento["element_ids"]


def test_un_documento_sin_texto_no_produce_fragmentos():
    assert _fragmentos("   ") == []


# --- las defensas: nada entra sin cita verificable ---------------------------


async def test_se_descarta_lo_que_cita_un_element_id_inexistente():
    """EL test del bloque.

    Un modelo puede devolver una cita con forma correcta que no corresponde a
    nada del documento. El prompt lo prohíbe, pero un prompt no es una garantía:
    la comprobación vive en Python.
    """
    fragmentos = _fragmentos()
    llm = FixedLLM(
        {
            "modules": [
                {
                    "name": "Módulo Fantasma",
                    "description": None,
                    "functionalities": [],
                    "entities": [],
                    "source_ref": "el-9999",  # no existe en el documento
                    "evidence": "algo que suena verosímil",
                    "confidence": 0.95,
                    "origin": "stated",
                }
            ],
            "entities": [],
            "functionalities": [],
            "decisions": [],
        }
    )
    resultado = await extract_knowledge(llm, fragmentos)

    assert resultado["modules"] == []
    assert resultado["discarded"], "el descarte no puede ser silencioso"
    descarte = resultado["discarded"][0]
    assert descarte["name"] == "Módulo Fantasma"
    assert "no es un elemento" in descarte["reason"]


async def test_se_descarta_lo_que_llega_sin_evidencia():
    fragmentos = _fragmentos()
    element_id = fragmentos[0]["element_ids"][0]
    llm = FixedLLM(
        {
            "modules": [],
            "entities": [
                {
                    "name": "Entidad sin respaldo",
                    "description": None,
                    "attributes": [],
                    "source_ref": element_id,
                    "evidence": "   ",
                    "confidence": 0.9,
                    "origin": "stated",
                }
            ],
            "functionalities": [],
            "decisions": [],
        }
    )
    resultado = await extract_knowledge(llm, fragmentos)
    assert resultado["entities"] == []
    assert "evidencia" in resultado["discarded"][0]["reason"]


async def test_un_fragmento_irreparable_no_tumba_la_carga():
    """Cuarentena: perder el documento entero por un fragmento sería peor."""

    class RotoLLM:
        async def complete_json(self, *, system: str, user: str) -> str:
            return "esto no es JSON"

    fragmentos = _fragmentos()
    resultado = await extract_knowledge(RotoLLM(), fragmentos, max_repairs=0)
    assert resultado["skipped"], "el fragmento fallido debe quedar en cuarentena"
    assert resultado["modules"] == []


async def test_lo_mismo_nombrado_en_varios_fragmentos_se_une():
    """Sin unir, un módulo citado en cinco secciones entraría cinco veces.

    Los fragmentos se construyen a mano y no con `TextToCIRAdapter` porque el
    adaptador de texto libre deja el documento en un solo elemento: aquí lo que se
    prueba es la unión entre fragmentos, no el troceado.
    """
    fragmentos = [
        {
            "ref": f"frag-{i:04d}",
            "element_ids": [f"el-{i:04d}"],
            "text": f"[el-{i:04d}] El modulo Reparto gestiona rutas.",
        }
        for i in range(3)
    ]

    llm = MockLLM(
        build_payload=lambda element_id: {
            "modules": [
                {
                    "name": "Reparto",
                    "description": None,
                    "functionalities": [],
                    "entities": [],
                    "source_ref": element_id,
                    "evidence": "El modulo Reparto gestiona rutas.",
                    "confidence": 0.8,
                    "origin": "stated",
                }
            ],
            "entities": [],
            "functionalities": [],
            "decisions": [],
        }
    )
    resultado = await extract_knowledge(llm, fragmentos)
    assert len(resultado["modules"]) == 1
    # Pero no se pierde de dónde salieron las otras menciones.
    assert resultado["modules"][0]["also_seen_in"]


# --- el caso de uso acordado (fixture sintética) -----------------------------


async def test_el_documento_de_modernizacion_produce_la_forma_acordada():
    """5 aplicaciones + 16 microservicios + 15 tablas maestras.

    Los NOMBRES de la fixture son sintéticos (el documento real no está en el
    repositorio); los RECUENTOS son la forma acordada del sistema destino. Si el
    documento real cambia esos números, este test lo dirá.
    """
    fragmentos = _fragmentos()
    resultado = await extract_knowledge(MockLLM(), fragmentos)

    nombres_modulos = {m["name"] for m in resultado["modules"]}
    assert nombres_modulos == set(APLICACIONES) | set(MICROSERVICIOS)
    assert len(nombres_modulos) == 21  # 5 aplicaciones + 16 microservicios

    nombres_entidades = {e["name"] for e in resultado["entities"]}
    assert nombres_entidades == set(TABLAS_MAESTRAS)
    assert len(nombres_entidades) == 15

    # Las decisiones son lo más valioso y lo que más fácil se pierde.
    titulos = {d["title"] for d in resultado["decisions"]}
    assert "Reportes asíncronos en Python" in titulos
    assert "App de destinatarios en Flutter" in titulos
    assert not resultado["discarded"]


async def test_los_activos_generados_son_guardables_tal_cual():
    """Lo que produce INV3 tiene que encajar en el contrato de activos de INV1."""
    from app.models.inventory import InventoryAssetType
    from app.schemas.inventario import validate_asset_content

    fragmentos = _fragmentos()
    conocimiento = await extract_knowledge(MockLLM(), fragmentos)
    activos = build_assets(conocimiento, document_name="modernizacion.md")

    # Un activo `document` con la lectura completa + uno `module` por módulo.
    documentos = [a for a in activos if a["asset_type"] == "document"]
    modulos = [a for a in activos if a["asset_type"] == "module"]
    assert len(documentos) == 1
    assert len(modulos) == 21

    for activo in activos:
        validado = validate_asset_content(
            InventoryAssetType(activo["asset_type"]), activo["content"]
        )
        assert validado

    # El activo documento conserva la trazabilidad completa.
    contenido = documentos[0]["content"]
    assert contenido["source_document"] == "modernizacion.md"
    assert len(contenido["entities"]) == 15
    assert all(e["evidence"] for e in contenido["entities"])


async def test_un_documento_que_no_aporta_nada_deja_constancia():
    """Que un documento no aportara conocimiento también es información."""
    fragmentos = _fragmentos()
    vacio = FixedLLM(
        {"modules": [], "entities": [], "functionalities": [], "decisions": []}
    )
    conocimiento = await extract_knowledge(vacio, fragmentos)
    activos = build_assets(conocimiento, document_name="acta.docx")
    assert len(activos) == 1
    assert activos[0]["asset_type"] == "document"


# --- lectura del documento: se reutiliza el pipeline del EF ------------------


def test_se_reutiliza_el_lector_del_agente_ef(tmp_path):
    """No hay una segunda forma de leer un documento en esta plataforma."""
    ruta = tmp_path / "doc.md"
    ruta.write_text(DOCUMENTO_SINTETICO, encoding="utf-8")
    cir = document_to_cir(str(ruta), ".md", title="doc.md")
    assert cir.elements
    assert any("microservicios" in (e.text or "").lower() for e in cir.elements)


def test_una_extension_no_soportada_se_rechaza_al_ingerir(tmp_path):
    """El guard de extensiones es el del EF: no se duplica ni se relaja."""
    from ai.errors import UnsupportedFileError
    from ai.tools.ingest import LocalStorage, ingest

    with pytest.raises(UnsupportedFileError):
        ingest("hoja.xlsx", b"contenido", LocalStorage(str(tmp_path)))
