"""Tests de INTERPRET, CRITIQUE y QUESTION_GEN (Bloque 6)."""

import json

from ai.agents.ef.critique import critique, find_orphan_refs
from ai.agents.ef.interpret import interpret
from ai.agents.ef.question_gen import generate_questions


def _consolidado():
    return {
        "requirements": {
            "business": [{"id": "REQ-B-001", "text": "Registrar siniestro."}],
            "functional": [
                {"id": "REQ-F-001", "text": "Cambiar el checkpoint del siniestro."}
            ],
            "non_functional": [],
        },
        "actors": [{"id": "ACT-001", "name": "Operador", "confidence": 0.9}],
        "modules": [{"id": "MOD-001", "name": "Siniestros"}],
        "menus": [],
        "processes": [{"id": "PRO-001", "name": "Registro", "confidence": 0.8}],
        "business_rules": [],
        "validations": [
            {"id": "VAL-001", "rule": "Fecha no futura.", "field_ref": "numero_guia"}
        ],
        "fields": [
            {"id": "FLD-001", "name": "numero_guia", "confidence": 0.9},
            {"id": "FLD-002", "name": "estado", "confidence": 0.3},  # baja confianza
        ],
    }


# --- INTERPRET --------------------------------------------------------------


def test_interpret_supuestos_desde_glosario():
    si = interpret(_consolidado(), {"entities": []}, summary=None)
    # 'checkpoint' aparece en un requisito -> supuesto SUP-001 del glosario
    sups = si["interpretation_assumptions"]
    assert any(s["id"] == "SUP-001" for s in sups)
    assert any("checkpoint" in s["assumption"] for s in sups)
    # scope con refs a requisitos
    assert si["scope_for_systems"][0]["requirement_refs"] == ["REQ-F-001"]
    assert si["what_process_requests"]


def test_interpret_fallback_a_procesos_sin_requisitos():
    """REGRESIÓN (#2): sin requisitos pero CON procesos, INTERPRET no queda vacío
    (antes: 'no se identificó petición', 0 alcance)."""
    cons = {
        "requirements": {"business": [], "functional": [], "non_functional": []},
        "actors": [],
        "modules": [],
        "menus": [],
        "processes": [
            {"id": "PRO-001", "name": "Solicitud de vacaciones", "steps": []}
        ],
        "business_rules": [],
        "validations": [],
        "fields": [],
    }
    si = interpret(cons, {"entities": []}, summary=None)
    assert "Solicitud de vacaciones" in si["what_process_requests"]
    assert "no se identificó" not in si["what_process_requests"]
    assert si["scope_for_systems"]
    assert si["scope_for_systems"][0]["requirement_refs"] == ["PRO-001"]


# --- CRITIQUE ---------------------------------------------------------------


async def test_critique_ref_huerfana_deterministica():
    cons = _consolidado()
    cons["validations"][0]["field_ref"] = "campo_inexistente"  # ref huérfana plantada
    result = await critique(cons, {"entities": []})
    inc = result["inconsistencies"]
    assert len(inc) == 1
    assert inc[0]["kind"] == "orphan_ref"
    assert "campo_inexistente" in inc[0]["conflicting_refs"]


async def test_critique_baja_confianza_es_candidato():
    result = await critique(_consolidado(), {"entities": []})
    # FLD-002 tiene confidence 0.3 < 0.5
    assert any("FLD-002" in a["description"] for a in result["ambiguities"])


async def test_critique_pase_llm_contradiccion():
    class ContradictionLLM:
        async def complete_json(self, *, system, user):
            return json.dumps(
                {
                    "ambiguities": [],
                    "missing_info": [],
                    "inconsistencies": [
                        {
                            "description": "Una regla exige guía y otra la prohíbe.",
                            "conflicting_refs": ["BR-001", "BR-002"],
                        }
                    ],
                }
            )

    result = await critique(_consolidado(), {"entities": []}, llm=ContradictionLLM())
    contradiccion = [
        i for i in result["inconsistencies"] if i.get("kind") != "orphan_ref"
    ]
    assert len(contradiccion) == 1
    assert "prohíbe" in contradiccion[0]["description"]


def test_find_orphan_refs():
    cons = _consolidado()
    cons["menus"] = [{"id": "MEN-001", "module_ref": "MOD-999"}]
    orphans = find_orphan_refs(cons, {"entities": []})
    assert any(o["ref"] == "MOD-999" for o in orphans)


async def test_critique_llm_missing_info_genera_pregunta():
    """REGRESIÓN (#3): con el pase LLM cableado, los vacíos del texto (p. ej. sin
    plazo de respuesta) se vuelven preguntas al analista. Sin critique_llm el
    pipeline real generaba 0 preguntas."""

    class VaciosLLM:
        async def complete_json(self, *, system, user):
            return json.dumps(
                {
                    "ambiguities": [],
                    "missing_info": [
                        {
                            "description": "No se define el plazo de respuesta del jefe.",
                            "expected_where": "Flujo de aprobación.",
                        }
                    ],
                    "inconsistencies": [],
                }
            )

    result = await critique(_consolidado(), {"entities": []}, llm=VaciosLLM())
    assert any("plazo de respuesta" in m["description"] for m in result["missing_info"])

    questions, _obs = generate_questions(result, _consolidado())
    plazo_q = [q for q in questions if "plazo de respuesta" in q["question"]]
    assert len(plazo_q) == 1
    assert plazo_q[0]["blocking"] is True
    assert plazo_q[0]["audience"] == "negocio"


# --- QUESTION_GEN -----------------------------------------------------------


def test_question_gen_rutas():
    critique_result = {
        "ambiguities": [
            {"id": "AMB-001", "description": "Confianza baja en campo 'FLD-002'."}
        ],
        "missing_info": [
            {"id": "MISS-001", "description": "No se identificó responsable de cierre."}
        ],
        "inconsistencies": [
            {
                "id": "INC-001",
                "description": "Referencia huérfana: 'MOD-999'.",
                "kind": "orphan_ref",
                "conflicting_refs": ["MOD-999"],
            },
            {
                "id": "INC-002",
                "description": "Contradicción entre dos reglas.",
                "conflicting_refs": ["BR-001", "BR-002"],
            },
        ],
        "observations": [],
    }
    questions, obs_extra = generate_questions(critique_result, _consolidado())

    # La ref huérfana (técnica) NO es pregunta: es observación.
    assert len(obs_extra) == 1
    assert "MOD-999" in obs_extra[0]["description"]

    # Preguntas: contradicción (blocking), faltante (blocking), baja conf (no blocking)
    by_id = {q["question"]: q for q in questions}
    assert len(questions) == 3
    contradiccion = next(q for q in questions if "Contradicción" in q["question"])
    assert contradiccion["blocking"] is True
    assert contradiccion["audience"] == "negocio"
    baja = next(q for q in questions if "Confianza baja" in q["question"])
    assert baja["blocking"] is False
