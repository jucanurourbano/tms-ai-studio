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


class _FakeAIMessage:
    """Emula ``AIMessage`` de LangChain: solo expone ``content``."""

    def __init__(self, content) -> None:
        self.content = content


class BlockContentChat:
    """Fake ``ChatAnthropic`` que reproduce la forma REAL de la respuesta.

    En ``langchain-anthropic`` 1.x + ``claude-sonnet-5`` la respuesta llega como
    una **lista de bloques** (``thinking`` + ``text``), no como string. Envuelve
    la salida JSON de cualquier mock (``DimAwareLLM``, ``CritiqueLLM``, ...) en
    esa forma para ejercitar el adaptador real ``ClaudeLLMClient`` de punta a
    punta: es exactamente el escenario que rompía la extracción.
    """

    def __init__(self, inner) -> None:
        self._inner = inner

    async def ainvoke(self, messages):
        system = next((c for r, c in messages if r == "system"), "")
        user = next((c for r, c in messages if r == "user"), "")
        raw = await self._inner.complete_json(system=system, user=user)
        return _FakeAIMessage(
            [
                {"type": "thinking", "thinking": "Razonando sobre el fragmento..."},
                {"type": "text", "text": raw},
            ]
        )


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


class RichCritiqueLLM:
    """Pase de crítica con hallazgos en las TRES categorías (analista escéptico).

    Reproduce los vacíos típicos del dominio vacaciones: sin plazo/escalamiento,
    definiciones ambiguas y contenidos sin detallar. Sirve al test de humo para
    verificar que QUESTION_GEN los convierte en preguntas."""

    async def complete_json(self, *, system: str, user: str) -> str:
        return json.dumps(
            {
                "ambiguities": [
                    {
                        "description": (
                            "No se especifica si los 15 días son hábiles o "
                            "calendario."
                        ),
                        "source_ref": "BR-001",
                    }
                ],
                "missing_info": [
                    {
                        "description": (
                            "No se define qué ocurre si el jefe no responde "
                            "(plazo/escalamiento)."
                        ),
                        "expected_where": "Flujo de aprobación.",
                    }
                ],
                "inconsistencies": [
                    {
                        "description": "El reporte exportable no detalla su contenido.",
                        "conflicting_refs": ["PRO-001"],
                    }
                ],
            },
            ensure_ascii=False,
        )


def _payload_from_user(user: str) -> dict:
    """Extrae el JSON del mensaje de usuario (formato ``ENCABEZADO:\\n<json>``)."""
    _, _, body = user.partition("\n")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


class ScrumMapLLM:
    """LLM mock del Agente Scrum: responde por nodo según el rol del system prompt.

    - EPICS: una épica que cita MOD-001/PRO-001 reales.
    - STORIES: una historia por requisito funcional, anclada al RF de la pasada;
      si el RF no es ``REQ-F-001``, depende de ``REQ-F-001`` (prueba dependencias).
    - CRITERIA: un criterio Gherkin anclado a BR-001.
    - ESTIMATE / PRIORITIZE / CRITIQUE: se completan en bloques posteriores.
    """

    async def complete_json(self, *, system: str, user: str) -> str:
        if "Agrupador de épicas" in system:
            return json.dumps(
                {
                    "epics": [
                        {
                            "title": "Gestión de Siniestros",
                            "description": "Registro y seguimiento de siniestros.",
                            "source_refs": ["MOD-001", "PRO-001"],
                            "confidence": 0.8,
                        }
                    ]
                },
                ensure_ascii=False,
            )
        if "Redactor de historias" in system:
            rf = _payload_from_user(user).get("functional_requirement", {})
            rf_id = rf.get("id", "REQ-F-001")
            deps = [] if rf_id == "REQ-F-001" else ["REQ-F-001"]
            return json.dumps(
                {
                    "stories": [
                        {
                            "role": "operador de siniestros",
                            "goal": f"gestionar el requisito {rf_id}",
                            "benefit": "mantener la trazabilidad del proceso",
                            "requirement_refs": [rf_id],
                            "process_refs": ["PRO-001"],
                            "rule_refs": ["BR-001"],
                            "depends_on_requirements": deps,
                            "epic_hint": "MOD-001",
                            "confidence": 0.7,
                        }
                    ]
                },
                ensure_ascii=False,
            )
        if "Analista de criterios" in system:
            return json.dumps(
                {
                    "acceptance_criteria": [
                        {
                            "format": "gherkin",
                            "given": "un siniestro registrado",
                            "when": "el operador ejecuta la acción",
                            "then": "el sistema responde según la regla",
                            "source_refs": ["BR-001"],
                        }
                    ]
                },
                ensure_ascii=False,
            )
        if "Estimador ágil" in system:
            return json.dumps(
                {
                    "story_points": 5,
                    "rationale": "CRUD con validación de guía y estados.",
                    "confidence": 0.7,
                },
                ensure_ascii=False,
            )
        if "Product analyst" in system:
            return json.dumps(
                {
                    "priority": "must",
                    "value": 4,
                    "effort": 3,
                    "rationale": "Requisito central del proceso.",
                },
                ensure_ascii=False,
            )
        return "{}"
