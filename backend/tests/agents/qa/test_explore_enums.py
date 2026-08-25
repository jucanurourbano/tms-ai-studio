"""Los conjuntos cerrados del extractor: C1–C5 de QC5.

**C1 — todo lo de aquí es HTML SINTÉTICO, y hay un candado que lo obliga.** En las
fixtures hay exactamente cero enums, y no por casualidad: el saneador vacía todo
``value`` antes de comitear, así que un ``<select>`` saneado no declara ningún
conjunto (F2, §13.4). Probar los enums contra fixtures sería probarlos contra
listas vacías — un test verde sobre un comportamiento que no ocurre.

Lo que este fichero fija:

* **C2** — ``radio``/``checkbox`` agrupados por ``name`` son un conjunto cerrado,
  igual que las ``<option>`` de un ``<select>``.
* **C3** — el tope de A6, **reutilizando** ``common.enum_evidence``: por encima, la
  huella y la etiqueta de apertura como evidencia; nunca un conjunto recortado.
* **C4** — los enums falsos no anclan: un ``<select>`` de clientes es un volcado de
  producción con forma de catálogo.
* **C5** — ningún ``anchor_ref`` cambia entre corridas si no cambió la aplicación.
* Y el **límite duro**: ninguna evidencia alcanza la celda de Excel.
"""

import ast
from pathlib import Path

import pytest

from ai.agents.qa.common import CELDA_EXCEL_MAX_CHARS, ENUM_MAX_OPCIONES
from ai.agents.qa.explore import dom
from ai.agents.qa.explore.extract import (
    ANCLA_ENUM,
    MINIMO_DE_GRUPO,
    MOTIVOS_DE_DESCARTE,
    _selector_y_motivo,
    anclas_de,
    descartes_de,
    extraer,
    motivo_de_inestabilidad,
    motivo_no_es_catalogo,
    parece_identificador_opaco,
    veces_por_selector,
)

BACKEND = Path(__file__).resolve().parents[3]
MODULO = Path(__file__)


def _enums(html: str, path: str = "/x"):
    return [a for a in anclas_de(html, path) if a.attribute == ANCLA_ENUM]


def _claves(html: str, path: str = "/x") -> list[str]:
    return [d.clave for d in descartes_de(html, path)]


def _select(valores, nombre: str = "cat", extra: str = "") -> str:
    opciones = "".join(f'<option value="{v}">{v}</option>' for v in valores)
    atributos = f'name="{nombre}"' + (f" {extra}" if extra else "")
    return f"<select {atributos}>{opciones}</select>"


def _radios(valores, nombre: str = "servicio", tipo: str = "radio") -> str:
    return "".join(
        f'<input type="{tipo}" name="{nombre}" id="{nombre}-{i}" value="{v}">'
        for i, v in enumerate(valores)
    )


# --- C1: el candado de que esto es sintético ---------------------------------


def test_c1_este_fichero_no_toca_ninguna_fixture():
    """El criterio dice «tests de enum con HTML sintético, **nunca** contra
    fixtures», y una intención no se hace cumplir sola: allí hay cero enums (F2) y
    un test verde contra una lista vacía no prueba nada. Se vigila el import, que
    es por donde entraría."""
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    modulos = {
        nodo.module or ""
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom)
    } | {
        alias.name
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Import)
        for alias in nodo.names
    }
    # Por AST y no por texto: un candado que busca su propia palabra prohibida en
    # el fichero se encuentra a sí mismo dentro del ``assert`` y falla siempre. Lo
    # que se vigila es de dónde importa, que es por donde entraría una fixture.
    delatores = {m for m in modulos if "fixtures" in m}
    assert delatores == set(), f"Importa fixtures: {delatores}"
    llamadas = {
        nodo.func.id
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
    }
    assert "cargar" not in llamadas


# --- C2: radio y checkbox son un enum con otra sintaxis ----------------------


@pytest.mark.parametrize("tipo", ["radio", "checkbox"])
def test_c2_un_grupo_por_name_es_un_conjunto_cerrado(tipo):
    html = f"<form>{_radios(['EXPRESS', 'REGULAR'], tipo=tipo)}</form>"
    (enum,) = _enums(html)
    assert enum.selector == 'input[name="servicio"]'
    assert enum.selector_strategy == "name"
    assert enum.value == "EXPRESS | REGULAR"


