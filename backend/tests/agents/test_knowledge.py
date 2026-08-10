"""Tests del conocimiento inyectable: glosario (EF), stack de la casa (A0),
convenciones de base de datos (BD0) y convenciones de API (API0)."""

import re

import pytest

from ai.knowledge import (
    DB_ENGINES,
    api_conventions_block,
    api_error,
    api_error_catalog,
    constraint_error_id,
    db_conventions_block,
    default_schema,
    engine_type_map,
    exposure_for,
    glossary_block,
    house_architecture_style,
    identity_clause,
    load_api_conventions,
    load_db_conventions,
    load_glossary,
    load_tech_stack,
    max_identifier_length,
    openapi_type,
    security_scheme_for,
    success_status,
    tech_stack_block,
    tech_stack_sources,
    type_synonyms,
)


def test_glossary_sigue_disponible():
    """El glosario logístico no se rompe al generalizar el loader."""
    terms = load_glossary()
    assert "checkpoint" in terms
    assert "GLOSARIO LOGÍSTICO" in glossary_block()


# --- Glosario ampliado (INV0) ------------------------------------------------


def test_glosario_cubre_los_terminos_del_programa_de_modernizacion():
    """INV0: los términos operativos del TMS entran al glosario de TODOS los agentes.

    Sin ellos, `EXTRACT` lee "recaudo" o "manifiesto" como palabras corrientes y
    el EF sale con entidades mal interpretadas. El glosario es la única defensa.
    """
    terms = load_glossary()
    for termino in (
        "courier",
        "Punto Urbano",
        "DWS",
        "admisión",
        "cross-docking",
        "recaudo",
        "leadtime",
        "handheld",
        "logística inversa",
        "guía electrónica",
        "manifiesto",
    ):
        assert termino in terms, f"falta el término «{termino}»"
        assert terms[termino].strip(), f"«{termino}» está sin definir"
    # Los ocho términos originales de CLAUDE.md §8 siguen intactos.
    for termino in ("checkpoint", "guía", "shipper", "siniestro", "papeleta", "DEO"):
        assert termino in terms


def test_recaudo_y_recupero_no_se_confunden():
    """Son dos cosas distintas y se parecen: el glosario debe separarlas.

    `recupero` es recuperación económica interna; `recaudo` es cobro al
    destinatario contra entrega. Un agente que los mezcle produce reglas de
    negocio equivocadas sobre el dinero.
    """
    terms = load_glossary()
    assert terms["recaudo"] != terms["recupero"]
    assert "recupero" in terms["recaudo"], "el glosario no advierte la confusión"


def test_todo_termino_del_glosario_llega_al_bloque_del_prompt():
    """Un término definido pero no renderizado es un término que no existe."""
    block = glossary_block()
    for termino in load_glossary():
        assert f"- {termino}:" in block


def test_tech_stack_carga_y_marca_pendiente_de_validacion():
    data = load_tech_stack()
    # Nace explícitamente pendiente de validación por el equipo de Urbano.
    assert data.get("status") == "pendiente_de_validacion"
    assert data.get("version") == 0
    layers = data.get("layers", {})
    # Capas críticas presentes con default + allow-list.
    for layer in ("language_backend", "database_relational", "auth"):
        assert layer in layers
        assert layers[layer].get("default")
        assert isinstance(layers[layer].get("allowed"), list)
        assert layers[layer]["allowed"]


def test_el_motor_relacional_esta_validado_y_es_postgresql_16():
    """Capa confirmada por el equipo de Urbano: PostgreSQL 16.

    Es la única validada por ahora, así que el `status` GLOBAL sigue pendiente: el
    archivo no puede dar por buenas las demás capas (lenguaje, framework, nube)
    solo porque el motor ya esté decidido.
    """
    layer = load_tech_stack()["layers"]["database_relational"]
    assert layer["validated"] is True
    assert layer["default"] == "PostgreSQL"
    assert layer["default_version"] == "16"
    # Los otros motores siguen en la lista blanca (integraciones con legados).
    assert set(layer["allowed"]) == {"PostgreSQL", "SQL Server", "Oracle", "MySQL"}
    assert load_tech_stack()["status"] == "pendiente_de_validacion"


