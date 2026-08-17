import { describe, expect, it } from "vitest";

import {
  COVERAGE_STATUS,
  countsByKind,
  formatMinutes,
  kindStyleOf,
  TEST_CASE_KIND,
  TEST_CASE_KIND_ORDER,
  TEST_PRIORITY,
  TEST_PRIORITY_ORDER,
} from "./test-case-kind";
import type { TestCaseType } from "./types/qa";

describe("vocabulario de los tipos de caso", () => {
  it("cubre los cuatro tipos del contrato, sin inventar ninguno", () => {
    // El enum del backend es cerrado a propósito; si aquí faltara un tipo, sus
    // casos se pintarían sin badge y se leerían como si no tuvieran clase.
    expect(TEST_CASE_KIND_ORDER).toEqual([
      "functional",
      "negative",
      "boundary",
      "authorization",
    ]);
    expect(Object.keys(TEST_CASE_KIND).sort()).toEqual(
      [...TEST_CASE_KIND_ORDER].sort(),
    );
  });

  it("cada tipo dice de dónde sale, no solo cómo se llama", () => {
    // El `hint` es lo que permite a quien revisa saber qué respalda un caso.
    for (const type of TEST_CASE_KIND_ORDER) {
      expect(kindStyleOf(type).hint.length).toBeGreaterThan(20);
      expect(kindStyleOf(type).label).toBeTruthy();
      expect(kindStyleOf(type).plural).toBeTruthy();
    }
    expect(kindStyleOf("boundary").hint).toContain("verbatim");
    expect(kindStyleOf("authorization").hint).toContain("contrato de API");
  });

  it("da un color distinto a cada tipo", () => {
    const dots = TEST_CASE_KIND_ORDER.map((t) => TEST_CASE_KIND[t].dot);
    expect(new Set(dots).size).toBe(dots.length);
  });

  it("no usa plantillas de clase: Tailwind necesita verlas literales", () => {
    for (const type of TEST_CASE_KIND_ORDER) {
      expect(TEST_CASE_KIND[type].badge).not.toContain("${");
      expect(TEST_CASE_KIND[type].dot).not.toContain("${");
    }
  });
});

describe("prioridad y cobertura", () => {
  it("cubre las cuatro prioridades heredadas del MoSCoW", () => {
    expect(TEST_PRIORITY_ORDER).toEqual(["critica", "alta", "media", "baja"]);
    expect(Object.keys(TEST_PRIORITY).sort()).toEqual(
      [...TEST_PRIORITY_ORDER].sort(),
    );
  });

  it("no pinta igual «sin cubrir» que «no verificable»", () => {
    // No son sinónimos: uno es un hueco, el otro una decisión respaldada por una
    // pregunta. Igualarlos haría creer que falta trabajo donde falta respuesta.
    expect(COVERAGE_STATUS.uncovered.dot).not.toBe(
      COVERAGE_STATUS.not_testable.dot,
    );
    expect(COVERAGE_STATUS.covered.dot).not.toBe(
      COVERAGE_STATUS.uncovered.dot,
    );
  });
});

describe("conteo por tipo", () => {
  const casos = (tipos: TestCaseType[]) => tipos.map((type) => ({ type }));

  it("cuenta en el orden de presentación y omite los que valen cero", () => {
    expect(
      countsByKind(casos(["negative", "functional", "functional"])),
    ).toEqual([
      { type: "functional", count: 2 },
      { type: "negative", count: 1 },
    ]);
  });

  it("sin casos, no devuelve nada", () => {
    expect(countsByKind([])).toEqual([]);
  });
});

describe("formato del esfuerzo", () => {
  it("traduce los minutos a horas para que se pueda planificar", () => {
    // «485 min» obliga a dividir mentalmente cada vez que alguien quiere saber
    // si el plan cabe en una tarde.
    expect(formatMinutes(45)).toBe("45 min");
    expect(formatMinutes(60)).toBe("1 h");
    expect(formatMinutes(62)).toBe("1 h 2 min");
    expect(formatMinutes(485)).toBe("8 h 5 min");
  });

  it("un plan sin esfuerzo no dice «0 h»", () => {
    expect(formatMinutes(0)).toBe("0 min");
  });
});