def test_c2_el_selector_del_grupo_casa_con_TODOS_sus_miembros_a_proposito():
    """La unicidad que se exige a un ancla de atributo sería aquí justo lo
    contrario de lo que hace falta: el ``[name]`` que casa con los dos radios **es**
    el grupo. Por eso el ancla de grupo no pasa por ``selector_de_ancla``."""
    html = f"<form>{_radios(['EXPRESS', 'REGULAR'])}</form>"
    veces = veces_por_selector(dom.elementos(html))
    assert veces['input[name="servicio"]'] == 2
    (enum,) = _enums(html)
    assert enum.selector == 'input[name="servicio"]'


def test_c2_los_miembros_conservan_sus_propias_anclas():
    """El grupo añade un ancla, no sustituye a las de sus miembros: un ``required``
    en uno de los radios se sigue pudiendo romper por separado."""
    html = (
        '<form><input type="radio" name="s" id="a" value="EXPRESS" required>'
        '<input type="radio" name="s" id="b" value="REGULAR"></form>'
    )
    anclas = anclas_de(html, "/x")
    assert [(a.attribute, a.selector) for a in anclas] == [
        ("required", 'input[id="a"]'),
        (ANCLA_ENUM, 'input[name="s"]'),
    ]


def test_c2_un_control_suelto_no_declara_un_conjunto():
    """Un ``checkbox`` solo declara un sí/no, y su ancla útil es ``required``.
    «Un valor fuera del conjunto» sobre un conjunto de uno es ruido."""
    html = '<form><input type="checkbox" name="acepto" value="SI" required></form>'
    assert _enums(html) == []
    assert _claves(html) == ["grupo-de-uno"]
    assert [a.attribute for a in anclas_de(html, "/x")] == ["required"]


def test_c2_el_minimo_declarado_es_el_que_se_aplica():
    assert MINIMO_DE_GRUPO == 2
    assert _enums(f"<form>{_radios(['A'] )}</form>") == []
    assert _enums(f"<form>{_radios(['A', 'B'])}</form>")


def test_c2_un_miembro_sin_value_deja_el_conjunto_a_medias_y_no_ancla():
    """Sin ``value`` el navegador envía ``on``: el conjunto no es el que se ve, y
    un conjunto a medias produce un caso que afirma que un valor legítimo debe
    rechazarse."""
    html = (
        '<form><input type="radio" name="s" value="EXPRESS">'
        '<input type="radio" name="s"></form>'
    )
    assert _enums(html) == []
    assert "enum-sin-value" in _claves(html)


def test_c2_la_evidencia_del_grupo_es_subcadena_exacta_del_documento():
    """Las etiquetas concatenadas no son subcadena de nada, y la verificación
    verbatim contra el DOM (§2.4.3) las rechazaría."""
    html = (
        "<form><label>Express</label>"
        '<input type="radio" name="s" value="EXPRESS">'
        "<label>Regular</label>"
        '<input type="radio" name="s" value="REGULAR"></form>'
    )
    (enum,) = _enums(html)
    assert enum.evidence in html
    assert "EXPRESS" in enum.evidence and "REGULAR" in enum.evidence


def test_c2_dos_grupos_distintos_son_dos_anclas():
    html = (
        f"<form>{_radios(['EXPRESS', 'REGULAR'], nombre='servicio')}"
        f"{_radios(['SI', 'NO'], nombre='urgente')}</form>"
    )
    assert [e.selector for e in _enums(html)] == [
        'input[name="servicio"]',
        'input[name="urgente"]',
    ]


# --- C3: el tope de A6, reutilizado y no reescrito ---------------------------


def _catalogo(n: int, ancho: int = 6) -> list[str]:
    """Un catálogo con forma de maestro real: códigos numéricos uniformes."""
    return [str(150000 + i).zfill(ancho) for i in range(n)]


def test_c3_un_enum_de_dominio_viaja_entero():
    valores = ["BORRADOR", "EMITIDA", "EN_RUTA", "ENTREGADA", "ANULADA"]
    (enum,) = _enums(_select(valores))
    assert enum.value == " | ".join(valores)


