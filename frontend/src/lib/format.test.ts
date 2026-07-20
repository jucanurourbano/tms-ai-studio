import { describe, expect, it } from "vitest";

import {
  absoluteTime,
  filterByTitle,
  relativeTime,
  sourceLabel,
} from "@/lib/format";

const NOW = Date.parse("2026-07-20T12:00:00Z");
const ago = (ms: number) => new Date(NOW - ms).toISOString();

const SEC = 1000;
const MIN = 60 * SEC;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

describe("relativeTime", () => {
  it("devuelve — para valores vacíos o inválidos", () => {
    expect(relativeTime(null, NOW)).toBe("—");
    expect(relativeTime(undefined, NOW)).toBe("—");
    expect(relativeTime("no-es-fecha", NOW)).toBe("—");
  });

  it("muestra 'hace un momento' para menos de 45 s", () => {
    expect(relativeTime(ago(10 * SEC), NOW)).toBe("hace un momento");
  });

  it("escala a minutos, horas y días", () => {
    expect(relativeTime(ago(5 * MIN), NOW)).toBe("hace 5 min");
    expect(relativeTime(ago(3 * HOUR), NOW)).toBe("hace 3 h");
    expect(relativeTime(ago(5 * DAY), NOW)).toBe("hace 5 d");
  });

  it("escala a meses y años con plural correcto", () => {
    expect(relativeTime(ago(60 * DAY), NOW)).toBe("hace 2 meses");
    expect(relativeTime(ago(30 * DAY), NOW)).toBe("hace 1 mes");
    expect(relativeTime(ago(365 * DAY), NOW)).toBe("hace 1 año");
    expect(relativeTime(ago(2 * 365 * DAY), NOW)).toBe("hace 2 años");
  });
});

describe("sourceLabel", () => {
  it("traduce el tipo de fuente al español", () => {
    expect(sourceLabel("document")).toBe("Documento");
    expect(sourceLabel("text")).toBe("Texto");
    expect(sourceLabel(null)).toBe("—");
    expect(sourceLabel(undefined)).toBe("—");
  });
});

describe("absoluteTime", () => {
  it("devuelve cadena vacía para valores inválidos", () => {
    expect(absoluteTime(null)).toBe("");
    expect(absoluteTime("no-es-fecha")).toBe("");
  });

  it("devuelve una cadena no vacía para una fecha válida", () => {
    expect(absoluteTime(ago(0)).length).toBeGreaterThan(0);
  });
});

describe("filterByTitle", () => {
  const rows = [
    { job_id: "01ABC", title: "Registro de siniestros" },
    { job_id: "01DEF", title: "Gestión de guías" },
    { job_id: "01GHI", title: null },
  ];

  it("sin query devuelve todos los ítems", () => {
    expect(filterByTitle(rows, "")).toHaveLength(3);
    expect(filterByTitle(rows, "   ")).toHaveLength(3);
  });

  it("filtra por título sin distinguir mayúsculas", () => {
    const out = filterByTitle(rows, "SINIESTRO");
    expect(out).toHaveLength(1);
    expect(out[0].job_id).toBe("01ABC");
  });

  it("también coincide contra el id del job", () => {
    const out = filterByTitle(rows, "01def");
    expect(out).toHaveLength(1);
    expect(out[0].job_id).toBe("01DEF");
  });

  it("no rompe con títulos nulos", () => {
    expect(filterByTitle(rows, "inexistente")).toHaveLength(0);
  });
});
