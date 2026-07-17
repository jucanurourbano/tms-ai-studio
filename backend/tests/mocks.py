"""Mocks compartidos de tests. NUNCA se llama a la API real (REGLA DE PRESUPUESTO)."""

import json

# Contenido sintético del dominio siniestros por dimensión.
_RESPONSES: dict[str, dict] = {
    "REQUISITOS": {
        "business": [
            {
                "text": "Registrar cada siniestro asociándolo a su guía.",
                "priority": "alta",
                "source_ref": "el-0001",
                "evidence": "Todo siniestro debe registrarse con su guía.",
                "confidence": 0.95,
                "origin": "stated",
            }
        ],
        "functional": [
            {
                "text": "Cambiar el estado (checkpoint) del siniestro.",
                "source_ref": "el-0002",
                "evidence": "El operador actualiza el estado del siniestro.",
                "confidence": 0.9,
                "origin": "stated",
            }
        ],
        "non_functional": [],
    },
    "ACTORES": {
        "actors": [
            {
                "name": "Operador de siniestros",
                "description": "Registra y da seguimiento a los siniestros.",
                "responsibilities": ["Registrar siniestro", "Actualizar estado"],
                "source_ref": "el-0001",
                "evidence": "El operador registra el siniestro.",
                "confidence": 0.9,
                "origin": "stated",
            }
        ]
    },
    "MÓDULOS": {
        "modules": [
            {
                "name": "Gestión de Siniestros",
                "description": "Registro y seguimiento de siniestros.",
                "source_ref": "el-0000",
                "evidence": "Módulo de siniestros.",
                "confidence": 0.7,
                "origin": "derived",
            }
        ],
        "menus": [
            {
                "name": "Siniestros",
                "module_ref": "Gestión de Siniestros",
                "path": "/siniestros",
                "source_ref": "el-0000",
                "evidence": "Menú de siniestros.",
                "confidence": 0.6,
                "origin": "derived",
            }
        ],
    },
    "PROCESOS": {
        "processes": [
            {
                "name": "Registro de siniestro",
                "description": "Del reporte al cierre del siniestro.",
                "steps": ["Reportar", "Registrar", "Investigar", "Recuperar", "Cerrar"],
                "actor_refs": ["Operador de siniestros"],
                "source_ref": "el-0003",
                "evidence": "Flujo del proceso de siniestros.",
                "confidence": 0.85,
                "origin": "stated",
            }
        ]
    },
    "REGLAS DE NEGOCIO": {
        "business_rules": [
            {
                "statement": "Un siniestro sin guía asociada no puede registrarse.",
                "source_ref": "el-0001",
                "evidence": "No se registra un siniestro sin guía.",
                "confidence": 0.9,
                "origin": "stated",
            }
        ],
        "validations": [
            {
                "rule": "La fecha del siniestro no puede ser futura.",
                "field_ref": "fecha_siniestro",
                "source_ref": "el-0002",
                "evidence": "La fecha no puede ser posterior a hoy.",
                "confidence": 0.8,
                "origin": "derived",
            }
        ],
    },
    "CAMPOS": {
        "fields": [
            {
                "name": "numero_guia",
                "entity_ref": "Siniestro",
                "data_type": "string",
                "required": True,
                "source_ref": "el-0001",
                "evidence": "Número de guía del siniestro.",
                "confidence": 0.9,
                "origin": "stated",
            },
            {
                "name": "fecha_siniestro",
                "entity_ref": "Siniestro",
                "data_type": "date",
                "required": True,
                "source_ref": "el-0002",
                "evidence": "Fecha del siniestro.",
                "confidence": 0.8,
                "origin": "derived",
            },
            {
                "name": "guia_id",
                "entity_ref": "Siniestro",
                "data_type": "string",
                "required": False,
                "source_ref": "el-0001",
                "evidence": "Referencia a la guía.",
                "confidence": 0.7,
                "origin": "derived",
            },
            {
                "name": "numero",
                "entity_ref": "Guia",
                "data_type": "string",
                "required": True,
                "source_ref": "el-0004",
                "evidence": "Número de la guía.",
                "confidence": 0.7,
                "origin": "derived",
            },
        ]
    },
}


class DimAwareLLM:
    """LLM mock: devuelve JSON válido según la dimensión del system prompt.

    Con ``invalid_for`` fuerza JSON inválido para una dimensión (prueba cuarentena).
    """

    def __init__(self, invalid_for: str | None = None) -> None:
        self.invalid_for = invalid_for

    async def complete_json(self, *, system: str, user: str) -> str:
        for keyword, payload in _RESPONSES.items():
            if keyword in system:
                if self.invalid_for and self.invalid_for in system:
                    return "{ esto no es json válido"
                return json.dumps(payload, ensure_ascii=False)
        return "{}"


class CritiqueLLM:
    """Mock del pase LLM de crítica: planta una contradicción semántica."""

    async def complete_json(self, *, system: str, user: str) -> str:
        return json.dumps(
            {
                "ambiguities": [],
                "missing_info": [],
                "inconsistencies": [
                    {
                        "description": (
                            "Una regla exige guía para registrar y otra permite "
                            "registrar sin guía."
                        ),
                        "conflicting_refs": ["BR-001"],
                    }
                ],
            },
            ensure_ascii=False,
        )