# --- Stack real del programa de modernización (INV0) -------------------------


def test_aurora_serverless_no_contamina_el_allow_list_de_dialectos():
    """INV0: Aurora es un DESPLIEGUE de PostgreSQL, no un dialecto más.

    Es el candado del bloque. `allowed` de `database_relational` es el contrato de
    dialectos del Agente BD: `DB_ENGINES` debe coincidir con él y `engine_type_map`
    traduce cada `logical_type` motor a motor. Si alguien añadiera "Aurora" a esa
    lista, el mapa de tipos se quedaría sin traducción y el DDL sería
    irrenderizable. El dato de Aurora vive en claves propias.
    """
    layer = load_tech_stack()["layers"]["database_relational"]
    assert layer["dialect"] == "postgresql"
    assert "Aurora" in layer["managed_service"]
    assert layer["deployment"] == "aws_aurora_serverless_v2"
    # El allow-list sigue siendo EXACTAMENTE el de los dialectos soportados.
    normalizados = {p.lower().replace(" ", "") for p in layer["allowed"]}
    assert normalizados == set(DB_ENGINES)
    assert not any("aurora" in p.lower() for p in layer["allowed"])


def test_las_capas_confirmadas_por_el_documento_estan_validadas():
    """Las capas que el documento de modernización fija dejan de ser borrador."""
    layers = load_tech_stack()["layers"]
    esperado = {
        "framework_frontend": "React",
        "language_frontend": "TypeScript",
        "styling_frontend": "Tailwind CSS",
        "mobile_android": "Kotlin + Jetpack Compose",
        "mobile_multiplatform": "Flutter",
        "reporting_async": "Python",
        "cloud": "AWS",
        "database_relational": "PostgreSQL",
    }
    for capa, tecnologia in esperado.items():
        assert capa in layers, f"falta la capa {capa}"
        assert layers[capa]["validated"] is True, f"{capa} no está validada"
        assert layers[capa]["default"] == tecnologia
    assert layers["framework_frontend"]["default_version"] == "19"


def test_toda_capa_validada_cita_su_fuente():
    """Una capa validada SIN documento que la respalde es una afirmación desnuda.

    El archivo entero existe para que el agente no invente tecnologías; validar una
    capa "porque sí" reintroduciría por la puerta de atrás justo eso.
    """
    data = load_tech_stack()
    fuentes = tech_stack_sources()
    assert fuentes, "el archivo no declara ninguna fuente"
    for capa, cfg in data["layers"].items():
        if not (cfg or {}).get("validated"):
            continue
        origen = cfg.get("source")
        assert origen, f"la capa validada «{capa}» no cita fuente"
        assert origen in fuentes, f"«{capa}» cita una fuente inexistente: {origen}"
        assert fuentes[origen].get("ref"), f"la fuente «{origen}» no tiene ref"


def test_el_lenguaje_de_backend_sigue_SIN_validar():
    """CANDADO: Python para reportes NO autoriza a asumir Python como backend.

    El documento de modernización fija Python solo para la reportería asíncrona.
    Dar por validada `language_backend` a partir de ese dato sería exactamente la
    inferencia sin evidencia que el ISDF prohíbe. Este test impide que se cuele.
    """
    layers = load_tech_stack()["layers"]
    assert not layers["language_backend"].get("validated"), (
        "language_backend se marcó validada: el documento no fija el lenguaje de "
        "los microservicios, solo Python para reportería asíncrona."
    )
    # Y la capa que SÍ está validada acota su alcance a la reportería.
    assert layers["reporting_async"]["validated"] is True
    assert layers["reporting_async"]["default"] == "Python"


def test_el_estilo_arquitectonico_vive_fuera_de_layers():
    """No es una entrada del `stack[]`: el agente ya lo decide vía ADR-001.

    Bajo `layers` habría DOS fuentes de verdad para la misma decisión, y el nodo
    STACK podría afirmar un estilo esquivando el flujo del ADR.
    """
    data = load_tech_stack()
    assert "architecture_style" not in data["layers"]
    casa = house_architecture_style()
    assert casa["style_default"] == "microservices"
    assert casa["validated"] is True
    assert casa["source"] in tech_stack_sources()


