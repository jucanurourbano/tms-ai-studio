"""Enumeraciones de valores cerrados del QaArtifact.

Todo enum aquí es un **conjunto cerrado que el LLM debe elegir**, nunca texto
libre: es lo que permite agrupar, contar y filtrar los casos de forma determinista
sin volver a pasar por el modelo. La regla es la misma que en el Agente BD con los
tipos lógicos: el modelo decide semántica, Python decide la forma.
"""

from enum import Enum


class TestCaseType(str, Enum):
    """Clase de caso de prueba.

    Los cuatro tipos no son un adorno taxonómico: cada uno tiene una **fuente
    distinta** y por eso un cortafuegos distinto. Los funcionales salen del criterio
    Gherkin; los negativos de su inversión; los de borde exigen un límite **anclado
    en evidencia**; los de autorización se **derivan** de la matriz del ApiArtifact
    y no existen sin él.
    """

    #: Camino feliz: el criterio se cumple tal como está redactado.
    FUNCTIONAL = "functional"
    #: El sistema debe rechazar: dato inválido, estado incorrecto, paso omitido.
    NEGATIVE = "negative"
    #: Frontera de una validación (límite, longitud, formato, obligatoriedad).
    BOUNDARY = "boundary"
    #: Un actor intenta lo que su alcance no permite. Requiere ApiArtifact.
    AUTHORIZATION = "authorization"


class TestPriority(str, Enum):
    """Prioridad de ejecución del caso, heredada del MoSCoW de la historia.

    El mapeo es directo (``must``→``critica``, ``should``→``alta``,
    ``could``→``media``, ``wont``→``baja``) con **un suelo** (QA-D4): un caso de
    autorización nunca baja de ``alta``, porque un fallo de autorización es de
    seguridad y no de funcionalidad — se despliega y nadie lo ve hasta que alguien
    lee datos que no le tocan.
    """

    CRITICA = "critica"
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class AutomationHint(str, Enum):
    """Por dónde conviene automatizar el caso.

    Es una **sugerencia** al equipo, no una decisión de arquitectura de pruebas: de
    ahí el nombre. Un caso con ``endpoint_ref`` es automatizable por API; uno que
    describe navegación es de UI; uno que exige inspección humana es manual.
    """

    API = "api"
    UI = "ui"
    MANUAL = "manual"


class DataKind(str, Enum):
    """Naturaleza de un dato de prueba dentro de un caso o un dataset."""

    #: Cumple todas las validaciones conocidas.
    VALID = "valid"
    #: Viola deliberadamente una validación citada.
    INVALID = "invalid"
    #: Está exactamente en la frontera (el límite, el límite±1).
    BOUNDARY = "boundary"


class BoundaryKind(str, Enum):
    """Qué clase de frontera prueba un caso de borde.

    Cerrado a propósito: "el saldo no puede ser negativo" y "la fecha de fin debe
    ser posterior a la de inicio" son fronteras de distinta naturaleza y se generan
    con plantillas distintas. Un texto libre aquí haría imposible agruparlas.
    """

    MIN = "min"
    MAX = "max"
    LENGTH = "length"
    FORMAT = "format"
    #: Obligatoriedad simple: el campo no puede faltar.
    REQUIRED = "required"
    #: Obligatoriedad **condicional**: exigido solo si se cumple algo más.
    CONDITIONAL = "conditional"
    #: Orden entre dos fechas u orden temporal.
    DATE_ORDER = "date_order"
    #: Pertenencia a un conjunto cerrado (enum, catálogo).
    ENUM = "enum"
    #: Unicidad: el valor ya existe.
    UNIQUE = "unique"


class AnchorSource(str, Enum):
    """De dónde sale el límite que justifica un caso de borde (QA-D2).

    ``EF_TEXT`` obliga a cita verbatim porque el EF guarda las validaciones como
    texto libre; ``API_FIELD`` es un dato estructurado (``max_length``, ``enum``,
    ``required``) y **prevalece** sobre lo extraído del texto cuando ambos existen.
    """

    #: Extraído del texto de una ``VAL-``/``BR-`` del EF, con cita verbatim.
    EF_TEXT = "ef_text"
    #: Leído de un campo estructurado del ApiArtifact.
    API_FIELD = "api_field"


class CoverageStatus(str, Enum):
    """Estado de cobertura de una fila de la matriz de trazabilidad."""

    #: Tiene al menos un caso de prueba.
    COVERED = "covered"
    #: No tiene ninguno. Advertencia o hallazgo según el MoSCoW de la historia.
    UNCOVERED = "uncovered"
    #: Declarado **no verificable**: hay pregunta al QA lead, no caso.
    NOT_TESTABLE = "not_testable"
