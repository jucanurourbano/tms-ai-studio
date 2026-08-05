// Rutas de referencia del artefacto de BD: qué id abre qué sección del hub.
//
// Vive fuera de la vista para poder testearse sin montar el componente, porque la
// regla que importa no es "TBL-001 abre Tablas" sino la contraria: el modelo cita
// constantemente ids del EF (ENT-…, FLD-…, BR-…, VAL-…) y de la arquitectura
// (ADR-…, STK-…) que **no viven en este artefacto**. Esos chips no deben navegar a
// ningún sitio: deben avisar de dónde está el dato.

import type { RefRoute } from "@/lib/artifact-refs";

export const BD_REF_ROUTES: RefRoute[] = [
  { prefix: "TBL-", sectionId: "tablas" },
  { prefix: "COL-", sectionId: "diccionario" },
  { prefix: "DIC-", sectionId: "diccionario" },
  { prefix: "FK-", sectionId: "tablas" },
  { prefix: "UQ-", sectionId: "tablas" },
  { prefix: "CK-", sectionId: "tablas" },
  { prefix: "IDX-", sectionId: "tablas" },
  { prefix: "DDL-", sectionId: "ddl" },
  { prefix: "SEED-", sectionId: "semilla" },
  { prefix: "DBD-", sectionId: "decisiones" },
  { prefix: "RM-", sectionId: "reglas" },
  { prefix: "RISK-", sectionId: "analisis", tabId: "riesgos" },
  { prefix: "OBS-", sectionId: "analisis", tabId: "observaciones" },
  { prefix: "Q-", sectionId: "preguntas" },
];
