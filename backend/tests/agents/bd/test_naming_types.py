"""Tests de la nomenclatura física y la normalización de tipos (BD2).

Estas dos piezas son el cimiento determinista del agente: si el nombre de una
tabla o el tipo de una columna dependieran del humor del LLM, el DDL no sería
reproducible ni testeable.
"""

import pytest

from ai.agents.bd.naming import (
    columns_suffix,
    constraint_name,
    fk_column_name,
    is_reserved,
    junction_table_name,
    pk_column_name,
    pluralize,
    singularize,
    snake,
    strip_accents,
    table_name,
    truncate_identifier,
)
from ai.agents.bd.schemas.enums import LogicalType
from ai.agents.bd.types import (
    TypeSource,
    default_length,
    default_precision,
    normalize_type,
)
from ai.knowledge import max_identifier_length

# --- Nomenclatura -----------------------------------------------------------


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("Siniestro", "siniestro"),
        ("Guía", "guia"),
        ("Número de guía", "numero_de_guia"),
        ("NumeroGuia", "numero_guia"),
        ("  Recupero  Económico ", "recupero_economico"),
        ("papeleta/descuento", "papeleta_descuento"),
    ],
)
def test_snake_normaliza_acentos_y_camel(entrada: str, esperado: str):
    assert snake(entrada) == esperado


def test_strip_accents_no_toca_lo_demas():
    assert strip_accents("ubigeo: José Ñuñez") == "ubigeo: Jose Nunez"


@pytest.mark.parametrize(
    "singular,plural",
    [
        ("siniestro", "siniestros"),
        ("guia", "guias"),
        ("papel", "papeles"),
        ("vez", "veces"),
        ("estado_siniestro", "estado_siniestros"),
        ("siniestros", "siniestros"),  # ya en plural: no se duplica la s
    ],
)
def test_pluralize_castellano(singular: str, plural: str):
    assert pluralize(singular) == plural


@pytest.mark.parametrize(
    "plural,singular",
    [
        ("siniestros", "siniestro"),
        ("guias", "guia"),
        ("papeles", "papel"),
        ("veces", "vez"),
    ],
)
def test_singularize_es_inverso_de_pluralize(plural: str, singular: str):
    assert singularize(plural) == singular
    assert pluralize(singular) == plural


def test_table_name_usa_la_convencion_de_la_casa():
    assert table_name("Siniestro") == "siniestros"
    assert table_name("Guía") == "guias"


def test_columnas_de_clave_siguen_el_patron():
    assert pk_column_name("guia") == "guia_id"
    assert fk_column_name("guia") == "guia_id"


def test_junction_table_name_es_independiente_del_sentido():
    """La misma pareja produce el mismo nombre en cualquier orden.

    Si dependiera del sentido en que el EF declara la relación, una relación N:M
    declarada dos veces (una por lado) generaría dos tablas puente distintas.
    """
    assert junction_table_name("guias", "etiquetas") == junction_table_name(
        "etiquetas", "guias"
    )
    assert junction_table_name("guias", "etiquetas") == "etiquetas_guias"


def test_constraint_name_sigue_los_patrones():
    assert constraint_name("primary_key", "siniestros", "postgresql") == "pk_siniestros"
    assert (
        constraint_name(
            "foreign_key", "siniestros", "postgresql", referenced_table="guias"
        )
        == "fk_siniestros_guias"
    )
    assert (
        constraint_name(
            "index",
            "siniestros",
            "postgresql",
            columns=columns_suffix(["estado_id", "fecha"]),
        )
        == "ix_siniestros_estado_id_fecha"
    )


@pytest.mark.parametrize("engine", ["postgresql", "sqlserver", "oracle", "mysql"])
def test_identificadores_respetan_el_limite_del_motor(engine: str):
    """Oracle (30) es el caso estrecho: el nombre se recorta, no se emite inválido."""
    largo = "fk_" + "seguimiento_de_siniestros_" * 4 + "guias"
    resultado = constraint_name("foreign_key", largo, engine, referenced_table="guias")
    assert len(resultado) <= max_identifier_length(engine)


def test_truncado_conserva_unicidad():
    """Dos nombres con el mismo prefijo largo no colisionan tras recortar.

    Es exactamente cómo aparecen los "duplicate constraint name" en Oracle.
    """
    base = "ix_siniestros_seguimiento_operativo_detallado_"
    a = truncate_identifier(base + "estado", "oracle")
    b = truncate_identifier(base + "fecha", "oracle")
    assert a != b
    assert len(a) <= 30 and len(b) <= 30


