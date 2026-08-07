import { describe, expect, it } from "vitest";

import { API_REF_ROUTES } from "./api-refs";
import { makeRefResolver } from "./artifact-refs";
import { ISDF_NAV } from "./isdf";
import { ruleFor } from "./route-permissions";

const resolve = makeRefResolver(API_REF_ROUTES);

describe("referencias del artefacto de API", () => {
  it("lleva cada pieza del contrato a su sección", () => {
    expect(resolve("RES-001")).toEqual({
      sectionId: "recursos",
      tabId: undefined,
    });
    expect(resolve("EP-007")?.sectionId).toBe("endpoints");
    expect(resolve("PRM-0003")?.sectionId).toBe("endpoints");
    expect(resolve("SCH-002")?.sectionId).toBe("esquemas");
    expect(resolve("SF-0021")?.sectionId).toBe("esquemas");
    expect(resolve("AUTH-011")?.sectionId).toBe("autorizacion");
    expect(resolve("ERR-409")?.sectionId).toBe("errores");
    expect(resolve("ARM-005")?.sectionId).toBe("reglas");
    expect(resolve("Q-001")?.sectionId).toBe("preguntas");
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
    // El contrato cita el modelo de datos, el EF y la arquitectura en cada
    // pantalla. Fingir un destino sería peor que avisar: el usuario acabaría en
    // una sección que no contiene lo que buscaba.
    for (const ajeno of [
      "TBL-002", // tabla del modelo de datos
      "COL-0014", // columna del modelo de datos
      "ENT-001", // entidad del EF
      "BR-003", // regla del EF
      "VAL-001", // validación del EF
      "CRUD-001", // celda de la matriz CRUD del EF
      "ACT-002", // actor del EF
      "API-001", // endpoint declarado en el EF
      "CMP-001", // componente de la arquitectura
      "STK-007", // stack de la arquitectura
    ]) {
      expect(
        resolve(ajeno),
        `${ajeno} no vive en el artefacto de API`,
      ).toBeNull();
    }
  });

  it("no confunde el prefijo de un endpoint con el de un error", () => {
    // `EP-` y `ERR-` comparten la primera letra; gana el prefijo más largo.
    expect(resolve("EP-001")?.sectionId).toBe("endpoints");
    expect(resolve("ERR-401")?.sectionId).toBe("errores");
  });
});

describe("el Agente API está enchufado a la aplicación", () => {
  it("aparece activo en la fase CONSTRUIR de la navegación", () => {
    const construir = ISDF_NAV.find((p) => p.key === "construir");
    const api = construir?.agents.find((a) => a.key === "api");
    expect(api?.enabled).toBe(true);
    expect(api?.href).toBe("/agents/api");
    expect(api?.module).toBe("api");
  });

  it("protege sus rutas: crear exige edición, consultar solo lectura", () => {
    expect(ruleFor("/agents/api/new")).toEqual({
      prefix: "/agents/api/new",
      module: "api",
      level: "full",
    });
    expect(ruleFor("/agents/api/jobs/01ABC")).toEqual({
      prefix: "/agents/api",
      module: "api",
      level: "read",
    });
  });
});