def test_c3_el_ubigeo_no_mete_el_catalogo_en_ninguna_parte_y_el_ancla_SIGUE():
    """El punto 4 de A6, literal: un ``<select>`` de 1.874 opciones no mete el
    catálogo ni en el prompt ni en el artefacto, **y sí** deja el ancla en pie. El
    hueco no se abre."""
    valores = _catalogo(1874)
    html = _select(valores, nombre="ubigeo")
    (enum,) = _enums(html)

    assert enum.value.startswith("1874 valores · sha256:")
    # El catálogo no viaja: ni en el valor ni en la evidencia.
    assert valores[500] not in enum.value
    assert valores[500] not in enum.evidence
    # Y la evidencia es la ETIQUETA DE APERTURA, no el contenido (A6, criterio 2).
    assert enum.evidence == '<select name="ubigeo">'
    assert "<option" not in enum.evidence


def test_c3_justo_en_el_tope_todavia_es_el_conjunto_y_uno_mas_es_huella():
    cabe = [f"COD{i:02d}" for i in range(ENUM_MAX_OPCIONES)]
    (enum,) = _enums(_select(cabe))
    assert enum.value == " | ".join(cabe)

    no_cabe = [f"COD{i:02d}" for i in range(ENUM_MAX_OPCIONES + 1)]
    (enum,) = _enums(_select(no_cabe))
    assert enum.value.startswith(f"{len(no_cabe)} valores · sha256:")


def test_c3_la_huella_no_es_un_prefijo_del_conjunto():
    """Nunca un recorte: un enum a medias produce un caso que afirma que un valor
    legítimo debe rechazarse, y ese caso pasa la ejecución certificando una
    mentira."""
    valores = _catalogo(400)
    (enum,) = _enums(_select(valores))
    for n in range(1, 12):
        assert enum.value != " | ".join(valores[:n])
    assert f"{len(valores)} valores" in enum.value


def test_c3_el_tope_tambien_gobierna_a_un_grupo_de_radios():
    """El tope es del CONJUNTO, no del ``<select>``: las dos formas del mismo hecho
    lo comparten, o el mismo catálogo daría dos evidencias distintas."""
    (enum,) = _enums(f"<form>{_radios(_catalogo(200), nombre='ubigeo')}</form>")
    assert enum.value.startswith("200 valores · sha256:")


def test_c3_el_extractor_reutiliza_la_funcion_del_tope_y_no_la_copia():
    """Criterio 5 de A6 en su forma de candado local. El candado global —nadie más
    declara las constantes, nadie más calcula una huella— vive en
    ``test_enum_evidence.py`` y sigue verde: aquí solo se comprueba que el import
    existe, que es lo que lo mantiene verde."""
    fuente = (BACKEND / "ai/agents/qa/explore/extract.py").read_text(encoding="utf-8")
    assert "from ai.agents.qa.common import" in fuente
    assert "enum_evidence" in fuente
    assert "hashlib" not in fuente and "sha256" not in fuente


# --- el límite duro: ninguna evidencia rompe el CSV del analista -------------


def test_ninguna_evidencia_alcanza_la_celda_de_excel():
    for html in (
        _select(_catalogo(1874), nombre="ubigeo"),
        _select(["A" * 400 for _ in range(50)], nombre="largo"),
        f"<form>{_radios(_catalogo(500))}</form>",
    ):
        for ancla in anclas_de(html, "/x"):
            assert len(ancla.evidence) < CELDA_EXCEL_MAX_CHARS


def test_una_etiqueta_gigante_no_ancla_en_vez_de_anclar_con_media_cita():
    """**Fail-closed aprobado.** A6.3 dice «ningún ``evidence``», no «ningún enum»:
    una etiqueta de apertura de legado con un blob dentro puede pasarse sola. No se
    recorta —una cita recortada deja de ser una cita, y podría dejar de ser
    subcadena del documento justo por donde se cortó—: no se emite el ancla, y el
    control aparece en descartes con su motivo."""
    blob = "x" * (CELDA_EXCEL_MAX_CHARS + 10)
    html = f'<form><input name="viejo" required data-estado="{blob}"></form>'
    assert anclas_de(html, "/x") == []
    assert _claves(html) == ["evidencia-enorme"]