def test_el_estilo_de_la_casa_usa_los_valores_del_enum_de_arquitectura():
    """Un estilo que el enum no conozca sería incomparable con el artefacto."""
    from ai.agents.arquitectura.schemas.enums import ArchitectureStyle

    validos = {e.value for e in ArchitectureStyle}
    casa = house_architecture_style()
    assert casa["style_default"] in validos
    assert set(casa["style_allowed"]) <= validos


def test_el_bloque_del_prompt_marca_lo_validado_y_no_filtra_el_estilo():
    """El agente debe distinguir "por defecto" de "confirmado por el equipo"."""
    block = tech_stack_block()
    assert "VALIDADA por el equipo" in block
    assert "Aurora" in block  # el servicio gestionado viaja con el motor
    # El estilo arquitectónico NO se ofrece como capa rellenable.
    assert "architecture_style" not in block
    assert "microservices" not in block


def test_tech_stack_block_es_allow_list_para_el_prompt():
    block = tech_stack_block()
    # Debe comunicar que es una allow-list y arrastrar el estado.
    assert "allow-list" in block
    assert "pendiente_de_validacion" in block
    # Incluye al menos una capa con su default renderizado.
    assert "language_backend" in block
    assert "por defecto" in block


# --- Convenciones de base de datos (BD0) ------------------------------------


def test_db_conventions_carga_y_marca_pendiente_de_validacion():
    """Nace explícitamente pendiente de validación, igual que el tech stack."""
    data = load_db_conventions()
    assert data.get("status") == "pendiente_de_validacion"
    assert data.get("version") == 0
    for bloque in ("naming", "keys", "audit", "catalogs", "defaults", "types"):
        assert data.get(bloque), f"falta el bloque {bloque}"


def test_los_motores_del_mapa_de_tipos_son_los_del_tech_stack():
    """El mapa de tipos cubre exactamente los motores del allow-list de A5.

    Si alguien añade un motor a `tech_stack.yaml` sin extender el mapa de tipos,
    el renderizador de DDL no sabría traducir y este test lo delata.
    """
    permitidos = load_tech_stack()["layers"]["database_relational"]["allowed"]
    # El allow-list usa nombres de producto ("SQL Server"); el mapa, claves.
    normalizados = {p.lower().replace(" ", "") for p in permitidos}
    esperados = {"sqlserver", "oracle", "postgresql", "mysql"}
    assert normalizados == esperados
    assert set(DB_ENGINES) == esperados


@pytest.mark.parametrize("engine", DB_ENGINES)
def test_todo_logical_type_se_traduce_en_todos_los_motores(engine: str):
    """Ningún `logical_type` puede quedarse sin tipo físico en un motor.

    Es la invariante que sostiene el diseño DB2 (el LLM elige un tipo lógico y
    Python lo traduce): un hueco aquí sería un DDL imposible de generar.
    """
    logicos = set(load_db_conventions()["types"].keys())
    mapa = engine_type_map(engine)
    assert set(mapa) == logicos
    assert all(valor for valor in mapa.values())


@pytest.mark.parametrize("engine", DB_ENGINES)
def test_cada_motor_tiene_identidad_y_limite_de_identificador(engine: str):
    """Datos que el renderizador necesita SIEMPRE (PK autoincremental, truncado)."""
    assert identity_clause(engine)
    assert max_identifier_length(engine) >= 30


def test_esquema_por_defecto_solo_donde_aplica():
    """Postgres/SQL Server tienen esquema; Oracle y MySQL no lo prefijan."""
    assert default_schema("postgresql") == "public"
    assert default_schema("sqlserver") == "dbo"
    assert default_schema("oracle") == ""
    assert default_schema("mysql") == ""


def test_placeholders_de_tipo_solo_usan_claves_conocidas():
    """Los tipos parametrizados solo admiten {length}/{precision}/{scale}."""
    permitidos = {"length", "precision", "scale"}
    for logical, per_engine in load_db_conventions()["types"].items():
        for engine, plantilla in per_engine.items():
            usados = set(re.findall(r"\{(\w+)\}", plantilla))
            assert usados <= permitidos, f"{logical}/{engine} usa {usados - permitidos}"


