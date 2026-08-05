import { describe, expect, it } from "vitest";

import { makeRefResolver } from "./artifact-refs";
import { BD_REF_ROUTES } from "./bd-refs";
import { ISDF_NAV } from "./isdf";
import { ruleFor } from "./route-permissions";

const resolve = makeRefResolver(BD_REF_ROUTES);

describe("referencias del artefacto de BD", () => {
  it("lleva cada objeto del esquema a su sección", () => {
    expect(resolve("TBL-001")).toEqual({
      sectionId: "tablas",
      tabId: undefined,
    });
    expect(resolve("FK-001")?.sectionId).toBe("tablas");
    expect(resolve("IDX-002")?.sectionId).toBe("tablas");
    expect(resolve("DDL-003")?.sectionId).toBe("ddl");
    expect(resolve("SEED-001")?.sectionId).toBe("semilla");
    expect(resolve("DIC-0004")?.sectionId).toBe("diccionario");
    expect(resolve("RM-002")?.sectionId).toBe("reglas");
    expect(resolve("DBD-001")?.sectionId).toBe("decisiones");
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
    // El modelo cita el EF y la arquitectura constantemente. Fingir un destino
    // sería peor que avisar: el usuario acabaría en una sección que no contiene
    // lo que buscaba.
    for (const ajeno of [
      "ENT-001", // entidad del EF
      "FLD-002", // campo del EF
      "BR-001", // regla del EF
      "VAL-001", // validación del EF
      "REL-001", // relación del EF
      "ADR-002", // decisión de la arquitectura
      "STK-004", // stack de la arquitectura
      "API-001", // endpoint inferido en el EF
    ]) {
      expect(resolve(ajeno), `${ajeno} no vive en el artefacto de BD`).toBeNull();
    }
  });

  it("no confunde COL- con CK- ni con constraint alguna", () => {
    expect(resolve("COL-0001")?.sectionId).toBe("diccionario");
    expect(resolve("CK-001")?.sectionId).toBe("tablas");
  });
});

describe("el Agente BD está enchufado a la aplicación", () => {
  it("aparece activo en la fase DISEÑAR de la navegación", () => {
    const disenar = ISDF_NAV.find((p) => p.key === "disenar");
    const bd = disenar?.agents.find((a) => a.key === "bd");
    expect(bd?.enabled).toBe(true);
    expect(bd?.href).toBe("/agents/bd");
    expect(bd?.module).toBe("bd");
  });

  it("protege sus rutas: crear exige edición, consultar solo lectura", () => {
    expect(ruleFor("/agents/bd/new")).toEqual({
      prefix: "/agents/bd/new",
      module: "bd",
      level: "full",
    });
    expect(ruleFor("/agents/bd/jobs/01ABC")).toEqual({
      prefix: "/agents/bd",
      module: "bd",
      level: "read",
    });
  });
});
