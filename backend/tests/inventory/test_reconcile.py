"""Fase RECONCILE: clasificación contra el inventario (INV4).

Aquí se calibran los umbrales, igual que el Jaccard del deduplicador del Scrum.
Los tests son la calibración: si alguien mueve un umbral, dicen qué se rompe.

La regla que gobierna el diseño y que estos tests vigilan: **entre "claramente lo
mismo" y "claramente distinto" no se adivina, se pregunta**. Un `new` equivocado
propone crear una tabla que lleva años en producción; un `reuse` equivocado apunta
el diseño nuevo contra una tabla que no es la que cree. Ambos son peores que una
pregunta.
"""

import pytest

from ai.inventory.matching import (
    NAME_DOUBT_THRESHOLD,
    NAME_MATCH_THRESHOLD,
    canonical_name,
    column_overlap,
    name_similarity,
    normalize_name,
    singularize,
)
from ai.inventory.nodes import conflict_questions
from ai.inventory.reconcile import (
    ReconciliationStatus,
    classify,
    flatten_db_schema,
    flatten_endpoints,
    summarize,
)


def tabla(nombre: str, *columnas: str) -> dict:
    return {
        "name": nombre,
        "columns": [{"name": c} for c in columnas],
    }


def inventario(*tablas: dict) -> list[dict]:
    return flatten_db_schema(
        [
            {
                "id": "asset-1",
                "name": "core",
                "system_id": "sys-1",
                "system_name": "TMS Moderno",
                "content": {"tables": list(tablas)},
            }
        ]
    )


# --- normalización -----------------------------------------------------------


@pytest.mark.parametrize(
    "plural,singular",
    [
        ("usuarios", "usuario"),
        ("envios", "envio"),
        ("clientes", "cliente"),  # NO "client"
        ("camiones", "camion"),
        ("direcciones", "direccion"),
        ("tarifas", "tarifa"),
        ("ubigeos", "ubigeo"),
        ("matrices", "matriz"),
        ("sedes", "sede"),
    ],
)
def test_singulariza_nombres_de_tabla(plural: str, singular: str):
    """El plural en «-es» solo se forma sobre consonante final válida.

    Quitar siempre «es» convertía `clientes` en `client`, y entonces `Cliente` y
    `clientes` NO se emparejaban: el diseño habría propuesto crear una tabla de
    clientes que ya existe.
    """
    assert singularize(plural) == singular


def test_normaliza_acentos_afijos_y_separadores():
    assert normalize_name("Envío") == "envio"
    assert normalize_name("tbl_Usuarios") == "usuario"
    assert normalize_name("motivos_devolucion") == "motivo devolucion"
    assert normalize_name("MotivoDevolucion") == "motivodevolucion"


def test_los_sinonimos_del_dominio_son_explicitos():
    """Lista corta y a mano: cada entrada es una decisión, no una inferencia."""
    assert canonical_name("Trabajador") == "usuario"
    assert canonical_name("Colaborador") == "usuario"
    assert canonical_name("Shipper") == "cliente"
    # Lo que NO está en la lista no se fuerza: se parecerá o no por léxico.
    assert canonical_name("Factura") == "factura"


# --- EL caso obligatorio -----------------------------------------------------


def test_trabajador_del_ef_contra_la_tabla_usuarios_JAMAS_es_new():
    """CASO OBLIGATORIO (INV4).

    Una entidad "Trabajador" del EF frente a la tabla maestra `usuarios` del
    esquema compartido tiene que salir `reuse` o `extend`. Que saliera `new` es
    exactamente el fallo que este módulo existe para impedir: propondría crear una
    tabla de personas que la organización lleva años manteniendo.
    """
    existente = inventario(
        tabla("usuarios", "usuario_id", "nombre", "email", "activo", "creado_en")
    )

    propuesta = tabla("Trabajador", "nombre", "email")
    veredicto = classify(
        propuesta["name"],
        existente,
        columnas_propuestas=[c["name"] for c in propuesta["columns"]],
    )

    assert veredicto.status is not ReconciliationStatus.NEW
    assert veredicto.status in (
        ReconciliationStatus.REUSE,
        ReconciliationStatus.EXTEND,
    )
    assert veredicto.candidate is not None
    assert veredicto.candidate.name == "usuarios"
    assert veredicto.candidate.system_name == "TMS Moderno"


def test_trabajador_con_columnas_nuevas_sale_extend_con_lo_que_falta():
    """El Agente BD necesita saber QUÉ falta para emitir el ALTER exacto."""
    existente = inventario(tabla("usuarios", "usuario_id", "nombre", "email"))
    veredicto = classify(
        "Trabajador",
        existente,
        columnas_propuestas=["nombre", "email", "codigo_planilla"],
    )
    assert veredicto.status is ReconciliationStatus.EXTEND
    assert veredicto.missing == ["codigo_planilla"]
    assert not veredicto.blocking