def test_sinonimos_de_tipo_apuntan_a_logical_types_reales():
    """Un sinónimo que apunte a un tipo inexistente rompería MODEL_MAP."""
    logicos = set(load_db_conventions()["types"].keys())
    assert set(type_synonyms()) <= logicos
    # Y los términos del EF que sí sabemos que aparecen están cubiertos.
    todos = {palabra for palabras in type_synonyms().values() for palabra in palabras}
    for termino in ("texto", "fecha", "monto", "booleano", "entero"):
        assert termino in todos


def test_db_conventions_block_no_filtra_tipos_sql_al_prompt():
    """El prompt recibe tipos LÓGICOS; jamás sintaxis SQL de un motor.

    Es la salvaguarda de DB2: si el bloque inyectara `NVARCHAR(MAX)`, el modelo
    podría copiarlo y colar sintaxis de SQL Server en un script de Postgres.
    """
    block = db_conventions_block("postgresql")
    assert "postgresql" in block
    assert "TIPOS LÓGICOS ADMITIDOS" in block
    assert "string" in block and "timestamp" in block
    for sintaxis in ("NVARCHAR", "VARCHAR2", "JSONB", "IDENTITY(1,1)", "BYTEA"):
        assert sintaxis not in block
    # Comunica la regla dura de no adivinar tipos.
    assert "PROHIBIDO adivinar" in block


# --- Convenciones de API (API0) ---------------------------------------------


def test_api_conventions_carga_y_marca_pendiente_de_validacion():
    """Nace pendiente de validación, igual que el tech stack y las de BD."""
    data = load_api_conventions()
    assert data.get("status") == "pendiente_de_validacion"
    assert data.get("version") == 0
    for bloque in (
        "paths",
        "properties",
        "types",
        "envelope",
        "pagination",
        "errors",
        "security",
        "exposure",
    ):
        assert data.get(bloque), f"falta el bloque {bloque}"


def test_las_decisiones_acordadas_estan_fijadas():
    """API6/API7/API8/API10/API11: lo acordado con el equipo, no es "REVISAR".

    Si alguien cambia una de estas cuatro sin pasar por el equipo, el contrato de
    todas las APIs generadas cambia de forma silenciosa. Este test es el candado.
    """
    data = load_api_conventions()
    assert data["paths"]["language"] == "es"  # API6: dominio en español
    assert data["paths"]["prefix"] == "/api/v1"
    assert data["paths"]["update_verb"] == "PATCH"  # API11
    assert data["properties"]["case"] == "snake_case"  # API7
    assert data["envelope"]["style"] == "api_response"  # API8
    assert data["pagination"]["style"] == "offset"  # API10
    # Los parámetros de protocolo van en inglés aunque el dominio sea español.
    assert data["pagination"]["limit_param"] == "limit"
    assert data["pagination"]["offset_param"] == "offset"
    assert data["sorting"]["param"] == "sort"


def test_todo_logical_type_del_agente_bd_tiene_tipo_openapi():
    """Invariante gemela de la del BD: el tipo del modelo de datos es el que viaja.

    El Agente API no vuelve a decidir tipos —los hereda de las columnas—, así que
    un `logical_type` sin traducción aquí sería un esquema imposible de renderizar.
    """
    from ai.agents.bd.schemas.enums import LogicalType

    for logical in LogicalType:
        mapeo = openapi_type(logical.value)
        assert mapeo, f"{logical.value} no tiene tipo OpenAPI"
        assert mapeo.get("type"), f"{logical.value} sin `type`"


def test_los_decimales_viajan_como_cadena():
    """Un importe en float de JavaScript pierde precisión: viaja como string."""
    assert openapi_type("decimal") == {"type": "string", "format": "decimal"}
    # Y los enteros grandes se distinguen de los normales (int64 vs int32).
    assert openapi_type("bigint")["format"] == "int64"
    assert openapi_type("integer")["format"] == "int32"


