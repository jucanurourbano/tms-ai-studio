"""Tests de INGEST y del chunker estructural (Bloque 3)."""

import pytest

from ai.agents.ef.prompts import build_user
from ai.errors import FileTooLargeError, UnsupportedFileError
from ai.tools.chunker import chunk_cir, estimate_tokens
from ai.tools.ingest import LocalStorage, compute_hash, ingest
from ai.tools.parsers._builder import CIRBuilder
from ai.tools.parsers.text_adapter import TextToCIRAdapter

# --- INGEST -----------------------------------------------------------------


def test_ingest_texto_ok(tmp_path):
    storage = LocalStorage(str(tmp_path / "storage"))
    content = "contenido de prueba".encode("utf-8")
    res = ingest("fuente.txt", content, storage)
    assert res.source_type == "text"
    assert res.content_hash == compute_hash(content)
    assert res.size_bytes == len(content)
    # el archivo quedó almacenado
    assert storage.read(res.storage_uri) == content


def test_ingest_extension_no_soportada(tmp_path):
    storage = LocalStorage(str(tmp_path / "s"))
    with pytest.raises(UnsupportedFileError):
        ingest("imagen.png", b"data", storage)


def test_ingest_archivo_muy_grande(tmp_path):
    storage = LocalStorage(str(tmp_path / "s"))
    big = b"x" * (2 * 1024 * 1024)  # 2 MB
    with pytest.raises(FileTooLargeError):
        ingest("grande.txt", big, storage, max_upload_mb=1)


def test_ingest_docx_firma_invalida(tmp_path):
    storage = LocalStorage(str(tmp_path / "s"))
    # .docx debe empezar con 'PK' (zip)
    with pytest.raises(UnsupportedFileError):
        ingest("falso.docx", b"no-es-docx", storage)


def test_ingest_vacio(tmp_path):
    storage = LocalStorage(str(tmp_path / "s"))
    with pytest.raises(UnsupportedFileError):
        ingest("vacio.txt", b"", storage)


# --- Chunker ----------------------------------------------------------------


def _cir_multiseccion():
    b = CIRBuilder(source_type="document", fidelity="full", title="Doc")
    b.add_section("Doc", level=0)
    b.add_paragraph("Introducción del documento.")
    b.add_heading("Sección A", level=1)
    b.add_paragraph("Texto de la sección A.")
    b.add_table([["Campo", "Tipo"], ["numero_guia", "texto"]])
    b.add_heading("Sección B", level=1)
    b.add_list(["uno", "dos"])
    return b.build()


def test_estimador_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def test_single_shot_bajo_umbral():
    cir = _cir_multiseccion()
    res = chunk_cir(cir, token_threshold=100_000)
    assert res.single_shot is True
    assert res.chunks_total == 1
    # provenance completa en el único chunk
    assert res.chunks[0].element_ids == [e.element_id for e in cir.elements]


def test_corte_por_heading_y_tabla_integra():
    cir = _cir_multiseccion()
    res = chunk_cir(cir, token_threshold=1)
    assert res.single_shot is False
    # se corta en section raíz + 2 headings => 3 chunks
    assert res.chunks_total == 3

    # cada element_id aparece exactamente una vez (partición estable)
    todos = [eid for c in res.chunks for eid in c.element_ids]
    assert sorted(todos) == sorted(e.element_id for e in cir.elements)

    # la tabla queda íntegra en un solo chunk y conserva su contenido
    tabla_el = cir.tables()[0]
    chunks_con_tabla = [c for c in res.chunks if tabla_el.element_id in c.element_ids]
    assert len(chunks_con_tabla) == 1
    assert "Campo | Tipo" in chunks_con_tabla[0].text

    # el contexto (breadcrumb) del chunk de la Sección A la referencia
    chunk_a = chunks_con_tabla[0]
    assert "Sección A" in chunk_a.context


# --- Candados: el documento NO se envía dos veces ---------------------------
#
# El mensaje al modelo es ``build_user(chunk.context, chunk.text)``: contexto y
# fragmento viajan JUNTOS. Un texto que esté en los dos se paga dos veces.

_PARRAFO = "El transportista registra la guia de remision y actualiza el checkpoint. "


def _payload(chunk):
    """Lo que realmente se manda al modelo por ese chunk."""
    return build_user(chunk.context, chunk.text)


def test_texto_plano_grande_no_se_envia_dos_veces():
    """El fallo medido: 2,00x por encima del umbral de single_shot.

    Un ``SECTION`` con el documento entero acababa en el breadcrumb (contexto)
    Y en el cuerpo (fragmento), y ``build_user`` mandaba los dos.
    """
    texto = (_PARRAFO * 600)[:40_960]  # 40 KB, muy por encima del umbral
    res = chunk_cir(TextToCIRAdapter.adapt(texto))

    assert res.single_shot is False
    enviado = sum(len(_payload(c)) for c in res.chunks)
    assert enviado < len(texto) * 1.05, f"{enviado / len(texto):.2f}x del fuente"


def test_el_elemento_que_abre_el_chunk_no_se_renderiza_tambien_en_el_cuerpo():
    """Contexto XOR cuerpo: el título va a uno de los dos, nunca a los dos."""
    centinela = "ROTULO-CENTINELA-UNICO-DE-ESTE-TEST"
    b = CIRBuilder(source_type="document", fidelity="full", title="Doc")
    b.add_section("Doc", level=0)
    b.add_heading(centinela, level=1)
    b.add_paragraph("Cuerpo de la sección.")
    res = chunk_cir(b.build(), token_threshold=1)

    chunk = next(c for c in res.chunks if centinela in _payload(c))
    assert centinela in chunk.context  # llega al modelo por el breadcrumb...
    assert centinela not in chunk.text  # ...y solo por ahí
    assert _payload(chunk).count(centinela) == 1


def test_un_titulo_sin_cuerpo_no_gasta_un_chunk_vacio():
    """Un FRAGMENTO vacío es una llamada por dimensión que no extrae nada.

    Pasa con un título seguido de su subtítulo. Sus ``element_ids`` se arrastran
    al chunk siguiente: la partición sigue cubriendo el CIR entero.
    """
    b = CIRBuilder(source_type="document", fidelity="full", title="Doc")
    b.add_section("Doc", level=0)
    b.add_heading("Sección A", level=1)  # sin cuerpo propio
    b.add_heading("Sección A.1", level=2)
    b.add_paragraph("El único cuerpo del documento.")
    cir = b.build()
    res = chunk_cir(cir, token_threshold=1)

    assert res.chunks_total == 1
    assert res.chunks[0].text.strip()
    # provenance íntegra pese a haber descartado dos grupos sin cuerpo
    assert res.chunks[0].element_ids == [e.element_id for e in cir.elements]
    # y el título descartado sigue llegando al modelo, por el breadcrumb
    assert "Sección A.1" in res.chunks[0].context


def test_documento_solo_de_titulos_no_devuelve_cero_chunks():
    """Degenerado: sin cuerpo no hay nada que trocear, pero callarse sería peor.

    Cero chunks dejaría al pipeline sin extraer nada EN SILENCIO.
    """
    b = CIRBuilder(source_type="document", fidelity="full", title="Doc")
    b.add_section("Doc", level=0)
    b.add_heading("Sección A", level=1)
    b.add_heading("Sección B", level=1)
    cir = b.build()
    res = chunk_cir(cir, token_threshold=1)

    assert res.chunks_total == 1
    assert res.chunks[0].element_ids == [e.element_id for e in cir.elements]
    assert "Sección B" in res.chunks[0].text
