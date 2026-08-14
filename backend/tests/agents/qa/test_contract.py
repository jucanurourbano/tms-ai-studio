"""Tests del contrato QaArtifact v1.0.0 (QA1): validación + round-trip.

Más allá del round-trip, fijan las **invariantes de diseño** del agente: que ningún
caso pueda existir sin el criterio del que nace, que ningún límite de borde pueda
existir sin la evidencia que lo sostiene, que ninguna cobertura pueda declararse sin
casos detrás, y que no puedan aparecer casos de autorización cuando no hubo contrato
de API del que derivarlos.

Todas describen el mismo error, que es el que este agente existe para no cometer:
un caso de prueba que **pasa** y certifica algo que nadie dijo. Un caso ausente se
ve en la cobertura; uno falso se firma como verificado.
"""

import pytest
from pydantic import ValidationError

from ai.agents.qa.schemas import (
    MOSCOW_TO_PRIORITY,
    SCHEMA_VERSION,
    AnchorSource,
    AuthCase,
    AuthScope,
    BoundaryAnchor,
    BoundaryKind,
    Coverage,
    CoverageStatus,
    DatasetRow,
    MoscowPriority,
    QaArtifact,
    SourceRef,
    TestCase,
    TestCaseType,
    TestPriority,
    TestStep,
    TraceRow,
)
from ai.agents.qa.schemas.examples import example_artifact

# --- Round-trip y forma del ejemplo -------------------------------------------


def test_ejemplo_valido_y_version():
    art = example_artifact()
    assert art.schema_version == SCHEMA_VERSION == "1.0.0"
    assert art.source.ready_snapshot is True
    # Enlace a los tres jobs: Scrum directo, EF transitivo y API indicado.
    assert art.source.scrum_job_id
    assert art.source.ef_job_id
    assert art.source.api_job_id
    assert art.source.api_available is True


def test_round_trip_sin_perdida():
    art = example_artifact()
    vuelta = QaArtifact.model_validate(art.model_dump(mode="json"))
    assert vuelta.model_dump(mode="json") == art.model_dump(mode="json")


def test_todo_caso_cita_su_criterio_y_su_historia():
    """El cortafuegos anti-invención, visto desde el artefacto terminado."""
    art = example_artifact()
    assert art.test_cases
    for caso in art.test_cases:
        assert caso.criterion_ref, f"{caso.id} sin criterio de origen"
        assert caso.story_ref, f"{caso.id} sin historia de origen"
        assert caso.steps, f"{caso.id} sin pasos"
        assert caso.expected_result


def test_el_ejemplo_cubre_las_cuatro_clases_de_caso():
    tipos = {c.type for c in example_artifact().test_cases}
    assert tipos == set(TestCaseType)


def test_los_pasos_estan_numerados_de_forma_contigua():
    for caso in example_artifact().test_cases:
        numeros = [p.number for p in caso.steps]
        assert numeros == list(range(1, len(numeros) + 1)), caso.id


def test_el_ejemplo_no_esta_listo_pese_a_cobertura_total():
    """Cobertura del 100% y aun así no listo: el semáforo no es solo cobertura.

    El plan cubre los dos criterios, pero queda una pregunta bloqueante porque una
    regla de autorización era ambigua. Un plan completo sobre un permiso que nadie
    precisó no es un plan ejecutable.
    """
    art = example_artifact()
    assert art.analysis.coverage.criteria_ratio == 1.0
    bloqueantes = [q for q in art.questions_for_qa_lead if q.blocking]
    assert bloqueantes, "el ejemplo debe conservar su pregunta bloqueante"
    assert bloqueantes[0].linked_to_ref == "AUTH-002"


def test_la_ausencia_del_caso_ambiguo_queda_observada():
    """Un caso que no se generó a propósito deja rastro (nunca descarte mudo)."""
    art = example_artifact()
    assert any(
        "AUTH-002" in (o.source_ref or "") for o in art.analysis.observations
    ), "la omisión deliberada debe quedar registrada como Observation"


def test_mapeo_moscow_a_prioridad_cerrado():
    """Candado: el mapeo MoSCoW → prioridad cubre los cuatro valores, sin huecos."""
    assert set(MOSCOW_TO_PRIORITY) == {m.value for m in MoscowPriority}
    assert set(MOSCOW_TO_PRIORITY.values()) <= {p.value for p in TestPriority}
    assert MOSCOW_TO_PRIORITY[MoscowPriority.MUST.value] == TestPriority.CRITICA.value


# --- Lo que el contrato debe IMPEDIR ------------------------------------------


def _pasos() -> list[TestStep]:
    return [TestStep(number=1, action="Hacer algo verificable.")]


def _caso_base(**extra) -> dict:
    return {
        "id": "TC-900",
        "title": "Caso de prueba",
        "story_ref": "US-001",
        "criterion_ref": "AC-001",
        "steps": _pasos(),
        "expected_result": "Algo observable ocurre.",
        **extra,
    }


def test_un_caso_sin_criterio_es_invalido():
    """Sin criterio no hay trazabilidad: el caso vendría de la nada."""
    datos = _caso_base()
    del datos["criterion_ref"]
    with pytest.raises(ValidationError):
        TestCase(**datos)


def test_un_caso_sin_pasos_es_invalido():
    """Un caso sin pasos cuenta en la cobertura y no prueba nada."""
    with pytest.raises(ValidationError):
        TestCase(**_caso_base(steps=[]))


