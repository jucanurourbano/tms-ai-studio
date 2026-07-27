import { describe, expect, it } from "vitest";

import { filterByQuery, matchesQuery, normalizeText } from "./artifact-search";

describe("normalizeText", () => {
  it("quita acentos y baja a minúsculas", () => {
    expect(normalizeText("Ambigüedad Crítica")).toBe("ambiguedad critica");
    expect(normalizeText("GUÍA")).toBe("guia");
  });
});

describe("matchesQuery", () => {
  it("sin consulta, todo encaja (el render no distingue 'sin filtro')", () => {
    expect(matchesQuery("", "cualquier cosa")).toBe(true);
    expect(matchesQuery("   ", null)).toBe(true);
  });

  it("ignora acentos y mayúsculas en ambos sentidos", () => {
    expect(matchesQuery("guia", "Registrar la guía de envío")).toBe(true);
    expect(matchesQuery("GUÍA", "registrar la guia")).toBe(true);
  });

  it("exige TODOS los términos, aunque estén en campos distintos", () => {
    expect(matchesQuery("checkpoint siniestro", "Cambiar checkpoint", "SIN-001 siniestro")).toBe(
      true,
    );
    expect(matchesQuery("checkpoint recupero", "Cambiar checkpoint")).toBe(false);
  });

  it("busca también por id (los campos numéricos y nulos no estorban)", () => {
    expect(matchesQuery("req-f-001", "REQ-F-001", null, undefined, 3)).toBe(true);
  });
});

describe("filterByQuery", () => {
  const items = [
    { id: "BR-001", statement: "El checkpoint solo avanza" },
    { id: "BR-002", statement: "La guía requiere shipper" },
  ];

  it("devuelve la misma lista sin consulta", () => {
    expect(filterByQuery("", items, (i) => [i.statement])).toBe(items);
  });

  it("filtra por cualquiera de los campos declarados", () => {
    expect(filterByQuery("shipper", items, (i) => [i.id, i.statement])).toEqual([
      items[1],
    ]);
    expect(filterByQuery("br-001", items, (i) => [i.id, i.statement])).toEqual([
      items[0],
    ]);
  });
});
