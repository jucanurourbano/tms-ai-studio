"""Tests de INGEST y del chunker estructural (Bloque 3)."""

import pytest

from ai.errors import FileTooLargeError, UnsupportedFileError
from ai.tools.chunker import chunk_cir, estimate_tokens
from ai.tools.ingest import LocalStorage, compute_hash, ingest
from ai.tools.parsers._builder import CIRBuilder

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
