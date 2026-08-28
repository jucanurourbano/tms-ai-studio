"""Chunker estructural del CIR.

Corta por heading/section; las tablas nunca se parten (cada tabla es un
elemento íntegro en su chunk). Cada chunk lleva el ``breadcrumb`` como contexto
y la provenance (``element_ids``). El texto de un elemento va al contexto O al
cuerpo, **nunca a los dos**: contexto y cuerpo se envían juntos en el mismo
mensaje al modelo, y duplicar ahí es pagar dos veces por el mismo documento.
Si el total estimado está por debajo del umbral, marca modo ``single_shot``
(un único pase con todo el contenido).
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

    # Corte por heading/section, en dos pasos: agrupar y luego emitir.
    #
    # 1) Agrupar. El elemento que ABRE el grupo (heading/section) aporta su
    #    texto al breadcrumb —``_context_for`` lo pone en la cola de la traza—
    #    y por eso NO se renderiza también en el cuerpo: ``build_user`` manda
    #    contexto y fragmento en el MISMO mensaje, así que estaría enviando el
    #    mismo texto dos veces. Su ``element_id`` sí queda en el grupo: la
    #    provenance no se toca.
    # groups: (context, element_ids, textos_del_cuerpo)
    groups: list[tuple[str, list[str], list[str]]] = [(cir.title or "", [], [])]
    for element in cir.elements:
        if element.type in (ElementType.HEADING, ElementType.SECTION):
            groups.append((_context_for(element), [element.element_id], []))
            continue
        _, ids, texts = groups[-1]
        ids.append(element.element_id)
        rendered = render_element(element)
        if rendered:
            texts.append(rendered)

    # 2) Emitir. Un grupo SIN cuerpo no se convierte en chunk: sería un
    #    FRAGMENTO vacío enviado una vez por dimensión, llamadas pagadas que no
    #    pueden extraer nada (pasa con un título seguido de su subtítulo). Sus
    #    ``element_ids`` se arrastran al siguiente chunk para que la partición
    #    siga cubriendo el CIR entero.
    chunks: list[Chunk] = []
    carried: list[str] = []
    for context, ids, texts in groups:
        if not texts:
            carried.extend(ids)
            continue
        chunks.append(
            Chunk(
                chunk_id=f"chunk-{len(chunks):04d}",
                order=len(chunks),
                context=context,
                element_ids=carried + ids,
                text="\n\n".join(texts),
                token_estimate=estimate_tokens(context + "\n" + "\n\n".join(texts)),
            )
        )
        carried = []

    if carried:
        if chunks:
            # Cola de títulos sin cuerpo: se pegan al último chunk para no
            # perder provenance.
            chunks[-1].element_ids.extend(carried)
        else:
            # Documento sin cuerpo (solo títulos). No hay nada que trocear,
            # pero devolver cero chunks dejaría al pipeline sin extraer nada
            # EN SILENCIO: se emite uno con todo, como en single_shot.
            chunks.append(
                Chunk(
                    chunk_id="chunk-0000",
                    order=0,
                    context=cir.title or "",
                    element_ids=carried,
                    text=full_text,
                    token_estimate=total_tokens,
                )
            )

    return ChunkingResult(
        chunks=chunks,
        single_shot=False,
        total_tokens=total_tokens,
        chunks_total=len(chunks),
    )