def test_pero_un_control_normal_del_mismo_documento_sigue_anclando():
    """El descarte es del control que no cabe, no de la página."""
    blob = "x" * (CELDA_EXCEL_MAX_CHARS + 10)
    html = (
        f'<form><input name="viejo" required data-estado="{blob}">'
        '<input name="ruc" required maxlength="11"></form>'
    )
    assert [a.selector for a in anclas_de(html, "/x")] == [
        'input[name="ruc"]',
        'input[name="ruc"]',
    ]
    assert _claves(html) == ["evidencia-enorme"]


# --- C4: los enums falsos ----------------------------------------------------

ULID = "01H5XABCDEFGHJKMNPQRSTVWXY"
UUID = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"


@pytest.mark.parametrize(
    "valores, pista",
    [
        ([ULID, "01H5XZZZZZZZZZZZZZZZZZZZZZ"], "identificador de fila"),
        ([UUID, "3f2504e0-4f89-11d3-9a0c-0305e82c3302"], "identificador de fila"),
        (["Juan Pérez García", "Ana Torres"], "forma de código"),
        (["COMERCIAL ANDINA S.A.C.", "LOGISTICA DEL SUR E.I.R.L."], "forma de código"),
        (["1", "2", "3", "4"], "secuencia sustituta"),
        (["01", "02", "03"], "secuencia sustituta"),
        ([str(i) for i in range(998, 1003)], "secuencia sustituta"),
    ],
)
def test_c4_una_lista_de_datos_no_ancla_como_conjunto_cerrado(valores, pista):
    """Un ``<select>`` de clientes, de colaboradores o de jobs es un volcado de
    producción con forma de catálogo. Anclarlo tendría dos costes a la vez: lleva
    datos reales al prompt y al PDF, y produce un caso que se pondrá rojo cada vez
    que alguien dé de alta un cliente **sin que haya cambiado la aplicación**."""
    html = _select(valores, nombre="cliente")
    assert _enums(html) == []
    assert _claves(html) == ["enum-no-es-catalogo"]
    assert pista in (motivo_no_es_catalogo(valores) or "")


@pytest.mark.parametrize(
    "valores",
    [
        ["BORRADOR", "EMITIDA", "EN_RUTA"],
        ["postgresql", "sqlserver", "oracle"],
        ["01-DNI", "02-RUC", "03-CE"],
        _catalogo(196),
        ["150101", "010101", "230201"],
    ],
)
def test_c4_un_catalogo_de_dominio_si_ancla(valores):
    """Ubigeo incluido: seis dígitos uniformes son un código, no una clave
    primaria. Es el ejemplo con el que se midió A6 y sigue en pie."""
    assert motivo_no_es_catalogo(valores) is None
    assert _enums(_select(valores))


def test_c4_un_solo_valor_malo_descarta_el_conjunto_entero():
    """**Fail-closed ante la duda.** La asimetría manda: un hueco se ve en la
    cobertura, un conjunto falso no."""
    assert motivo_no_es_catalogo(["BORRADOR", "EMITIDA", ULID]) is not None
    assert _enums(_select(["BORRADOR", "EMITIDA", ULID])) == []


def test_c4_el_select_conserva_sus_OTRAS_anclas():
    """Lo que se retira es la afirmación «este es el conjunto de lo aceptado», que
    es la que mentiría. El control se observó y sus límites siguen anclados."""
    html = _select([ULID, UUID], nombre="cliente", extra="required multiple")
    assert [a.attribute for a in anclas_de(html, "/x")] == ["required", "multiple"]


def test_c4_el_grupo_de_radios_pasa_por_el_mismo_discriminador():
    """Un grupo de radios de clientes es la misma fuga con otra sintaxis."""
    html = f"<form>{_radios([ULID, UUID], nombre='cliente')}</form>"
    assert _enums(html) == []
    assert "enum-no-es-catalogo" in _claves(html)


