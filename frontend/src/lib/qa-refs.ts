// Rutas de referencia del artefacto de QA: qué id abre qué sección del hub.
//
// Vive fuera de la vista para poder testearse sin montar el componente, y la
// regla que importa vuelve a ser la contraria a la obvia: el plan de pruebas cita
// constantemente ids que **no viven en este artefacto** —reglas y validaciones
// del EF (BR-…, VAL-…, FLD-…, ENT-…, REQ-F-…), épicas del plan Scrum (EPIC-…) y
// reglas y endpoints del contrato de API (AUTH-…, EP-…, COL-…)—. Esos chips no
// deben navegar a ningún sitio: deben avisar de dónde está el dato.
//
// `US-` y `AC-` son la excepción deliberada. Nacen en el Scrum, sí, pero la
// matriz de trazabilidad de ESTE artefacto está indexada por ellos: preguntar
// "¿y AC-002?" dentro del plan de pruebas tiene una respuesta aquí —qué casos lo
// cubren, o el hueco— y llevar ahí no finge nada.

import type { RefRoute } from "@/lib/artifact-refs";

export const QA_REF_ROUTES: RefRoute[] = [
  { prefix: "TC-", sectionId: "casos" },
  { prefix: "US-", sectionId: "trazabilidad" },
  { prefix: "AC-", sectionId: "trazabilidad" },
  { prefix: "DS-", sectionId: "datasets" },
  { prefix: "SUITE-", sectionId: "plan" },
  { prefix: "QQ-", sectionId: "preguntas" },
  { prefix: "RISK-", sectionId: "analisis", tabId: "riesgos" },
  { prefix: "OBS-", sectionId: "analisis", tabId: "observaciones" },
];
