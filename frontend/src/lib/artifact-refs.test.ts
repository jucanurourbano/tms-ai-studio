import { describe, expect, it } from "vitest";

import { makeRefResolver } from "./artifact-refs";

describe("makeRefResolver", () => {
  const resolve = makeRefResolver([
    { prefix: "REQ-", sectionId: "requisitos" },
    { prefix: "REQ-F-", sectionId: "requisitos", tabId: "funcionales" },
    { prefix: "BR-", sectionId: "modelo", tabId: "reglas" },
    { prefix: "Q-", sectionId: "preguntas" },
  ]);

  it("gana el prefijo MÁS LARGO, no el declarado primero", () => {
    expect(resolve("REQ-F-001")).toEqual({
      sectionId: "requisitos",
      tabId: "funcionales",
    });
    expect(resolve("REQ-B-001")).toEqual({
      sectionId: "requisitos",
      tabId: undefined,
    });
  });

  it("resuelve a la sub-pestaña que contiene la fila", () => {
    expect(resolve("BR-003")).toEqual({ sectionId: "modelo", tabId: "reglas" });
  });

  it("devuelve null para lo que no vive en este artefacto", () => {
    // Un plan Scrum cita RF del EF: el chip no puede navegar y debe avisar.
    expect(resolve("ENT-001")).toBeNull();
    expect(resolve("")).toBeNull();
  });
});
