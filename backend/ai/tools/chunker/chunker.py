"""Chunker estructural del CIR.

Corta por heading/section; las tablas nunca se parten (cada tabla es un
elemento íntegro en su chunk). Cada chunk lleva el ``breadcrumb`` como contexto
y la provenance (``element_ids``). Si el total estimado está por debajo del
umbral, marca modo ``single_shot`` (un único pase con todo el contenido).
"""

from pydantic import BaseModel, ConfigDict, Field

from ai.tools.cir import CIR, CIRElement, ElementType


def estimate_tokens(text: str) -> int:
    """Estimación simple de tokens (~4 caracteres por token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def render_element(element: CIRElement) -> str:
    """Renderiza un elemento del CIR a texto plano."""
    if element.type is ElementType.LIST and element.items:
        return "\n".join(f"- {item}" for item in element.items)
    if element.type is ElementType.TABLE and element.table:
        return "\n".join(" | ".join(row) for row in element.table.rows)
    return element.text or ""


class Chunk(BaseModel):
    """Fragmento de análisis con contexto y provenance."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    order: int
    context: str  # breadcrumb como contexto
    element_ids: list[str] = Field(default_factory=list)
    text: str
    token_estimate: int


class ChunkingResult(BaseModel):
    """Resultado del chunking."""

    model_config = ConfigDict(extra="forbid")

    chunks: list[Chunk] = Field(default_factory=list)
    single_shot: bool = False
    total_tokens: int = 0
    chunks_total: int = 0


def _context_for(element: CIRElement) -> str:
    """Contexto (breadcrumb) de un elemento que abre chunk."""
    trail = list(element.breadcrumb)
    if element.type in (ElementType.HEADING, ElementType.SECTION) and element.text:
        trail = trail + [element.text]
    return " > ".join(trail)


def chunk_cir(cir: CIR, token_threshold: int = 4096) -> ChunkingResult:
    """Divide un CIR en chunks; marca single_shot bajo el umbral."""
    full_text = cir.text_content()
    total_tokens = estimate_tokens(full_text)

    # Bajo umbral: un solo chunk (modo single_shot).
    if total_tokens < token_threshold:
        chunk = Chunk(
            chunk_id="chunk-0000",
            order=0,
            context=cir.title or "",
            element_ids=[e.element_id for e in cir.elements],
            text="\n\n".join(
                render_element(e) for e in cir.elements if render_element(e)
            ),
            token_estimate=total_tokens,
        )
        return ChunkingResult(
            chunks=[chunk],
            single_shot=True,
            total_tokens=total_tokens,
            chunks_total=1,
        )

    # Corte por heading/section.
    chunks: list[Chunk] = []
    current_ids: list[str] = []
    current_texts: list[str] = []
    current_context = cir.title or ""

    def flush() -> None:
        if not current_ids:
            return
        text = "\n\n".join(t for t in current_texts if t)
        chunks.append(
            Chunk(
                chunk_id=f"chunk-{len(chunks):04d}",
                order=len(chunks),
                context=current_context,
                element_ids=list(current_ids),
                text=text,
                token_estimate=estimate_tokens(current_context + "\n" + text),
            )
        )

    for element in cir.elements:
        if element.type in (ElementType.HEADING, ElementType.SECTION):
            flush()
            current_ids = []
            current_texts = []
            current_context = _context_for(element)
        current_ids.append(element.element_id)
        rendered = render_element(element)
        if rendered:
            current_texts.append(rendered)
    flush()

    return ChunkingResult(
        chunks=chunks,
        single_shot=False,
        total_tokens=total_tokens,
        chunks_total=len(chunks),
    )
