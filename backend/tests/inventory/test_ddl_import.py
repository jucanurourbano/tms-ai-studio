"""Lectura de dumps DDL hacia el inventario (INV2), sin LLM.

El riesgo que estos tests vigilan no es "parsear mal": es **parsear de menos sin
avisar**. ``sqlglot`` degrada a un nodo ``Command`` toda sentencia que no entiende,
sin lanzar excepción. Un importador ingenuo daría el dump por bueno y el
inventario se quedaría sin tablas, con lo que RECONCILE concluiría "esta tabla no
existe, créala" sobre una tabla que lleva años en producción.
"""

import pytest

from ai.inventory.ddl_import import DdlImportError, parse_ddl

DDL_COMPLETO = """
-- Esquema de ejemplo
CREATE TABLE usuarios (
  usuario_id BIGSERIAL PRIMARY KEY,
  nombre VARCHAR(120) NOT NULL,
  email VARCHAR(200) NOT NULL UNIQUE,
  activo BOOLEAN DEFAULT true,
  creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE envios (
  envio_id BIGSERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL,
  guia VARCHAR(40) NOT NULL,
  peso NUMERIC(10,2),
  observacion TEXT,
  CONSTRAINT ux_envios_guia UNIQUE (guia),
  CONSTRAINT ck_envios_peso CHECK (peso > 0)
);

ALTER TABLE envios
  ADD CONSTRAINT fk_envios_usuario FOREIGN KEY (usuario_id)
  REFERENCES usuarios (usuario_id) ON DELETE CASCADE;

CREATE UNIQUE INDEX ix_usuarios_email ON usuarios (email);
CREATE INDEX ix_envios_usuario ON envios (usuario_id);

COMMENT ON TABLE envios IS 'Envios de la red';
COMMENT ON COLUMN envios.guia IS 'Documento de envio';

GRANT SELECT ON usuarios TO lector;
"""


def tabla(resultado, nombre):
    return next(t for t in resultado.content["tables"] if t["name"] == nombre)


def columna(t, nombre):
    return next(c for c in t["columns"] if c["name"] == nombre)


# --- lectura correcta --------------------------------------------------------


def test_lee_tablas_columnas_y_tipos():
    r = parse_ddl(DDL_COMPLETO)
    assert not r.errors
    assert {t["name"] for t in r.content["tables"]} == {"usuarios", "envios"}

    usuarios = tabla(r, "usuarios")
    assert usuarios["primary_key"] == ["usuario_id"]
    assert columna(usuarios, "usuario_id")["primary_key"] is True
    # El tipo físico se conserva verbatim y ADEMÁS se normaliza al del Agente BD.
    assert columna(usuarios, "nombre")["type"] == "VARCHAR(120)"
    assert columna(usuarios, "nombre")["logical_type"] == "string"
    assert columna(usuarios, "creado_en")["logical_type"] == "timestamptz"
    assert columna(tabla(r, "envios"), "peso")["logical_type"] == "decimal"
    assert columna(tabla(r, "envios"), "observacion")["logical_type"] == "text"


def test_nulabilidad_por_defecto_es_la_de_sql():
    """En SQL una columna admite nulos salvo que se diga lo contrario."""
    r = parse_ddl(DDL_COMPLETO)
    envios = tabla(r, "envios")
    assert columna(envios, "guia")["nullable"] is False  # NOT NULL explícito
    assert columna(envios, "peso")["nullable"] is True  # sin declarar
    # Un tipo autoincremental implica NOT NULL aunque no se escriba.
    assert columna(envios, "envio_id")["nullable"] is False


def test_lee_defaults():
    """El DEFAULT se conserva, aunque sqlglot lo NORMALICE.

    `now()` se lee como `CURRENT_TIMESTAMP`: son la misma semántica y la forma
    canónica es la que conviene guardar, porque permite comparar dos esquemas que
    escribieron el mismo default de distinta manera.
    """
    r = parse_ddl(DDL_COMPLETO)
    usuarios = tabla(r, "usuarios")
    assert columna(usuarios, "activo")["default"] == "TRUE"
    assert columna(usuarios, "creado_en")["default"] == "CURRENT_TIMESTAMP"


def test_lee_la_fk_declarada_por_alter_con_su_accion():
    """pg_dump emite TODAS las FK como ALTER TABLE: sin esto no habría relaciones."""
    r = parse_ddl(DDL_COMPLETO)
    fks = tabla(r, "envios")["foreign_keys"]
    assert len(fks) == 1
    assert fks[0]["name"] == "fk_envios_usuario"
    assert fks[0]["referenced_table"] == "usuarios"
    assert fks[0]["referenced_columns"] == ["usuario_id"]
    assert fks[0]["on_delete"] == "cascade"


def test_lee_la_fk_inline_con_su_accion():
    r = parse_ddl(
        "CREATE TABLE a (id BIGSERIAL PRIMARY KEY);"
        "CREATE TABLE b (id BIGSERIAL PRIMARY KEY,"
        " a_id BIGINT REFERENCES a(id) ON DELETE SET NULL);"
    )
    fk = tabla(r, "b")["foreign_keys"][0]
    assert fk["referenced_table"] == "a"
    assert fk["on_delete"] == "set null"


def test_la_misma_fk_declarada_dos_veces_no_se_duplica():
    """Inline + ALTER es la MISMA relación; contarla dos veces engañaría a RECONCILE."""
    r = parse_ddl(
        "CREATE TABLE a (id BIGSERIAL PRIMARY KEY);"
        "CREATE TABLE b (id BIGSERIAL PRIMARY KEY, a_id BIGINT REFERENCES a(id));"
        "ALTER TABLE b ADD CONSTRAINT fk_b_a FOREIGN KEY (a_id) REFERENCES a (id);"
    )
    fks = tabla(r, "b")["foreign_keys"]
    assert len(fks) == 1
    # Gana la declaración CON nombre: es la que existe en el catálogo del motor.
    assert fks[0]["name"] == "fk_b_a"