def test_usuario_que_ya_tiene_todo_sale_reuse_sin_cambios():
    existente = inventario(tabla("usuarios", "usuario_id", "nombre", "email"))
    veredicto = classify("Usuario", existente, columnas_propuestas=["nombre", "email"])
    assert veredicto.status is ReconciliationStatus.REUSE
    assert not veredicto.blocking


# --- las cuatro clasificaciones ----------------------------------------------


def test_lo_que_no_existe_es_new():
    existente = inventario(tabla("usuarios", "usuario_id", "nombre"))
    veredicto = classify(
        "Siniestro", existente, columnas_propuestas=["siniestro_id", "descripcion"]
    )
    assert veredicto.status is ReconciliationStatus.NEW
    assert veredicto.candidate is None
    assert not veredicto.blocking


def test_un_parecido_dudoso_pregunta_en_vez_de_adivinar():
    """La banda de duda: ni se reutiliza ni se crea. Se pregunta.

    Es la decisión de diseño central del bloque. Cualquiera de las dos respuestas
    automáticas sería un error caro; una pregunta no lo es.
    """
    existente = inventario(tabla("comprobantes", "comprobante_id", "monto"))
    veredicto = classify("comprobante_pago", existente, columnas_propuestas=["monto"])
    assert veredicto.status is ReconciliationStatus.CONFLICT
    assert veredicto.blocking is True
    assert 0.55 <= veredicto.candidate.name_score < NAME_MATCH_THRESHOLD


def test_mismo_nombre_pero_estructura_incompatible_es_conflict():
    """Dos cosas distintas llamadas igual: el escenario más peligroso.

    Un `reuse` automático aquí apuntaría el diseño nuevo contra una tabla que NO
    es la que cree.
    """
    existente = inventario(
        tabla("movimientos", "movimiento_id", "almacen_id", "cantidad", "lote")
    )
    veredicto = classify(
        "Movimiento",
        existente,
        columnas_propuestas=["fecha_asiento", "debe", "haber", "cuenta_contable"],
    )
    assert veredicto.status is ReconciliationStatus.CONFLICT
    assert veredicto.blocking is True
    assert "estructura" in veredicto.reason.lower()


def test_sin_columnas_que_comparar_basta_el_nombre():
    """Componentes y endpoints no tienen columnas: se decide por nombre."""
    existente = inventario(tabla("usuarios", "usuario_id"))
    veredicto = classify("Usuario", existente)
    assert veredicto.status is ReconciliationStatus.REUSE


# --- umbrales ----------------------------------------------------------------


def test_anadir_una_columna_a_una_tabla_existente_es_extend_no_conflicto():
    """CALIBRACIÓN: el caso más normal de todos no puede salir conflicto.

    Propuesta de 2 columnas de las que 1 ya existe = 50% de solapamiento, por
    debajo del umbral estructural. Exigir el umbral entero aquí convertía en
    "conflicto" a una tabla a la que simplemente se le añade un campo — y llenaba
    el diseño de preguntas bloqueantes inútiles.

    La regla: con el nombre canónicamente IDÉNTICO, el nombre ya es evidencia
    fuerte y basta con que algo coincida. Con el nombre solo parecido se exige el
    umbral completo.
    """
    existente = inventario(tabla("usuarios", "usuario_id", "nombre"))
    veredicto = classify("Trabajador", existente, columnas_propuestas=["nombre", "dni"])
    assert veredicto.status is ReconciliationStatus.EXTEND
    assert veredicto.missing == ["dni"]
    assert not veredicto.blocking


def test_nombre_identico_pero_CERO_estructura_comun_sigue_siendo_conflicto():
    """La relajación anterior no puede tragarse la salvaguarda.

    Si no coincide NI UNA columna, dos cosas que se llaman igual siguen siendo
    sospechosas por mucho que el nombre coincida.
    """
    existente = inventario(tabla("movimientos", "almacen_id", "cantidad"))
    veredicto = classify("Movimiento", existente, columnas_propuestas=["debe", "haber"])
    assert veredicto.status is ReconciliationStatus.CONFLICT
    assert veredicto.blocking is True


def test_sede_y_sedes_se_emparejan():
    """CALIBRACIÓN del singular: «-des» resuelve a «-de» en este dominio.

    `sedes`→`sed` (por tratar la «d» como final válida) impedía emparejar la
    entidad `Sede` con su tabla `sedes`.
    """
    existente = inventario(tabla("sedes", "sede_id", "nombre"))
    veredicto = classify("Sede", existente, columnas_propuestas=["nombre"])
    assert veredicto.status is ReconciliationStatus.REUSE


def test_los_umbrales_estan_ordenados_y_dejan_banda_de_duda():
    """Sin banda intermedia no habría preguntas: todo sería reuse o new."""
    assert 0 < NAME_DOUBT_THRESHOLD < NAME_MATCH_THRESHOLD < 1.0


