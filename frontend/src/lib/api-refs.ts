// Rutas de referencia del artefacto de API: qué id abre qué sección del hub.
//
// Vive fuera de la vista para poder testearse sin montar el componente, porque la
// regla que importa no es "EP-001 abre Endpoints" sino la contraria: el contrato
// cita constantemente ids que **no viven en este artefacto** —columnas y tablas
// del modelo de datos (COL-…, TBL-…), reglas y actores del EF (BR-…, VAL-…,
// ACT-…, CRUD-…, API-…) y componentes de la arquitectura (CMP-…)—. Esos chips no
// deben navegar a ningún sitio: deben avisar de dónde está el dato.

import type { RefRoute } from "@/lib/artifact-refs";

export const API_REF_ROUTES: RefRoute[] = [
  { prefix: "RES-", sectionId: "recursos" },
  { prefix: "EP-", sectionId: "endpoints" },
  { prefix: "PRM-", sectionId: "endpoints" },
  { prefix: "SCH-", sectionId: "esquemas" },
  { prefix: "SF-", sectionId: "esquemas" },
  { prefix: "AUTH-", sectionId: "autorizacion" },
  { prefix: "ERR-", sectionId: "errores" },
  { prefix: "ARM-", sectionId: "reglas" },
  { prefix: "RISK-", sectionId: "analisis", tabId: "riesgos" },
  { prefix: "OBS-", sectionId: "analisis", tabId: "observaciones" },
  { prefix: "Q-", sectionId: "preguntas" },
];
