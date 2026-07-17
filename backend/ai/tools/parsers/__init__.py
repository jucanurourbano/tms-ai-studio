"""Parsers de fuentes a CIR."""

from .docx_parser import DocxParser
from .pdf_parser import PdfParser
from .text_adapter import TextToCIRAdapter

__all__ = ["DocxParser", "PdfParser", "TextToCIRAdapter"]
