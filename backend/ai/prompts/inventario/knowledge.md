EXTRACCIÓN DE CONOCIMIENTO DEL SISTEMA

Del fragmento que se te entrega, extrae cuatro colecciones:

**`modules`** — módulos, componentes, aplicaciones o microservicios del sistema.
Es la unidad de organización funcional que el documento use. Incluye en
`functionalities` y `entities` los nombres que el documento asocie a cada uno (solo
los que nombre; no los deduzcas de tu conocimiento del dominio).

**`entities`** — entidades de negocio que el sistema maneja (guía, envío, cliente,
manifiesto…). En `attributes` pon SOLO los atributos que el texto mencione.
Cuidado: esto NO es un modelo de datos. No inventes claves primarias, ni tipos, ni
campos de auditoría. Si el documento nombra la entidad sin detallar sus atributos,
deja `attributes` vacío.

**`functionalities`** — lo que el sistema PERMITE HACER (registrar una admisión,
consultar el estado de un envío, liquidar un recaudo). Verbos, no pantallas.

**`decisions`** — decisiones técnicas o de negocio que el documento deja tomadas
("se migrará a Aurora Serverless", "los reportes se generan de forma asíncrona",
"la app de destinatarios será multiplataforma"). En `rationale`, el motivo SI el
documento lo da; si no lo da, déjalo vacío en vez de imaginarlo.

Estas son las más valiosas y las que más fácil se pierden: si no quedan
registradas, el Agente Arquitectura las volverá a decidir desde cero y quizá de
otra manera, contradiciendo a un sistema que ya existe.

FORMATO DE SALIDA (solo JSON):

{
  "modules": [{"name": "...", "description": "...", "functionalities": ["..."],
               "entities": ["..."], "source_ref": "el-0003",
               "evidence": "texto verbatim", "confidence": 0.9,
               "origin": "stated"}],
  "entities": [{"name": "...", "description": "...", "attributes": ["..."],
                "source_ref": "el-0004", "evidence": "texto verbatim",
                "confidence": 0.8, "origin": "stated"}],
  "functionalities": [{"name": "...", "description": "...",
                       "source_ref": "el-0005", "evidence": "texto verbatim",
                       "confidence": 0.8, "origin": "stated"}],
  "decisions": [{"title": "...", "rationale": "...", "source_ref": "el-0006",
                 "evidence": "texto verbatim", "confidence": 0.9,
                 "origin": "stated"}]
}