def test_c4_el_discriminador_no_mira_los_rotulos_y_esto_es_la_decision():
    """El texto no entra en la decisión: «La Libertad» y «Juan Pérez» son
    estructuralmente idénticos, así que cualquier regla sobre rótulos o mata las
    provincias o deja pasar los nombres. Y hay un motivo más fuerte que su
    imprecisión — leer el texto para decidir mete el texto en el camino de la
    decisión, y el texto es justo lo que no queremos que viaje."""
    con_nombres = (
        '<select name="c">'
        '<option value="C001">Juan Pérez García</option>'
        '<option value="C002">Ana Torres Quispe</option>'
        "</select>"
    )
    (enum,) = _enums(con_nombres)
    assert enum.value == "C001 | C002"
    assert "Juan" not in enum.value


def test_c4_RESIDUAL_una_pk_uniforme_de_cuatro_digitos_todavia_ancla():
    """**Residual conocido de C4, fijado como comportamiento y no como sorpresa.**

    Una lista de clientes con clave primaria entera y longitud uniforme de al menos
    cuatro dígitos (1000–9999) pasa el discriminador y ancla como si fuera un
    catálogo. El día que la tabla cruce a 10000, las longitudes dejarán de ser
    uniformes y el mismo ``<select>`` **dejará de anclar** — sin que haya cambiado
    la aplicación.

    Está escrito aquí a propósito: el residual no está mitigado, está **diferido**,
    y por eso es peor que uno que falla hoy. La regla no se refina antes de verla
    funcionar; el dueño y el plan viven en ``docs/diseno-qa-modo-c.md`` (§14.6).
    """
    uniforme = [str(n) for n in range(1000, 1010)]
    assert motivo_no_es_catalogo(uniforme) is None
    assert _enums(_select(uniforme, nombre="cliente"))

    # El mismo maestro, el día que cruza el millar siguiente:
    cruzado = uniforme + ["10000"]
    assert "secuencia sustituta" in (motivo_no_es_catalogo(cruzado) or "")
    assert _enums(_select(cruzado, nombre="cliente")) == []


@pytest.mark.parametrize(
    "valor, opaco",
    [
        (ULID, True),
        (UUID, True),
        ("a3f9c2e18b7d4f6a9c0e1b2d", True),
        ("Xk92mQvR7tLp4Zc1Nb8s", True),
        ("BORRADOR", False),
        ("150101", False),
        ("ESTADO_MUY_LARGO_PERO_LEGIBLE", False),
        ("", False),
    ],
)
def test_c4_que_cuenta_como_identificador_opaco(valor, opaco):
    """La frontera, con sus casos escritos. ``ESTADO_MUY_LARGO_PERO_LEGIBLE`` no cae
    porque le faltan minúsculas y dígitos: son las tres clases juntas las que
    distinguen un token de un código descriptivo largo."""
    assert parece_identificador_opaco(valor) is opaco


def test_c4_un_entero_no_es_opaco_por_si_solo():
    """Deliberado: los códigos de dominio reales son numéricos con frecuencia. Esa
    ambigüedad la resuelve la regla 3, no ésta."""
    assert not parece_identificador_opaco("150101")
    assert motivo_no_es_catalogo(["150101", "010101"]) is None


# --- C5: ningún ref cambia si no cambió la aplicación ------------------------


@pytest.mark.parametrize(
    "valor, pista",
    [
        ("editar-{storyId}", "plantilla"),
        ("fila-${id}", "plantilla"),
        ("{{ item.id }}", "plantilla"),
        ("row-<%= id %>", "plantilla"),
        (f"guia-{ULID}", "ULID/UUID"),
        (f"item-{UUID}", "ULID/UUID"),
        ("hash-a3f9c2e18b7d4f6a9c0e1b2d", "hexadecimal"),
        ("fila-00123456", "número"),
        ("ruc", None),
        ("guia-2024", None),
    ],
)
def test_c5_que_hace_inestable_a_un_selector(valor, pista):
    motivo = motivo_de_inestabilidad(valor)
    if pista is None:
        assert motivo is None
    else:
        assert motivo and pista in motivo


