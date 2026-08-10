"""Documento (docx/pdf/txt) → activos de conocimiento del inventario (INV3).

Reutiliza **tal cual** el pipeline de parsing del Agente EF (``DocxParser`` /
``PdfParser`` / ``TextToCIRAdapter`` → CIR → chunker): no hay una segunda forma de
leer un documento en esta plataforma, y duplicarla sería garantizar que las dos se
comportan distinto con el mismo archivo.

Sobre el CIR corre un pase LLM de extracción de conocimiento, con el mismo patrón
de *structured output* + cuarentena que EXTRACT: un fragmento que el modelo no
consigue devolver en el esquema NO tumba la carga, queda apartado y se informa.

Lo que este módulo NO hace: inventar. Todo elemento extraído arrastra su
``source_ref`` al elemento del CIR y su ``evidence`` verbatim, y los que llegan sin
cita **se descartan aquí**, en Python, sin confiar en que el prompt baste.
"""

from pathlib import Path
from typing import Any, Optional

from ai.agents.base.structured import LLMClient, run_structured_map
from ai.knowledge import glossary_block
from ai.tools.chunker import chunk_cir, estimate_tokens
from ai.tools.cir import CIR
from ai.tools.parsers import DocxParser, PdfParser, TextToCIRAdapter

from .schemas import KnowledgeExtract

PROMPT_VERSION = "1.0.0"

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts" / "inventario"


def load_prompt(name: str) -> str:
    """Lee un archivo de prompt de ``ai/prompts/inventario/``."""
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_system() -> str:
    """System prompt: base + tarea + glosario logístico.

    El glosario entra porque sin él el modelo lee "recaudo" o "manifiesto" como
    palabras corrientes y extrae entidades mal entendidas (INV0).
    """
    return f"{load_prompt('_base.md')}\n\n{load_prompt('knowledge.md')}\n\n{glossary_block()}"


def document_to_cir(uri: str, extension: str, *, title: Optional[str] = None) -> CIR:
    """Parsea la fuente a CIR con el MISMO lector que usa el Agente EF."""
    if extension == ".docx":
        return DocxParser.parse(uri)
    if extension == ".pdf":
        return PdfParser.parse(uri)
    raw = Path(uri).read_bytes().decode("utf-8", errors="replace")
    return TextToCIRAdapter.adapt(raw, title=title)


def _element_text(element: dict) -> str:
    """Texto plano de un elemento del CIR (las tablas se aplanan por filas)."""
    if element.get("text"):
        return str(element["text"])
    tabla = element.get("table") or {}
    filas = tabla.get("rows") or []
    return "\n".join(" | ".join(str(c) for c in fila) for fila in filas)


def build_fragments(cir: CIR, *, token_threshold: int = 4096) -> list[dict]:
    """Trocea el CIR en fragmentos con sus ``element_id``, para el map del LLM.

    Cada fragmento lleva los ids reales de sus elementos: son los únicos valores
    que el modelo puede usar como ``source_ref``, y lo que permite verificar
    después —en Python— que no se inventó la cita.
    """
    troceado = chunk_cir(cir, token_threshold=token_threshold)
    elementos = {e.element_id: e.model_dump() for e in cir.elements}

    fragmentos: list[dict] = []
    for indice, chunk in enumerate(troceado.chunks):
        ids = list(chunk.element_ids)
        lineas = []
        for element_id in ids:
            elemento = elementos.get(element_id)
            if elemento is None:
                continue
            texto = _element_text(elemento).strip()
            if texto:
                lineas.append(f"[{element_id}] {texto}")
        if not lineas:
            continue
        fragmentos.append(
            {
                "ref": f"frag-{indice:04d}",
                "element_ids": ids,
                "text": "\n".join(lineas),
            }
        )
    return fragmentos


def _valid_items(
    items: list[dict], permitidos: set[str], descartes: list[dict], clase: str
) -> list[dict]:
    """Filtra en Python lo que el prompt pidió pero no puede garantizar.

    Dos cosas se comprueban aquí y no se dan por buenas:

    1. Que ``source_ref`` sea un ``element_id`` REAL del fragmento. Un modelo puede
       devolver una cita con forma correcta que no corresponde a nada.
    2. Que haya ``evidence`` no vacía.

    Lo descartado NUNCA desaparece en silencio: se acumula para el informe (misma
    regla que los descartes del assembler en el resto de agentes).
    """
    validos: list[dict] = []
    for item in items:
        ref = item.get("source_ref")
        if ref not in permitidos:
            descartes.append(
                {
                    "kind": clase,
                    "name": item.get("name") or item.get("title") or "(sin nombre)",
                    "reason": (
                        f"cita «{ref}», que no es un elemento de este fragmento del "
                        "documento"
                    ),
                }
            )
            continue
        if not (item.get("evidence") or "").strip():
            descartes.append(
                {
                    "kind": clase,
                    "name": item.get("name") or item.get("title") or "(sin nombre)",
                    "reason": "no aporta evidencia verbatim del documento",
                }
            )
            continue
        validos.append(item)
    return validos


