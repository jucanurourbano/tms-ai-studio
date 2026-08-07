"""Render y validación del documento OpenAPI (sin LLM).

``render`` construye el documento 3.1 desde el contrato estructurado y ``validate``
lo comprueba en capas. ``smoke`` (capa L3a) vive aparte porque depende de
``openapi-core``, que es dependencia solo de test.
"""

from .render import build_document, build_openapi, to_yaml
from .validate import check_round_trip, check_spec, check_structure, validate_spec

__all__ = [
    "build_document",
    "build_openapi",
    "check_round_trip",
    "check_spec",
    "check_structure",
    "to_yaml",
    "validate_spec",
]