def test_c5_dos_corridas_de_la_misma_pantalla_dan_EL_MISMO_ref():
    """El test que es el criterio entero. La misma plantilla renderizada con dos
    filas distintas —el caso real: la aplicación no cambió, cambió el dato— tiene
    que producir refs idénticos, o la suite no compara nada."""

    def pagina(fila_id: str) -> str:
        return (
            f'<form><input id="editar-{fila_id}" aria-label="Editar {fila_id}" '
            'required maxlength="11"></form>'
        )

    primera = [a.ref for a in anclas_de(pagina("00123456"), "/guias")]
    segunda = [a.ref for a in anclas_de(pagina("00987654"), "/guias")]
    assert primera == segunda
    assert primera, "Y no se consigue emitiendo cero anclas: el hueco no vale."


def test_c5_el_ancla_sobrevive_por_la_ruta_estructural_y_nace_marcada():
    """Rechazar el ``id`` interpolado no abre un hueco: cae a la estrategia
    siguiente y acaba en la estructural, que es estable por construcción y
    **frágil** — y por eso nace marcada, para que ``CRITIQUE`` pueda avisarlo."""
    html = '<form><input id="fila-00123456" required></form>'
    (ancla,) = anclas_de(html, "/x")
    assert ancla.selector_strategy == "structural"
    assert ancla.fragil
    assert "00123456" not in ancla.ref


def test_c5_un_name_estable_gana_a_un_id_interpolado():
    """El orden de preferencia no cambia: lo que cambia es que un candidato
    inestable se salta. Aquí el primero ya sirve."""
    html = '<form><input name="ruc" id="fila-00123456" required></form>'
    (ancla,) = anclas_de(html, "/x")
    assert ancla.selector == 'input[name="ruc"]'
    assert not ancla.fragil


def test_c5_un_aria_label_interpolado_se_salta_y_uno_estable_no():
    inestable = '<form><input aria-label="Editar guía 00123456" required></form>'
    assert anclas_de(inestable, "/x")[0].selector_strategy == "structural"

    estable = '<form><input aria-label="Número de RUC" required></form>'
    assert anclas_de(estable, "/x")[0].selector_strategy == "aria-label"


def test_c5_un_grupo_con_name_interpolado_no_ancla_su_conjunto():
    """El grupo no tiene ruta estructural a la que caer: su selector **es** el
    ``[name]``. Así que aquí sí se prefiere el hueco."""
    html = f"<form>{_radios(['SI', 'NO'], nombre=f'respuesta-{ULID}')}</form>"
    assert _enums(html) == []
    assert "selector-inestable" in _claves(html)


# --- los descartes: cerrados, y cada clase con su caso escrito ---------------


def _elemento_duplicado() -> str:
    """El único motivo que no se alcanza desde HTML: con ``_Lector`` la ruta
    estructural es única por construcción. Se alcanza construyendo el elemento a
    mano, que es como llegarán en QC7 desde el navegador."""
    duplicado = dom.Elemento(
        tag="input", attrs={"name": "ruc"}, ruta=("input:nth-of-type(1)",)
    )
    veces = veces_por_selector([duplicado, duplicado])
    return _selector_y_motivo(duplicado, veces)[1]


#: Un caso por clase de descarte. La tabla no es decorativa: el test de abajo exige
#: que **toda** clase tenga el suyo, así que añadir un motivo obliga a escribir el
#: HTML que lo produce — misma regla que ``ATRIBUTOS_ANCLA`` y su tabla de HTML.
CASOS_DE_DESCARTE = {
    "etiqueta-no-css": lambda: _claves(
        "<div><asp:panel><input required></asp:panel></div>"
    ),
    "sin-selector-unico": lambda: [_elemento_duplicado()],
    "selector-inestable": lambda: _claves(
        f"<form>{_radios(['SI', 'NO'], nombre=f'r-{ULID}')}</form>"
    ),
    "evidencia-enorme": lambda: _claves(
        f'<input name="v" required data-x="{"x" * (CELDA_EXCEL_MAX_CHARS + 1)}">'
    ),
    "enum-sin-cierre": lambda: _claves('<select name="c"><option value="A">A'),
    "enum-sin-value": lambda: _claves('<select name="c"><option>A</option></select>'),
    "enum-vacio": lambda: _claves(
        '<select name="c"><option value=""></option></select>'
    ),
    "enum-no-es-catalogo": lambda: _claves(_select([ULID, UUID])),
    "grupo-de-uno": lambda: _claves('<input type="radio" name="s" value="A">'),
}