def _merge_by_name(items: list[dict], clave: str) -> list[dict]:
    """Une elementos repetidos entre fragmentos, quedándose con el más confiable.

    Un documento largo nombra el mismo módulo en varias secciones. Sin unir, el
    inventario tendría el módulo cinco veces y RECONCILE lo compararía cinco
    veces. Se conserva la ocurrencia de mayor ``confidence`` y se acumulan las
    citas de las demás, para no perder de dónde salió cada mención.
    """
    por_nombre: dict[str, dict] = {}
    for item in items:
        nombre = (item.get(clave) or "").strip()
        if not nombre:
            continue
        actual = por_nombre.get(nombre.lower())
        if actual is None:
            item["also_seen_in"] = []
            por_nombre[nombre.lower()] = item
            continue
        if item.get("confidence", 0) > actual.get("confidence", 0):
            item["also_seen_in"] = actual.get("also_seen_in", []) + [
                actual["source_ref"]
            ]
            por_nombre[nombre.lower()] = item
        else:
            actual.setdefault("also_seen_in", []).append(item["source_ref"])
    return list(por_nombre.values())


async def extract_knowledge(
    llm: LLMClient,
    fragments: list[dict],
    *,
    concurrency: int = 3,
    max_repairs: int = 2,
) -> dict[str, Any]:
    """Pase LLM sobre los fragmentos → conocimiento consolidado del documento.

    Devuelve ``{modules, entities, functionalities, decisions, discarded, skipped,
    tokens}``. Los fragmentos irreparables quedan en ``skipped`` (cuarentena) y la
    carga sigue: perder un documento entero porque un fragmento no validó sería
    peor que cargarlo incompleto avisando.
    """
    system = build_system()

    resultados, saltados, tokens = await run_structured_map(
        llm,
        fragments,
        build_system=lambda _item: system,
        build_user=lambda item: (
            "FRAGMENTO DEL DOCUMENTO (usa SOLO estos element_id como source_ref):\n"
            + item["text"]
        ),
        schema=KnowledgeExtract,
        ref_of=lambda item: item["ref"],
        stage="KNOWLEDGE_EXTRACT",
        estimate_tokens=estimate_tokens,
        concurrency=concurrency,
        max_repairs=max_repairs,
    )

    por_ref = {f["ref"]: f for f in fragments}
    descartes: list[dict] = []
    acumulado: dict[str, list[dict]] = {
        "modules": [],
        "entities": [],
        "functionalities": [],
        "decisions": [],
    }

    for resultado in resultados:
        fragmento = por_ref.get(resultado["ref"], {})
        permitidos = set(fragmento.get("element_ids") or [])
        # `run_structured_map` devuelve el modelo YA volcado a dict. Acceder por
        # atributo devolvería vacío en silencio, que es la peor forma de fallar
        # aquí: el documento parecería no haber aportado nada.
        datos = resultado["data"]
        if hasattr(datos, "model_dump"):
            datos = datos.model_dump()
        for clase in acumulado:
            crudos = [dict(item) for item in (datos.get(clase) or [])]
            acumulado[clase].extend(_valid_items(crudos, permitidos, descartes, clase))

    return {
        "modules": _merge_by_name(acumulado["modules"], "name"),
        "entities": _merge_by_name(acumulado["entities"], "name"),
        "functionalities": _merge_by_name(acumulado["functionalities"], "name"),
        "decisions": _merge_by_name(acumulado["decisions"], "title"),
        "discarded": descartes,
        "skipped": saltados,
        "tokens": tokens,
    }


def build_assets(
    knowledge: dict[str, Any], *, document_name: str
) -> list[dict[str, Any]]:
    """Convierte el conocimiento extraído en activos listos para el inventario.

    Produce un activo ``document`` con la lectura completa (siempre, aunque venga
    vacío: que un documento no aportara nada también es información) y un activo
    ``module`` por cada módulo identificado, que es la unidad con la que después
    trabaja RECONCILE.
    """
    activos: list[dict[str, Any]] = [
        {
            "asset_type": "document",
            "name": document_name,
            "content": {
                "source_document": document_name,
                "modules": knowledge["modules"],
                "entities": knowledge["entities"],
                "functionalities": knowledge["functionalities"],
                "decisions": knowledge["decisions"],
                "discarded": knowledge["discarded"],
            },
        }
    ]

    for modulo in knowledge["modules"]:
        entidades = [
            e
            for e in knowledge["entities"]
            if e["name"] in (modulo.get("entities") or [])
        ]
        funcionalidades = [
            f
            for f in knowledge["functionalities"]
            if f["name"] in (modulo.get("functionalities") or [])
        ]
        activos.append(
            {
                "asset_type": "module",
                "name": modulo["name"],
                "content": {
                    "name": modulo["name"],
                    "description": modulo.get("description"),
                    "source_ref": modulo["source_ref"],
                    "evidence": modulo["evidence"],
                    "confidence": modulo.get("confidence"),
                    "origin": modulo.get("origin"),
                    "entities": entidades,
                    "functionalities": funcionalidades,
                },
            }
        )
    return activos