def test_lee_unique_check_e_indices():
    r = parse_ddl(DDL_COMPLETO)
    envios = tabla(r, "envios")
    unicas = [c for c in envios["constraints"] if c["kind"] == "unique"]
    checks = [c for c in envios["constraints"] if c["kind"] == "check"]
    assert unicas[0]["name"] == "ux_envios_guia"
    assert unicas[0]["columns"] == ["guia"]
    assert checks[0]["name"] == "ck_envios_peso"
    assert "peso" in checks[0]["expression"]

    usuarios = tabla(r, "usuarios")
    indice = next(i for i in usuarios["indexes"] if i["name"] == "ix_usuarios_email")
    assert indice["columns"] == ["email"]
    assert indice["unique"] is True
    assert tabla(r, "envios")["indexes"][0]["unique"] is False


def test_lee_comentarios_de_tabla_y_columna():
    """La documentación del esquema real es justo lo que el EF no tiene."""
    r = parse_ddl(DDL_COMPLETO)
    assert tabla(r, "envios")["comment"] == "Envios de la red"
    assert columna(tabla(r, "envios"), "guia")["comment"] == "Documento de envio"


def test_las_sentencias_irrelevantes_se_cuentan_no_se_esconden():
    """GRANT/SET no describen la forma, pero el informe dice cuántas hubo."""
    r = parse_ddl(DDL_COMPLETO)
    assert r.ignored_statements >= 1
    assert r.as_report()["ignored_statements"] >= 1


# --- lo que NO puede pasar en silencio ---------------------------------------


def test_una_sentencia_ilegible_se_reporta_con_su_linea():
    """EL test del bloque.

    `sqlglot` no lanza excepción ante esto: devuelve un nodo `Command`. Sin la
    detección explícita, el dump se daría por bueno y faltaría una tabla que sí
    existe en producción — y RECONCILE diría "créala".
    """
    sql = (
        "CREATE TABLE buena (id BIGSERIAL PRIMARY KEY);\n"
        "\n"
        "CREATE TABLE ESTO ESTA MAL (((;\n"
        "\n"
        "CREATE TABLE otra_buena (id BIGSERIAL PRIMARY KEY);\n"
    )
    r = parse_ddl(sql)
    assert len(r.errors) == 1
    fallo = r.errors[0]
    assert fallo.code == "unparsed_statement"
    assert fallo.line == 3, f"debía señalar la línea 3, señaló {fallo.line}"
    assert "Línea 3" in fallo.message
    # Y las tablas que SÍ se entendieron entran igualmente.
    assert {t["name"] for t in r.content["tables"]} == {"buena", "otra_buena"}


def test_el_informe_expone_los_errores_para_la_api():
    r = parse_ddl(
        "CREATE TABLE buena (id BIGSERIAL PRIMARY KEY);\nCREATE TABLE MAL (((;\n"
    )
    reporte = r.as_report()
    assert reporte["tables"] == 1
    assert reporte["errors"] and reporte["errors"][0]["line"] == 2


def test_un_archivo_sin_tablas_lo_dice():
    r = parse_ddl("GRANT SELECT ON algo TO alguien;")
    assert any(e.code == "no_tables_found" for e in r.errors)
    assert r.content["tables"] == []


def test_archivo_vacio_falla_con_mensaje_claro():
    with pytest.raises(DdlImportError, match="vacío"):
        parse_ddl("   \n  ")


def test_comilla_sin_cerrar_interrumpe_con_explicacion():
    """Un fallo de tokenizado deja el resto del archivo sin significado."""
    with pytest.raises(DdlImportError) as exc:
        parse_ddl("CREATE TABLE t (a int);\nSELECT 'sin cerrar")
    assert "comilla" in exc.value.message


def test_un_indice_sobre_tabla_desconocida_avisa():
    """No se inventa la tabla: se avisa de que el dump está incompleto."""
    r = parse_ddl(
        "CREATE TABLE a (id BIGSERIAL PRIMARY KEY);"
        "CREATE INDEX ix_x ON no_existe (col);"
    )
    assert any(w.code == "index_on_unknown_table" for w in r.warnings)


def test_un_alter_sobre_tabla_desconocida_avisa():
    r = parse_ddl(
        "CREATE TABLE a (id BIGSERIAL PRIMARY KEY);"
        "ALTER TABLE no_existe ADD CONSTRAINT c UNIQUE (col);"
    )
    assert any(w.code == "alter_on_unknown_table" for w in r.warnings)


def test_un_tipo_desconocido_deja_logical_type_en_none_sin_adivinar():
    """Adivinar el tipo produciría comparaciones falsas en RECONCILE."""
    r = parse_ddl("CREATE TABLE t (id BIGSERIAL PRIMARY KEY, raro POINT);")
    assert columna(tabla(r, "t"), "raro")["logical_type"] is None
    # Pero el tipo real se conserva, para que una persona pueda decidir.
    assert columna(tabla(r, "t"), "raro")["type"]


def test_el_contenido_leido_valida_contra_el_contrato_del_activo():
    """Lo que produce el lector tiene que poder guardarse tal cual (INV1)."""
    from app.models.inventory import InventoryAssetType
    from app.schemas.inventario import validate_asset_content

    r = parse_ddl(DDL_COMPLETO)
    validado = validate_asset_content(InventoryAssetType.DB_SCHEMA, r.content)
    assert len(validado["tables"]) == 2