@pytest.mark.parametrize("clave", sorted(MOTIVOS_DE_DESCARTE))
def test_cada_clase_de_descarte_tiene_su_caso_y_se_produce(clave):
    assert clave in CASOS_DE_DESCARTE, f"«{clave}» no tiene caso escrito."
    assert clave in CASOS_DE_DESCARTE[clave]()


def test_toda_clase_de_descarte_lleva_su_explicacion():
    assert set(CASOS_DE_DESCARTE) == set(MOTIVOS_DE_DESCARTE)
    assert all(texto.strip() for texto in MOTIVOS_DE_DESCARTE.values())


def test_un_control_sin_nada_que_anclar_no_es_un_descarte():
    """Una lista de descartes llena de ruido no la mira nadie: un ``<input>`` de
    texto sin atributos de validación no dejó ningún hueco, simplemente no había
    nada que anclar."""
    assert descartes_de("<div><asp:panel><input></asp:panel></div>", "/x") == []


def test_el_descarte_dice_donde_estaba_para_poder_mirarlo():
    html = '<form>\n<select name="cliente">' + "".join(
        f'<option value="{v}">x</option>' for v in (ULID, UUID)
    )
    html += "</select></form>"
    (descarte,) = descartes_de(html, "/x")
    assert descarte.linea == 2
    assert descarte.origen == '<select name="cliente">'
    assert "catálogo de dominio" in descarte.motivo


def test_extraer_devuelve_las_dos_mitades_y_anclas_de_es_su_atajo():
    html = _select(["BORRADOR", "EMITIDA"]) + _select([ULID, UUID], nombre="cliente")
    resultado = extraer(html, "/x")
    assert resultado.anclas == anclas_de(html, "/x")
    assert resultado.descartes == descartes_de(html, "/x")
    assert len(resultado.anclas) == 1 and len(resultado.descartes) == 1


def test_los_descartes_tambien_son_deterministas():
    html = _select([ULID, UUID], nombre="cliente")
    assert descartes_de(html, "/x") == descartes_de(html, "/x")


def test_el_motivo_de_un_descarte_no_cita_NINGUN_valor():
    """Un motivo viaja al artefacto, al CSV y al PDF exactamente igual que una
    evidencia. Citar un nombre de cliente para explicar por qué no se citan los
    nombres de los clientes sería la misma fuga entrando por la puerta de atrás —
    y con un valor basta: el descarte se emite una vez por control, pero una
    pantalla tiene muchos controles.

    El motivo describe la **regla** que falló. Quién es el infractor se ve abriendo
    la página; qué regla falló, no."""
    valores = [f"Cliente Numero {i:04d} S.A.C." for i in range(200)]
    (descarte,) = descartes_de(_select(valores, nombre="cliente"), "/x")
    assert len(descarte.motivo) < 300
    assert not [v for v in valores if v in descarte.motivo]
    assert "Cliente" not in descarte.motivo
    # Y el nombre del control sí, porque es lo que permite ir a mirarlo.
    assert descarte.origen == '<select name="cliente">'


@pytest.mark.parametrize(
    "valores, regla",
    [
        ([ULID, UUID], "identificador de fila"),
        (["Juan Pérez", "Ana Torres"], "sin forma de código"),
        (["1", "2", "3"], "secuencia sustituta"),
    ],
)
def test_el_descarte_dice_QUE_REGLA_fallo_y_no_solo_que_fallo(valores, regla):
    """Condición del criterio C4: la regla 3 —la del residual diferido— tiene que
    poder mirarse. Un descarte que solo dice «no es un catálogo» deja al lector con
    la misma duda con la que llegó, y es la regla 3 la que más falta hace ver:
    es la que un día dejará de dispararse sola."""
    (descarte,) = descartes_de(_select(valores, nombre="c"), "/x")
    assert descarte.clave == "enum-no-es-catalogo"
    assert regla in descarte.motivo