def test_binary_usa_content_encoding_no_format_binary():
    """OpenAPI 3.1 es JSON Schema 2020-12: `format: binary` ya no existe ahí.

    Es el error más fácil de cometer al portar un documento de 3.0 a 3.1, y lo
    fija el mapa para que el renderizador no pueda equivocarse.
    """
    assert openapi_type("binary") == {"type": "string", "contentEncoding": "base64"}


def test_catalogo_de_errores_completo_y_con_codigos_estables():
    catalogo = api_error_catalog()
    estados = {e["status"] for e in catalogo}
    assert {400, 401, 403, 404, 409, 422, 500} <= estados
    for entrada in catalogo:
        assert entrada["id"] and entrada["code"] and entrada["message"]
        assert entrada["when"], f"{entrada['id']} no dice cuándo se usa"
    # Ids únicos: los referencia cada endpoint en `status_codes`.
    ids = [e["id"] for e in catalogo]
    assert len(ids) == len(set(ids))
    assert api_error("ERR-409")["code"] == "recurso_duplicado"
    assert api_error("ERR-INEXISTENTE") == {}


def test_las_constraints_del_modelo_deciden_el_codigo_de_estado():
    """Los códigos NO los elige el LLM: salen de la constraint que se viola."""
    assert constraint_error_id("unique") == "ERR-409"
    assert constraint_error_id("check") == "ERR-422"
    assert constraint_error_id("not_null") == "ERR-422"
    assert constraint_error_id("foreign_key") == "ERR-404"
    # Una constraint desconocida cae en validación fallida, nunca en 500.
    assert constraint_error_id("lo_que_sea") == "ERR-422"


def test_semantica_http_de_los_codigos_de_exito():
    assert success_status("create") == 201
    assert success_status("delete") == 204
    assert success_status("list") == 200
    assert success_status("read_item") == 200


def test_el_proveedor_de_auth_del_stack_decide_el_esquema_de_seguridad():
    """La capa `auth` de tech_stack.yaml aterriza en un esquema del documento."""
    permitidos = load_tech_stack()["layers"]["auth"]["allowed"]
    esquemas = load_api_conventions()["security"]["schemes"]
    for proveedor in permitidos:
        # Todo proveedor del allow-list tiene traducción, y apunta a un esquema real.
        assert security_scheme_for(proveedor) in esquemas
    # Un proveedor desconocido cae al default (y quien llama decide si preguntar).
    assert security_scheme_for("Algo Exótico") == "bearer_jwt"
    assert security_scheme_for("") == "bearer_jwt"


def test_toda_exposicion_distinta_de_crud_lleva_motivo():
    """API12: una tabla que no se publica dice por qué. Nunca es omisión muda."""
    from ai.agents.bd.schemas.enums import TableKind

    assert exposure_for(TableKind.ENTITY.value) == ("crud", "")
    for kind in (TableKind.CATALOG, TableKind.JUNCTION, TableKind.AUDIT):
        exposicion, motivo = exposure_for(kind.value)
        assert exposicion != "crud"
        assert motivo, f"{kind.value} se excluye sin motivo escrito"


def test_api_conventions_block_no_filtra_sintaxis_del_documento_al_prompt():
    """El prompt recibe REGLAS; jamás la forma del documento OpenAPI.

    Salvaguarda gemela de la del BD (donde el bloque nunca muestra SQL): si el
    bloque enseñara `$ref`, `components` o un tipo de JSON Schema, el modelo podría
    intentar escribir el documento en vez de decidir la semántica.
    """
    block = api_conventions_block()
    for sintaxis in (
        "openapi:",
        "$ref",
        "components",
        "contentEncoding",
        "application/json",
        "int64",
        "date-time",
        "securitySchemes",
    ):
        assert sintaxis not in block, f"el bloque filtra «{sintaxis}» al prompt"
    # Comunica lo que sí debe respetar el modelo.
    assert "pendiente_de_validacion" in block
    assert "/api/v1" in block and "snake_case" in block and "PATCH" in block
    assert "limit" in block and "sort" in block
    # Y las dos reglas duras del agente.
    assert "PROHIBIDO escribir YAML" in block
    assert "PROHIBIDO inventar" in block