def test_un_caso_de_borde_sin_limite_es_invalido():
    with pytest.raises(ValidationError, match="no declara el límite"):
        TestCase(**_caso_base(type=TestCaseType.BOUNDARY))


def test_un_limite_del_ef_sin_cita_verbatim_es_invalido():
    """El corazón de QA-D2: sin la frase, el límite es una invención."""
    with pytest.raises(ValidationError, match="cita verbatim"):
        BoundaryAnchor(
            rule_ref="VAL-001",
            kind=BoundaryKind.MAX,
            anchor_source=AnchorSource.EF_TEXT,
            value="1000",
        )


def test_un_limite_del_ef_sin_regla_citada_es_invalido():
    with pytest.raises(ValidationError, match="rule_ref"):
        BoundaryAnchor(
            kind=BoundaryKind.MAX,
            anchor_source=AnchorSource.EF_TEXT,
            evidence="El monto no puede superar los 1000 soles.",
        )


def test_un_limite_del_api_sin_campo_citado_es_invalido():
    with pytest.raises(ValidationError, match="api_field_ref"):
        BoundaryAnchor(kind=BoundaryKind.REQUIRED, anchor_source=AnchorSource.API_FIELD)


def test_un_limite_estructural_del_api_no_necesita_regla_ni_cita():
    """La otra cara: un dato duro del contrato se sostiene solo."""
    anchor = BoundaryAnchor(
        kind=BoundaryKind.REQUIRED,
        anchor_source=AnchorSource.API_FIELD,
        api_field_ref="SF-005",
    )
    assert anchor.rule_ref is None and anchor.evidence is None


def test_un_caso_de_autorizacion_sin_regla_es_invalido():
    with pytest.raises(ValidationError, match="no cita la regla"):
        TestCase(**_caso_base(type=TestCaseType.AUTHORIZATION))


def test_sin_api_no_puede_haber_casos_de_autorizacion():
    """QA-D1/QA-D7: la dependencia opcional no entra por la puerta de atrás."""
    caso = TestCase(
        **_caso_base(
            type=TestCaseType.AUTHORIZATION,
            auth_context=AuthCase(
                auth_rule_ref="AUTH-001",
                endpoint_ref="EP-001",
                scope=AuthScope.OWN_TEAM,
            ),
        )
    )
    fuente_sin_api = SourceRef(
        scrum_job_id="01SC",
        scrum_artifact_hash="h1",
        ef_job_id="01EF",
        ef_artifact_hash="h2",
        api_available=False,
        api_absent_reason="No se indicó contrato de API para este plan.",
    )
    with pytest.raises(ValidationError, match="sin ApiArtifact"):
        QaArtifact(source=fuente_sin_api, test_cases=[caso])


def test_sin_api_el_motivo_es_obligatorio():
    """La ausencia se declara: 'no hay' y 'no se pudo' no pueden confundirse."""
    with pytest.raises(ValidationError, match="api_absent_reason"):
        SourceRef(
            scrum_job_id="01SC",
            scrum_artifact_hash="h1",
            ef_job_id="01EF",
            ef_artifact_hash="h2",
            api_available=False,
        )


def test_con_api_hacen_falta_id_y_hash():
    with pytest.raises(ValidationError, match="api_job_id"):
        SourceRef(
            scrum_job_id="01SC",
            scrum_artifact_hash="h1",
            ef_job_id="01EF",
            ef_artifact_hash="h2",
            api_available=True,
        )
    with pytest.raises(ValidationError, match="hash"):
        SourceRef(
            scrum_job_id="01SC",
            scrum_artifact_hash="h1",
            ef_job_id="01EF",
            ef_artifact_hash="h2",
            api_available=True,
            api_job_id="01AP",
        )


def test_un_criterio_cubierto_sin_casos_es_invalido():
    """Cobertura falsa, la mentira más barata de este artefacto."""
    with pytest.raises(ValidationError, match="cubierto sin ningún caso"):
        TraceRow(
            story_ref="US-001",
            criterion_ref="AC-001",
            status=CoverageStatus.COVERED,
            test_case_ids=[],
        )


def test_un_criterio_no_verificable_exige_pregunta():
    """'No se puede probar' sin destinatario sería una excusa, no un hallazgo."""
    with pytest.raises(ValidationError, match="sin pregunta"):
        TraceRow(
            story_ref="US-001",
            criterion_ref="AC-003",
            status=CoverageStatus.NOT_TESTABLE,
        )
    fila = TraceRow(
        story_ref="US-001",
        criterion_ref="AC-003",
        status=CoverageStatus.NOT_TESTABLE,
        question_ref="QQ-002",
    )
    assert fila.question_ref == "QQ-002"


def test_una_cobertura_imposible_es_invalida():
    with pytest.raises(ValidationError, match="imposible"):
        Coverage(criteria_total=2, criteria_covered=3)


def test_una_fila_de_dataset_sin_valores_es_invalida():
    with pytest.raises(ValidationError, match="ningún valor"):
        DatasetRow(id="DS-001-R9", expectation="Se acepta.", values={})


def test_extra_forbid_en_todo_el_contrato():
    """Structured output cerrado: una clave inventada no pasa desapercibida."""
    with pytest.raises(ValidationError):
        TestCase(**_caso_base(clave_inventada="x"))