def test_truncado_es_estable_entre_procesos():
    """El sufijo sale de sha1, no de hash(): mismo nombre ⇒ mismo recorte siempre.

    Con ``hash()`` el resultado cambiaría en cada proceso (PYTHONHASHSEED) y el
    DDL dejaría de ser reproducible.
    """
    nombre = "ix_" + "x" * 60
    # Valor fijado a propósito: si alguien cambia el algoritmo de sufijo, este test
    # lo detecta, porque renombraría constraints de esquemas ya entregados.
    assert truncate_identifier(nombre, "oracle") == "ix_xxxxxxxxxxxxxxxxxxxxxx_1b08"


def test_palabras_reservadas_se_detectan():
    assert is_reserved("order") is True
    assert is_reserved("Grupo") is False


# --- Normalización de tipos -------------------------------------------------


@pytest.mark.parametrize(
    "declarado,esperado",
    [
        ("string", LogicalType.STRING),
        ("texto", LogicalType.STRING),
        ("date", LogicalType.DATE),
        ("fecha", LogicalType.DATE),
        ("fecha y hora", LogicalType.TIMESTAMP),
        ("número decimal", LogicalType.DECIMAL),
        ("booleano", LogicalType.BOOLEAN),
        ("entero", LogicalType.INTEGER),
        ("observaciones", LogicalType.TEXT),
    ],
)
def test_tipo_declarado_se_reconoce(declarado: str, esperado: LogicalType):
    decision = normalize_type(declarado, field_name="campo")
    assert decision.logical_type is esperado
    assert decision.source is TypeSource.DECLARED
    assert decision.ambiguous is False


def test_sinonimo_mas_largo_gana():
    """«texto largo» debe resolver a TEXT y no a STRING por contener «texto»."""
    assert normalize_type("texto largo").logical_type is LogicalType.TEXT


def test_tipo_dentro_de_una_frase():
    decision = normalize_type("número decimal con 2 posiciones", field_name="monto")
    assert decision.logical_type is LogicalType.DECIMAL
    assert decision.source is TypeSource.DECLARED


@pytest.mark.parametrize(
    "campo,esperado",
    [
        ("fecha_siniestro", LogicalType.DATE),
        ("fecha_hora_registro", LogicalType.TIMESTAMP),
        ("guia_id", LogicalType.BIGINT),
        ("monto_recupero", LogicalType.DECIMAL),
        ("cantidad_bultos", LogicalType.INTEGER),
        ("es_reincidente", LogicalType.BOOLEAN),
        ("observacion", LogicalType.TEXT),
        ("nombre_cliente", LogicalType.STRING),
    ],
)
def test_tipo_inferido_del_nombre_cuando_el_EF_no_lo_declara(
    campo: str, esperado: LogicalType
):
    decision = normalize_type(None, field_name=campo)
    assert decision.logical_type is esperado
    assert decision.source is TypeSource.INFERRED_FROM_NAME
    # Inferido no es lo mismo que declarado: baja la confianza.
    assert decision.confidence < 0.9


def test_tipo_desconocido_se_marca_ambiguo_y_no_se_adivina():
    """Sin base ni en el tipo ni en el nombre: candidato conservador + ambiguo."""
    decision = normalize_type("", field_name="zzz", required=True)
    assert decision.ambiguous is True
    assert decision.source is TypeSource.UNKNOWN
    assert (
        decision.logical_type is LogicalType.STRING
    )  # el que menos información pierde
    assert decision.confidence <= 0.4


def test_required_no_cambia_el_tipo_pero_baja_la_confianza():
    """`required` solo informa a QUESTION_GEN si la ambigüedad es bloqueante."""
    opcional = normalize_type("", field_name="zzz", required=False)
    obligatorio = normalize_type("", field_name="zzz", required=True)
    assert opcional.logical_type is obligatorio.logical_type
    assert obligatorio.confidence < opcional.confidence


def test_longitudes_por_defecto_segun_el_nombre():
    assert default_length(LogicalType.STRING, "codigo_estado") == 30
    assert default_length(LogicalType.STRING, "nombre_cliente") == 150
    assert default_length(LogicalType.STRING, "cualquier_cosa") == 100
    # Los tipos sin longitud no la inventan.
    assert default_length(LogicalType.DATE, "fecha") is None
    assert default_length(LogicalType.BIGINT, "guia_id") is None


def test_precision_por_defecto_solo_para_decimal():
    assert default_precision(LogicalType.DECIMAL) == (12, 2)
    assert default_precision(LogicalType.INTEGER) == (None, None)
