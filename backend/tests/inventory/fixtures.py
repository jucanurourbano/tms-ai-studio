"""Fixture SINTÉTICA del documento de modernización (INV3).

⚠️  IMPORTANTE — LOS NOMBRES DE AQUÍ SON INVENTADOS PARA LA PRUEBA.

El documento real (``PROYECTO_MODERNIZACION_v4``) **no está en el repositorio**.
Lo que sí se conoce, y es lo que esta fixture reproduce, es su FORMA: el sistema
destino "TMS Moderno" con **5 aplicaciones**, **16 microservicios** y **15 tablas
maestras** en un esquema compartido.

Por eso esta fixture fija los *recuentos* (que son el contrato acordado) con
nombres genéricos y plausibles de un TMS de courier. No pretende adivinar cómo se
llaman de verdad los microservicios de Urbano: inventar esos nombres y dejarlos
en un test los convertiría, con el tiempo, en una fuente de verdad falsa.

Cuando el documento real se incorpore, se sustituyen los nombres y los recuentos
deberían seguir cuadrando; si no cuadran, es el test el que avisa.
"""

# --- Forma acordada del sistema destino --------------------------------------

APLICACIONES = [
    "Portal Web Operativo",
    "App Courier Android",
    "App Destinatarios",
    "Back Office Administrativo",
    "Portal de Clientes",
]

MICROSERVICIOS = [
    "ms-admision",
    "ms-distribucion",
    "ms-tracking",
    "ms-manifiestos",
    "ms-rutas",
    "ms-facturacion",
    "ms-recaudo",
    "ms-tarifario",
    "ms-clientes",
    "ms-destinatarios",
    "ms-identidad",
    "ms-notificaciones",
    "ms-reportes",
    "ms-logistica-inversa",
    "ms-geolocalizacion",
    "ms-integraciones",
]

TABLAS_MAESTRAS = [
    "usuarios",
    "clientes",
    "destinatarios",
    "ubigeos",
    "sedes",
    "rutas",
    "vehiculos",
    "couriers",
    "tipos_servicio",
    "estados_envio",
    "tarifas",
    "monedas",
    "empresas",
    "contratos",
    "motivos_devolucion",
]

assert len(APLICACIONES) == 5
assert len(MICROSERVICIOS) == 16
assert len(TABLAS_MAESTRAS) == 15


DOCUMENTO_SINTETICO = f"""# Proyecto de Modernización del TMS

## Alcance

El nuevo TMS se construye como una arquitectura de microservicios desplegada en
AWS, con la base de datos en Aurora Serverless v2 compatible con PostgreSQL.

## Aplicaciones

El sistema expone {len(APLICACIONES)} aplicaciones cliente:
{chr(10).join(f"- {a}" for a in APLICACIONES)}

## Microservicios

La plataforma se descompone en {len(MICROSERVICIOS)} microservicios:
{chr(10).join(f"- {m}" for m in MICROSERVICIOS)}

## Esquema compartido

Los microservicios comparten un esquema con {len(TABLAS_MAESTRAS)} tablas
maestras:
{chr(10).join(f"- {t}" for t in TABLAS_MAESTRAS)}

## Decisiones

Los reportes pesados se generan de forma asíncrona en Python, fuera del ciclo de
petición y respuesta. La aplicación de destinatarios se construye con Flutter para
cubrir Android e iOS con un solo equipo.
"""


def knowledge_del_documento(element_id: str) -> dict:
    """Extracción que un modelo produciría sobre la fixture, citando ``element_id``.

    Se usa como respuesta del LLM MOCKEADO: los tests nunca llaman a la API real
    (REGLA DE PRESUPUESTO).
    """

    def item(nombre: str, evidencia: str) -> dict:
        return {
            "name": nombre,
            "description": None,
            "source_ref": element_id,
            "evidence": evidencia,
            "confidence": 0.9,
            "origin": "stated",
        }

    return {
        "modules": [
            {**item(nombre, f"- {nombre}"), "functionalities": [], "entities": []}
            for nombre in APLICACIONES + MICROSERVICIOS
        ],
        "entities": [
            {**item(nombre, f"- {nombre}"), "attributes": []}
            for nombre in TABLAS_MAESTRAS
        ],
        "functionalities": [],
        "decisions": [
            {
                "title": "Reportes asíncronos en Python",
                "rationale": "Fuera del ciclo de petición y respuesta.",
                "source_ref": element_id,
                "evidence": "Los reportes pesados se generan de forma asíncrona",
                "confidence": 0.9,
                "origin": "stated",
            },
            {
                "title": "App de destinatarios en Flutter",
                "rationale": "Cubrir Android e iOS con un solo equipo.",
                "source_ref": element_id,
                "evidence": "se construye con Flutter",
                "confidence": 0.9,
                "origin": "stated",
            },
        ],
    }
