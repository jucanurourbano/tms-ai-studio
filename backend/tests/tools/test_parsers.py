"""Tests de parsers a CIR (Bloque 3)."""

import pytest
from docx import Document

from ai.errors import ScannedPDFError
from ai.tools.cir import ElementType
from ai.tools.parsers import DocxParser, TextToCIRAdapter
from ai.tools.parsers import pdf_parser as pdf_mod

# --- TextToCIRAdapter -------------------------------------------------------


def test_texto_estructurado():
    texto = (
        "# Proceso de Siniestros\n\n"
        "Este documento describe el registro de siniestros.\n\n"
        "- Reportar el siniestro\n- Registrar la guía\n- Cerrar\n"
    )
    cir = TextToCIRAdapter.adapt(texto, title="Siniestros")
    tipos = [e.type for e in cir.elements]
    assert ElementType.HEADING in tipos
    assert ElementType.LIST in tipos
    assert ElementType.PARAGRAPH in tipos
    # provenance/orden estables
    assert [e.element_id for e in cir.elements] == [
        f"el-{i:04d}" for i in range(len(cir.elements))
    ]


def test_texto_plano_un_solo_section():
    texto = "solo una linea de texto plano sin estructura alguna aqui"
    cir = TextToCIRAdapter.adapt(texto)
    assert len(cir.elements) == 1
    assert cir.elements[0].type is ElementType.SECTION
    assert cir.source_type == "text"


def test_breadcrumb_traza_headings():
    texto = "# A\n\n## B\n\nparrafo bajo B\n"
    cir = TextToCIRAdapter.adapt(texto, title="Doc")
    parrafo = next(e for e in cir.elements if e.type is ElementType.PARAGRAPH)
    # breadcrumb incluye la sección raíz y los headings ancestros
    assert "Doc" in parrafo.breadcrumb
    assert "B" in parrafo.breadcrumb


# --- DocxParser -------------------------------------------------------------


def test_docx_estructura_y_tabla_integra(tmp_path):
    doc = Document()
    doc.add_heading("Proceso de Siniestros", level=1)
    doc.add_paragraph("Introducción al proceso.")
    doc.add_paragraph("Reportar siniestro", style="List Bullet")
    doc.add_paragraph("Registrar guía", style="List Bullet")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Campo"
    table.cell(0, 1).text = "Tipo"
    table.cell(1, 0).text = "numero_guia"
    table.cell(1, 1).text = "texto"
    path = tmp_path / "proc.docx"
    doc.save(str(path))

    cir = DocxParser.parse(path)
    assert cir.fidelity == "full"
    assert any(e.type is ElementType.HEADING for e in cir.elements)
    assert any(e.type is ElementType.LIST for e in cir.elements)

    tablas = cir.tables()
    assert len(tablas) == 1
    tbl = tablas[0].table
    assert tbl.n_rows == 2 and tbl.n_cols == 2
    assert tbl.rows[0] == ["Campo", "Tipo"]
    assert tbl.rows[1] == ["numero_guia", "texto"]


# --- PdfParser (pypdf monkeypatcheado) --------------------------------------


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


def _fake_reader(pages_text):
    class _FakeReader:
        def __init__(self, _path):
            self.pages = [_FakePage(t) for t in pages_text]

    return _FakeReader


def test_pdf_texto_con_coordenadas_de_pagina(monkeypatch):
    monkeypatch.setattr(
        pdf_mod,
        "PdfReader",
        _fake_reader(["# Título\n\nUn párrafo de la página uno.", "Texto página dos."]),
    )
    cir = pdf_mod.PdfParser.parse("dummy.pdf")
    assert cir.fidelity == "degraded"
    assert any(e.type is ElementType.HEADING for e in cir.elements)
    assert any(e.coordinates.page == 2 for e in cir.elements)


def test_pdf_escaneado_lanza_error(monkeypatch):
    monkeypatch.setattr(pdf_mod, "PdfReader", _fake_reader(["", "   ", "\n"]))
    with pytest.raises(ScannedPDFError):
        pdf_mod.PdfParser.parse("scan.pdf")