def test_el_solapamiento_se_mide_sobre_lo_propuesto():
    """Una tabla de 40 columnas de la que se necesitan 5 sigue siendo reutilizable.

    Medir sobre la unión penalizaría a las tablas grandes de producción, que son
    justo las que más conviene reutilizar.
    """
    assert (
        column_overlap(["nombre", "email"], ["a", "b", "c", "nombre", "email"]) == 1.0
    )
    assert column_overlap(["nombre", "nuevo"], ["nombre"]) == 0.5
    assert column_overlap([], ["nombre"]) == 0.0


def test_el_solapamiento_normaliza_los_nombres_de_columna():
    assert column_overlap(["Envío"], ["envios"]) == 1.0


# --- aplanado ----------------------------------------------------------------


def test_el_aplanado_arrastra_la_procedencia():
    """Un veredicto que no se puede comprobar no es revisable."""
    plano = inventario(tabla("usuarios", "usuario_id"))
    assert plano[0]["asset_id"] == "asset-1"
    assert plano[0]["system_name"] == "TMS Moderno"
    assert plano[0]["columns"] == ["usuario_id"]


def test_el_endpoint_se_compara_por_metodo_y_ruta():
    """Misma ruta con distinto verbo son operaciones distintas."""
    plano = flatten_endpoints(
        [
            {
                "id": "a1",
                "name": "api",
                "system_id": "s1",
                "system_name": "TMS",
                "content": {
                    "endpoints": [
                        {"method": "get", "path": "/api/v1/envios"},
                        {"method": "post", "path": "/api/v1/envios"},
                    ]
                },
            }
        ]
    )
    assert {e["name"] for e in plano} == {"GET /api/v1/envios", "POST /api/v1/envios"}


# --- resumen y preguntas -----------------------------------------------------


def test_el_resumen_cuenta_por_estado_y_marca_lo_bloqueante():
    existente = inventario(
        tabla("usuarios", "usuario_id", "nombre"),
        tabla("comprobantes", "comprobante_id"),
    )
    veredictos = [
        classify("Usuario", existente, columnas_propuestas=["nombre"]),
        classify("Siniestro", existente, columnas_propuestas=["x"]),
        classify("comprobante_pago", existente, columnas_propuestas=["y"]),
    ]
    resumen = summarize(veredictos)
    assert resumen["counts"]["reuse"] == 1
    assert resumen["counts"]["new"] == 1
    assert resumen["counts"]["conflict"] == 1
    assert resumen["blocking"] == 1
    assert resumen["total"] == 3


def test_cada_conflicto_produce_UNA_pregunta_bloqueante():
    existente = inventario(tabla("comprobantes", "comprobante_id"))
    elementos = [{"id": "TBL-001", "name": "comprobante_pago"}]
    veredictos = {
        "TBL-001": classify(
            "comprobante_pago", existente, columnas_propuestas=["monto"]
        ).as_dict()
    }
    preguntas = conflict_questions(
        veredictos, elementos, audience="tecnico", prefijo="QR"
    )
    assert len(preguntas) == 1
    assert preguntas[0]["blocking"] is True
    assert preguntas[0]["linked_to_ref"] == "TBL-001"
    assert "comprobante_pago" in preguntas[0]["text"]
    assert "comprobantes" in preguntas[0]["text"]


def test_lo_que_no_es_conflicto_no_genera_pregunta():
    existente = inventario(tabla("usuarios", "usuario_id", "nombre"))
    elementos = [{"id": "TBL-001", "name": "Usuario"}]
    veredictos = {
        "TBL-001": classify(
            "Usuario", existente, columnas_propuestas=["nombre"]
        ).as_dict()
    }
    assert (
        conflict_questions(veredictos, elementos, audience="tecnico", prefijo="QR")
        == []
    )


# --- contrato ----------------------------------------------------------------


def test_el_veredicto_encaja_en_el_contrato_del_artefacto():
    """Lo que produce RECONCILE tiene que poder guardarse en el artefacto."""
    from ai.inventory.contract import ReconciliationRef, ReconciliationSummary

    existente = inventario(tabla("usuarios", "usuario_id", "nombre"))
    veredicto = classify("Trabajador", existente, columnas_propuestas=["nombre", "dni"])
    ref = ReconciliationRef.model_validate(veredicto.as_dict())
    assert ref.status == "extend"
    assert ref.matched.name == "usuarios"
    assert ref.missing == ["dni"]

    resumen = summarize([veredicto])
    resumen.update({"performed": True, "system_id": "s1", "system_name": "TMS"})
    assert ReconciliationSummary.model_validate(resumen).reconciled == 1


def test_los_campos_de_reconciliacion_son_opcionales():
    """Retrocompatibilidad: un artefacto anterior a INV4 sigue validando."""
    from ai.inventory.contract import ReconciliationSummary

    vacio = ReconciliationSummary()
    assert vacio.performed is False
    assert vacio.system_id is None
