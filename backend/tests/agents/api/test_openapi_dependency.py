"""Contrato con las librerías de validación de OpenAPI (bloque API0).

No prueban código propio: **fijan el comportamiento de la dependencia** del que va
a depender la capa L2 del Agente API, igual que la suite del Agente BD fija el de
sqlglot. Sirven para dos cosas:

1. Demostrar que la validación funciona **sin red ni tooling externo**, que es la
   razón por la que se eligió esta librería y no un `swagger-cli` en Node.
2. Documentar la trampa que encontró la prueba de humo del bloque: un ``$ref``
   colgante **no** sale por ``iter_errors()``, sale como **excepción**. El
   validador de L2 tendrá que capturarla y convertirla en un
   ``validation.errors``, o una referencia rota tumbaría el pipeline en vez de
   reportarse. El diseño ya exige que ningún fallo de validación caiga el job
   (docs/diseno-agente-api.md §5).
"""

import pytest
from openapi_spec_validator import OpenAPIV31SpecValidator

#: Documento mínimo válido en OpenAPI 3.1, con la forma que renderizará el agente.
SPEC_MINIMA = {
    "openapi": "3.1.0",
    "info": {"title": "API de Siniestros", "version": "1.0.0"},
    "paths": {
        "/api/v1/siniestros": {
            "get": {
                "operationId": "listarSiniestros",
                "responses": {"200": {"description": "Listado de siniestros."}},
            }
        }
    },
}


def _errores(spec: dict) -> list:
    return list(OpenAPIV31SpecValidator(spec).iter_errors())


def test_un_documento_31_valido_no_produce_errores():
    assert _errores(SPEC_MINIMA) == []


def test_detecta_un_documento_incompleto():
    """Falta `info.version`: el error se ve, con mensaje accionable."""
    spec = {**SPEC_MINIMA, "info": {"title": "API de Siniestros"}}
    errores = _errores(spec)
    assert errores
    assert "version" in errores[0].message


def test_una_operacion_sin_respuestas_NO_la_caza_el_validador_31():
    """Hueco de la especificación 3.1 que L1 tiene que cubrir por su cuenta.

    En OpenAPI **3.0** el campo `responses` era obligatorio en toda operación; en
    **3.1** dejó de serlo. Consecuencia práctica: un endpoint que no declara qué
    devuelve —un contrato inservible para el Agente Backend y para el Frontend—
    pasa la validación de la librería sin una sola queja.

    Por eso "todo endpoint declara sus códigos de estado" es una comprobación
    **estructural (L1)** y no se delega en L2. Este test es el recordatorio de que
    no se puede quitar de L1 pensando que la librería la cubre.
    """
    spec = {
        **SPEC_MINIMA,
        "paths": {"/api/v1/siniestros": {"get": {"operationId": "listarSiniestros"}}},
    }
    assert _errores(spec) == []


def test_una_referencia_colgante_LANZA_en_vez_de_reportarse():
    """La trampa: `$ref` a un esquema inexistente **explota**, no se reporta.

    Este test existe para que el comportamiento quede escrito y la capa L2 nazca
    defensiva. La comprobación L1 nº 1 (todos los `$ref` resuelven) se hace antes
    precisamente para que este caso no llegue nunca hasta aquí, pero L2 igual debe
    capturar: un bug del renderizador podría colar una referencia rota.
    """
    spec = {
        **SPEC_MINIMA,
        "paths": {
            "/api/v1/siniestros": {
                "get": {
                    "operationId": "listarSiniestros",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/NoExiste"}
                                }
                            },
                        }
                    },
                }
            }
        },
    }
    # No se afirma la clase concreta (es interna de `referencing`): lo que importa
    # es que sale por excepción y que L2 tendrá que envolver la llamada.
    with pytest.raises(Exception):  # noqa: B017
        _errores(spec)


def test_la_validacion_no_sale_a_la_red():
    """Requisito de diseño: el documento es autocontenido y se valida offline.

    Se comprueba de la forma más directa posible: un documento cuyo único `$ref`
    apunta a `#/components/...` valida sin que exista ninguna referencia remota.
    """
    spec = {
        **SPEC_MINIMA,
        "paths": {
            "/api/v1/siniestros": {
                "get": {
                    "operationId": "listarSiniestros",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Siniestro"}
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Siniestro": {
                    "type": "object",
                    "properties": {"numero_guia": {"type": "string"}},
                }
            }
        },
    }
    assert _errores(spec) == []


def test_openapi_core_puede_construir_la_especificacion():
    """Capa L3a disponible: un runtime real es capaz de cargar el documento.

    Es el análogo de la prueba de humo contra SQLite del Agente BD. Aquí solo se
    verifica que la librería está y construye; los chequeos de petición/respuesta
    con ejemplos llegan en el bloque API6, cuando exista un documento generado.
    """
    from openapi_core import OpenAPI

    assert OpenAPI.from_dict(SPEC_MINIMA) is not None
