import { describe, expect, it } from "vitest";

import { makeRefResolver } from "./artifact-refs";
import { ISDF_NAV } from "./isdf";
import { QA_REF_ROUTES } from "./qa-refs";
import { ruleFor } from "./route-permissions";

const resolve = makeRefResolver(QA_REF_ROUTES);

describe("referencias del artefacto de QA", () => {
  it("lleva cada pieza del plan a su sección", () => {
    expect(resolve("TC-001")).toEqual({ sectionId: "casos", tabId: undefined });
    expect(resolve("DS-001")?.sectionId).toBe("datasets");
    expect(resolve("SUITE-002")?.sectionId).toBe("plan");
    expect(resolve("QQ-001")?.sectionId).toBe("preguntas");
  });

  it("resuelve historias y criterios a la matriz, que está indexada por ellos", () => {
    // Nacen en el plan Scrum, pero preguntar "¿y AC-002?" DENTRO del plan de
    // pruebas tiene respuesta aquí: qué casos lo cubren, o el hueco.
    expect(resolve("US-003")?.sectionId).toBe("trazabilidad");
    expect(resolve("AC-002")?.sectionId).toBe("trazabilidad");
  });

  it("abre la sub-pestaña correcta del análisis", () => {
    expect(resolve("RISK-001")).toEqual({
      sectionId: "analisis",
      tabId: "riesgos",
    });
    expect(resolve("OBS-002")).toEqual({
      sectionId: "analisis",
      tabId: "observaciones",
    });
  });

  it("NO resuelve los ids que pertenecen a otros artefactos", () => {
    // El plan cita el EF, el Scrum y el contrato de API en cada caso. Fingir un
    // destino sería peor que avisar: el usuario acabaría en una sección que no
    // contiene lo que buscaba.
    for (const ajeno of [
      "REQ-F-001", // requisito del EF
      "BR-003", // regla del EF
      "VAL-001", // validación del EF
      "FLD-002", // campo del EF
      "ENT-001", // entidad del EF
      "ACT-002", // actor del EF
      "EPIC-001", // épica del plan Scrum
      "AUTH-002", // regla de la matriz del contrato de API
      "EP-007", // endpoint del contrato de API
      "COL-0014", // columna del modelo de datos
    ]) {
      expect(
        resolve(ajeno),
        `${ajeno} no vive en el artefacto de QA`,
      ).toBeNull();
    }
  });
});

describe("el Agente QA está enchufado a la aplicación", () => {
  it("aparece activo en la fase VERIFICAR de la navegación", () => {
    const verificar = ISDF_NAV.find((p) => p.key === "verificar");
    const qa = verificar?.agents.find((a) => a.key === "qa");
    expect(qa?.enabled).toBe(true);
    expect(qa?.href).toBe("/agents/qa");
    expect(qa?.module).toBe("qa");
  });

  it("protege sus rutas: crear exige edición, consultar solo lectura", () => {
    expect(ruleFor("/agents/qa/new")).toEqual({
      prefix: "/agents/qa/new",
      module: "qa",
      level: "full",
    });
    expect(ruleFor("/agents/qa/jobs/01ABC")).toEqual({
      prefix: "/agents/qa",
      module: "qa",
      level: "read",
    });
  });
});
